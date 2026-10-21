from civ6advisor.dataset import load_achievements, load_leaders
from civ6advisor.engine import batch, planner

ACH = load_achievements()
LEADERS = load_leaders()
PCT = {k: 5.0 for k in ACH}
PCT["new_achievement_4_25"] = 0.6


def test_suggestions_are_internally_compatible():
    sug = planner.suggest(ACH, LEADERS, PCT, "emperor", limit=8)
    assert sug
    for s in sug:
        achs = [ACH[i] for i in s.ids]
        assert batch.combine(achs, LEADERS).conflicts == []
        assert not any(a["constraints"]["scenario"] or a["constraints"]["multiplayer"] for a in achs)
        assert s.score > 0


def test_max_difficulty_respected():
    for s in planner.suggest(ACH, LEADERS, PCT, "king", limit=8):
        for i in s.ids:
            d = ACH[i]["constraints"]["difficulty_min"]
            assert d is None or batch.DIFFICULTIES.index(d) <= batch.DIFFICULTIES.index("king")


def test_season_has_no_overlap():
    plan = planner.season(ACH, LEADERS, PCT, "emperor", games=4)
    seen = set()
    for s in plan:
        assert not seen & set(s.ids)
        seen |= set(s.ids)


def test_effort_grows_with_difficulty():
    easy = planner.estimate_effort([ACH["new_achievement_2_3"]], LEADERS)
    hard = planner.estimate_effort([ACH["new_achievement_2_7"]], LEADERS)
    assert hard > easy


def test_warning_late_era_religious():
    achs = [ACH["new_achievement_5_2"], ACH["new_achievement_4_25"]]  # atomic start + religious win
    assert any("religion" in w for w in planner.warnings(achs, LEADERS))
