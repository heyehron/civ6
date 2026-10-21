import json
from pathlib import Path

import pytest

from civ6advisor.dataset import DATA_DIR, load_achievements, load_leaders
from civ6advisor.engine import playbook
from civ6advisor.state.model import GameState

ACH = load_achievements()
LEADERS = load_leaders()
DEMO = json.loads((DATA_DIR / "demo" / "batch_a_turn40.json").read_text(encoding="utf-8"))


def state(**kw):
    return GameState.from_snapshot({"turn": 10, **kw})


@pytest.mark.parametrize("cond,expected", [
    ({"field": "turn", "op": "gte", "value": 10}, True),
    ({"field": "turn", "op": "lt", "value": 10}, False),
    ({"field": "missing", "op": "eq", "value": 1}, None),
    ({"all": [{"field": "turn", "op": "eq", "value": 10}, {"field": "missing", "op": "eq", "value": 1}]}, None),
    ({"all": [{"field": "turn", "op": "eq", "value": 9}, {"field": "missing", "op": "eq", "value": 1}]}, False),
    ({"any": [{"field": "turn", "op": "eq", "value": 10}, {"field": "missing", "op": "eq", "value": 1}]}, True),
    ({"not": {"field": "turn", "op": "eq", "value": 10}}, False),
    ({"field": "game_modes", "op": "contains", "value": "DRAMATIC_AGES"}, True),
    ({"field": "game_modes", "op": "count_gte", "value": 1}, True),
    ({"field": "leader", "op": "in", "value": ["leader_tamar"]}, True),
    ({"field": "yields.faith", "op": "gt", "value": 5}, True),
])
def test_evaluate(cond, expected):
    s = state(game_modes=["GAMEMODE_DRAMATICAGES"], leader="LEADER_TAMAR", yields={"faith": 6})
    assert playbook.evaluate(cond, s.fields()) is expected


def test_all_repo_playbooks_valid_and_linked():
    pbs = playbook.load_dir(DATA_DIR / "playbooks")
    assert len(pbs) >= 25
    for aid, pb in pbs.items():
        assert aid in ACH, aid
        assert playbook.validate(pb) == [], (aid, playbook.validate(pb))


def test_auto_playbook_valid_for_every_achievement():
    for a in ACH.values():
        pb = playbook.auto_playbook(a, LEADERS)
        assert playbook.validate(pb) == [], (a["id"], playbook.validate(pb))


def test_auto_playbook_catches_wrong_setup():
    pb = playbook.auto_playbook(ACH["raf_achievement_07"], LEADERS)  # win as Tamar
    st = playbook.evaluate_playbook(pb, state(leader="LEADER_KRISTINA"), set())
    assert st.failed


def test_validate_reports_problems():
    bad = {"achievement": "x", "steps": [{"id": "a", "text": "t", "done_when": {"field": "nope", "op": "eq", "value": 1}},
                                         {"id": "a", "text": ""}]}
    errs = " ".join(playbook.validate(bad))
    assert "not produced" in errs and "duplicate" in errs and "missing 'text'" in errs


def test_demo_state_batch_a_progress():
    s = GameState.from_snapshot(dict(DEMO))
    pbs = playbook.load_dir(DATA_DIR / "playbooks")
    adv = playbook.advise([pbs["new_achievement_4_25"], pbs["raf_achievement_19"]], s, set())
    champs = adv.statuses[0]
    done = {x.step["id"]: x.done for x in champs.steps}
    assert done["meet_zanzibar"] and done["found_zoroastrianism"] and done["dominant"]
    assert not done["suzerain"]
    assert not champs.failed
    assert adv.next_action is not None


def test_deadline_alerts_and_manual():
    pb = {"achievement": "x", "title": "X", "steps": [
        {"id": "a", "text": "A", "done_when": {"field": "religion_founded", "op": "eq", "value": True}, "deadline_turn": 12},
        {"id": "b", "text": "B", "manual": True}]}
    adv = playbook.advise([pb], state(turn=9), set())
    assert [a.level for a in adv.alerts] == ["at_risk"]
    adv = playbook.advise([pb], state(turn=13), set())
    assert [a.level for a in adv.alerts] == ["missed"]
    adv = playbook.advise([pb], state(turn=13, religion={"type": "RELIGION_X"}), {"x:b"})
    assert adv.statuses[0].done


def test_next_action_prefers_nearest_deadline():
    late = {"achievement": "late", "title": "L", "steps": [{"id": "s", "text": "late", "manual": True, "deadline_turn": 90}]}
    soon = {"achievement": "soon", "title": "S", "steps": [{"id": "s", "text": "soon", "manual": True, "deadline_turn": 30}]}
    adv = playbook.advise([late, soon], state(), set())
    assert adv.next_action[1].step["text"] == "soon"


def test_save_and_load_roundtrip(tmp_path: Path):
    pb = {"achievement": "ABC", "title": "t", "steps": [{"id": "a", "text": "x", "manual": True}], "_path": "x"}
    playbook.save(pb, tmp_path)
    loaded = playbook.load_dir(tmp_path)
    assert "abc" in loaded and "_path" in loaded["abc"] and "_path" not in json.loads((tmp_path / "abc.json").read_text())


def test_setup_and_final_steps_are_not_next_actions_mid_game():
    pb = {"achievement": "x", "title": "X", "steps": [
        {"id": "lobby", "text": "Lobby thing", "manual": True},
        {"id": "work", "text": "Real work", "manual": True},
        {"id": "win", "text": "Win", "manual": True}]}
    assert playbook.advise([pb], state(turn=1), set()).next_action[1].step["id"] == "lobby"
    assert playbook.advise([pb], state(turn=40), set()).next_action[1].step["id"] == "work"
    assert playbook.advise([pb], state(turn=40), {"x:work"}).next_action[1].step["id"] == "win"
