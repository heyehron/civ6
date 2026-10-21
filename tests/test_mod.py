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
    assert kinds.count("snapshot") == 1  # identical repeat snapshots are skipped
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


@pytest.mark.skipif(LUA is None, reason="lua interpreter not installed")
def test_mod_reports_section_errors_instead_of_hiding_them(tmp_path):
    script = (f'dofile("{ROOT / "tests/lua/mock_civ.lua"}") '
              'Players[0].GetTreasury = function() error("boom") end '
              f'dofile("{ROOT / "mod/CIV6ADV/UI/CIV6ADV.lua"}")')
    out = subprocess.run([LUA, "-e", script], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    log = tmp_path / "Lua.log"
    log.write_text("".join(f"CIV6ADV: {line}\n" for line in out.stdout.splitlines()), encoding="utf-8")
    snaps = [p for p in LogTailer(log).poll() if p["kind"] == "snapshot"]
    assert snaps and any("boom" in e for e in snaps[0]["mod_errors"])
    assert snaps[0]["leader"] == "LEADER_TAMAR"  # the other sections still made it
    from civ6advisor.state import diagnose
    texts = " ".join(c.text for c in diagnose._advisor_lines(log.read_text(encoding="utf-8")))
    assert "section errors" in texts and "boom" in texts


def test_diagnose_flags_mod_that_never_snapshots(tmp_path):
    from civ6advisor.state import diagnose
    text = 'x CIV6ADV|{"kind":"hello","version":2}\nx CIV6ADV|{"kind":"warning","text":"no local player yet (init)"}\n'
    checks = diagnose._advisor_lines(text)
    assert [c.level for c in checks][-1] == "fail" and any("no local player" in c.text for c in checks)
