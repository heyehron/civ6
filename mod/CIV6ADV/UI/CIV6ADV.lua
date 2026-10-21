-- Civ VI Achievement Advisor: UI-only state export.
-- Prints one line per snapshot to Lua.log:   CIV6ADV|{json}
-- Every section is wrapped in pcall, so an API that differs between game versions
-- only drops that field instead of breaking the export. Untested in-game until M0.

local MARKER = "CIV6ADV|"
local lastTurnSent = -1
local pending = false

-- JSON ---------------------------------------------------------------------------------
local function esc(s)
  s = tostring(s)
  s = s:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t')
  return s
end

local function isArray(t)
  local n = 0
  for k, _ in pairs(t) do
    if type(k) ~= "number" then return false end
    n = n + 1
  end
  return n == #t
end

local function toJson(v)
  local t = type(v)
  if t == "nil" then return "null" end
  if t == "boolean" then return v and "true" or "false" end
  if t == "number" then
    if v ~= v or v == math.huge or v == -math.huge then return "null" end
    if math.floor(v) == v then return string.format("%d", v) end
    return string.format("%.2f", v)
  end
  if t == "string" then return '"' .. esc(v) .. '"' end
  if t == "table" then
    local parts = {}
    if next(v) == nil then return "[]" end
    if isArray(v) then
      for i = 1, #v do parts[#parts + 1] = toJson(v[i]) end
      return "[" .. table.concat(parts, ",") .. "]"
    end
    for k, val in pairs(v) do parts[#parts + 1] = '"' .. esc(k) .. '":' .. toJson(val) end
    return "{" .. table.concat(parts, ",") .. "}"
  end
  return "null"
end

-- Helpers ------------------------------------------------------------------------------
local function try(fn, fallback)
  local ok, res = pcall(fn)
  if ok then return res end
  return fallback
end

local function lookup(tableName, key, column)
  return try(function()
    local row = GameInfo[tableName][key]
    return row and row[column] or nil
  end, nil)
end

local function localPlayer()
  local id = Game.GetLocalPlayer()
  if id == nil or id < 0 then return nil, nil end
  return id, Players[id]
end

-- Sections -----------------------------------------------------------------------------
local function setupInfo(s, id)
  local cfg = PlayerConfigurations[id]
  s.leader = try(function() return cfg:GetLeaderTypeName() end)
  s.civ = try(function() return cfg:GetCivilizationTypeName() end)
  s.difficulty = try(function() return lookup("Difficulties", cfg:GetHandicapTypeID(), "DifficultyType") end)
  s.speed = try(function() return lookup("GameSpeeds", GameConfiguration.GetGameSpeedType(), "GameSpeedType") end)
  s.start_era = try(function() return lookup("Eras", GameConfiguration.GetStartEra(), "EraType") end)
  s.map_type = try(function() return MapConfiguration.GetScript() end)
  s.map_size = try(function() return lookup("Maps", MapConfiguration.GetMapSize(), "MapSizeType") end)
  s.game_id = try(function() return tostring(GameConfiguration.GetValue("GAME_SYNC_RANDOM_SEED") or "") .. "-" ..
    tostring(MapConfiguration.GetValue("RANDOM_SEED") or "") end, "")
  s.game_modes = try(function()
    local out = {}
    if GameInfo.GameModeItems then
      for row in GameInfo.GameModeItems() do
        if GameConfiguration.GetValue(row.GameModeType) then out[#out + 1] = row.GameModeType end
      end
    end
    return out
  end, {})
end

local function eraInfo(s, id)
  s.era = try(function() return GameInfo.Eras[Game.GetEras():GetCurrentEra()].EraType end)
  s.era_score = try(function() return Game.GetEras():GetPlayerCurrentScore(id) end)
  s.age = try(function()
    local eras = Game.GetEras()
    if eras:HasHeroicGoldenAge(id) then return "heroic" end
    if eras:HasGoldenAge(id) then return "golden" end
    if eras:HasDarkAge(id) then return "dark" end
    return "normal"
  end)
  s.extra_era = try(function()
    local eras = Game.GetEras()
    return { golden_threshold = eras:GetPlayerGoldenAgeThreshold(id), dark_threshold = eras:GetPlayerDarkAgeThreshold(id) }
  end)
end

local function researchInfo(s, player)
  local techs, civics = {}, {}
  try(function()
    local pt = player:GetTechs()
    for row in GameInfo.Technologies() do
      if pt:HasTech(row.Index) then techs[#techs + 1] = row.TechnologyType end
    end
    s.current_tech = lookup("Technologies", pt:GetResearchingTech(), "TechnologyType")
  end)
  try(function()
    local pc = player:GetCulture()
    for row in GameInfo.Civics() do
      if pc:HasCivic(row.Index) then civics[#civics + 1] = row.CivicType end
    end
    s.current_civic = lookup("Civics", pc:GetProgressingCivic(), "CivicType")
    s.government = lookup("Governments", pc:GetCurrentGovernment(), "GovernmentType")
    local pols = {}
    for i = 0, pc:GetNumPolicySlots() - 1 do
      local p = pc:GetSlotPolicy(i)
      if p ~= nil and p >= 0 then pols[#pols + 1] = lookup("Policies", p, "PolicyType") end
    end
    s.policies = pols
  end)
  s.techs_known, s.civics_known = techs, civics
end

local function cityInfo(s, id, player)
  local cities, owned = {}, {}
  try(function()
    for _, city in player:GetCities():Members() do
      local c = { name = Locale.Lookup(city:GetName()), population = city:GetPopulation(),
                  capital = city:IsCapital(), districts = {}, buildings = {}, wonders = {} }
      try(function()
        for _, d in city:GetDistricts():Members() do
          if d:IsComplete() then c.districts[#c.districts + 1] = GameInfo.Districts[d:GetType()].DistrictType end
        end
      end)
      try(function()
        local b = city:GetBuildings()
        for row in GameInfo.Buildings() do
          if b:HasBuilding(row.Index) and not b:IsPillaged(row.Index) then
            if row.IsWonder then
              c.wonders[#c.wonders + 1] = row.BuildingType
              owned[#owned + 1] = row.BuildingType
            else
              c.buildings[#c.buildings + 1] = row.BuildingType
            end
          end
        end
      end)
      c.religion = try(function()
        local r = city:GetReligion():GetMajorityReligion()
        if r ~= nil and r >= 0 then return GameInfo.Religions[r].ReligionType end
        return nil
      end)
      cities[#cities + 1] = c
    end
  end)
  s.cities, s.wonders_owned = cities, owned
end

local function economyInfo(s, player)
  s.yields = try(function()
    return { science = player:GetTechs():GetScienceYield(), culture = player:GetCulture():GetCultureYield(),
             gold = player:GetTreasury():GetGoldYield() - player:GetTreasury():GetTotalMaintenance(),
             faith = player:GetReligion():GetFaithYield() }
  end, {})
  s.balances = try(function()
    return { gold = player:GetTreasury():GetGoldBalance(), faith = player:GetReligion():GetFaithBalance() }
  end, {})
  s.resources = try(function()
    local out = {}
    local res = player:GetResources()
    for row in GameInfo.Resources() do
      local n = res:GetResourceAmount(row.Index)
      if n and n > 0 then out[row.ResourceType] = n end
    end
    return out
  end, {})
  s.units = try(function()
    local out = {}
    for _, u in player:GetUnits():Members() do
      local t = GameInfo.Units[u:GetType()].UnitType
      out[t] = (out[t] or 0) + 1
    end
    return out
  end, {})
end

local function religionInfo(s, id, player)
  s.religion = try(function()
    local r = player:GetReligion():GetReligionTypeCreated()
    if r == nil or r < 0 then return {} end
    local row = GameInfo.Religions[r]
    local name = try(function() return Locale.Lookup(Game.GetReligion():GetName(r)) end, nil)
    local n = 0
    for _, city in player:GetCities():Members() do
      if city:GetReligion():GetMajorityReligion() == r then n = n + 1 end
    end
    return { type = row.ReligionType, name = name or Locale.Lookup(row.Name), majority_cities = n }
  end, {})
  s.victory_progress = s.victory_progress or {}
  try(function()
    local r = player:GetReligion():GetReligionTypeCreated()
    if r == nil or r < 0 then return end
    local civs, needed = 0, 0
    for _, pid in ipairs(PlayerManager.GetAliveMajorIDs()) do
      needed = needed + 1
      local p = Players[pid]
      if p:GetReligion():GetReligionInMajorityOfCities() == r then civs = civs + 1 end
    end
    s.victory_progress.religious = civs
    s.victory_progress.religious_needed = needed
  end)
end

local function cityStateInfo(s, id, player)
  s.city_states = try(function()
    local out = {}
    local diplo = player:GetDiplomacy()
    for _, minor in ipairs(PlayerManager.GetAliveMinors()) do
      local mid = minor:GetID()
      if diplo:HasMet(mid) then
        local cs = { name = Locale.Lookup(PlayerConfigurations[mid]:GetCivilizationShortDescription()) }
        cs.suzerain = try(function() return minor:GetInfluence():GetSuzerain() == id end, false)
        cs.envoys = try(function() return minor:GetInfluence():GetTokensReceived(id) end)
        cs.religion = try(function()
          local cap = minor:GetCities():GetCapitalCity()
          local r = cap:GetReligion():GetMajorityReligion()
          if r ~= nil and r >= 0 then return GameInfo.Religions[r].ReligionType end
          return nil
        end)
        out[#out + 1] = cs
      end
    end
    return out
  end, {})
end

local function diplomacyInfo(s, id, player)
  s.at_war_with = try(function()
    local out = {}
    local diplo = player:GetDiplomacy()
    for _, pid in ipairs(PlayerManager.GetAliveMajorIDs()) do
      if pid ~= id and diplo:IsAtWarWith(pid) then
        out[#out + 1] = PlayerConfigurations[pid]:GetCivilizationTypeName()
      end
    end
    return out
  end, {})
  try(function()
    s.victory_progress = s.victory_progress or {}
    s.victory_progress.diplomatic = player:GetStats():GetDiplomaticVictoryPoints()
  end)
  try(function()
    s.victory_progress = s.victory_progress or {}
    s.victory_progress.tourism = player:GetStats():GetTourism()
  end)
  try(function()
    local held = 0
    for _, pid in ipairs(PlayerManager.GetAliveMajorIDs()) do
      for _, city in Players[pid]:GetCities():Members() do
        if city:IsOriginalCapital() and city:GetOwner() == id then held = held + 1 end
      end
    end
    s.victory_progress = s.victory_progress or {}
    s.victory_progress.capitals_held = held
  end)
  s.governors = try(function()
    local out = {}
    for _, g in ipairs(player:GetGovernors():GetGovernorList()) do
      local row = GameInfo.Governors[g:GetType()]
      out[#out + 1] = { type = row.GovernorType, established = g:IsEstablished() }
    end
    return out
  end, {})
end

-- Snapshot -----------------------------------------------------------------------------
local function snapshot()
  local id, player = localPlayer()
  if player == nil then return end
  local s = { kind = "snapshot", turn = Game.GetCurrentGameTurn() }
  local sections = {
    function() setupInfo(s, id) end,
    function() eraInfo(s, id) end,
    function() researchInfo(s, player) end,
    function() cityInfo(s, id, player) end,
    function() economyInfo(s, player) end,
    function() religionInfo(s, id, player) end,
    function() cityStateInfo(s, id, player) end,
    function() diplomacyInfo(s, id, player) end,
  }
  for _, fn in ipairs(sections) do pcall(fn) end
  s.wonders_lost = ExposedMembers and ExposedMembers.CIV6ADV_LOST or {}
  print(MARKER .. toJson(s))
end

-- Debounce: several events fire per action; send at most one snapshot per frame burst.
local function requestSnapshot()
  if pending then return end
  pending = true
  ContextPtr:SetUpdate(function()
    ContextPtr:ClearUpdate()
    pending = false
    pcall(snapshot)
  end)
end

-- Events -------------------------------------------------------------------------------
local lost = {}
ExposedMembers = ExposedMembers or {}
ExposedMembers.CIV6ADV_LOST = lost

local function onWonderCompleted(x, y, buildingIndex, playerIndex)
  local id = Game.GetLocalPlayer()
  if playerIndex ~= id then
    local row = GameInfo.Buildings[buildingIndex]
    if row then lost[#lost + 1] = row.BuildingType end
  end
  requestSnapshot()
end

local function onTurnBegin()
  local t = Game.GetCurrentGameTurn()
  if t ~= lastTurnSent then
    lastTurnSent = t
    requestSnapshot()
  end
end

local function hook(name, fn)
  local ok = pcall(function() Events[name].Add(fn) end)
  if not ok then print(MARKER .. toJson({ kind = "warning", text = "event not available: " .. name })) end
end

local function init()
  hook("LocalPlayerTurnBegin", onTurnBegin)
  hook("ResearchCompleted", requestSnapshot)
  hook("CivicCompleted", requestSnapshot)
  hook("CityAddedToMap", requestSnapshot)
  hook("WonderCompleted", onWonderCompleted)
  hook("GameEraChanged", requestSnapshot)
  hook("ReligionFounded", requestSnapshot)
  hook("GovernmentPolicyChanged", requestSnapshot)
  hook("InfluenceGiven", requestSnapshot)
  hook("DistrictBuildProgressChanged", requestSnapshot)
  hook("LoadGameViewStateDone", requestSnapshot)
  print(MARKER .. toJson({ kind = "hello", version = 1 }))
  requestSnapshot()
end

pcall(init)
