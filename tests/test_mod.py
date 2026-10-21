"""Runs the Lua mod against a mocked Civ VI API and parses its output with the log reader."""
import shutil
import subprocess
from pathlib import Path

import pytest

from civ6advisor.state.log_source import LogTailer

ROOT = Path(__file__).resolve().parents[1]
LUA = shutil.which("lua5.1") or shutil.which("lua")


@pytest.mark.skipif(LUA is None, reason="lua interpreter not installed")
def test_mod_snapshot_parses(tmp_path):
    script = f'dofile("{ROOT / "tests/lua/mock_civ.lua"}") dofile("{ROOT / "mod/CIV6ADV/UI/CIV6ADV.lua"}")'
    out = subprocess.run([LUA, "-e", script], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    log = tmp_path / "Lua.log"
    log.write_text("".join(f"CIV6ADV: {line}\n" for line in out.stdout.splitlines()), encoding="utf-8")
    tailer = LogTailer(log)
    payloads = tailer.poll()
    kinds = [p["kind"] for p in payloads]
    assert "hello" in kinds and "snapshot" in kinds and "warning" in kinds  # InfluenceGiven is missing in the mock
    state = tailer.apply(payloads)
    assert state.turn == 12
    assert state.leader == "LEADER_TAMAR"
    assert state.difficulty == "emperor"
    assert state.map_type == "shuffle" and state.map_size == "duel" and state.speed == "online"
    assert state.start_era == "classical" and state.age == "dark"
    assert state.game_modes == ["dramatic_ages"]
    assert state.religion["type"] == "RELIGION_ZOROASTRIANISM"
    f = state.fields()
    assert [x.lower() for x in f["suzerain_of"]] == ["zanzibar"]
    assert f["city_states_following_my_religion"] == 1
    assert f["district_counts"]["DISTRICT_HOLY_SITE"] == 1
    assert state.yields["gold"] == 8
    assert state.resources["RESOURCE_SILVER"] == 2
    assert f["governors_established"] == 1
