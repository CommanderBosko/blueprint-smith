-- bps-harness: paste job.blueprint on a lab surface, feed and sink its ports, power it, measure it,
-- then write script-output/bps-result.json. Contract: docs/m1-harness-plan.md ("Contract").
-- Setup runs in on_init (during --create); measuring runs in on_tick (during --benchmark).
local job = require("job")   -- generated per run by the Python runner

local RESULT_FILE = "bps-result.json"
local LIST_KEYS = {"errors", "outputs", "machines", "series", "log"}
local DV = {[0] = {0, -1}, [4] = {1, 0}, [8] = {0, 1}, [12] = {-1, 0}}
local LOADER = {["transport-belt"] = "loader", ["fast-transport-belt"] = "fast-loader",
  ["express-transport-belt"] = "express-loader", ["turbo-transport-belt"] = "turbo-loader"}
local STATUS = {}
for k, v in pairs(defines.entity_status) do STATUS[v] = k end
local HARNESS_POLE = "medium-electric-pole"
local MARGIN = 32   -- tiles of map around the blueprint for big entities, loaders, chests and power

local function fail(msg) table.insert(storage.build.errors, msg) end
local function log_(msg) table.insert(storage.log, msg) end
local function failed() return #storage.build.errors > 0 end

-- Expected items of `item` per craft of `recipe`.
local function product_amount(recipe, item)
  local r = recipe and prototypes.recipe[recipe]
  if not r then return 0 end
  local total = 0
  for _, p in pairs(r.products) do
    if p.type == "item" and p.name == item then
      local a = p.amount or (p.amount_min + p.amount_max) / 2
      total = total + a * (p.probability or 1) + (p.extra_count_fraction or 0)
    end
  end
  return total
end

local function write_result()
  storage.done = true
  local W, N = job.warmup_ticks, job.window_ticks
  local outputs = {}
  for _, o in ipairs(storage.outputs) do
    local produced = 0
    for _, m in ipairs(storage.machine_info) do produced = produced + (m.crafts or 0) * product_amount(m.recipe, o.item) end
    table.insert(outputs, {item = o.item, target = o.target, count = o.count, rate = o.count * 60 / N,
      produced_rate = produced * 60 / N,
      lane_rates = {o.lanes[1] * 60 / N, o.lanes[2] * 60 / N}, other_items = o.other})
  end
  local machines = {}
  for i, m in ipairs(storage.machine_info) do
    local tl = storage.tally[i]
    table.insert(machines, {name = m.name, position = m.position, recipe = m.recipe, crafts = m.crafts or 0,
      output_growth = m.output_growth or 0,
      working = ((tl.working or 0) + (tl.normal or 0)) / N, statuses = tl})
  end
  storage.power.unpowered_machine_ticks = storage.unpowered
  local json = helpers.table_to_json({
    version = 1, build = storage.build, ticks = {warmup = W, window = N}, outputs = outputs,
    machines = machines, power = storage.power, series = storage.series, log = storage.log,
  })
  -- table_to_json writes an empty table as {}; these keys always hold lists.
  for _, k in ipairs(LIST_KEYS) do json = json:gsub('"' .. k .. '":{}', '"' .. k .. '":[]') end
  helpers.write_file(RESULT_FILE, json, false)
end

local function check_job()
  if type(job.blueprint) ~= "string" then fail("job.blueprint is not a string") end
  if not (type(job.window_ticks) == "number" and job.window_ticks > 0) then fail("job.window_ticks must be > 0") end
  if not (type(job.warmup_ticks) == "number" and job.warmup_ticks >= 0) then fail("job.warmup_ticks must be >= 0") end
  if job.research ~= nil and job.research ~= "none" and job.research ~= "all" then
    fail("job.research must be \"none\" or \"all\", got " .. tostring(job.research))
  end
  for i, p in ipairs(job.ports or {}) do
    if not (type(p.tile) == "table" and type(p.tile[1]) == "number" and type(p.tile[2]) == "number") then
      fail(string.format("port %d: tile must be {x, y}", i))
    end
    if type(p.rate) ~= "number" then fail(string.format("port %d: rate must be a number", i)) end
    if p.role ~= "input" and p.role ~= "output" then fail(string.format("port %d: bad role %s", i, tostring(p.role))) end
    if not DV[p.direction] then fail(string.format("port %d: bad direction %s", i, tostring(p.direction))) end
    if not LOADER[p.belt] then fail(string.format("port %d: no loader for belt %s", i, tostring(p.belt))) end
    if not prototypes.item[p.item] then fail(string.format("port %d: unknown item %s", i, tostring(p.item))) end
  end
