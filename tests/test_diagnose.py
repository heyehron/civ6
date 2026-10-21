import os

import pytest

from civ6advisor import config
from civ6advisor.state import diagnose


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def levels(checks):
    return [c.level for c in checks]


def test_no_civ_folder(home):
    checks = diagnose.run(config.default_lua_log())
    assert levels(checks) == ["fail"] and "not found" in checks[0].text


def test_finds_onedrive_documents(home):
    civ = home / "OneDrive" / "Documents" / "My Games" / "Sid Meier's Civilization VI"
    civ.mkdir(parents=True)
    assert config.find_civ_dir() == civ
    assert config.default_lua_log().endswith("Lua.log") and "OneDrive" in config.default_lua_log()


def test_install_and_log_states(home):
    civ = home / "Documents" / "My Games" / "Sid Meier's Civilization VI"
    (civ / "Logs").mkdir(parents=True)
    log = str(civ / "Logs" / "Lua.log")

    texts = " ".join(c.text for c in diagnose.run(log))
    assert "not installed" in texts and "does not exist" in texts

    dest = diagnose.install_mod(civ)
    assert (dest / "UI" / "CIV6ADV.lua").exists()
    assert "Mod installed" in " ".join(c.text for c in diagnose.run(log))

    (civ / "Logs" / "Lua.log").write_text("", encoding="utf-8")
    assert "empty" in " ".join(c.text for c in diagnose.run(log))

    (civ / "Logs" / "Lua.log").write_text("some other output\n", encoding="utf-8")
    assert "no advisor lines" in " ".join(c.text for c in diagnose.run(log))

    (civ / "Logs" / "Lua.log").write_text("CIV6ADV|" + '{"kind":"hello"}\n', encoding="utf-8")
    assert "1 advisor line" in " ".join(c.text for c in diagnose.run(log))


def test_appoptions_logging_lines_are_reported(home):
    civ = home / "Documents" / "My Games" / "Sid Meier's Civilization VI"
    civ.mkdir(parents=True)
    (civ / "AppOptions.txt").write_text("[Video]\nWidth 1920\n[Debug]\nEnableDebugMenu 0\n", encoding="utf-8")
    texts = " ".join(c.text for c in diagnose.run(str(civ / "Logs" / "Lua.log")))
    assert "EnableDebugMenu 0" in texts and "Width" not in texts
