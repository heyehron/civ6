# Civ VI Achievement Advisor — Functional Specification

Status: M1, M2, M4 (app side) and M5 built; M0 and M3 need testing on the user's PC.

## 1. Purpose and scope

A local desktop tool that:

1. Pulls the user's Civ VI achievement status from Steam and hides unlocked ones.
2. Lets the user pick a batch of target achievements and rejects incompatible picks.
3. Produces the exact lobby setup for that batch.
4. During play, reads exact game state from a UI-only Civ VI mod and shows the next action, progress and failure alerts on a second monitor.
5. Offers an optional local AI assistant (Ollama) that answers with the app's own context and drafts playbooks.

Non-goals:

- No cloud LLM calls at runtime. Steam is the only internet call, and its result is cached so the app runs offline afterwards. The AI assistant talks only to a local Ollama server (`localhost`).
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

- Player status: the community XML `steamcommunity.com/{id|profiles}/<profile>/stats/289070/achievements/?xml=1` gives `apiname`, name, description, icon and unlock state, and needs no API key. Always add a unique query parameter, because the endpoint can serve a stale cached copy.
- Optional: if an API key is in the OS credential store (`keyring`, service `civ6advisor`), `GetPlayerAchievements` is used instead.
- Rarity: `ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2?gameid=289070`, which needs no key. The `...ForGame` name returns 404.
- Requires the user's Steam profile **Game details** to be public.
- The profile name or SteamID64 is stored in `~/.civ6advisor/config.json` (not secret).
- All apinames are lowercased; Steam mixes case between endpoints.
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
    "turn_limit":    null,
    "turn_min":      null,
    "requires_win":  false,
    "choices":       {},
    "lobby_required": [],
    "multiplayer":   false,
    "multi_game":    false
  },
  "effort": 1,
  "risk": 1,
  "playbook": "playbooks/ACHIEVEMENT_XYZ.json",
  "verified": false,
  "inferred": [],
  "notes": ""
}
```

Rules:

- `null` or an empty list means unconstrained.
- `turn_min`: the game must end after this turn. Conflicts with a `turn_limit` at or below it.
- `requires_win`: the game must be won. `victory` additionally fixes the victory type.
- `choices`: exclusive in-game picks such as `secret_society`, `religion_name` or `scenario_side`. Two different values for one key conflict.
- `lobby_required`: other lobby settings, such as a city-state pool, a specific AI opponent or a natural wonder.
- `multiplayer: true` is greyed out (out of scope). `multi_game: true` progresses across games.
- `inferred` lists the constraint fields that were inferred rather than read from the description.
- `civ` constraints resolve to leaders through `data/leaders.json`.
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
score = rarity + overlap_gain − risk_penalty
rarity       = ln(100 / global unlock %)
overlap_gain = number of currently selected targets the candidate shares a
               constrained attribute with
risk_penalty = weight × (batch risk after adding − batch risk before)
batch risk   = sum of member risk (default 2 when unset)
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
- Supported ops: `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `contains`, `not_contains`, `count_gte`, `in`, `exists`. String comparison ignores case.
- Conditions combine with `{"all": [...]}`, `{"any": [...]}` and `{"not": cond}`. `field` is a dotted path into `GameState.fields()` (for example `yields.faith` or `building_counts.BUILDING_SHOPPING_MALL`).
- A missing field means "cannot track yet", never "failed".
- `"manual": true` steps are ticked by the user on the In-game page. Ticks are stored per game in `~/.civ6advisor/progress.json`.
- Optional step keys: `detail` (how-to text) and `final` (closing step; `win`, `goal`, `check`, `verify` and `confirm` ids are final automatically).
- Progress = completed steps / total steps.
- Next action = the first open non-final step across all targets, ordered by the nearest deadline. Manual `lobby*`/`setup*` steps stop being candidates after turn 3.
- Alert when a `fail_when` fires, or when the turn passes `deadline_turn − 5` with the step unfinished.
- Top-level keys: `title`, `summary`, `tips[]`, `author` (`hand`, `auto` or `ai-draft`) and `verified`.
- Sources, in override order: automatic setup checks built from the constraints → `data/playbooks/` (committed) → `~/.civ6advisor/playbooks/` (the user's edits and AI drafts).
- AI drafts are always saved with `author: ai-draft` and `verified: false`.

### 4.5 Game state — `mod/` and `src/state/`

**Lua mod (`mod/`)**

- UI context only (`AffectsSavedGames=0`), so it does not change gameplay.
- Hooks game events: turn start, tech and civic changes, city founded, district and wonder completed (any player), era change.
- On each event, writes one line through `print()`: `CIV6ADV|{json}`. A small JSON serialiser is included in the mod because Civ's Lua has none.
- Writes a full snapshot at turn start and after each hooked event (debounced to one per frame). Lines carry `kind`: `snapshot`, `delta` (merged onto the last snapshot; the reader supports it, the mod does not send it yet), `hello` or `warning`.
- Each API section is wrapped in `pcall`, so an API difference drops one field instead of breaking the export. Missing events are reported as `warning` lines.
- Raw game names (`LEADER_TAMAR`, `MAPSIZE_DUEL`, `Shuffle.lua`) are normalised by `GameState.from_snapshot`.

**Log reader (`src/state/log_source.py`)**

- Tails `Documents/My Games/Sid Meier's Civilization VI/Logs/Lua.log` (polled every 1 s, which is cheap).
- Ignores lines without the `CIV6ADV|` prefix.
- Detects a new game or loaded save and resets state.

**`GameState` model (`src/state/model.py`)**

```
turn, game_id, era, start_era, leader, civ, difficulty, map_type, map_size, speed, game_modes[],
current_tech, current_civic, techs_known[], civics_known[], government, policies[],
cities[{name, capital, population, districts[], buildings[], wonders[], religion}],
wonders_owned[], wonders_lost[]   # built by another player
yields{science, culture, gold, faith}, balances{gold, faith},
religion{type, name, majority_cities}, city_states[{name, suzerain, envoys, religion}],
era_score, age, victory_progress{religious, religious_needed, diplomatic, tourism, capitals_held},
at_war_with[], great_people[], units{}, resources{}, governors[{type, established}]
```

Derived fields for playbooks: `difficulty_level`, `era_index`, `cities_count`, `total_population`,
`max_city_population`, `districts_all`, `buildings_all`, `building_counts`, `district_counts`,
`suzerain_of`, `city_states_met`, `city_states_count`, `city_states_following_my_religion`,
`religion_founded`, `governors_appointed`, `governors_established`. The full list with descriptions is
`FIELD_CATALOG` in `src/civ6advisor/state/model.py`.

All sources produce this same model.

### 4.6 Vision fallback — `src/state/vision_source.py` (optional, off by default)

Only built if the Lua route fails verification (§8, milestone M0) or leaves a gap.

- `mss` capture of the primary monitor. Native full screen may produce black frames; this is to be tested in M0.
- Crop the UI regions **at native resolution** first, then send only the crops. Never downscale before cropping.
- Crop regions are stored as screen fractions, per resolution and UI-scale profile.
- Model: `qwen2.5vl:3b` via Ollama (`localhost:11434`), JSON output, with a confidence value per field.
- Frames are dropped while a request is still in flight; requests never queue.

### 4.7 App and HUD — `src/ui/`

Pages (sidebar, Ctrl+1…6):

| Page | Contents |
|---|---|
| Achievements | Filterable table with icons, rarity and fit score; conflict greying with reasons; detail panel showing read/inferred constraints; edit effort, risk, verified and notes (written back to `data/achievements.json`) |
| Batch planner | Current targets, Required/Recommended/Free checklist (copy as text), suggested batches, season plan with no overlap, saved batches |
| Playbooks | List per batch / written / all locked; JSON editor with live validation and rendered preview; AI draft and AI improve |
| In game | Source (live Lua.log, demo snapshot, file); next action; per-target step tree with manual ticks; alerts; game-state summary |
| Assistant | Streaming local AI chat; context toggles (batch, game state, playbook progress, focused achievement); quick prompts; optional screenshot |
| Settings | Steam profile and optional API key (keyring), Lua.log path, Ollama server/model/temperature, planner weights, HUD monitor and opacity |

- HUD monitor selection: use any screen that is not `QGuiApplication.primaryScreen()`. If there is only one monitor, use a normal window.
- In-game HUD (read-only):
  1. Target stack: selected achievements with progress %.
  2. Hero panel: the next action, in large text.
  3. Alerts: failed or at-risk steps.
  4. Icon area: locally cached icons for the current step.
- Background work runs in `QThread`/`QTimer`; no asyncio.

### 4.8 Batch planner — `src/engine/planner.py`

- For each anchor (a leader-win achievement, a leader with 2+ feats, or a game mode), it greedily adds compatible achievements: win conditions first, then that leader's feats, then feats for modes already on.
- It respects the user's highest difficulty and skips additions that raise a plausibility warning (for example a late start era with a religious victory).
- Value = Σ ln(100 / global %) ÷ effort. **Effort is a heuristic** from difficulty, victory type, map size, feat count, modes, lobby requirements and user risk.
- *Best next game* re-ranks for diversity. *Season plan* repeatedly takes the best batch and removes its achievements.

### 4.9 Local AI — `src/ai/`

- `OllamaClient` streams `/api/chat`. `ChatRunner` runs it on a `QThread`, so the UI never blocks.
- The system prompt states Online speed, Gathering Storm rules, and that draft or inferred constraints are unverified. Context is built from the app's own data (`prompts.py`).
- Playbook drafting uses Ollama JSON mode. The reply is parsed (`extract_json`) and validated before it reaches the editor, and nothing is saved without the user pressing Save.
- Screenshot questions grab the primary screen with Qt and need a vision model (`qwen2.5vl:3b`).

### 4.10 Asset cache

- Steam achievement icons are downloaded on first display into `~/.civ6advisor/assets/icons/`. A wiki icon scraper (`src/scraper/`) is not built.
- Assets are copyrighted (Firaxis/2K). They are **never committed**, and the path is outside the repo.
- The UI must work with no icons present (text fallback).
- Steam achievement icons come from the schema URLs and are cached in the same place.

## 5. Workflows

**Pre-game**

1. First run: enter the Steam profile (custom URL name or SteamID64) and sync. An API key is optional.
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
│   ├── leaders.json
│   └── demo/                 # sample snapshot for testing playbooks
├── mod/CIV6ADV/              # Civ VI UI-only mod (.modinfo + UI/*.xml, *.lua)
├── src/civ6advisor/
│   ├── steam/                # sync + cache
│   ├── state/                # model, log_source (vision_source not built)
│   ├── engine/               # batch, planner, playbook
│   ├── ai/                   # ollama client, prompts, Qt worker
│   └── ui/                   # theme, widgets, pages/, hud
├── tools/seed_dataset.py
├── tests/                    # incl. Lua mod run against a mocked Civ API (needs lua5.1)
├── main.py
└── requirements.txt          # PySide6, requests, keyring, pytest
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

Current status: M0: mod written, not yet tested in game. M1: 320 entries drafted, none verified. M2: done. M3: reader and model done, the mod runs against a mocked API in tests; real-game test pending. M4: 28 hand playbooks plus auto setup checks; Batch A covered. M5: icons, HUD and theme done; hotkeys not built.

## 9. Open questions

1. Does `Lua.log` output require a logging setting in `AppOptions.txt`, and how often is it flushed? (M0)
2. Do any "by turn X" achievements behave differently at Online speed?
3. Which Civ VI event names are available in the UI context for wonders completed by other players? (M0/M3)
4. Which batch is first? This decides which ~30 achievements and which playbooks to write first.
