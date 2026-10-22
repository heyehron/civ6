import json

from civ6advisor.state.log_source import LogTailer
from civ6advisor.state.model import GameState, norm_map_type


def test_normalisation():
    s = GameState.from_snapshot({"difficulty": "DIFFICULTY_DEITY", "map_size": "MAPSIZE_HUGE", "map_type": "InlandSea.lua",
                                 "speed": "GAMESPEED_ONLINE", "era": "ERA_MEDIEVAL",
                                 "game_modes": ["GAMEMODE_HEROES", "GAMEMODE_SECRETSOCIETIES"], "foo": 1})
    assert (s.difficulty, s.map_size, s.map_type, s.speed, s.era) == ("deity", "huge", "inland_sea", "online", "medieval")
    assert s.game_modes == ["heroes_and_legends", "secret_societies"]
    f = s.fields()
    assert f["difficulty_level"] == 7 and f["era_index"] == 2 and f["foo"] == 1


def test_map_type_names():
    assert norm_map_type("Island_Plates.lua") == "island_plates"
    assert norm_map_type("Maps/Archipelago.lua") == "archipelago"


def test_tailer_handles_partial_lines_and_reset(tmp_path):
    log = tmp_path / "Lua.log"
    snap = {"kind": "snapshot", "game_id": "g1", "turn": 3}
    line = "CIV6ADV: CIV6ADV|" + json.dumps(snap)
    log.write_text("noise\n" + line[:20], encoding="utf-8")
    t = LogTailer(log)
    assert t.poll() == []
    with log.open("a", encoding="utf-8") as f:
        f.write(line[20:] + "\n")
    st = t.apply(t.poll())
    assert st.turn == 3
    with log.open("a", encoding="utf-8") as f:
        f.write("CIV6ADV|" + json.dumps({"kind": "delta", "turn": 4, "techs_known": ["TECH_X"]}) + "\n")
    st = t.apply(t.poll())
    assert st.turn == 4 and st.techs_known == ["TECH_X"]
    log.write_text("CIV6ADV|" + json.dumps({"kind": "snapshot", "game_id": "g2", "turn": 1}) + "\n", encoding="utf-8")
    st = t.apply(t.poll())
    assert st.turn == 1 and st.game_id == "g2"


def test_empty_lua_tables_arrive_as_lists_and_are_normalised():
    # The mod writes an empty Lua table as [] whether it was a list or a dictionary.
    snap = {"turn": 3, "leader": "LEADER_FREDERICK_BARBAROSSA", "religion": [], "yields": [], "balances": [],
            "victory_progress": [], "units": [], "resources": [], "game_modes": [], "cities": [],
            "city_states": [], "governors": [], "policies": [], "techs_known": []}
    s = GameState.from_snapshot(snap)
    f = s.fields()  # must not raise
    assert s.religion == {} and s.yields == {} and f["religion_founded"] is False
    assert f["city_states_following_my_religion"] == 0 and f["cities_count"] == 0


def test_in_game_page_shows_state_for_empty_tables(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("CIV6ADVISOR_HOME", str(tmp_path))
    from PySide6.QtWidgets import QApplication

    from civ6advisor.ui.appstate import AppState
    from civ6advisor.ui.pages.ingame import InGamePage
    app = QApplication.instance() or QApplication([])
    state = AppState()
    state.set_selected(["raf_achievement_07"])
    page = InGamePage(state)
    state.set_game_state(GameState.from_snapshot({"turn": 3, "leader": "LEADER_TAMAR", "religion": [], "yields": []}))
    assert "Turn" in page.state_lbl.text() and "Could not show" not in page.state_lbl.text()
