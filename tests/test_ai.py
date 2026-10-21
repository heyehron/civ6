import json

import pytest

from civ6advisor.ai import prompts
from civ6advisor.ai.ollama import Message, OllamaClient, OllamaError, extract_json
from civ6advisor.dataset import load_achievements, load_leaders

ACH = load_achievements()
LEADERS = load_leaders()


class FakeResp:
    def __init__(self, status=200, lines=(), payload=None):
        self.status_code, self._lines, self._payload, self.text = status, lines, payload, ""

    def iter_lines(self):
        yield from self._lines

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSession:
    def __init__(self, resp):
        self.resp, self.body = resp, None

    def post(self, url, json=None, **kw):
        self.body = json
        return self.resp

    def get(self, url, **kw):
        return self.resp


def test_stream_joins_tokens_and_sends_images():
    lines = [json.dumps({"message": {"content": "Hel"}}).encode(), b"",
             json.dumps({"message": {"content": "lo"}, "done": True}).encode()]
    sess = FakeSession(FakeResp(lines=lines))
    c = OllamaClient(session=sess)
    assert c.chat([Message("user", "hi", [b"\x89PNG"])]) == "Hello"
    assert sess.body["messages"][0]["images"] and sess.body["stream"] is True


def test_missing_model_message():
    c = OllamaClient(model="nope", session=FakeSession(FakeResp(status=404)))
    with pytest.raises(OllamaError, match="ollama pull nope"):
        c.chat([Message("user", "x")])


def test_models_list():
    c = OllamaClient(session=FakeSession(FakeResp(payload={"models": [{"name": "b"}, {"name": "a"}]})))
    assert c.models() == ["a", "b"]


@pytest.mark.parametrize("text", ['{"a": 1}', '```json\n{"a": 1}\n```', 'Sure! Here: {"a": 1} hope it helps'])
def test_extract_json(text):
    assert extract_json(text) == {"a": 1}


def test_prompts_contain_context():
    sel = [ACH["new_achievement_4_25"], ACH["raf_achievement_07"]]
    ctx = prompts.batch_context(sel, LEADERS, {"new_achievement_4_25": 0.6}, set())
    assert "We Are The Champions" in ctx and "Zanzibar" in ctx and "[Required]" in ctx
    p = prompts.playbook_prompt(ACH["new_achievement_4_25"])
    assert "religion.type" in p and "count_gte" in p