end

-- Lab surface big enough for the blueprint (it is pasted centred on {0,0}) plus the harness around it.
local function make_surface(stack)
  local x0, y0, x1, y1 = math.huge, math.huge, -math.huge, -math.huge
  for _, e in pairs(stack.get_blueprint_entities() or {}) do
    x0, y0 = math.min(x0, e.position.x), math.min(y0, e.position.y)
    x1, y1 = math.max(x1, e.position.x), math.max(y1, e.position.y)
  end
  local half = x0 == math.huge and 0 or math.max(x1 - x0, y1 - y0) / 2
  local radius = math.ceil((half + MARGIN) / 32)
  game.map_settings.pollution.enabled = false
  game.map_settings.enemy_expansion.enabled = false
  game.map_settings.enemy_evolution.enabled = false
  local surface = game.create_surface("bps", {no_enemies_mode = true, peaceful_mode = true,
    default_enable_all_autoplace_controls = false})
  surface.generate_with_lab_tiles = true
  surface.always_day = true
  surface.peaceful_mode = true
  surface.request_to_generate_chunks({0, 0}, radius)
  surface.force_generate_chunk_requests()
  log_(string.format("surface chunk radius %d for a %dx%d blueprint", radius, x1 - x0, y1 - y0))
  return surface
end

-- Put the planned items (modules) straight into the target entity, then drop the proxy.
local function fulfil(proxy)
  local target = proxy.proxy_target
  if not target then
    fail(string.format("item-request-proxy at %s,%s has no target", proxy.position.x, proxy.position.y))
    return
  end
  for _, plan in pairs(proxy.insert_plan) do
    local item = {name = plan.id.name, quality = plan.id.quality or "normal"}
    for _, pos in pairs(plan.items.in_inventory or {}) do
      local inv = target.get_inventory(pos.inventory)
      item.count = pos.count or 1
      if not (inv and inv[pos.stack + 1].set_stack(item)) then
        fail(string.format("could not insert %d %s (%s) into %s at %s,%s", item.count, item.name, item.quality,
          target.name, target.position.x, target.position.y))
      end
    end
    if (plan.items.grid_count or 0) > 0 then fail("equipment-grid requests are not supported: " .. item.name) end
  end
  proxy.destroy()
end

