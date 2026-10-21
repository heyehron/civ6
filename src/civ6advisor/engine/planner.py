"""Batch suggestions: build whole-game batches from the locked achievements.

Heuristic, not optimal. For each anchor (a leader, or a game mode) the planner
greedily adds compatible achievements in this order:

1. "win" conditions (map type, map size, start era, victory, difficulty)
2. leader / civ feats for the chosen leader
3. feats that need a game mode the batch already turns on

Then it scores the batch as Σ rarity / estimated difficulty. The difficulty
estimate is a rough heuristic and is shown as such in the UI.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .batch import DIFFICULTIES, combine

WIN_ATTRS = ("map_type", "map_size", "start_era", "victory", "difficulty_min")


@dataclass
class Suggestion:
    anchor: str
    ids: list[str]
    rarity: float
    effort: float
    score: float
    warnings: list[str] = field(default_factory=list)


def rarity(pct: float | None) -> float:
    return math.log(100 / pct) if pct else 0.5


def _is_win_condition(a: dict) -> bool:
    c = a["constraints"]
    return c.get("requires_win") and not c.get("leader") and not c.get("civ") and any(c.get(x) for x in WIN_ATTRS)


def _leader_feat(a: dict) -> bool:
    c = a["constraints"]
    return bool(c.get("leader") or c.get("civ"))


def estimate_effort(achs: list[dict], leaders: dict) -> float:
    """1 = an ordinary win at a comfortable level; each factor adds on top."""
    s = combine(achs, leaders)
    effort = 1.0
    if s.requires_win:
        lvl = s.diff_lo
        effort += {5: 0.8, 6: 1.6, 7: 2.6}.get(lvl, 0.0)
        vic = s.sets["victory"]
        if vic and len(vic) == 1:
            effort += {"domination": 0.8, "diplomatic": 0.5, "culture": 0.3, "science": 0.2,
                       "religious": 0.1}.get(next(iter(vic)), 0.0)
        size = s.sets["map_size"]
        if size and len(size) == 1:
            effort += {"huge": 0.8, "large": 0.4, "duel": -0.3, "tiny": -0.2}.get(next(iter(size)), 0.0)
    feats = [a for a in achs if not a["constraints"].get("requires_win")]
    effort += 0.25 * len(feats)
    effort += 0.15 * len(s.modes_required)
    effort += 0.2 * sum(len(a["constraints"].get("lobby_required", [])) for a in achs)
    effort += sum(((a.get("risk") or 2) - 2) * 0.3 for a in achs)
    return max(effort, 0.5)


LATE_ERAS = {"industrial", "modern", "atomic", "information"}


def warnings(achs: list[dict], leaders: dict) -> list[str]:
    """Plausibility checks the hard constraints cannot express. All unverified."""
    s = combine(achs, leaders)
    out: list[str] = []
    era, vic, size = s.sets["start_era"], s.sets["victory"], s.sets["map_size"]
    if era and era <= LATE_ERAS and vic == {"religious"}:
        out.append("Late start era with a religious victory: founding a religion may be hard or impossible.")
    if era and era <= LATE_ERAS and any("Hero" in a["description"] for a in achs):
        out.append("Late start era: early Heroes may already be gone.")
    if size == {"duel"} and len({(i["setting"], i["value"]) for i, _ in s.lobby if i["setting"] == "AI opponent"}) > 1:
        out.append("Duel map holds one AI; more AI opponents are required than fit by default.")
    if any("lose" in a["description"].lower() for a in achs) and s.requires_win:
        out.append("Batch includes a 'lose something' feat alongside a win; time it carefully.")
    if s.diff_lo >= 6:
        out.append("Immortal/Deity win: high failure risk.")
    return out


def _fits(batch: list[dict], cand: dict, leaders: dict, max_diff: int) -> bool:
    c = cand["constraints"]
    if c.get("multiplayer") or c.get("scenario"):
        return False
    if c.get("difficulty_min") and DIFFICULTIES.index(c["difficulty_min"]) > max_diff:
        return False
    return not combine(batch + [cand], leaders).conflicts


def build(anchor_ids: list[str], pool: dict[str, dict], leaders: dict, pct: dict[str, float],
          max_diff: int) -> list[dict]:
    batch = [pool[i] for i in anchor_ids if i in pool]
    if combine(batch, leaders).conflicts:
        return []
    rest = [a for a in pool.values() if a not in batch]
    by_rarity = sorted(rest, key=lambda a: -rarity(pct.get(a["id"])))

    def add_where(pred) -> None:
        for a in by_rarity:
            if a not in batch and pred(a) and _fits(batch, a, leaders, max_diff) and \
                    len(warnings(batch + [a], leaders)) <= len(warnings(batch, leaders)):
                batch.append(a)

    has_leader = any(_leader_feat(a) for a in batch)
    add_where(_is_win_condition)
    if has_leader:
        add_where(_leader_feat)
    modes = set(combine(batch, leaders).modes_required)
    if modes:
        add_where(lambda a: set(a["constraints"].get("game_modes_required", [])) and
                  set(a["constraints"]["game_modes_required"]) <= modes and not _leader_feat(a))
    return batch


def suggest(locked: dict[str, dict], leaders: dict, pct: dict[str, float], max_difficulty: str = "emperor",
            limit: int = 12) -> list[Suggestion]:
    max_diff = DIFFICULTIES.index(max_difficulty)
    pool = {k: a for k, a in locked.items()
            if not a["constraints"].get("multiplayer") and not a["constraints"].get("scenario")}

    anchors: list[tuple[str, list[str]]] = []
    for a in pool.values():
        c = a["constraints"]
        if c.get("requires_win") and c.get("leader") and not c.get("victory"):
            anchors.append((a["name"], [a["id"]]))
    by_leader: dict[frozenset, list[str]] = {}
    for a in pool.values():
        c = a["constraints"]
        if (c.get("leader") or c.get("civ")) and not c.get("requires_win"):
            key = frozenset(c.get("leader") or c.get("civ"))
            by_leader.setdefault(key, []).append(a["id"])
    for ids in by_leader.values():
        if len(ids) >= 2 and not any(set(ids) & set(x[1]) for x in anchors):
            anchors.append((pool[ids[0]]["name"] + " (+ civ feats)", ids[:1]))
    for mode in sorted({m for a in pool.values() for m in a["constraints"].get("game_modes_required", [])}):
        first = next(a for a in pool.values() if mode in a["constraints"].get("game_modes_required", []))
        anchors.append((f"{mode.replace('_', ' ').title()} mode", [first["id"]]))

    out: list[Suggestion] = []
    seen: set[frozenset] = set()
    for name, ids in anchors:
        batch = build(ids, pool, leaders, pct, max_diff)
        if not batch:
            continue
        key = frozenset(a["id"] for a in batch)
        if key in seen:
            continue
        seen.add(key)
        r = sum(rarity(pct.get(a["id"])) for a in batch)
        e = estimate_effort(batch, leaders)
        out.append(Suggestion(name, [a["id"] for a in batch], r, e, r / e, warnings(batch, leaders)))
    return _diversify(out, pct, limit)


def _diversify(cands: list[Suggestion], pct: dict[str, float], limit: int) -> list[Suggestion]:
    """Greedy re-rank: rarity already offered by a higher pick counts half."""
    picked: list[Suggestion] = []
    used: set[str] = set()
    pool = list(cands)
    while pool and len(picked) < limit:
        def adj(s: Suggestion) -> float:
            dup = sum(rarity(pct.get(i)) for i in s.ids if i in used)
            return (s.rarity - 0.5 * dup) / s.effort
        best = max(pool, key=adj)
        pool.remove(best)
        picked.append(best)
        used.update(best.ids)
    return picked


def season(locked: dict[str, dict], leaders: dict, pct: dict[str, float], max_difficulty: str = "emperor",
           games: int = 6) -> list[Suggestion]:
    """A sequence of non-overlapping batches: best batch, remove it, repeat."""
    remaining = dict(locked)
    plan: list[Suggestion] = []
    for _ in range(games):
        best = suggest(remaining, leaders, pct, max_difficulty, limit=1)
        if not best:
            break
        plan.append(best[0])
        for i in best[0].ids:
            remaining.pop(i, None)
    return sorted(plan, key=lambda s: -s.score)
