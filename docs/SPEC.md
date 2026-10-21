# Civ VI Achievement Advisor — Functional Specification

Status: planning draft. Supersedes the two earlier drafts.

## 1. Purpose and scope

A local desktop tool that:

1. Pulls the user's Civ VI achievement status from Steam and hides unlocked ones.
2. Lets the user pick a batch of target achievements and rejects incompatible picks.
3. Produces the exact lobby setup for that batch.
4. During play, reads exact game state from a UI-only Civ VI mod and shows the next action, progress and failure alerts on a second monitor.

Non-goals:

- No cloud LLM calls at runtime. Steam Web API is the only network call, and its result is cached so the app runs offline afterwards.
- No automated input to the game. The tool advises; the user plays.
- No multiplayer support.

## 2. Fixed decisions

| Item | Decision |
|---|---|
| Game mode | Single player, Online speed |
| Content | All DLC and expansions owned; no ownership checks |
| Game display | Native full screen, primary monitor |
| Game state source | **Option B**: UI-only Lua mod writes state to a log file (primary). Vision is an optional fallback, off by default |
| GPU | RTX 4060 (8 GB VRAM) |
| Repo | Public (`heyehron/civ6`) |
| Language / UI | Python 3.12, PySide6 |

Consequences:

- **Native full screen.** Clicking the second monitor minimises Civ. The HUD must therefore be **read-only during play**. All interaction (picking achievements, settings) happens before launching the game. Optional global hotkeys may be added later.
- **8 GB VRAM.** Civ VI at 1440p uses a large share of 8 GB. Qwen-2.5-VL-7B (≈6 GB at Q4) will not coexist with it cleanly. If the vision fallback is ever enabled, use `qwen2.5vl:3b`.

## 3. Architecture

```
 PRE-GAME                                      IN-GAME
 ┌──────────────┐                              ┌──────────────────────────┐
 │ Steam Web API│                              │ Civ VI (native fullscreen)│
 └──────┬───────┘                              │  └─ UI-only Lua mod       │
        │ sync (cached)                        └────────────┬─────────────┘
        v                                                   │ appends state lines
 ┌──────────────┐   ┌─────────────────────┐                 v
 │ steam/       │──>│ achievements.json   │        ┌─────────────────┐
 │ sync + prune │   │ (committed source)  │        │ Lua.log         │
 └──────────────┘   └─────────┬───────────┘        └────────┬────────┘
                              │ loaded at start             │ tail
                              v                             v
                    ┌──────────────────────────────────────────────────┐
                    │ engine/                                          │
                    │  batching  → lobby checklist                     │
                    │  playbooks + GameState → next action, progress,  │
                    │                          alerts                  │
                    └────────────────────────┬─────────────────────────┘
                                             │ Qt signals
                                             v
                    ┌──────────────────────────────────────────────────┐
                    │ ui/ — PySide6 HUD on secondary monitor           │
                    │ (falls back to a normal window if 1 monitor)     │
                    └──────────────────────────────────────────────────┘
```

Vision fallback (optional) plugs in as another `GameState` source next to the log reader. The engine does not know which source is active.

## 4. Components

### 4.1 Steam sync — `src/steam/`

- `GetSchemaForGame` (AppID 289070): achievement internal ID (`apiname`), display name, description and icon URL.
- `GetPlayerAchievements`: unlock status per `apiname`.
- Requires the user's Steam profile **Game details** to be public.
- API key is stored in the OS credential store via `keyring`. SteamID64 is stored in a plain config file (not secret).
- The last successful response is cached to `~/.civ6advisor/steam_cache.json`. If the network fails, the cache is used and the UI shows a "last synced" timestamp.
- Unlocked achievements are hidden from the picker (toggle to show them).

### 4.2 Achievement dataset — `data/achievements.json`

The single source of truth. It is committed to git as JSON, not as a binary `.db`. Achievements are keyed by Steam `apiname`, so names are never typed by hand.

```json
{
  "id": "ACHIEVEMENT_XYZ",
  "name": "from Steam schema",
  "description": "from Steam schema",
  "content": "base | rise_and_fall | gathering_storm | new_frontier | scenario | leader_pack",
  "constraints": {
    "leader":        ["LEADER_CLEOPATRA"],
    "civ":           null,
    "victory":       ["science"],
    "difficulty_min": "deity",
    "difficulty_max": null,
    "map_type":      null,
    "map_size":      null,
    "start_era":     null,
    "ruleset":       "gathering_storm",
    "game_modes_required":  [],
    "game_modes_forbidden": [],
    "scenario":      null,
    "turn_limit":    null
  },
  "effort": 1,
  "risk": 1,
  "playbook": "playbooks/ACHIEVEMENT_XYZ.json",
  "verified": false,
  "notes": ""
}
```

