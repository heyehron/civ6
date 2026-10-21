from civ6advisor.dataset import load_achievements, load_leaders
from civ6advisor.engine.batch import DIFFICULTIES

ACH = load_achievements()
LEADERS = load_leaders()
KEYS = {"leader", "civ", "victory", "difficulty_min", "difficulty_max", "map_type", "map_size", "start_era",
        "ruleset", "game_modes_required", "game_modes_forbidden", "scenario", "turn_limit", "turn_min",
        "requires_win", "choices", "lobby_required", "multiplayer", "multi_game"}


def test_every_entry_has_full_schema():
    assert len(ACH) == 320
    for a in ACH.values():
        assert set(a["constraints"]) == KEYS, a["id"]
        assert a["verified"] in (True, False)


def test_references_resolve():
    civs = {v["civ"] for v in LEADERS.values()}
    for a in ACH.values():
        c = a["constraints"]
        for lid in c["leader"] or []:
            assert lid in LEADERS, (a["id"], lid)
        for civ in c["civ"] or []:
            assert civ in civs, (a["id"], civ)
        for d in (c["difficulty_min"], c["difficulty_max"]):
            assert d is None or d in DIFFICULTIES, a["id"]


def test_every_leader_win_is_tagged():
    for a in ACH.values():
        if a["description"].lower().startswith(("win a regular game as", "win a game as")):
            assert a["constraints"]["leader"], a["id"]
