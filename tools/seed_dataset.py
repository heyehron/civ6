"""Seed or refresh data/achievements.json from a Steam community achievements XML.

Usage: python tools/seed_dataset.py <achievements.xml>

Constraints are drafted from the description text plus the OVERRIDES table
below. Existing entries keep their constraints, effort, risk, verified flag and
notes; only name, description and icon are refreshed. New achievements are
added with verified = false.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "achievements.json"
LEADERS = json.loads((ROOT / "data" / "leaders.json").read_text(encoding="utf-8"))["leaders"]

SIZES = ["duel", "tiny", "small", "standard", "large", "huge"]
ERAS = ["ancient", "classical", "medieval", "renaissance", "industrial", "modern", "atomic", "information"]
DIFFICULTIES = ["settler", "chieftain", "warlord", "prince", "king", "emperor", "immortal", "deity"]

SCENARIOS = {
    "Red Death": "red_death",
    "Pirates": "pirates",
    "Outback Tycoon": "outback_tycoon",
    "Jadwiga's Legacy": "jadwigas_legacy",
    "Conquests of Alexander": "conquests_of_alexander",
    "Gifts of the Nile": "gifts_of_the_nile",
    "Path to Nirvana": "paths_to_nirvana",
    "Paths to Nirvana": "paths_to_nirvana",
    "Black Death": "black_death",
    "War Machine": "war_machine",
    "Vikings, Traders, and Raiders!": "vikings_traders_raiders",
}
PREFIX_SCENARIO = {"rd2_": "red_death", "royale_": "red_death", "arr_": "pirates"}
MAP_TYPES = {
    "continents", "pangaea", "fractal", "island_plates", "inland_sea", "shuffle", "archipelago",
    "small_continents", "seven_seas", "tilted_axis", "lakes", "primordial", "splintered_fractal", "terra",
}

CIVS = {
    "america": "CIVILIZATION_AMERICA", "australia": "CIVILIZATION_AUSTRALIA", "aztecs": "CIVILIZATION_AZTEC",
    "babylon": "CIVILIZATION_BABYLON_STK", "brazil": "CIVILIZATION_BRAZIL", "byzantium": "CIVILIZATION_BYZANTIUM",
    "china": "CIVILIZATION_CHINA", "egypt": "CIVILIZATION_EGYPT", "england": "CIVILIZATION_ENGLAND",
    "france": "CIVILIZATION_FRANCE", "gaul": "CIVILIZATION_GAUL", "georgia": "CIVILIZATION_GEORGIA",
    "germany": "CIVILIZATION_GERMANY", "greece": "CIVILIZATION_GREECE", "hungary": "CIVILIZATION_HUNGARY",
    "india": "CIVILIZATION_INDIA", "indonesia": "CIVILIZATION_INDONESIA", "japan": "CIVILIZATION_JAPAN",
    "kongo": "CIVILIZATION_KONGO", "macedon": "CIVILIZATION_MACEDON", "maori": "CIVILIZATION_MAORI",
    "maya": "CIVILIZATION_MAYA", "nubia": "CIVILIZATION_NUBIA", "ottomans": "CIVILIZATION_OTTOMAN",
    "persia": "CIVILIZATION_PERSIA", "poland": "CIVILIZATION_POLAND", "portugal": "CIVILIZATION_PORTUGAL",
    "rome": "CIVILIZATION_ROME", "russia": "CIVILIZATION_RUSSIA", "scythia": "CIVILIZATION_SCYTHIA",
    "spain": "CIVILIZATION_SPAIN", "sumeria": "CIVILIZATION_SUMERIA", "sweden": "CIVILIZATION_SWEDEN",
}


def _leader_aliases() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for lid, info in LEADERS.items():
        base = re.sub(r"\s*\(.*\)", "", info["name"]).lower()
        out.setdefault(base, []).append(lid)
    extra = {
        "theodore roosevelt": "teddy roosevelt", "teddy": "teddy roosevelt", "suleiman the magnificent": "suleiman",
        "queen seondeok": "seondeok", "queen wilhelmina": "wilhelmina", "genghis": "genghis khan",
        "eleanor": "eleanor of aquitaine", "harald hardrada": "harald hardrada",
    }
    for alias, target in extra.items():
        out[alias] = out[target]
    return out


ALIASES = _leader_aliases()


def _match_prefix(text: str, table: dict) -> str | None:
    text = text.lower()
    best = None
    for key in table:
        if text.startswith(key) and (len(text) == len(key) or not text[len(key)].isalpha()):
            if best is None or len(key) > len(best):
                best = key
    return best


def content_of(api: str) -> str:
    a = api.lower()
    if a.startswith(("rd2_", "royale_", "arr_")):
        return "scenario"
    if a.startswith("raf_"):
        return "rise_and_fall"
    if a.startswith("vsv_"):
        return "gathering_storm"
    if a.startswith(("stk", "neb_")):
        return "new_frontier"
    if a.startswith("dlc"):
        return "leader_pack"
    return "base"


def empty_constraints() -> dict:
    return {
        "leader": None, "civ": None, "victory": None,
        "difficulty_min": None, "difficulty_max": None,
        "map_type": None, "map_size": None, "start_era": None, "ruleset": None,
        "game_modes_required": [], "game_modes_forbidden": [],
        "scenario": None, "turn_limit": None, "turn_min": None,
        "requires_win": False, "choices": {}, "lobby_required": [],
        "multiplayer": False, "multi_game": False,
    }


def draft(api: str, desc: str) -> tuple[dict, list[str]]:
    """Return (constraints, inferred_fields) read from the description text."""
    c = empty_constraints()
    inferred: list[str] = []
    d = desc.strip()
    low = d.lower()

    if re.match(r"win\b", low) or " win " in f" {low} ":
        c["requires_win"] = True
    if "multiplayer" in low:
        c["multiplayer"] = True
    if "across multiple games" in low:
        c["multi_game"] = True

    for name, sid in SCENARIOS.items():
        if name.lower() in low:
            c["scenario"] = sid
    for prefix, sid in PREFIX_SCENARIO.items():
        if api.lower().startswith(prefix):
            c["scenario"] = sid
    if c["scenario"]:
        m = re.match(r"^([A-Z][\w ]+?) - ", d)
        if m:
            c["choices"]["scenario_side"] = m.group(1).strip()
        m = re.search(r"\b[Aa]s (?:the )?([A-Z][^,.]+?)(?:,|\.|$| on | at | using | within )", d)
        if m:
            c["choices"]["scenario_side"] = m.group(1).strip()

    m = re.search(r"(?:at|on) (\w+)(?: difficulty|$)", d, re.I)
    if m and m.group(1).lower() in DIFFICULTIES:
        c["difficulty_min"] = m.group(1).lower()

    m = re.search(r"with an? (\w+) era start", low)
    if m and m.group(1) in ERAS:
        c["start_era"] = [m.group(1)]

    m = re.search(r"\bon (?:the |a )?([\w ]+?) map\b", low)
    if m:
        words = m.group(1).split()
        sizes = [w for w in words if w in SIZES]
        if sizes:
            c["map_size"] = [sizes[0]]
        rest = "_".join(w for w in words if w not in SIZES)
        if rest in MAP_TYPES:
            c["map_type"] = [rest]
    if "standard sized map or larger" in low:
        c["map_size"] = ["standard", "large", "huge"]

    m = re.search(r"with an? (science|culture|cultural|domination|religious|diplomatic) victory", low)
    if m:
        c["victory"] = ["culture" if m.group(1) == "cultural" else m.group(1)]
    elif re.search(r"win an? (diplomatic|cultural|culture) victory$", low):
        v = re.search(r"win an? (\w+) victory$", low).group(1)
        c["victory"] = ["culture" if v == "cultural" else v]

    m = re.search(r"win a (?:regular )?game as (.+?)\.?$", d, re.I)
    if m and not c["scenario"]:
        key = _match_prefix(m.group(1), ALIASES)
        if key:
            c["leader"] = sorted(ALIASES[key])
    else:
        m = re.search(r"\b(?:[Pp]laying as|[Aa]s) (?:the )?([A-Z].*)$", d)
        if m and not c["scenario"]:
            key = _match_prefix(m.group(1), ALIASES)
            civ = _match_prefix(m.group(1), CIVS)
            if civ and (not key or len(civ) >= len(key)):
                c["civ"] = [CIVS[civ]]
            elif key:
                c["leader"] = sorted(ALIASES[key])

    if "dramatic age" in low:
        c["game_modes_required"].append("dramatic_ages")
    if re.search(r"\bheroe?s?\b", low) and not c["scenario"]:
        c["game_modes_required"].append("heroes_and_legends")
    if "barbarian clan" in low:
        c["game_modes_required"].append("barbarian_clans")
    if "zombie" in low and not c["scenario"]:
        c["game_modes_required"].append("zombie_defense")
    if "apocalypse" in low:
        c["game_modes_required"].append("apocalypse")
    if re.search(r"monopol|industries|corporation", low):
        c["game_modes_required"].append("monopolies_and_corporations")
    m = re.search(r"for the ([\w ]+?) secret society", low)
    if m:
        c["game_modes_required"].append("secret_societies")
        c["choices"]["secret_society"] = m.group(1).replace(" ", "_")
    if "8 or more players" in low:
        c["lobby_required"].append({"setting": "Players", "value": "8 or more"})

    m = re.search(r"within (?:the first )?(\w+) turns$", low)
    if m and c["scenario"]:
        n = {"ten": 10}.get(m.group(1), m.group(1))
        c["turn_limit"] = int(n)
    m = re.search(r"after turn (\d+)", low)
    if m:
        c["turn_min"] = int(m.group(1))

    if c["scenario"]:
        c["ruleset"] = None
    return c, inferred


def cs(name: str) -> dict:
    return {"setting": "City-state pool", "value": f"include {name}"}


def ai(name: str) -> dict:
    return {"setting": "AI opponent", "value": name}


def nw(name: str) -> dict:
    return {"setting": "Natural wonder", "value": f"{name} on the map"}


# api -> (constraint updates, inferred field names, note). Lists replace drafted values.
OVERRIDES: dict[str, tuple[dict, list[str], str]] = {
    "new_achievement_3_0": ({"lobby_required": [cs("Hattusa")]}, [], ""),
    "new_achievement_3_1": ({"lobby_required": [cs("La Venta")]}, ["lobby_required"],
                            "Colossal Head is assumed to be La Venta's suzerain improvement."),
    "new_achievement_3_2": ({"lobby_required": [cs("Nan Madol")]}, [], ""),
    "new_achievement_3_4": ({"civ": ["CIVILIZATION_ARABIA"]}, ["civ"], "Mamluk is Arabia's unique unit."),
    "new_achievement_3_5": ({"civ": ["CIVILIZATION_AZTEC"], "map_size": ["standard"]}, ["map_size"],
                            "Unclear whether larger maps also count."),
    "new_achievement_3_10": ({"map_size": ["huge"]}, [], ""),
    "new_achievement_3_11": ({"civ": ["CIVILIZATION_FRANCE"]}, ["civ"], "Chateau is France's unique improvement."),
    "new_achievement_3_12": ({"lobby_required": [cs("Jerusalem")]}, [], ""),
    "new_achievement_3_14": ({"civ": ["CIVILIZATION_INDIA"], "map_size": ["huge"]}, [], ""),
    "new_achievement_3_17": ({"civ": ["CIVILIZATION_NORWAY"]}, ["civ"], "Viking Longship is Norway's unique unit."),
    "new_achievement_3_18": ({"civ": ["CIVILIZATION_ROME"]}, ["civ"], "Legion is Rome's unique unit."),
    "new_achievement_3_20": ({"civ": ["CIVILIZATION_SCYTHIA"]}, [], ""),
    "new_achievement_3_23": ({"lobby_required": [nw("Galapagos Islands")]}, ["lobby_required"],
                             "Natural wonder picker availability unverified."),
    "new_achievement_3_3": ({"civ": ["CIVILIZATION_AMERICA"], "lobby_required": [nw("Crater Lake"), nw("Yosemite")]},
                            ["lobby_required"], "Natural wonder picker availability unverified."),
    "new_achievement_4_4": ({"map_type": ["fractal"]}, [], ""),
    "new_achievement_4_7": ({}, [], "Continent names are random; 'Nena' must exist. Needs a bomber and nukes."),
    "new_achievement_4_8": ({"civ": ["CIVILIZATION_AMERICA"]}, ["civ"], "New York is an American city name."),
    "new_achievement_4_24": ({"victory": ["science"], "lobby_required": [ai("Egypt (any leader)")]},
                             ["lobby_required"], "Needs a captured Egyptian city."),
    "new_achievement_4_25": ({"victory": ["religious"], "lobby_required": [cs("Zanzibar")],
                              "choices": {"religion_name": "zoroastrianism"}}, [],
                             "City-state picker sets a pool, not a guarantee: select only Zanzibar."),
    "new_achievement_4_26": ({"victory": ["culture"], "lobby_required": [
                                {"setting": "Duplicate leaders", "value": "allowed; your leader also as an AI"}]},
                             ["lobby_required"], "Duplicate-leader lobby option is inferred."),
    "new_achievement_4_27": ({"victory": ["domination"], "map_size": ["huge"], "map_type": ["island_plates"]}, [], ""),
    "dlc1_achievement_01": ({"lobby_required": [cs("Granada")]}, ["lobby_required"],
                            "Alcazar assumed to be Granada's improvement; Alhambra is a wonder."),
    "dlc1_achievement_02": ({"lobby_required": [cs("Armagh"), nw("Giant's Causeway")]}, ["lobby_required"],
                            "Monastery assumed to be Armagh's improvement."),
    "dlc1_achievement_03": ({"lobby_required": [nw("Eyjafjallajokull")]}, ["lobby_required"], ""),
    "dlc2_achievement_02": ({"civ": ["CIVILIZATION_POLAND"]}, [], ""),
    "dlc3_achievement_02": ({"civ": ["CIVILIZATION_AUSTRALIA"]}, [], ""),
    "dlc4_achievement_03": ({"civ": ["CIVILIZATION_MACEDON"]}, [], ""),
    "dlc4_achievement_04": ({"civ": ["CIVILIZATION_PERSIA"], "lobby_required": [ai("Scythia")]}, [], ""),
    "dlc4_achievement_10": ({"civ": ["CIVILIZATION_SCYTHIA"], "lobby_required": [ai("Persia")]}, [], ""),
    "dlc5_achievement_3": ({"civ": ["CIVILIZATION_EGYPT"], "lobby_required": [ai("Nubia")]}, [], ""),
    "dlc5_achievement_4": ({"civ": ["CIVILIZATION_NUBIA"], "lobby_required": [ai("Egypt"), ai("a civ that conquers Egypt's capital")]},
                           ["lobby_required"], ""),
    "dlc6_achievement_06": ({"civ": ["CIVILIZATION_INDONESIA"]}, [], ""),
    "raf_achievement_11": ({"lobby_required": [ai("Philip II (Spain)")]}, [], ""),
    "raf_achievement_12": ({"victory": ["culture"]}, [], ""),
    "raf_achievement_14": ({}, [], "Needs an AI to beat you to a wonder."),
    "raf_achievement_17": ({"leader": ["LEADER_SEONDEOK"]}, [], ""),
    "raf_achievement_18": ({"leader": ["LEADER_SHAKA"]}, [], ""),
    "raf_achievement_21": ({}, [], "Must happen before the Industrial Era, so a late start era likely breaks it."),
    "raf_achievement_25": ({"lobby_required": [ai("Gilgamesh")]}, [], ""),
    "raf_achievement_27": ({"lobby_required": [nw("Great Barrier Reef")]}, ["lobby_required"], ""),
    "raf_achievement_33": ({"requires_win": True}, [], ""),
    "stk3_achievement_03": ({"civ": ["CIVILIZATION_BYZANTIUM"], "lobby_required": [ai("Rome")]}, [], ""),
    "stk2_achievement_02": ({"civ": ["CIVILIZATION_ETHIOPIA"]}, ["civ"], "Oromo Cavalry is Ethiopia's unique unit."),
    "stk3_achievement_04": ({"civ": ["CIVILIZATION_GAUL"]}, [], ""),
    "stk3_achievement_07": ({"civ": ["CIVILIZATION_GEORGIA"]}, [], ""),
    "stk1_achievement_04": ({"leader": ["LEADER_SIMON_BOLIVAR"]}, [], ""),
    "stk1_achievement_05": ({"requires_win": True}, [], ""),
    "stk1_achievement_06": ({"game_modes_required": ["apocalypse"]}, ["game_modes_required"],
                            "Comets fall in Apocalypse mode."),
    "stk1_achievement_07": ({"game_modes_required": ["apocalypse"]}, ["game_modes_required"],
                            "Soothsayer is an Apocalypse-mode unit."),
    "stk4_achievement_03": ({"multi_game": True}, [], ""),
    "stk6_achievement_02": ({"civ": ["CIVILIZATION_PORTUGAL"], "lobby_required": [ai("Brazil"), ai("India"), ai("Japan")]}, [], ""),
    "stk6_achievement_04": ({"game_modes_required": ["zombie_defense"]}, [], ""),
    "stk6_achievement_05": ({"game_modes_required": ["zombie_defense"]}, ["game_modes_required"],
                            "Traps assumed to be Zombie Defense mode."),
    "vsv_achievement_11": ({"civ": ["CIVILIZATION_RUSSIA"], "lobby_required": [ai("Canada")]}, ["lobby_required"],
                           "Ice Hockey Rink is Canada's improvement."),
    "vsv_achievement_17": ({"lobby_required": [ai("Maori (or play as Maori)")]}, ["lobby_required"], ""),
    "vsv_achievement_18": ({}, [], "Needs Stonehenge on a coastal lowland tile and climate change."),
    "vsv_achievement_20": ({}, [], "Nobel Prizes are World Congress special sessions; random."),
    "vsv_achievement_21": ({"requires_win": False, "victory": None}, [],
                           "A World Congress resolution, not a game win. Diplomatic victory must be enabled."),
    "vsv_achievement_25": ({"civ": ["CIVILIZATION_MAORI"], "lobby_required": [nw("Ngauruhoe")]}, ["lobby_required"], ""),
    "vsv_achievement_30": ({"leader": sorted(ALIASES["eleanor of aquitaine"]),
                            "lobby_required": [ai("Eleanor of Aquitaine (duplicate leaders allowed)")]},
                           ["lobby_required"], ""),
    "vsv_achievement_34": ({"civ": ["CIVILIZATION_ROME"], "lobby_required": [nw("Vesuvius")]}, ["lobby_required"], ""),
    "vsv_achievement_50": ({"lobby_required": [ai("America (city named Cleveland)")]}, ["lobby_required"],
                           "Cleveland is an American city name."),
    "vsv_achievement_26": ({"lobby_required": [cs("Mecca")]}, [], ""),
    "dlc3_achievement_08": ({"multiplayer": True}, [], ""),
    "rd2_achievement_04": ({"multi_game": True}, ["multi_game"], ""),
}


def main(xml_path: str) -> None:
    root = ET.parse(xml_path).getroot()
    existing = {}
    if DATA.exists():
        existing = {a["id"]: a for a in json.loads(DATA.read_text(encoding="utf-8"))["achievements"]}
    out = []
    for node in root.iter("achievement"):
        api = node.findtext("apiname").strip()
        name = (node.findtext("name") or "").strip()
        desc = (node.findtext("description") or "").strip()
        icon = (node.findtext("iconClosed") or "").strip()
        if api in existing:
            entry = existing[api]
            entry.update(name=name, description=desc, icon=icon)
            out.append(entry)
            continue
        cons, inferred = draft(api, desc)
        note = ""
        if api in OVERRIDES:
            upd, inf, note = OVERRIDES[api]
            cons.update(upd)
            inferred += inf
        out.append({
            "id": api, "name": name, "description": desc, "icon": icon,
            "content": content_of(api), "constraints": cons,
            "effort": None, "risk": None, "playbook": None,
            "verified": False, "inferred": inferred, "notes": note,
        })
    DATA.write_text(json.dumps({"version": 1, "achievements": out}, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(f"{len(out)} achievements written to {DATA}")


if __name__ == "__main__":
    main(sys.argv[1])
