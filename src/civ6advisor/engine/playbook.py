"""Playbook evaluation (SPEC §4.4).

Conditions are declarative and never executed as code:

    {"field": "religion.type", "op": "eq", "value": "RELIGION_ZOROASTRIANISM"}
    {"all": [cond, ...]}   {"any": [cond, ...]}   {"not": cond}

A step marked "manual": true cannot be tracked from game state; the user ticks it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..state.model import FIELD_CATALOG, GameState, lookup

OPS = ("eq", "ne", "lt", "lte", "gt", "gte", "contains", "not_contains", "count_gte", "exists", "in")
UNKNOWN = object()


class PlaybookError(ValueError):
    pass


def _cmp(op: str, actual: Any, value: Any) -> bool:
    if op == "exists":
        return actual is not None and actual != [] and actual != ""
    if actual is None:
        return False
    if op == "eq":
        return _eq(actual, value)
    if op == "ne":
        return not _eq(actual, value)
    if op in ("lt", "lte", "gt", "gte"):
        a, b = float(actual), float(value)
        return {"lt": a < b, "lte": a <= b, "gt": a > b, "gte": a >= b}[op]
    if op == "contains":
        return any(_eq(x, value) for x in actual) if isinstance(actual, (list, tuple, set)) else \
            str(value).lower() in str(actual).lower()
    if op == "not_contains":
        return not _cmp("contains", actual, value)
    if op == "count_gte":
        if isinstance(value, dict):  # {"item": X, "n": 3}: occurrences of X
            return sum(1 for x in actual if _eq(x, value["item"])) >= int(value["n"])
        return len(actual) >= int(value)
    if op == "in":
        return any(_eq(actual, v) for v in value)
    raise PlaybookError(f"unknown op {op}")


def _eq(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    return a == b


def evaluate(cond: dict | None, fields: dict[str, Any]) -> bool | None:
    """True/False, or None when a referenced field is missing (cannot track)."""
    if not cond:
        return None
    if "all" in cond:
        results = [evaluate(c, fields) for c in cond["all"]]
        if any(r is False for r in results):
            return False
        return None if any(r is None for r in results) else True
    if "any" in cond:
        results = [evaluate(c, fields) for c in cond["any"]]
        if any(r is True for r in results):
            return True
        return None if any(r is None for r in results) else False
    if "not" in cond:
        r = evaluate(cond["not"], fields)
        return None if r is None else not r
    found, actual = lookup(fields, cond["field"])
    if not found:
        return None
    return _cmp(cond["op"], actual, cond.get("value"))


def validate_condition(cond: Any, where: str) -> list[str]:
    errs: list[str] = []
    if cond is None:
        return errs
    if not isinstance(cond, dict):
        return [f"{where}: condition must be an object"]
    for key in ("all", "any"):
        if key in cond:
            if not isinstance(cond[key], list) or not cond[key]:
                return [f"{where}.{key}: must be a non-empty list"]
            for i, c in enumerate(cond[key]):
                errs += validate_condition(c, f"{where}.{key}[{i}]")
            return errs
    if "not" in cond:
        return validate_condition(cond["not"], f"{where}.not")
    if "field" not in cond or "op" not in cond:
        return [f"{where}: needs 'field' and 'op'"]
    if cond["op"] not in OPS:
        errs.append(f"{where}: unknown op '{cond['op']}' (use one of {', '.join(OPS)})")
    root = cond["field"].split(".")[0]
    if cond["field"] not in FIELD_CATALOG and root not in {k.split(".")[0] for k in FIELD_CATALOG}:
        errs.append(f"{where}: field '{cond['field']}' is not produced by the game-state model")
    if cond["op"] != "exists" and "value" not in cond:
        errs.append(f"{where}: needs 'value'")
    return errs


def validate(pb: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(pb, dict):
        return ["playbook must be a JSON object"]
    if not pb.get("achievement"):
        errs.append("missing 'achievement'")
    steps = pb.get("steps")
    if not isinstance(steps, list) or not steps:
        return errs + ["'steps' must be a non-empty list"]
    seen = set()
    for i, st in enumerate(steps):
        where = f"steps[{i}]"
        if not isinstance(st, dict):
            errs.append(f"{where}: must be an object")
            continue
        sid = st.get("id")
        if not sid:
            errs.append(f"{where}: missing 'id'")
        elif sid in seen:
            errs.append(f"{where}: duplicate id '{sid}'")
        seen.add(sid)
        if not st.get("text"):
            errs.append(f"{where}: missing 'text'")
        if not st.get("manual") and not st.get("done_when"):
            errs.append(f"{where}: needs 'done_when' or \"manual\": true")
        errs += validate_condition(st.get("done_when"), f"{where}.done_when")
        errs += validate_condition(st.get("fail_when"), f"{where}.fail_when")
        dl = st.get("deadline_turn")
        if dl is not None and (not isinstance(dl, int) or dl <= 0):
            errs.append(f"{where}: deadline_turn must be a positive integer")
    return errs


@dataclass
class StepStatus:
    step: dict
    done: bool
    failed: bool
    trackable: bool
    at_risk: bool
    missed: bool


@dataclass
class PlaybookStatus:
    achievement: str
    title: str
    steps: list[StepStatus]
    progress: float
    next_step: StepStatus | None
    failed: bool

    @property
    def done(self) -> bool:
        return all(s.done for s in self.steps)


@dataclass
class Alert:
    level: str  # failed | missed | at_risk | untracked
    achievement: str
    text: str


@dataclass
class Advice:
    statuses: list[PlaybookStatus]
    next_action: tuple[PlaybookStatus, StepStatus] | None
    alerts: list[Alert] = field(default_factory=list)


FINAL_IDS = {"win", "goal", "check", "verify", "confirm"}


SETUP_GRACE_TURNS = 3


def is_setup(step: dict) -> bool:
    """Manual lobby/setup steps cannot be acted on once the game is under way."""
    return bool(step.get("manual")) and str(step.get("id", "")).startswith(("lobby", "setup"))


def is_final(step: dict) -> bool:
    """Steps that close a playbook (win, confirm) only become the next action when nothing else is open."""
    return bool(step.get("final")) or step.get("id") in FINAL_IDS


def evaluate_playbook(pb: dict, state: GameState, manual_done: set[str]) -> PlaybookStatus:
    fields = state.fields()
    out: list[StepStatus] = []
    for st in pb["steps"]:
        key = f"{pb['achievement']}:{st['id']}"
        done_r = evaluate(st.get("done_when"), fields)
        fail_r = evaluate(st.get("fail_when"), fields)
        done = key in manual_done or done_r is True
        trackable = bool(st.get("done_when")) and done_r is not None
        dl = st.get("deadline_turn")
        missed = bool(dl and not done and state.turn > dl)
        at_risk = bool(dl and not done and not missed and state.turn >= dl - 5)
        out.append(StepStatus(st, done, fail_r is True and not done, trackable, at_risk, missed))
    done_n = sum(s.done for s in out)
    nxt = next((s for s in out if not s.done), None)
    return PlaybookStatus(pb["achievement"], pb.get("title", pb["achievement"]), out,
                          done_n / len(out) if out else 1.0, nxt, any(s.failed for s in out))


def advise(playbooks: list[dict], state: GameState, manual_done: set[str]) -> Advice:
    statuses = [evaluate_playbook(pb, state, manual_done) for pb in playbooks]
    alerts: list[Alert] = []
    for ps in statuses:
        for s in ps.steps:
            if s.failed:
                alerts.append(Alert("failed", ps.achievement, f"{ps.title}: {s.step['text']} — failed"))
            elif s.missed:
                alerts.append(Alert("missed", ps.achievement,
                                    f"{ps.title}: {s.step['text']} — deadline turn {s.step['deadline_turn']} passed"))
            elif s.at_risk:
                alerts.append(Alert("at_risk", ps.achievement,
                                    f"{ps.title}: {s.step['text']} — due by turn {s.step['deadline_turn']}"))
    order = {"failed": 0, "missed": 1, "at_risk": 2}
    alerts.sort(key=lambda a: order.get(a.level, 9))

    candidates = []
    for ps in statuses:
        if ps.failed:
            continue
        open_steps = [s for s in ps.steps if not s.done and not (state.turn > SETUP_GRACE_TURNS and is_setup(s.step))]
        work = [s for s in open_steps if not is_final(s.step)]
        if open_steps:
            candidates.append((ps, (work or open_steps)[0]))
    big = 10 ** 9
    candidates.sort(key=lambda t: (t[1].step.get("deadline_turn") or big, is_final(t[1].step),
                                   statuses.index(t[0])))
    return Advice(statuses, candidates[0] if candidates else None, alerts)


# Loading --------------------------------------------------------------------------------

def load_dir(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for f in sorted(path.glob("*.json")):
        try:
            pb = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(pb, dict) and pb.get("achievement"):
            pb["_path"] = str(f)
            out[pb["achievement"].lower()] = pb
    return out


def save(pb: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{pb['achievement'].lower()}.json"
    data = {k: v for k, v in pb.items() if not k.startswith("_")}
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# Auto playbooks -------------------------------------------------------------------------

def auto_playbook(ach: dict, leaders: dict[str, dict]) -> dict:
    """A setup-check playbook built from an achievement's constraints.

    Used when no hand-written playbook exists. It verifies the lobby settings on
    turn 1 so setup mistakes surface before any real time is spent.
    """
    from .batch import DIFFICULTIES  # local import avoids a cycle at module load

    c = ach["constraints"]
    steps: list[dict] = []
    if c.get("leader") or c.get("civ"):
        if c.get("leader"):
            names = ", ".join(leaders[x]["name"] for x in c["leader"] if x in leaders)
            steps.append({"id": "setup_leader", "text": f"Play as {names}",
                          "done_when": {"field": "leader", "op": "in", "value": c["leader"]},
                          "fail_when": {"all": [{"field": "leader", "op": "exists"},
                                                {"not": {"field": "leader", "op": "in", "value": c["leader"]}}]}})
        else:
            steps.append({"id": "setup_civ", "text": "Play as " + ", ".join(
                x.replace("CIVILIZATION_", "").title() for x in c["civ"]),
                "done_when": {"field": "civ", "op": "in", "value": c["civ"]},
                "fail_when": {"all": [{"field": "civ", "op": "exists"},
                                      {"not": {"field": "civ", "op": "in", "value": c["civ"]}}]}})
    if c.get("difficulty_min"):
        lvl = DIFFICULTIES.index(c["difficulty_min"])
        steps.append({"id": "setup_difficulty", "text": f"Difficulty {c['difficulty_min'].title()} or harder",
                      "done_when": {"field": "difficulty_level", "op": "gte", "value": lvl},
                      "fail_when": {"field": "difficulty_level", "op": "lt", "value": lvl}})
    for attr, label in (("map_type", "Map type"), ("map_size", "Map size"), ("start_era", "Start era")):
        if c.get(attr):
            pretty = " / ".join(v.replace("_", " ").title() for v in c[attr])
            steps.append({"id": f"setup_{attr}", "text": f"{label}: {pretty}",
                          "done_when": {"field": attr, "op": "in", "value": c[attr]},
                          "fail_when": {"all": [{"field": attr, "op": "exists"},
                                                {"not": {"field": attr, "op": "in", "value": c[attr]}}]}})
    for m in c.get("game_modes_required", []):
        steps.append({"id": f"setup_mode_{m}", "text": f"Game mode on: {m.replace('_', ' ').title()}",
                      "done_when": {"field": "game_modes", "op": "contains", "value": m}})
    for item in c.get("lobby_required", []):
        steps.append({"id": f"setup_{len(steps)}", "text": f"{item['setting']}: {item['value']}", "manual": True})
    if c.get("victory"):
        v = c["victory"][0]
        steps.append({"id": "win", "text": f"Win with a {v.title()} victory", "manual": True})
    elif c.get("requires_win"):
        steps.append({"id": "win", "text": "Win the game", "manual": True})
    else:
        steps.append({"id": "goal", "text": ach["description"], "manual": True})
    return {"achievement": ach["id"], "title": ach["name"], "summary": ach["description"],
            "author": "auto", "verified": False, "tips": [], "steps": steps}
