import pytest

from civ6advisor.dataset import load_achievements, load_leaders
from civ6advisor.engine import batch

LEADERS = load_leaders()
ACH = load_achievements()


def mk(aid, **c):
    base = {"leader": None, "civ": None, "victory": None, "difficulty_min": None, "difficulty_max": None,
            "map_type": None, "map_size": None, "start_era": None, "ruleset": None,
            "game_modes_required": [], "game_modes_forbidden": [], "scenario": None, "turn_limit": None,
            "turn_min": None, "requires_win": False, "choices": {}, "lobby_required": [],
            "multiplayer": False, "multi_game": False}
    base.update(c)
    return {"id": aid, "name": aid, "constraints": base}


def attrs(achs):
    return {c.attribute for c in batch.combine(achs, LEADERS).conflicts}


def test_two_leader_wins_conflict():
    assert attrs([mk("a", leader=["LEADER_TAMAR"]), mk("b", leader=["LEADER_KRISTINA"])]) == {"leader"}


def test_civ_and_leader_intersect():
    england = mk("a", civ=["CIVILIZATION_ENGLAND"])
    assert attrs([england, mk("b", leader=["LEADER_ELIZABETH"])]) == set()
    assert attrs([england, mk("c", leader=["LEADER_TAMAR"])]) == {"leader"}


def test_one_victory_type_per_game():
    assert attrs([mk("a", victory=["science"]), mk("b", victory=["culture"])]) == {"victory"}


def test_difficulty_range():
    assert attrs([mk("a", difficulty_min="deity"), mk("b", difficulty_max="king")]) == {"difficulty"}
    assert attrs([mk("a", difficulty_min="king"), mk("b", difficulty_min="emperor")]) == set()


def test_scenario_only_with_same_scenario():
    assert attrs([mk("a", scenario="red_death"), mk("b")]) == {"scenario"}
    assert attrs([mk("a", scenario="red_death"), mk("b", scenario="red_death")]) == set()


def test_mode_required_and_forbidden():
    assert attrs([mk("a", game_modes_required=["zombie_defense"]),
                  mk("b", game_modes_forbidden=["zombie_defense"])]) == {"game_mode"}


def test_exclusive_in_game_choice():
    assert attrs([mk("a", choices={"secret_society": "owls"}),
                  mk("b", choices={"secret_society": "voidsingers"})]) == {"secret_society"}


def test_turn_window():
    assert attrs([mk("a", turn_limit=25), mk("b", turn_min=80)]) == {"turn"}


def test_multiplayer_excluded():
    assert attrs([mk("a", multiplayer=True)]) == {"multiplayer"}


def test_conflicts_with_reports_only_candidate():
    sel = [mk("a", victory=["science"])]
    assert batch.conflicts_with(sel, mk("b", victory=["science"]), LEADERS) == []
    assert batch.conflicts_with(sel, mk("c", victory=["religious"]), LEADERS)[0].attribute == "victory"


def test_score_prefers_rare_and_overlapping():
    sel = [mk("a", map_size=["duel"])]
    common = batch.score(mk("x"), sel, 50.0, LEADERS)
    rare = batch.score(mk("y"), sel, 1.0, LEADERS)
    overlap = batch.score(mk("z", map_size=["duel"]), sel, 50.0, LEADERS)
    assert rare > common and overlap > common


def test_checklist_labels():
    items = batch.lobby_checklist([mk("a", leader=["LEADER_TAMAR"], difficulty_min="emperor",
                                      victory=["religious"])], LEADERS)
    by = {(i.setting, i.label): i for i in items}
    assert by[("Leader", "Required")].value == "Tamar"
    assert by[("Difficulty", "Required")].value == "Emperor or harder"
    assert ("Other victory types", "Recommended") in by
    assert by[("Map type", "Free")].value == "Your choice"


@pytest.mark.parametrize("ids", [
    # Batch A from docs/BATCH_PLAN.md
    ["new_achievement_2_5", "new_achievement_4_2", "new_achievement_3_25", "new_achievement_4_29",
     "raf_achievement_07", "new_achievement_4_25", "raf_achievement_19", "stk3_achievement_06",
     "stk3_achievement_07", "raf_achievement_33"],
    # Batch B
    ["new_achievement_2_11", "new_achievement_4_1", "new_achievement_4_27", "new_achievement_4_30",
     "neb_achievement_13", "new_achievement_3_10", "raf_achievement_34", "stk2_achievement_06"],
])
def test_planned_batches_are_compatible_in_dataset(ids):
    assert batch.combine([ACH[i] for i in ids], LEADERS).conflicts == []


def test_dataset_known_conflict():
    # Selfie (culture) cannot share a game with Island Hopping (domination).
    assert "victory" in attrs([ACH["new_achievement_4_26"], ACH["new_achievement_4_27"]])