Rules:

- `null` or an empty list means unconstrained.
- `effort` and `risk` are 1–5 and are set by the user.
- `verified: false` entries are shown with a warning. Initial tagging may be LLM-drafted offline, but only user-verified entries count as trusted.
- At startup the app builds an in-memory or SQLite index from the JSON. The `.db` file is never committed.

### 4.3 Batching engine — `src/engine/batch.py`

Compatibility between selected achievements:

- **Set attributes** (`leader`, `civ`, `victory`, `map_type`, `map_size`, `start_era`, `ruleset`, `scenario`): intersect the allowed sets. An empty intersection means a conflict.
- **Victory:** at most one victory type per game.
- **Difficulty:** effective range is `max(difficulty_min)` to `min(difficulty_max)`. An empty range means a conflict.
- **Game modes:** a mode both required and forbidden means a conflict.
- **Scenario:** a scenario achievement only combines with achievements from the same scenario.
- **Turn limit:** the strictest limit applies.

UI behaviour: after each pick, achievements that would conflict are greyed out, and hovering one shows which attribute conflicts.

Ranking of the remaining candidates:

```
score = overlap_gain − risk_penalty
overlap_gain = number of currently selected targets the candidate shares a
               constrained attribute with
risk_penalty = weight × (batch risk after adding − batch risk before)
```

With ≈300 items this is computed instantly. Algorithmic complexity is not a concern.

Lobby checklist output. Every setting is labelled with how it was decided:

| Label | Meaning |
|---|---|
| **Required** | Forced by a selected achievement; shows which one |
| **Recommended** | Makes the run easier; shows the reason |
| **Free** | User's choice |

### 4.4 Playbooks — `data/playbooks/*.json`

The playbooks hold the advice; nothing else in the system generates it. Each achievement has an ordered list of steps that can be checked against `GameState`.

```json
{
  "achievement": "ACHIEVEMENT_XYZ",
  "steps": [
    {
      "id": "build_pyramids",
      "text": "Build the Pyramids",
      "done_when":  {"field": "wonders_owned", "op": "contains", "value": "BUILDING_PYRAMIDS"},
      "fail_when":  {"field": "wonders_lost", "op": "contains", "value": "BUILDING_PYRAMIDS"},
      "deadline_turn": 80
    }
  ]
}
```

- Checks are declarative (`field` / `op` / `value`). They are never evaluated as Python code, because the JSON is user-editable data.
- Supported ops: `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `contains`, `not_contains`, `count_gte`.
- Progress = completed steps / total steps.
- Next action = the first unfinished step across all targets, ordered by the nearest deadline.
- Alert when a `fail_when` fires, or when the turn passes `deadline_turn − 5` with the step unfinished.
- Playbooks are written by hand. Start with the user's first batch only.

### 4.5 Game state — `mod/` and `src/state/`

**Lua mod (`mod/`)**

- UI context only (`AffectsSavedGames=0`), so it does not change gameplay.
- Hooks game events: turn start, tech and civic changes, city founded, district and wonder completed (any player), era change.
- On each event, writes one line through `print()`: `CIV6ADV|{json}`. A small JSON serialiser is included in the mod because Civ's Lua has none.
- Writes a full snapshot at turn start, and a delta for each event in between.

**Log reader (`src/state/log_source.py`)**

- Tails `Documents/My Games/Sid Meier's Civilization VI/Logs/Lua.log` (polled every 1 s, which is cheap).
- Ignores lines without the `CIV6ADV|` prefix.
- Detects a new game or loaded save and resets state.

**`GameState` model (`src/state/model.py`)**

```
turn, era, leader, civ, difficulty, map_type, map_size, speed,
current_tech, current_civic, techs_known[], civics_known[],
cities[{name, districts[], buildings[], wonders[]}],
wonders_owned[], wonders_lost[]   # built by another player
yields{science, culture, gold, faith}, victory_progress{}
```

All sources produce this same model.

### 4.6 Vision fallback — `src/state/vision_source.py` (optional, off by default)

