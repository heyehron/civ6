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
