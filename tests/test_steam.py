import pytest

from civ6advisor.steam import sync

XML = """<?xml version="1.0"?><playerstats><privacyState>{p}</privacyState><achievements>
<achievement closed="1"><apiname><![CDATA[NEW_ACHIEVEMENT_2_0]]></apiname></achievement>
<achievement closed="0"><apiname><![CDATA[new_achievement_2_1]]></apiname></achievement>
</achievements></playerstats>"""


def test_parse_lowercases_and_splits():
    unlocked, every = sync.parse_player_xml(XML.format(p="public"))
    assert unlocked == {"new_achievement_2_0"}
    assert every == {"new_achievement_2_0", "new_achievement_2_1"}


def test_private_profile_raises():
    with pytest.raises(sync.ProfilePrivate):
        sync.parse_player_xml(XML.format(p="friendsonly"))


@pytest.mark.parametrize("profile,expected", [
    ("NobodyYouKnow", "https://steamcommunity.com/id/NobodyYouKnow/stats/289070/achievements/"),
    ("76561197999693974", "https://steamcommunity.com/profiles/76561197999693974/stats/289070/achievements/"),
    ("https://steamcommunity.com/id/NobodyYouKnow/", "https://steamcommunity.com/id/NobodyYouKnow/stats/289070/achievements/"),
])
def test_profile_url(profile, expected):
    assert sync.profile_url(profile) == expected


def test_sync_falls_back_to_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "HOME", tmp_path)
    monkeypatch.setattr(sync, "CACHE", tmp_path / "steam_cache.json")
    monkeypatch.setattr(sync, "api_key", lambda: None)
    sync.save_cache(sync.SyncResult(1.0, "x", {"a"}, {"a": 5.0}))

    class Boom:
        def get(self, *a, **k):
            import requests
            raise requests.ConnectionError("offline")

    res = sync.sync("x", session=Boom())
    assert res.from_cache and res.unlocked == {"a"}