Only built if the Lua route fails verification (§8, milestone M0) or leaves a gap.

- `mss` capture of the primary monitor. Native full screen may produce black frames; this is to be tested in M0.
- Crop the UI regions **at native resolution** first, then send only the crops. Never downscale before cropping.
- Crop regions are stored as screen fractions, per resolution and UI-scale profile.
- Model: `qwen2.5vl:3b` via Ollama (`localhost:11434`), JSON output, with a confidence value per field.
- Frames are dropped while a request is still in flight; requests never queue.

### 4.7 HUD — `src/ui/`

- Monitor selection: use any screen that is not `QGuiApplication.primaryScreen()`. If there is only one monitor, use a normal window.
- Pre-game view: Steam sync status, achievement picker with conflict greying and ranking, lobby checklist.
- In-game view (read-only):
  1. Target stack: selected achievements with progress %.
  2. Hero panel: the next action, in large text.
  3. Alerts: failed or at-risk steps.
  4. Icon area: locally cached icons for the current step.
- Background work runs in `QThread`/`QTimer`; no asyncio.

### 4.8 Asset cache — `src/scraper/`

- Optional script that downloads icons from the Civ wiki into `~/.civ6advisor/assets/`.
- Assets are copyrighted (Firaxis/2K). They are **never committed**, and the path is outside the repo.
- The UI must work with no icons present (text fallback).
- Steam achievement icons come from the schema URLs and are cached in the same place.

## 5. Workflows

**Pre-game**

1. First run: enter the Steam API key and SteamID64; sync.
2. Pick targets. Incompatible ones grey out; the ranking suggests additions.
3. Review the lobby checklist: Required / Recommended / Free.
4. Ensure the advisor mod is enabled in Additional Content.
5. Launch Civ VI and set up the lobby per the checklist.

**In-game**

1. The log reader picks up the turn-start snapshot.
2. The engine evaluates playbooks, then the HUD updates the next action, progress and alerts.
3. Each event delta triggers re-evaluation.
4. After the game, re-sync Steam to confirm unlocks.

## 6. Repository layout

```
civ6/
├── .gitignore
├── README.md
├── docs/SPEC.md
├── data/
│   ├── achievements.json
│   └── playbooks/
├── mod/                      # Civ VI UI-only mod (.modinfo + .lua)
├── src/civ6advisor/
│   ├── steam/
│   ├── state/                # model, log_source, vision_source
│   ├── engine/               # batch, playbook evaluation
│   ├── ui/
│   └── scraper/
├── tests/
├── main.py
└── requirements.txt          # PySide6, requests, keyring, pytest
                              # (+ mss, pillow, ollama only if 4.6 is built)
```

## 7. Public repo rules

- Never commit the Steam API key, `.env`, the `.db` file, caches or scraped assets (see `.gitignore`).
- Store the API key with `keyring` only.
- If a key is ever pushed: revoke it on Steam immediately. Deleting the commit is not enough.

## 8. Milestones

Each milestone is usable on its own. Do not start the next one until the acceptance criteria pass.

| # | Deliverable | Acceptance |
|---|---|---|
| M0 | Verification spike | (a) A minimal UI-only mod enabled, and an easy achievement still unlocks. (b) A `print()` from the mod appears in `Lua.log` during play, and the delay before it appears is measured. (c) The Steam API returns the schema and player status for the user's account. **If (a) or (b) fails, revisit §4.5 before continuing.** |
| M1 | Dataset | Schema finalised; all achievements imported from the Steam schema; constraints tagged for the first ~30 targets and marked verified |
| M2 | Pre-game app | Steam sync, picker, conflict greying, ranking, lobby checklist; batching covered by unit tests |
| M3 | Game state | Mod and log reader produce a correct `GameState` over a 20-turn test game |
| M4 | Advisor | Playbooks for one real batch; the HUD shows the next action, progress and alerts during a full game |
| M5 | Polish | Icon cache, HUD layout, optional hotkeys |
| M6 | Vision fallback | Only if M0 or M3 exposed a gap |

## 9. Open questions

1. Does `Lua.log` output require a logging setting in `AppOptions.txt`, and how often is it flushed? (M0)
2. Do any "by turn X" achievements behave differently at Online speed?
3. Which Civ VI event names are available in the UI context for wonders completed by other players? (M0/M3)
4. Which batch is first? This decides which ~30 achievements and which playbooks to write first.
