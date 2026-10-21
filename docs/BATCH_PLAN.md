# Achievement batch plan

Snapshot: 2026-10-21, 67 / 320 unlocked, 253 locked. Rarity comes from
`ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2`. The method name
`...ForGame` now returns 404.

Scope: regular single-player games at Online speed, with all DLC. Scenarios
(68) and multiplayer are out of scope.

## Ranking

`score = Σ ln(100 / global%) / D`

`D` is a 1–5 difficulty estimate for a player who has won at King. **Every D
value is unverified.**

| # | Batch | Core | Score | + stretch |
|---|---|---|---|---|
| A | Tamar religious, Shuffle / Duel, Emperor | 8 | 11.4 | 14.7 |
| A′ | A at Deity | 10 | 8.4 | 10.5 |
| D | Hammurabi, Heroes + Barbarian Clans, Fractal | 6 | 6.8 | 13.2 |
| B | Elizabeth I domination, Huge Island Plates | 6 | 5.6 | 7.7 |
| C | Laurier diplomatic, Archipelago | 5 | 5.4 | 6.5 |
| E | Kristina Selfie culture, Tiny | 4 | 5.2 | 7.0 |
| F | Mansa Musa, Atomic start | 3 | 4.7 | 4.7 |

No two batches share a map type, map size, start era or leader.

## Batch A lobby checklist

Targets:

| Role | Achievements |
|---|---|
| Core | Emperor's New Groove, Riffle and Bridge, Here's Looking At You Kid, After Antiquity, Radiant Deeds Bright as Sunshine, We Are The Champions, Holy Righteous Queen Tamar, The City Ever-Shining |
| Stretch | No Light Without the Dark, Dark Horse |

| Setting | Value | Label | Source |
|---|---|---|---|
| Leader | Tamar (Georgia) | Required | Radiant Deeds, Holy Righteous Queen Tamar, No Light Without the Dark (description) |
| Difficulty | Emperor | Required | Emperor's New Groove (description) |
| Map type | Shuffle | Required | Riffle and Bridge (description) |
| Map size | Duel | Required | Here's Looking At You Kid (description) |
| Start era | Classical | Required | After Antiquity (description) |
| Game mode | Dramatic Ages on | Required | The City Ever-Shining, No Light Without the Dark (description) |
| Victory | Religious | Required | We Are The Champions (description) |
| Other victory types | Off | Recommended | Stops an accidental non-religious win (community guide) |
| City-state picker | Zanzibar only | Required | We Are The Champions. The picker is a pool and not a guarantee (Dec 2020 patch notes), so a pool of one is the only way to force Zanzibar |
| City-state count | 1 | Recommended | With one city-state, Holy Righteous Queen Tamar only needs Zanzibar to convert. **Unverified:** a city-state can fail to spawn when placement is tight |
| AI opponent | Not Saladin (Arabia), not a religion-focused civ | Recommended | Arabia reserves a Great Prophet (wiki). Duel allows 2 religions (wiki), so with any other opponent you do not have to race for a prophet |
| Religion name | Zoroastrianism | Required | We Are The Champions (description) |
| Speed | Online | Fixed | SPEC §2 |
| Barbarians | Free | Free | — |

### Restart checks (all unverified)

Restarts are cheap only in the first turns, so check these early.

1. **Turns 1–15.** Zanzibar exists on the map. If it doesn't, restart.
2. **Religion founding.** If the AI takes the Zoroastrianism name before you,
   restart. It is unverified whether a custom name on a different religion
   type would count.
3. **Before the win.** You are suzerain of Zanzibar and Zoroastrianism is your
   dominant religion.
4. **Dark Horse (stretch).** With Dramatic Ages on, time the final conversion
   during a Dark Age.

### Inferred, not read (unverified)

- A Classical start does not block founding a pantheon or religion.
- Dramatic Ages works with a Classical start and a Duel map.
- The Shuffle map script runs on Duel size.
- Online speed has no effect on these targets, since none has a turn limit
  (SPEC open question 2).
