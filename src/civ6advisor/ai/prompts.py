"""Prompt builders. Context comes from the app's own data; the model is told what is verified."""
from __future__ import annotations

import json

from ..engine.batch import lobby_checklist
from ..engine.playbook import OPS
from ..state.model import FIELD_CATALOG, GameState

SYSTEM = """You are an expert Sid Meier's Civilization VI coach helping a player earn Steam achievements.

Rules:
- The game is single player at Online speed with all DLC (Gathering Storm rules).
  Online speed has about half the turns of Standard; scale any turn numbers you give.
- Facts inside CONTEXT come from the player's own data. Achievement descriptions are exact.
  Constraints marked "draft" or "inferred" are unverified guesses; say so if you rely on them.
- When you are not sure about a game mechanic, say "unverified" instead of guessing confidently.
- Be concise and concrete: give actions, in order, with turn targets where useful.
- Use short markdown: headings, bullets, bold for key actions. No filler."""


def achievement_brief(a: dict, pct: float | None = None, unlocked: bool = False) -> str:
    c = {k: v for k, v in a["constraints"].items() if v not in (None, [], {}, False)}
    status = "UNLOCKED" if unlocked else "locked"
    rare = f"{pct:.1f}% of players" if pct is not None else "rarity unknown"
    verified = "verified" if a.get("verified") else f"draft (inferred fields: {', '.join(a.get('inferred') or []) or 'none'})"
    note = f"\n  notes: {a['notes']}" if a.get("notes") else ""
    return (f"- {a['name']} [{a['id']}] ({status}, {rare})\n  description: {a['description']}\n"
            f"  constraints ({verified}): {json.dumps(c, ensure_ascii=False)}{note}")


def batch_context(selected: list[dict], leaders: dict, pct: dict, unlocked: set[str]) -> str:
    if not selected:
        return "No target achievements selected."
    lines = ["Target achievements for this game:"]
    lines += [achievement_brief(a, pct.get(a["id"]), a["id"] in unlocked) for a in selected]
    lines.append("\nLobby checklist computed by the app:")
    for it in lobby_checklist(selected, leaders):
        lines.append(f"- [{it.label}] {it.setting}: {it.value}")
    return "\n".join(lines)


def state_context(state: GameState | None) -> str:
    if state is None:
        return "No live game state available."
    f = state.fields()
    keep = ["turn", "era", "leader", "civ", "difficulty", "map_type", "map_size", "speed", "game_modes",
            "government", "policies", "cities_count", "total_population", "districts_all", "wonders_owned",
            "wonders_lost", "yields", "balances", "religion", "suzerain_of", "city_states_met",
            "city_states_following_my_religion", "era_score", "age", "victory_progress", "at_war_with",
            "current_tech", "current_civic", "great_people"]
    slim = {k: f.get(k) for k in keep if f.get(k) not in (None, [], {}, "")}
    return "Live game state (from the advisor mod):\n" + json.dumps(slim, ensure_ascii=False)


def advice_context(advice) -> str:
    if advice is None:
        return ""
    lines = ["Playbook progress:"]
    for ps in advice.statuses:
        nxt = ps.next_step.step["text"] if ps.next_step else "complete"
        lines.append(f"- {ps.title}: {round(ps.progress * 100)}% · next: {nxt}{' · FAILED' if ps.failed else ''}")
    for al in advice.alerts[:8]:
        lines.append(f"- ALERT [{al.level}] {al.text}")
    return "\n".join(lines)


def build_context(parts: list[str]) -> str:
    body = "\n\n".join(p for p in parts if p)
    return f"CONTEXT\n=======\n{body}\n=======" if body else ""


PLAYBOOK_EXAMPLE = {
    "achievement": "raf_achievement_19",
    "title": "Holy Righteous Queen Tamar",
    "summary": "As Tamar, every city-state follows your religion.",
    "tips": ["Keep the city-state count low in the lobby."],
    "steps": [
        {"id": "found", "text": "Found a religion", "detail": "Holy Site + Astrology early.",
         "done_when": {"field": "religion_founded", "op": "eq", "value": True}, "deadline_turn": 60},
        {"id": "all_cs", "text": "Every city-state follows your religion",
         "done_when": {"all": [{"field": "city_states_count", "op": "gte", "value": 1},
                               {"field": "city_states_following_my_religion", "op": "gte", "value": 1}]}},
        {"id": "verify", "text": "Check the unlock popup", "manual": True},
    ],
}


def playbook_prompt(a: dict, extra: str = "") -> str:
    fields = "\n".join(f"- {k}: {v}" for k, v in FIELD_CATALOG.items())
    return f"""Write a playbook for this Civilization VI achievement as a single JSON object.

{achievement_brief(a)}

JSON schema:
{{"achievement": "<id>", "title": "<name>", "summary": "<one sentence>",
  "tips": ["<short tip>", ...],
  "steps": [{{"id": "<snake_case>", "text": "<imperative, max 8 words>", "detail": "<how, 1-2 sentences>",
             "done_when": <condition>, "fail_when": <condition or omit>, "deadline_turn": <int or omit>,
             "manual": <true if it cannot be checked from game state; then omit done_when>}}]}}

A condition is {{"field": F, "op": OP, "value": V}} or {{"all": [...]}} / {{"any": [...]}} / {{"not": cond}}.
OP is one of: {", ".join(OPS)}. count_gte compares list length; "in" checks the field is in a list value.
F must be one of these game-state fields (dotted paths allowed):
{fields}

Requirements:
- 4 to 9 ordered steps: setup checks first, then the plan, then the goal.
- Turn numbers are for ONLINE speed (about half of Standard). Only add deadline_turn when timing matters.
- Use "manual": true for anything the fields above cannot express.
- Put uncertain mechanics in tips prefixed with "Unverified:".
- Output JSON only.

Example of the format:
{json.dumps(PLAYBOOK_EXAMPLE, indent=1)}
{extra}"""


QUICK_PROMPTS = {
    "Plan this batch": "Give me a turn-by-turn plan for the selected batch at Online speed: opening build order, "
                       "mid-game priorities, and the exact moments each target achievement can fail.",
    "What now?": "Based on the live game state and playbook progress, what are the 3 most important things to do "
                 "this turn and the next few turns? Flag anything at risk.",
    "Lobby check": "Double-check the lobby checklist for the selected batch. Point out any setting that is missing, "
                   "risky, or that I might get wrong in the setup screen.",
    "Failure risks": "List the ways this batch can fail, most likely first, and how to prevent each.",
    "Verify constraints": "Review the constraints of the selected achievements. For each, say whether it matches "
                          "your knowledge of the game, and flag any that look wrong or missing. Mark guesses.",
}
