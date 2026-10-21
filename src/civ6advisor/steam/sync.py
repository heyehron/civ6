"""Steam sync (SPEC §4.1): player unlock status and global percentages, cached locally.

Player status comes from the community XML, which needs no API key but needs the
profile's Game details to be public. If an API key is stored in the OS keyring,
GetPlayerAchievements is used instead.
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import requests

APPID = 289070
HOME = Path.home() / ".civ6advisor"
CACHE = HOME / "steam_cache.json"
CONFIG = HOME / "config.json"
KEYRING_SERVICE = "civ6advisor"
GLOBAL_URL = "https://api.steampowered.com/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/"
PLAYER_API_URL = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
TIMEOUT = 20


class SteamError(Exception):
    pass


class ProfilePrivate(SteamError):
    pass


@dataclass
class SyncResult:
    synced_at: float
    profile: str
    unlocked: set[str]
    pct: dict[str, float]
    from_cache: bool = False


def profile_url(profile: str) -> str:
    profile = profile.strip().rstrip("/")
    profile = re.sub(r"^https?://steamcommunity\.com/(id|profiles)/", "", profile)
    kind = "profiles" if re.fullmatch(r"\d{17}", profile) else "id"
    return f"https://steamcommunity.com/{kind}/{profile}/stats/{APPID}/achievements/"


def parse_player_xml(text: str) -> tuple[set[str], set[str]]:
    """Return (unlocked, all) apinames, lowercased."""
    root = ET.fromstring(text)
    privacy = (root.findtext("privacyState") or "").strip()
    if privacy and privacy != "public":
        raise ProfilePrivate(f"Steam profile game details are '{privacy}'; set them to Public.")
    unlocked, every = set(), set()
    for node in root.iter("achievement"):
        api = (node.findtext("apiname") or "").strip().lower()
        every.add(api)
        if node.get("closed") == "1":
            unlocked.add(api)
    if not every:
        raise SteamError("No achievements in the Steam response.")
    return unlocked, every


def fetch_player_xml(profile: str, session: requests.Session) -> set[str]:
    # The community endpoint can serve a stale copy; a unique query string avoids it.
    r = session.get(profile_url(profile), params={"xml": 1, "l": "english", "t": int(time.time())},
                    timeout=TIMEOUT)
    if r.status_code == 429:
        raise SteamError("Steam is rate-limiting requests; try again in a few minutes.")
    r.raise_for_status()
    return parse_player_xml(r.text)[0]


def resolve_steamid(profile: str, session: requests.Session) -> str:
    if re.fullmatch(r"\d{17}", profile):
        return profile
    r = session.get(f"https://steamcommunity.com/id/{profile}/", params={"xml": 1}, timeout=TIMEOUT)
    r.raise_for_status()
    sid = ET.fromstring(r.text).findtext("steamID64")
    if not sid:
        raise SteamError(f"Could not resolve SteamID64 for '{profile}'.")
    return sid.strip()


def fetch_player_api(profile: str, key: str, session: requests.Session) -> set[str]:
    r = session.get(PLAYER_API_URL, params={"appid": APPID, "key": key,
                                            "steamid": resolve_steamid(profile, session)}, timeout=TIMEOUT)
    if r.status_code == 403:
        raise ProfilePrivate("Steam refused the request; check the API key and profile privacy.")
    r.raise_for_status()
    stats = r.json().get("playerstats", {})
    if not stats.get("success", False):
        raise ProfilePrivate(stats.get("error", "Steam returned no player stats."))
    return {a["apiname"].lower() for a in stats.get("achievements", []) if a.get("achieved")}


def fetch_global(session: requests.Session) -> dict[str, float]:
    r = session.get(GLOBAL_URL, params={"gameid": APPID}, timeout=TIMEOUT)
    r.raise_for_status()
    rows = r.json()["achievementpercentages"]["achievements"]
    return {a["name"].lower(): float(a["percent"]) for a in rows}


def api_key() -> str | None:
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, "steam_api_key")
    except Exception:
        return None


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=1), encoding="utf-8")


def load_cache() -> SyncResult | None:
    try:
        raw = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return SyncResult(raw["synced_at"], raw["profile"], set(raw["unlocked"]), raw["pct"], from_cache=True)


def save_cache(res: SyncResult) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"synced_at": res.synced_at, "profile": res.profile,
                                 "unlocked": sorted(res.unlocked), "pct": res.pct}), encoding="utf-8")


def sync(profile: str, session: requests.Session | None = None) -> SyncResult:
    """Fetch from Steam and update the cache. Falls back to the cache on network errors."""
    session = session or requests.Session()
    try:
        key = api_key()
        unlocked = fetch_player_api(profile, key, session) if key else fetch_player_xml(profile, session)
        res = SyncResult(time.time(), profile, unlocked, fetch_global(session))
    except ProfilePrivate:
        raise
    except (requests.RequestException, SteamError, ValueError, KeyError) as exc:
        cached = load_cache()
        if cached is None:
            raise SteamError(f"Sync failed and no cache exists: {exc}") from exc
        return cached
    save_cache(res)
    return res
