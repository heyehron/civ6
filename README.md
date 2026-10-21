# Civ VI Achievement Advisor

A local tool for picking Civ VI achievement batches that fit in one game, with the lobby setup each batch needs. See `docs/SPEC.md`.

Status: M1 (dataset draft) and M2 (pre-game app) are done. M0, M3 and M4 (game state and in-game advice) are not started.

## Run

```
pip install -r requirements.txt
python main.py
```

1. Enter your Steam custom URL name or SteamID64 and press **Sync Steam**. Your profile's **Game details** setting must be Public. No API key is needed.
2. Tick target achievements. Any achievement that conflicts turns grey; hover over it to see why. The remaining ones are ranked by score.
3. Use the lobby checklist on the right to set up the game.

Every constraint in `data/achievements.json` is a draft (`verified: false`). Fields listed in `inferred` were guessed rather than read from the achievement text. Check them before relying on them.

## Tests

```
python -m pytest -q
```

## Refreshing the dataset

```
python tools/seed_dataset.py <saved achievements XML>
```

This adds new achievements and refreshes names and descriptions. It never changes existing constraints.
