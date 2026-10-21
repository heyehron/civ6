"""Checks that explain why the advisor mod's output is not reaching the app."""
from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .. import config
from .log_source import MARKER

MOD_NAME = "CIV6ADV"
REPO_MOD = Path(__file__).resolve().parents[3] / "mod" / MOD_NAME
LOG_HINTS = ("log", "debug", "tuner", "console")


@dataclass
class Check:
    level: str  # ok | warn | fail | info
    text: str
    fix: str = ""


def _age(p: Path) -> str:
    secs = max(0, time.time() - p.stat().st_mtime)
    if secs < 90:
        return f"{int(secs)}s ago"
    if secs < 5400:
        return f"{int(secs // 60)} min ago"
    return f"{secs / 3600:.1f} h ago"


def install_mod(civ_dir: Path) -> Path:
    """Copy the repo's mod folder into the game's Mods folder, replacing an older copy."""
    if not REPO_MOD.exists():
        raise FileNotFoundError(f"Mod source not found: {REPO_MOD}")
    dest = civ_dir / "Mods" / MOD_NAME
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(REPO_MOD, dest)
    return dest


def run(log_path: str) -> list[Check]:
    out: list[Check] = []
    civ = config.find_civ_dir()
    if civ is None:
        tried = "; ".join(str(p) for p in config.civ_dir_candidates())
        return [Check("fail", "Civ VI's user folder was not found.",
                      f"Start Civ VI once so it creates it, or set the Lua.log path in Settings. Looked in: {tried}")]
    out.append(Check("ok", f"Civ VI user folder: {civ}"))

    mod = civ / "Mods" / MOD_NAME
    if not mod.exists():
        out.append(Check("fail", "The advisor mod is not installed.",
                         "Press Install mod, then enable it under Additional Content in Civ VI."))
    else:
        missing = [f for f in ("CIV6ADV.modinfo", "UI/CIV6ADV.lua", "UI/CIV6ADV.xml") if not (mod / f).exists()]
        if missing:
            out.append(Check("fail", f"Mod folder is incomplete (missing {', '.join(missing)}).",
                             "Press Install mod to replace it."))
        else:
            same = (mod / "UI" / "CIV6ADV.lua").read_bytes() == (REPO_MOD / "UI" / "CIV6ADV.lua").read_bytes() \
                if REPO_MOD.exists() else True
            out.append(Check("ok" if same else "warn", "Mod installed" + ("" if same else " but differs from the repo copy."),
                             "" if same else "Press Install mod to update it, then restart Civ VI."))
            out.append(Check("info", "Make sure it is ticked under Additional Content (Mods) before starting a "
                                     "new game. A mod only loads when the game starts."))

    logs = config.find_logs_dir()
    if logs is None:
        tried = "; ".join(str(p) for p in config.logs_dir_candidates())
        out.append(Check("warn", "No Civ VI Logs folder found.", f"It appears after Civ VI has run. Looked in: {tried}"))
    else:
        out.append(Check("ok", f"Logs folder: {logs}"))
        files = sorted(logs.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        out.append(Check("info", "Log files: " + (", ".join(f"{f.name} ({_age(f)})" for f in files[:6]) or "none")))

    lp = Path(log_path)
    if logs is not None and lp.parent != logs:
        out.append(Check("warn", f"Settings point to {lp.parent}, but the logs folder is {logs}.",
                         "Press Use detected log path (or fix it in Settings)."))
    if not lp.exists():
        out.append(Check("fail", f"{lp.name} does not exist.",
                         "Civ VI writes Lua.log only when Lua logging is on. Check the AppOptions.txt lines "
                         "below, and look for a different log name in the list above."))
    else:
        text = lp.read_text(encoding="utf-8", errors="replace")
        n = text.count(MARKER)
        if n:
            out.append(Check("ok", f"{lp.name} has {n} advisor line(s), last written {_age(lp)}."))
        elif lp.stat().st_size == 0:
            out.append(Check("warn", f"{lp.name} exists but is empty (written {_age(lp)}).",
                             "Logging may be on but the mod did not run: is it enabled, and did you start a "
                             "new or reloaded game after enabling it?"))
        else:
            out.append(Check("warn", f"{lp.name} has content ({_age(lp)}) but no advisor lines.",
                             "Lua logging works, but the mod did not print. Check that the mod is enabled and "
                             "look in the log for errors mentioning CIV6ADV."))
            err = [ln for ln in text.splitlines() if "CIV6ADV" in ln][:3]
            if err:
                out.append(Check("info", "Lines mentioning CIV6ADV: " + " | ".join(e[:140] for e in err)))

    opts = civ / "AppOptions.txt"
    if opts.exists():
        lines = [ln.strip() for ln in opts.read_text(encoding="utf-8", errors="replace").splitlines()
                 if any(h in ln.lower() for h in LOG_HINTS)]
        out.append(Check("info", "AppOptions.txt logging-related lines: " + (" | ".join(lines) or "none found"),
                         "If Lua.log is missing, the option that turns Lua logging on is usually here. Paste these "
                         "lines to the developer if unsure."))
    else:
        out.append(Check("warn", "AppOptions.txt not found."))
    return out
