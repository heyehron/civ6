"""Batch compatibility, candidate ranking and lobby checklist (SPEC §4.3)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

DIFFICULTIES = ["settler", "chieftain", "warlord", "prince", "king", "emperor", "immortal", "deity"]
SET_ATTRS = ("victory", "map_type", "map_size", "start_era", "ruleset")
LABELS = {"victory": "Victory", "map_type": "Map type", "map_size": "Map size",
          "start_era": "Start era", "ruleset": "Ruleset"}
DEFAULT_RISK = 2


@dataclass
class Conflict:
    attribute: str
    detail: str
    ids: list[str]


@dataclass
class BatchState:
    leaders: set[str] | None = None
    sets: dict[str, set[str] | None] = field(default_factory=lambda: {a: None for a in SET_ATTRS})
    scenario: set[str | None] = field(default_factory=set)
    diff_lo: int = 0
    diff_hi: int = len(DIFFICULTIES) - 1
    modes_required: dict[str, list[str]] = field(default_factory=dict)
    modes_forbidden: dict[str, list[str]] = field(default_factory=dict)
    choices: dict[str, tuple[str, list[str]]] = field(default_factory=dict)
    turn_limit: int | None = None
    turn_min: int | None = None
    requires_win: list[str] = field(default_factory=list)
    lobby: list[tuple[dict, str]] = field(default_factory=list)
    sources: dict[str, list[str]] = field(default_factory=dict)
    conflicts: list[Conflict] = field(default_factory=list)

    def _src(self, attr: str, aid: str) -> None:
        self.sources.setdefault(attr, []).append(aid)


def _allowed_leaders(c: dict, leaders: dict[str, dict]) -> set[str] | None:
    allowed: set[str] | None = None
    if c.get("leader"):
        allowed = set(c["leader"])
    if c.get("civ"):
        by_civ = {lid for lid, info in leaders.items() if info["civ"] in c["civ"]}
        allowed = by_civ if allowed is None else allowed & by_civ
    return allowed


def combine(achs: list[dict], leaders: dict[str, dict]) -> BatchState:
    """Fold achievements into one game state, recording every conflict found."""
    s = BatchState()
    for a in achs:
        aid, c = a["id"], a["constraints"]

        if c.get("multiplayer"):
            s.conflicts.append(Conflict("multiplayer", "Multiplayer is out of scope", [aid]))

        allowed = _allowed_leaders(c, leaders)
        if allowed is not None:
            s._src("leader", aid)
            s.leaders = allowed if s.leaders is None else s.leaders & allowed
            if not s.leaders:
                s.conflicts.append(Conflict("leader", "No leader satisfies every pick", s.sources["leader"][:]))

        for attr in SET_ATTRS:
            vals = c.get(attr)
            if not vals:
                continue
            s._src(attr, aid)
            cur = s.sets[attr]
            s.sets[attr] = set(vals) if cur is None else cur & set(vals)
            if not s.sets[attr]:
                s.conflicts.append(Conflict(attr, f"{LABELS[attr]} requirements do not overlap",
                                            s.sources[attr][:]))

        s.scenario.add(c.get("scenario"))
        s._src("scenario", aid)
        if len(s.scenario) > 1:
            names = ", ".join(sorted(x or "regular game" for x in s.scenario))
            s.conflicts.append(Conflict("scenario", f"Different games: {names}", s.sources["scenario"][:]))

        if c.get("difficulty_min"):
            s._src("difficulty", aid)
            s.diff_lo = max(s.diff_lo, DIFFICULTIES.index(c["difficulty_min"]))
        if c.get("difficulty_max"):
            s._src("difficulty", aid)
            s.diff_hi = min(s.diff_hi, DIFFICULTIES.index(c["difficulty_max"]))
        if s.diff_lo > s.diff_hi:
            s.conflicts.append(Conflict("difficulty", "Difficulty range is empty", s.sources["difficulty"][:]))

        for m in c.get("game_modes_required", []):
            s.modes_required.setdefault(m, []).append(aid)
        for m in c.get("game_modes_forbidden", []):
            s.modes_forbidden.setdefault(m, []).append(aid)
        for m in set(s.modes_required) & set(s.modes_forbidden):
            if aid in s.modes_required[m] or aid in s.modes_forbidden[m]:
                s.conflicts.append(Conflict("game_mode", f"{m} is both required and forbidden",
                                            s.modes_required[m] + s.modes_forbidden[m]))

        for key, val in c.get("choices", {}).items():
            if key in s.choices and s.choices[key][0] != val:
                s.conflicts.append(Conflict(key, f"{key}: {s.choices[key][0]} vs {val}",
                                            s.choices[key][1] + [aid]))
            else:
                s.choices.setdefault(key, (val, []))[1].append(aid)

        if c.get("turn_limit"):
            s._src("turn", aid)
            s.turn_limit = c["turn_limit"] if s.turn_limit is None else min(s.turn_limit, c["turn_limit"])
        if c.get("turn_min"):
            s._src("turn", aid)
            s.turn_min = c["turn_min"] if s.turn_min is None else max(s.turn_min, c["turn_min"])
        if s.turn_limit is not None and s.turn_min is not None and s.turn_min >= s.turn_limit:
            s.conflicts.append(Conflict("turn", f"Must end after turn {s.turn_min} and by turn {s.turn_limit}",
                                        s.sources["turn"][:]))

        if c.get("requires_win"):
            s.requires_win.append(aid)
        for item in c.get("lobby_required", []):
            s.lobby.append((item, aid))
    return s


def conflicts_with(selected: list[dict], candidate: dict, leaders: dict[str, dict]) -> list[Conflict]:
    """Conflicts that adding `candidate` to an already compatible selection would cause."""
    return [x for x in combine(selected + [candidate], leaders).conflicts if candidate["id"] in x.ids]


def _shared(a: dict, b: dict, leaders: dict[str, dict]) -> bool:
    ca, cb = a["constraints"], b["constraints"]
    if _allowed_leaders(ca, leaders) is not None and _allowed_leaders(cb, leaders) is not None:
        return True
    if any(ca.get(x) and cb.get(x) for x in SET_ATTRS):
        return True
    if ca.get("scenario") and ca.get("scenario") == cb.get("scenario"):
        return True
    if set(ca.get("game_modes_required", [])) & set(cb.get("game_modes_required", [])):
        return True
    if set(ca.get("choices", {})) & set(cb.get("choices", {})):
        return True
    return bool(ca.get("difficulty_min") and cb.get("difficulty_min"))


@dataclass
class Weights:
    rarity: float = 1.0
    overlap: float = 1.0
    risk: float = 0.5


def risk_of(a: dict) -> int:
    return a.get("risk") or DEFAULT_RISK


def score(candidate: dict, selected: list[dict], pct: float | None, leaders: dict[str, dict],
          w: Weights = Weights()) -> float:
    """rarity + overlap_gain − risk_penalty. Batch risk is the sum of member risks."""
    rarity = math.log(100 / pct) if pct else 0.0
    overlap = sum(_shared(candidate, s, leaders) for s in selected)
    return w.rarity * rarity + w.overlap * overlap - w.risk * risk_of(candidate)


@dataclass
class ChecklistItem:
    setting: str
    value: str
    label: str  # Required | Recommended | Free
    sources: list[str]


def _fmt(vals: set[str]) -> str:
    vals = sorted(vals)
    pretty = [v.replace("_", " ").title() for v in vals]
    return pretty[0] if len(pretty) == 1 else "one of: " + ", ".join(pretty)


def lobby_checklist(selected: list[dict], leaders: dict[str, dict]) -> list[ChecklistItem]:
    s = combine(selected, leaders)
    items: list[ChecklistItem] = []
    src = s.sources

    scen = {x for x in s.scenario if x}
    if scen:
        items.append(ChecklistItem("Scenario", _fmt(scen), "Required", src.get("scenario", [])))
    items.append(ChecklistItem("Speed", "Online", "Required", ["fixed (SPEC §2)"]))

    if s.leaders is not None:
        names = {leaders[x]["name"] for x in s.leaders}
        items.append(ChecklistItem("Leader", _fmt(names) if len(names) > 1 else names.pop(),
                                   "Required", src["leader"]))
    else:
        items.append(ChecklistItem("Leader", "Your choice", "Free", []))

    if "difficulty" in src:
        lo, hi = DIFFICULTIES[s.diff_lo], DIFFICULTIES[s.diff_hi]
        rng = f"{lo.title()} or harder" if hi == "deity" else f"{lo.title()}–{hi.title()}"
        items.append(ChecklistItem("Difficulty", rng, "Required", src["difficulty"]))
        items.append(ChecklistItem("Difficulty", lo.title(), "Recommended",
                                   ["lowest level that still counts"]))
    else:
        items.append(ChecklistItem("Difficulty", "Your choice", "Free", []))

    for attr in ("map_type", "map_size", "start_era", "victory", "ruleset"):
        vals = s.sets[attr]
        if vals is not None:
            items.append(ChecklistItem(LABELS[attr], _fmt(vals), "Required", src[attr]))
        elif attr != "ruleset":
            items.append(ChecklistItem(LABELS[attr], "Your choice", "Free", []))

    if s.sets["victory"] is not None and len(s.sets["victory"]) == 1:
        items.append(ChecklistItem("Other victory types", "Off", "Recommended",
                                   ["avoids an accidental win by another route"]))

    for m, ids in sorted(s.modes_required.items()):
        items.append(ChecklistItem("Game mode", f"{m.replace('_', ' ').title()} on", "Required", ids))
    for m, ids in sorted(s.modes_forbidden.items()):
        items.append(ChecklistItem("Game mode", f"{m.replace('_', ' ').title()} off", "Required", ids))

    if s.turn_limit is not None:
        items.append(ChecklistItem("Turn limit", f"finish by turn {s.turn_limit}", "Required", src["turn"]))
    if s.turn_min is not None:
        items.append(ChecklistItem("Turn minimum", f"finish after turn {s.turn_min}", "Required", src["turn"]))

    merged: dict[tuple[str, str], list[str]] = {}
    for item, aid in s.lobby:
        merged.setdefault((item["setting"], item["value"]), []).append(aid)
    for (setting, value), ids in merged.items():
        items.append(ChecklistItem(setting, value, "Required", ids))
    if any(k == "City-state pool" for k, _ in merged):
        items.append(ChecklistItem("City-state pool", "only the listed city-states", "Recommended",
                                   ["the picker sets a pool, not a guarantee"]))

    for key, (val, ids) in sorted(s.choices.items()):
        items.append(ChecklistItem(f"In game: {key.replace('_', ' ')}", str(val).replace("_", " ").title(),
                                   "Required", ids))
    return items