local function build(force)
  local inv = game.create_inventory(1)
  local stack = inv[1]
  local rc = stack.import_stack(job.blueprint)
  if rc ~= 0 or not (stack.valid_for_read and stack.is_blueprint) then
    inv.destroy()
    return fail("import_stack failed (rc " .. rc .. "); the string must be a single blueprint")
  end
  local surface = make_surface(stack)
  local expected = stack.get_blueprint_entity_count()
  local ghosts = stack.build_blueprint{surface = surface, force = force, position = {0, 0},
    build_mode = defines.build_mode.forced, skip_fog_of_war = true}
  inv.destroy()
  local built, proxies, placed = {}, {}, 0
  for _, g in pairs(ghosts) do
    if g.valid and g.type == "entity-ghost" then
      placed = placed + 1
      local _, ent, proxy = g.silent_revive()
      if ent then table.insert(built, ent) end
      if proxy then table.insert(proxies, proxy) end
    end
  end
  if placed < expected then fail(string.format("only %d of %d blueprint entities could be placed", placed, expected)) end
  if #built == 0 then return fail("no entity was built") end
  for _, p in pairs(proxies) do if p.valid then fulfil(p) end end
  for _, p in pairs(surface.find_entities_filtered{type = "item-request-proxy"}) do fulfil(p) end
  storage.build.ghosts_left = surface.count_entities_filtered{type = {"entity-ghost", "tile-ghost"}}
  storage.build.proxies_left = surface.count_entities_filtered{type = "item-request-proxy"}

  local x0, y0, x1, y1 = math.huge, math.huge, -math.huge, -math.huge
  for _, e in pairs(built) do
    local b = e.bounding_box
    x0, y0 = math.min(x0, math.floor(b.left_top.x)), math.min(y0, math.floor(b.left_top.y))
    x1, y1 = math.max(x1, math.ceil(b.right_bottom.x)), math.max(y1, math.ceil(b.right_bottom.y))
  end
  storage.origin = {x0, y0}
  storage.box = {{x0, y0}, {x1, y1}}
  log_(string.format("built %d entities, %d module proxies, origin %d,%d, size %dx%d",
    #built, #proxies, x0, y0, x1 - x0, y1 - y0))
  return surface
end

-- Feed (input) or sink (output) a port: loader on the tile beyond the belt end, chest beyond the loader.
local function place_port(surface, force, i, p)
  local d = DV[p.direction]
  local cx, cy = storage.origin[1] + p.tile[1] + 0.5, storage.origin[2] + p.tile[2] + 0.5
  local where = string.format("port %d (%s %s at %d,%d)", i, p.role, p.item, p.tile[1], p.tile[2])
  local belt = surface.find_entities_filtered{position = {cx, cy}, type = {"transport-belt", "underground-belt"}}[1]
  if not belt then return fail(where .. ": no belt on the port tile") end
  if belt.direction ~= p.direction then
    return fail(string.format("%s: belt flows %d, port says %d", where, belt.direction, p.direction))
  end
  if belt.type == "transport-belt" and belt.name ~= p.belt then
    return fail(string.format("%s: belt is %s, port says %s", where, belt.name, p.belt))
  end
  local feed = p.role == "input"
  local sign = feed and -1 or 1                  -- feed: upstream of the port; sink: downstream
  local chest_name, loader_name = feed and "infinity-chest" or "steel-chest", LOADER[p.belt]
  local chest_pos = {cx + sign * 3 * d[1], cy + sign * 3 * d[2]}
  local loader_pos = {cx + sign * 1.5 * d[1], cy + sign * 1.5 * d[2]}
  if not surface.can_place_entity{name = loader_name, position = loader_pos, direction = p.direction, force = force} then
    return fail(where .. ": no room for the loader")
  end
  if not surface.can_place_entity{name = chest_name, position = chest_pos, force = force} then
    return fail(where .. ": no room for the chest")
  end
  local chest = surface.create_entity{name = chest_name, position = chest_pos, force = force}
  local loader = surface.create_entity{name = loader_name, position = loader_pos, direction = p.direction,
    type = feed and "output" or "input", force = force}
  if not (chest and loader) then return fail(where .. ": loader or chest not created") end
  if feed then chest.set_infinity_container_filter(1, {name = p.item, count = 100, mode = "at-least"}) end
  loader.update_connections()
  local c = loader.loader_container
  if not (c and c.unit_number == chest.unit_number) then return fail(where .. ": loader is not attached to its chest") end
  local linked = false
  for _, e in pairs(loader.belt_neighbours[feed and "outputs" or "inputs"]) do
    if e.unit_number == belt.unit_number then linked = true end
  end
  if not linked then return fail(where .. ": loader does not connect to the port belt") end
  if not feed then
    table.insert(storage.outputs, {item = p.item, target = p.rate, belt = belt,
      inv = chest.get_inventory(defines.inventory.chest), count = 0, other = 0, lanes = {0, 0}, seen = {{}, {}}})
  end
end

-- Energy interface + pole outside the blueprint, far enough that the pole's supply area stays off the blueprint.
local function place_power(surface, force)
  local power = {harness_linked = false, other_networks = 0}
  storage.power = power
  local box = storage.box
  local poles = surface.find_entities_filtered{area = box, type = "electric-pole"}
  if #poles == 0 then log_("no electric pole in the blueprint; harness power not connected") return end
  local proto = prototypes.entity[HARNESS_POLE]
  local gap = math.ceil(proto.get_supply_area_distance()) + 1
  local x0, y0, x1, y1 = box[1][1], box[1][2], box[2][1], box[2][2]
  local cands = {}
  for _, t in pairs(poles) do
    local tx, ty = math.floor(t.position.x), math.floor(t.position.y)
    for _, c in pairs({                          -- pole tile, energy interface centre: west, east, north, south
      {x0 - gap, ty, x0 - gap - 1, ty + 1}, {x1 + gap - 1, ty, x1 + gap + 1, ty + 1},
      {tx, y0 - gap, tx + 1, y0 - gap - 1}, {tx, y1 + gap - 1, tx + 1, y1 + gap + 1}}) do
      local pos = {c[1] + 0.5, c[2] + 0.5}
      table.insert(cands, {pole = pos, eei = {c[3], c[4]}, target = t,
        dist = (pos[1] - t.position.x) ^ 2 + (pos[2] - t.position.y) ^ 2})
    end
  end
  table.sort(cands, function(a, b) return a.dist < b.dist end)
  local pole, eei, target
  for _, c in ipairs(cands) do
    if surface.can_place_entity{name = HARNESS_POLE, position = c.pole, force = force}
      and surface.can_place_entity{name = "electric-energy-interface", position = c.eei, force = force} then
      pole = surface.create_entity{name = HARNESS_POLE, position = c.pole, force = force}
      eei = surface.create_entity{name = "electric-energy-interface", position = c.eei, force = force}
      target = c.target
      break
    end
  end
  if not (pole and eei) then return fail("no room for the harness pole and energy interface") end
  -- Creating the pole may auto-connect it already, so connect_to can return false; check networks instead.
  local copper = defines.wire_connector_id.pole_copper
  pole.get_wire_connector(copper, true).connect_to(target.get_wire_connector(copper, true), false)
  local net = pole.electric_network_id
  power.harness_linked = net ~= nil and net == target.electric_network_id and net == eei.electric_network_id
  for _, t in pairs(poles) do
    if t.electric_network_id and t.electric_network_id ~= net then power.other_networks = power.other_networks + 1 end
  end
  log_(string.format("harness pole at %s,%s wired to %s at %s,%s, %d blueprint poles on other networks",
    pole.position.x, pole.position.y, target.name, target.position.x, target.position.y, power.other_networks))
  if not power.harness_linked then fail("harness power is not linked to the blueprint's poles") end
end

local function setup()
  check_job()
  if failed() then return end
  local force = game.forces.player
  -- Research changes the numbers (steel productivity +10%, inserter hand size), so it's the job's choice.
  -- "none" matches ratios.py's base stats; script-built entities don't need research to exist.
  if job.research == "all" then force.research_all_technologies() else force.enable_all_recipes() end
  for name in pairs(prototypes.quality) do pcall(force.unlock_quality, name) end
  local surface = build(force)
  if failed() then return end
  for i, p in ipairs(job.ports or {}) do place_port(surface, force, i, p) end
  if failed() then return end
  place_power(surface, force)
  if failed() then return end
  storage.machines = surface.find_entities_filtered{area = storage.box, type = {"furnace", "assembling-machine"}}
  table.sort(storage.machines, function(a, b)
    if a.position.y ~= b.position.y then return a.position.y < b.position.y end
    return a.position.x < b.position.x
  end)
  for i, m in ipairs(storage.machines) do         -- positions in the port frame (relative to the origin)
    storage.machine_info[i] = {name = m.name, position = {m.position.x - storage.origin[1], m.position.y - storage.origin[2]}}
    storage.tally[i] = {}
  end
end

script.on_init(function()
  storage.log = {}
  storage.build = {ghosts_left = 0, proxies_left = 0, errors = {}}
  storage.origin = {0, 0}
  storage.outputs, storage.machines, storage.machine_info, storage.tally, storage.series = {}, {}, {}, {}, {}
  storage.power = {harness_linked = false, other_networks = 0}
  storage.bucket, storage.unpowered = 0, 0
  local ok, err = pcall(setup)
  if not ok then fail("setup error: " .. tostring(err)) end
  if failed() then                               -- don't measure a broken setup
    storage.outputs, storage.machine_info = {}, {}
    write_result()
  end
end)

-- Crafts so far including the current one's progress. Furnaces fed together finish in step, so counting
-- items at the sink aliases with the window (+-1 craft per machine); this doesn't.
local function crafts_done(m)
  return m.products_finished + m.crafting_progress
end

-- Items waiting in the machine's result slots. A blocked machine keeps crafting into them (a stack of plates
-- is minutes of output), so "working" alone hides a jam for that long; growth over the window doesn't.
local function held(m)
  local inv = m.get_output_inventory()
  return inv and inv.get_item_count() or 0
end

local function recipe_of(m)
  local r = m.get_recipe()
  if r then return r.name end
  local prev = m.type == "furnace" and m.previous_recipe
  if prev then return type(prev.name) == "string" and prev.name or prev.name.name end
end

local function tick(t)
  local W, N = job.warmup_ticks, job.window_ticks
  local in_window = t >= W and t < W + N
  if t == W - 1 or t == W + N - 1 then           -- snapshot crafts at the window's edges
    for i, m in ipairs(storage.machines) do
      local info = storage.machine_info[i]
      if m.valid and t == W - 1 then info.crafts_start, info.held_start = crafts_done(m), held(m)
      elseif m.valid then
        info.crafts, info.recipe = crafts_done(m) - (info.crafts_start or 0), recipe_of(m)
        info.output_growth = held(m) - (info.held_start or 0)
      end
    end
  end
  for i, o in ipairs(storage.outputs) do
    local n, all = 0, 0                          -- n: the port's item, any quality
    for _, it in pairs(o.inv.get_contents()) do
      all = all + it.count
      if it.name == o.item then n = n + it.count end
    end
    if all > 0 then o.inv.clear() end
    if in_window then o.count, o.other = o.count + n, o.other + all - n end
    if i == 1 then storage.bucket = storage.bucket + n end
    -- Per-lane flow: new unique_ids on the port tile. Seeding at W-1 skips items already there.
    if in_window or t == W - 1 then
      for lane = 1, 2 do
        local seen, now = o.seen[lane], {}
        for _, it in pairs(o.belt.get_transport_line(lane).get_detailed_contents()) do
          now[it.unique_id] = true
          -- One entry is a stack: up to 4 items on a stacked belt.
          if in_window and not seen[it.unique_id] then o.lanes[lane] = o.lanes[lane] + it.stack.count end
        end
        o.seen[lane] = now
      end
    end
  end
  if t % 600 == 599 then table.insert(storage.series, storage.bucket / 10); storage.bucket = 0 end
  if in_window then
    local unpowered = false
    for i, m in ipairs(storage.machines) do
      local s = m.valid and (STATUS[m.status] or "none") or "invalid"
      storage.tally[i][s] = (storage.tally[i][s] or 0) + 1
      if s == "no_power" or s == "low_power" then unpowered = true end
    end
    if unpowered then storage.unpowered = storage.unpowered + 1 end
  end
  if t >= W + N then write_result() end
end

script.on_event(defines.events.on_tick, function(ev)
  if storage.done then return end
  local ok, err = pcall(tick, ev.tick)
  if not ok then
    fail("measure error at tick " .. ev.tick .. ": " .. tostring(err))
    write_result()
  end
end)
