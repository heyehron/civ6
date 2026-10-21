"""GameState (SPEC §4.5): one model for every state source.

The Lua mod sends raw game type names (LEADER_TAMAR, MAPSIZE_DUEL, Shuffle.lua, ...).
`GameState.from_snapshot` normalises them to the vocabulary used by
data/achievements.json, and `fields()` exposes a flat dict that playbook
conditions read from.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..engine.batch import DIFFICULTIES

ERAS = ["ancient", "classical", "medieval", "renaissance", "industrial", "modern", "atomic", "information",
        "future"]
AGES = ("normal", "golden", "dark", "heroic")


def _norm_prefixed(value: str | None, prefix: str) -> str | None:
    if not value:
        return None
    v = str(value).upper()
    if v.startswith(prefix):
        v = v[len(prefix):]
    return v.lower()


def norm_map_type(script: str | None) -> str | None:
    if not script:
        return None
    s = re.sub(r"\.lua$", "", str(script).split("/")[-1].split("\\")[-1], flags=re.I)
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", s)  # InlandSea -> Inland_Sea
    return s.replace(" ", "_").lower()


def norm_mode(value: str) -> str:
    v = _norm_prefixed(value, "GAMEMODE_") or ""
    aliases = {
        "dramaticages": "dramatic_ages", "heroes": "heroes_and_legends", "heroesandlegends": "heroes_and_legends",
        "secretsocieties": "secret_societies", "monopolies": "monopolies_and_corporations",
        "barbarianclans": "barbarian_clans", "zombies": "zombie_defense", "zombiedefense": "zombie_defense",
        "apocalypse": "apocalypse", "corporations": "monopolies_and_corporations",
    }
    return aliases.get(v.replace("_", ""), v)


@dataclass
class GameState:
    turn: int = 0
    game_id: str = ""
    era: str | None = None
    start_era: str | None = None
    leader: str | None = None
    civ: str | None = None
    difficulty: str | None = None
    map_type: str | None = None
    map_size: str | None = None
    speed: str | None = None
    game_modes: list[str] = field(default_factory=list)
    current_tech: str | None = None
    current_civic: str | None = None
    techs_known: list[str] = field(default_factory=list)
    civics_known: list[str] = field(default_factory=list)
    government: str | None = None
    policies: list[str] = field(default_factory=list)
    cities: list[dict] = field(default_factory=list)
    wonders_owned: list[str] = field(default_factory=list)
    wonders_lost: list[str] = field(default_factory=list)
    yields: dict[str, float] = field(default_factory=dict)
    balances: dict[str, float] = field(default_factory=dict)
    religion: dict[str, Any] = field(default_factory=dict)
    city_states: list[dict] = field(default_factory=list)
    era_score: int | None = None
    age: str | None = None
    victory_progress: dict[str, Any] = field(default_factory=dict)
    at_war_with: list[str] = field(default_factory=list)
    great_people: list[str] = field(default_factory=list)
    units: dict[str, int] = field(default_factory=dict)
    resources: dict[str, int] = field(default_factory=dict)
    governors: list[dict] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_snapshot(cls, snap: dict) -> "GameState":
        known = {k: v for k, v in snap.items() if k in cls.__dataclass_fields__}
        s = cls(**known)
        s.extra = {k: v for k, v in snap.items() if k not in cls.__dataclass_fields__}
        s.difficulty = _norm_prefixed(s.difficulty, "DIFFICULTY_")
        s.map_size = _norm_prefixed(s.map_size, "MAPSIZE_")
        s.speed = _norm_prefixed(s.speed, "GAMESPEED_")
        s.era = _norm_prefixed(s.era, "ERA_")
        s.start_era = _norm_prefixed(s.start_era, "ERA_")
        s.map_type = norm_map_type(s.map_type)
        s.game_modes = sorted({norm_mode(m) for m in s.game_modes})
        if s.age and s.age.lower() in AGES:
            s.age = s.age.lower()
        return s

    def to_dict(self) -> dict:
        return asdict(self)

    def fields(self) -> dict[str, Any]:
        """Flat dict for playbook conditions, including derived fields."""
        f = {k: v for k, v in asdict(self).items() if k != "extra"}
        f.update(self.extra)
        f["difficulty_level"] = DIFFICULTIES.index(self.difficulty) if self.difficulty in DIFFICULTIES else None
        f["era_index"] = ERAS.index(self.era) if self.era in ERAS else None
        f["cities_count"] = len(self.cities)
        f["total_population"] = sum(int(c.get("population", 0)) for c in self.cities)
        f["districts_all"] = sorted({d for c in self.cities for d in c.get("districts", [])})
        f["buildings_all"] = sorted({b for c in self.cities for b in c.get("buildings", [])})
        f["suzerain_of"] = [cs["name"] for cs in self.city_states if cs.get("suzerain")]
        f["city_states_met"] = [cs["name"] for cs in self.city_states]
        f["city_states_count"] = len(self.city_states)
        my_rel = self.religion.get("type")
        f["city_states_following_my_religion"] = (
            sum(1 for cs in self.city_states if my_rel and cs.get("religion") == my_rel) if my_rel else 0
        )
        f["religion_founded"] = bool(my_rel)
        f["religion_type"] = my_rel
        counts: dict[str, int] = {}
        dcounts: dict[str, int] = {}
        for c in self.cities:
            for b in set(c.get("buildings", [])) | set(c.get("wonders", [])):
                counts[b] = counts.get(b, 0) + 1
            for d in set(c.get("districts", [])):
                dcounts[d] = dcounts.get(d, 0) + 1
        f["building_counts"] = counts
        f["district_counts"] = dcounts
        f["governors_established"] = sum(1 for g in self.governors if g.get("established"))
        f["governors_appointed"] = len(self.governors)
        f["max_city_population"] = max((int(c.get("population", 0)) for c in self.cities), default=0)
        return f


def lookup(fields: dict[str, Any], path: str) -> tuple[bool, Any]:
    """Resolve a dotted path. Returns (found, value)."""
    cur: Any = fields
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


FIELD_CATALOG: dict[str, str] = {
    "turn": "current turn number",
    "era": "current game era (ancient..future)",
    "era_index": "current era as 0-based index",
    "start_era": "start era chosen in the lobby",
    "leader": "your leader id, e.g. LEADER_TAMAR",
    "civ": "your civ id, e.g. CIVILIZATION_GEORGIA",
    "difficulty": "difficulty name, e.g. emperor",
    "difficulty_level": "difficulty as index 0=settler..7=deity",
    "map_type": "map script, e.g. shuffle, island_plates",
    "map_size": "duel/tiny/small/standard/large/huge",
    "speed": "game speed, e.g. online",
    "game_modes": "list of enabled game modes, e.g. dramatic_ages",
    "techs_known": "list of TECH_* ids you have",
    "civics_known": "list of CIVIC_* ids you have",
    "current_tech": "TECH_* being researched",
    "current_civic": "CIVIC_* being progressed",
    "government": "GOVERNMENT_* id",
    "policies": "list of POLICY_* ids slotted",
    "cities": "list of {name, population, districts[], buildings[], wonders[], religion, capital}",
    "cities_count": "number of cities you own",
    "total_population": "sum of city populations",
    "max_city_population": "largest city population",
    "districts_all": "every DISTRICT_* you own in any city",
    "buildings_all": "every BUILDING_* you own in any city",
    "wonders_owned": "list of BUILDING_* wonders you built",
    "wonders_lost": "wonders completed by other players",
    "yields.science": "science per turn (also culture, gold, faith)",
    "balances.gold": "gold in treasury (also faith)",
    "religion.type": "your founded RELIGION_* or null",
    "religion.name": "display name of your religion",
    "religion.majority_cities": "your cities following your religion",
    "religion_founded": "true once you founded a religion",
    "city_states": "list of {name, suzerain, envoys, religion}",
    "city_states_met": "names of city-states met",
    "city_states_count": "number of city-states met",
    "suzerain_of": "names of city-states you are suzerain of",
    "city_states_following_my_religion": "count of city-states whose majority religion is yours",
    "era_score": "your current era score",
    "age": "normal/golden/dark/heroic",
    "victory_progress.religious": "number of civs where your religion is the majority",
    "victory_progress.religious_needed": "civs needed for a religious victory",
    "victory_progress.science": "science victory projects completed",
    "victory_progress.diplomatic": "diplomatic victory points",
    "victory_progress.tourism": "your tourism per turn",
    "victory_progress.domestic_tourists": "largest domestic tourist count among rivals",
    "victory_progress.capitals_held": "original capitals you control",
    "at_war_with": "list of civ ids you are at war with",
    "great_people": "list of great person class ids you have recruited",
    "units": "dict of UNIT_* id -> count, e.g. units.UNIT_MISSIONARY",
    "resources": "dict of RESOURCE_* id -> amount you own, e.g. resources.RESOURCE_SILVER",
    "building_counts": "dict of BUILDING_* id -> number of your cities that have it",
    "district_counts": "dict of DISTRICT_* id -> number of your cities that have it",
    "governors": "list of {type, established, promotions[]}",
    "governors_appointed": "number of governors appointed",
    "governors_established": "number of governors established in a city",
}
