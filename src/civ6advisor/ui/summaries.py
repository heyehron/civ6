"""Human-readable summaries of constraints, shared by several pages."""
from __future__ import annotations

FIELD_LABELS = {
    "leader": "Leader", "civ": "Civilization", "victory": "Victory", "difficulty_min": "Difficulty ≥",
    "difficulty_max": "Difficulty ≤", "map_type": "Map type", "map_size": "Map size", "start_era": "Start era",
    "ruleset": "Ruleset", "game_modes_required": "Modes on", "game_modes_forbidden": "Modes off",
    "scenario": "Scenario", "turn_limit": "By turn", "turn_min": "After turn", "requires_win": "Needs a win",
    "choices": "In-game choice", "lobby_required": "Lobby", "multiplayer": "Multiplayer", "multi_game": "Across games",
}


def pretty(v) -> str:
    return str(v).replace("CIVILIZATION_", "").replace("LEADER_", "").replace("_", " ").title()


def value_text(key: str, val, leaders: dict) -> str:
    if key == "leader":
        return ", ".join(leaders.get(x, {}).get("name", pretty(x)) for x in val)
    if key == "lobby_required":
        return "; ".join(f"{i['setting']}: {i['value']}" for i in val)
    if key == "choices":
        return "; ".join(f"{pretty(k)} = {pretty(v)}" for k, v in val.items())
    if isinstance(val, bool):
        return "yes" if val else "no"
    if isinstance(val, list):
        return ", ".join(pretty(x) for x in val)
    return pretty(val)


def constraint_rows(a: dict, leaders: dict) -> list[tuple[str, str, bool]]:
    """(label, value, inferred) for every set constraint."""
    inferred = set(a.get("inferred") or [])
    rows = []
    for key, val in a["constraints"].items():
        if val in (None, [], {}, False):
            continue
        rows.append((FIELD_LABELS.get(key, key), value_text(key, val, leaders), key in inferred))
    return rows


def short_tags(a: dict, leaders: dict) -> str:
    c = a["constraints"]
    parts: list[str] = []
    if c.get("scenario"):
        parts.append(pretty(c["scenario"]))
    if c.get("leader"):
        names = {leaders.get(x, {}).get("name", x).split(" (")[0] for x in c["leader"]}
        parts.append("/".join(sorted(names)))
    elif c.get("civ"):
        parts.append("/".join(pretty(x) for x in c["civ"]))
    for key in ("victory", "map_type", "map_size", "start_era"):
        if c.get(key):
            parts.append("/".join(pretty(x) for x in c[key]))
    if c.get("difficulty_min"):
        parts.append(pretty(c["difficulty_min"]) + "+")
    for m in c.get("game_modes_required", []):
        parts.append(pretty(m))
    if c.get("multi_game"):
        parts.append("multi-game")
    if c.get("multiplayer"):
        parts.append("multiplayer")
    if not parts:
        parts.append("any game")
    return " · ".join(parts)
