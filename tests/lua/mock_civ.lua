-- Minimal mock of the Civ VI UI Lua API, enough to run CIV6ADV.lua outside the game.
local function gameTable(rows, key)
  local t = {}
  for i, r in ipairs(rows) do r.Index = i - 1; t[i - 1] = r; t[r[key]] = r end
  setmetatable(t, { __call = function()
    local i = -1
    return function() i = i + 1; return rows[i + 1] end
  end })
  return t
end

GameInfo = {
  Difficulties = gameTable({ { DifficultyType = "DIFFICULTY_PRINCE" }, { DifficultyType = "DIFFICULTY_EMPEROR" } }, "DifficultyType"),
  GameSpeeds = gameTable({ { GameSpeedType = "GAMESPEED_ONLINE" } }, "GameSpeedType"),
  Eras = gameTable({ { EraType = "ERA_ANCIENT" }, { EraType = "ERA_CLASSICAL" } }, "EraType"),
  Maps = gameTable({ { MapSizeType = "MAPSIZE_DUEL" } }, "MapSizeType"),
  Technologies = gameTable({ { TechnologyType = "TECH_POTTERY" }, { TechnologyType = "TECH_ASTROLOGY" } }, "TechnologyType"),
  Civics = gameTable({ { CivicType = "CIVIC_CODE_OF_LAWS" } }, "CivicType"),
  Governments = gameTable({ { GovernmentType = "GOVERNMENT_CHIEFDOM" } }, "GovernmentType"),
  Policies = gameTable({ { PolicyType = "POLICY_GOD_KING" } }, "PolicyType"),
  Districts = gameTable({ { DistrictType = "DISTRICT_CITY_CENTER" }, { DistrictType = "DISTRICT_HOLY_SITE" } }, "DistrictType"),
  Buildings = gameTable({ { BuildingType = "BUILDING_SHRINE", IsWonder = false }, { BuildingType = "BUILDING_STONEHENGE", IsWonder = true } }, "BuildingType"),
  Religions = gameTable({ { ReligionType = "RELIGION_PANTHEON", Name = "Pantheon" }, { ReligionType = "RELIGION_ZOROASTRIANISM", Name = "Zoroastrianism" } }, "ReligionType"),
  Resources = gameTable({ { ResourceType = "RESOURCE_SILVER" } }, "ResourceType"),
  Units = gameTable({ { UnitType = "UNIT_BUILDER" } }, "UnitType"),
  Governors = gameTable({ { GovernorType = "GOVERNOR_THE_EDUCATOR" } }, "GovernorType"),
  GameModeItems = gameTable({ { GameModeType = "GAMEMODE_DRAMATICAGES" } }, "GameModeType"),
}

local function members(list)
  return function() local i = 0; return function() i = i + 1; if list[i] then return i, list[i] end end end
end

local city = {
  GetName = function() return "LOC_CITY_TBILISI" end, GetPopulation = function() return 5 end,
  IsCapital = function() return true end, IsOriginalCapital = function() return true end,
  GetOwner = function() return 0 end,
  GetDistricts = function() return { Members = members({ { GetType = function() return 1 end, IsComplete = function() return true end } }) } end,
  GetBuildings = function() return { HasBuilding = function(_, i) return true end, IsPillaged = function() return false end } end,
  GetReligion = function() return { GetMajorityReligion = function() return 1 end } end,
}

local player = {
  GetCities = function() return { Members = members({ city }), GetCapitalCity = function() return city end } end,
  GetTechs = function() return { HasTech = function(_, i) return i == 1 end, GetResearchingTech = function() return 0 end,
                                 GetScienceYield = function() return 12.5 end } end,
  GetCulture = function() return { HasCivic = function() return true end, GetProgressingCivic = function() return 0 end,
                                   GetCurrentGovernment = function() return 0 end, GetNumPolicySlots = function() return 1 end,
                                   GetSlotPolicy = function() return 0 end, GetCultureYield = function() return 7 end } end,
  GetTreasury = function() return { GetGoldYield = function() return 10 end, GetTotalMaintenance = function() return 2 end,
                                    GetGoldBalance = function() return 150 end } end,
  GetReligion = function() return { GetFaithYield = function() return 9 end, GetFaithBalance = function() return 80 end,
                                    GetReligionTypeCreated = function() return 1 end,
                                    GetReligionInMajorityOfCities = function() return 1 end } end,
  GetResources = function() return { GetResourceAmount = function() return 2 end } end,
  GetUnits = function() return { Members = members({ { GetType = function() return 0 end } }) } end,
  GetDiplomacy = function() return { HasMet = function() return true end, IsAtWarWith = function() return false end } end,
  GetStats = function() return { GetDiplomaticVictoryPoints = function() return 3 end, GetTourism = function() return 4 end } end,
  GetGovernors = function() return { GetGovernorList = function() return { { GetType = function() return 0 end, IsEstablished = function() return true end } } end } end,
}

local minor = {
  GetID = function() return 5 end,
  GetInfluence = function() return { GetSuzerain = function() return 0 end, GetTokensReceived = function() return 3 end } end,
  GetCities = function() return { GetCapitalCity = function() return city end } end,
}

Players = { [0] = player, [5] = minor }
PlayerConfigurations = {
  [0] = { GetLeaderTypeName = function() return "LEADER_TAMAR" end, GetCivilizationTypeName = function() return "CIVILIZATION_GEORGIA" end,
          GetHandicapTypeID = function() return 1 end },
  [5] = { GetCivilizationShortDescription = function() return "LOC_CIVILIZATION_ZANZIBAR_NAME" end },
}
Game = {
  GetLocalPlayer = function() return 0 end, GetCurrentGameTurn = function() return 12 end,
  GetEras = function() return { GetCurrentEra = function() return 1 end, GetPlayerCurrentScore = function() return 21 end,
                                HasHeroicGoldenAge = function() return false end, HasGoldenAge = function() return false end,
                                HasDarkAge = function() return true end, GetPlayerGoldenAgeThreshold = function() return 30 end,
                                GetPlayerDarkAgeThreshold = function() return 18 end } end,
  GetReligion = function() return { GetName = function() return "LOC_RELIGION_ZOROASTRIANISM" end } end,
}
GameConfiguration = { GetGameSpeedType = function() return 0 end, GetStartEra = function() return 1 end,
                      GetValue = function(k) return k == "GAMEMODE_DRAMATICAGES" or 42 end }
MapConfiguration = { GetScript = function() return "Shuffle.lua" end, GetMapSize = function() return 0 end,
                     GetValue = function() return 7 end }
PlayerManager = { GetAliveMajorIDs = function() return { 0 } end, GetAliveMinors = function() return { minor } end }
Locale = { Lookup = function(s)
  return (tostring(s):gsub("^LOC_CITY_", ""):gsub("^LOC_CIVILIZATION_", ""):gsub("_NAME$", ""):gsub("^LOC_RELIGION_", ""):gsub("^%u", string.upper))
end }
ContextPtr = { SetUpdate = function(_, fn) fn(0) end, ClearUpdate = function() end }
Events = setmetatable({}, { __index = function(t, k)
  if k == "InfluenceGiven" then return nil end -- simulate a missing event
  local e = { Add = function() end }; rawset(t, k, e); return e end })
