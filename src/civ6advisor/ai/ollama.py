"""Minimal client for a local Ollama server. Local only: no cloud calls (SPEC §1)."""
from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from dataclasses import dataclass

import requests


class OllamaError(Exception):
    pass


@dataclass
class Message:
    role: str  # system | user | assistant
    content: str
    images: list[bytes] | None = None

    def to_api(self) -> dict:
        d = {"role": self.role, "content": self.content}
        if self.images:
            d["images"] = [base64.b64encode(b).decode("ascii") for b in self.images]
        return d


class OllamaClient:
    def __init__(self, url: str = "http://localhost:11434", model: str = "qwen2.5vl:3b",
                 temperature: float = 0.4, session: requests.Session | None = None):
        self.url = url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.session = session or requests.Session()

    def models(self, timeout: float = 2) -> list[str]:
        try:
            r = self.session.get(f"{self.url}/api/tags", timeout=timeout)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(f"Ollama is not reachable at {self.url}: {exc}") from exc
        return sorted(m["name"] for m in r.json().get("models", []))

    def chat_stream(self, messages: list[Message], json_mode: bool = False,
                    cancel=lambda: False) -> Iterator[str]:
        body = {"model": self.model, "messages": [m.to_api() for m in messages], "stream": True,
                "options": {"temperature": self.temperature}}
        if json_mode:
            body["format"] = "json"
        try:
            r = self.session.post(f"{self.url}/api/chat", json=body, stream=True, timeout=(5, 300))
        except requests.RequestException as exc:
            raise OllamaError(f"Ollama is not reachable at {self.url}: {exc}") from exc
        if r.status_code == 404:
            raise OllamaError(f"Model '{self.model}' not found. Run: ollama pull {self.model}")
        if r.status_code >= 400:
            raise OllamaError(f"Ollama error {r.status_code}: {r.text[:300]}")
        with r:
            for line in r.iter_lines():
                if cancel():
                    return
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except ValueError:
                    continue
                if chunk.get("error"):
                    raise OllamaError(chunk["error"])
                piece = chunk.get("message", {}).get("content", "")
                if piece:
                    yield piece
                if chunk.get("done"):
                    return

    def chat(self, messages: list[Message], json_mode: bool = False) -> str:
        return "".join(self.chat_stream(messages, json_mode))


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model reply (handles ``` fences and chatter)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except ValueError:
        pass
    start = text.find("{")
    depth = 0
    for i in range(start, len(text)) if start >= 0 else []:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except ValueError:
                    return None
    return None
