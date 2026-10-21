# Civ VI Achievement Advisor

A local desktop app that plans Civ VI achievement runs. It tells you which locked achievements fit in one game and the exact lobby setup for them. During play it tracks your progress live from a small UI-only mod and shows the next action on a second monitor. A local AI (Ollama) can answer questions using your own data.

See `docs/SPEC.md` for the design and `docs/BATCH_PLAN.md` for the first plan.

## Install

```
pip install -r requirements.txt
python main.py
```

Python 3.12 or newer.

## First run

1. **Settings → Steam:** enter your custom URL name (e.g. `NobodyYouKnow`) or SteamID64, then press **Save & sync now**. Your profile's *Game details* must be Public. No API key is needed.
2. **Settings → Local AI:** press **Test connection**. The default model is `qwen2.5vl:3b`. Any model you have pulled with Ollama works. For pre-game planning with Civ closed, a bigger text model (e.g. `qwen2.5:7b`) gives better answers.

## Using it

| Page | What to do |
|---|---|
| **Achievements** | Tick targets. Rows that conflict with your batch turn grey; hover to see why. The fit score ranks what pairs well. Click a row to see its requirements: *read* came from the achievement text, *inferred* is a guess. |
| **Batch planner** | Press **Generate** for suggested batches or a non-overlapping *season plan*, then **Use this batch**. The lobby checklist lists every setting as Required, Recommended or Free, and **Copy as text** copies it. |
| **Playbooks** | Step-by-step plans, checked live against the game. 28 are hand-written; every other achievement gets automatic setup checks. **Draft with AI** writes a new one, which is validated before you save it. |
| **In game** | **Connect** to Lua.log, or try **Demo snapshot** first. Tick manual steps when they're done. **Open HUD** puts a read-only panel on your second monitor. |
| **Assistant** | Ask anything. Context toggles decide what the AI sees. *Attach screenshot* sends your primary screen to a vision model. |

Shortcuts: Ctrl+1…6 switch pages, Ctrl+F searches achievements, Ctrl+Enter sends a chat message.

## The game mod (live tracking)

1. Copy `mod/CIV6ADV` into `Documents/My Games/Sid Meier's Civilization VI/Mods/`.
2. In Civ VI, enable **Civ VI Achievement Advisor** under *Additional Content*.
3. Start a game. The mod prints `CIV6ADV|{...}` lines to `Documents/My Games/Sid Meier's Civilization VI/Logs/Lua.log`.

**Not yet tested in game (milestone M0).** Before relying on it, check these:
- An easy achievement still unlocks with the mod enabled.
- `Lua.log` gets `CIV6ADV|` lines during play. If it stays empty, logging may need enabling in `AppOptions.txt` (unverified; SPEC open question 1).
- `warning` lines in the log name any game event the mod could not hook.

## Data

- `data/achievements.json` holds all 320 achievements with draft constraints (`verified: false`). Your edits on the Achievements page are written here.
- `data/playbooks/*.json` are the shared playbooks. Your own edits and AI drafts go to `~/.civ6advisor/playbooks/` unless you tick *Save into repo*.
- `~/.civ6advisor/` holds settings, the Steam cache, icons, saved batches, chat history and manual ticks. None of it is committed.

## Tests

```
python -m pytest -q
```

The mod test runs `CIV6ADV.lua` against a mocked Civ API when `lua5.1` is installed, and is skipped otherwise.

## Refreshing the dataset

```
python tools/seed_dataset.py <saved achievements XML>
```

This adds new achievements and refreshes names and descriptions. It never changes existing constraints.
