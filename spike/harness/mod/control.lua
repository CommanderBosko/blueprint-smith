-- Spike: paste job.blueprint on a lab surface, feed/sink its ports, power it, measure. See docs/m1-harness-plan.md.
local job = require("job")

local DV = {[0] = {0, -1}, [4] = {1, 0}, [8] = {0, 1}, [12] = {-1, 0}}
local STATUS = {}
for k, v in pairs(defines.entity_status) do STATUS[v] = k end
local LOADER = {["transport-belt"] = "loader", ["fast-transport-belt"] = "fast-loader",
  ["express-transport-belt"] = "express-loader", ["turbo-transport-belt"] = "turbo-loader"}

local function log_(msg) table.insert(storage.log, msg) end

local function place_loader(surface, force, port, origin, mode)
  local d = DV[port.direction]
  local cx, cy = origin[1] + port.tile[1] + 0.5, origin[2] + port.tile[2] + 0.5
  local sign = mode == "feed" and -1 or 1          -- feed: upstream of the port; sink: downstream
  local chest_name = mode == "feed" and "infinity-chest" or "steel-chest"
  local chest = surface.create_entity{name = chest_name, force = force,
    position = {cx + sign * 3 * d[1], cy + sign * 3 * d[2]}}
  if mode == "feed" then
    chest.set_infinity_container_filter(1, {name = port.item, count = 100, mode = "at-least"})
  end
  -- Try each orientation; keep the one whose container is our chest.
  for _, try in ipairs({{port.direction, "output"}, {port.direction, "input"},
                        {(port.direction + 8) % 16, "output"}, {(port.direction + 8) % 16, "input"}}) do
    local l = surface.create_entity{name = LOADER[port.belt], force = force, direction = try[1], type = try[2],
      position = {cx + sign * 1.5 * d[1], cy + sign * 1.5 * d[2]}}
    if l then
      l.update_connections()
      local c = l.loader_container
      local nb = l.belt_neighbours
      local names = function(t) local o = {} for _, e in pairs(t or {}) do table.insert(o, e.name .. "@" .. e.position.x .. "," .. e.position.y) end return table.concat(o, ";") end
      local belt_ok
      if mode == "feed" then belt_ok = #(nb.outputs or {}) > 0 else belt_ok = #(nb.inputs or {}) > 0 end
      local ok = c ~= nil and c.unit_number == chest.unit_number and belt_ok
      log_(string.format("%s loader dir=%d type=%s loader_type=%s pos=%s,%s container=%s chest@%s,%s in=[%s] out=[%s] ok=%s",
        mode, try[1], try[2], l.loader_type, l.position.x, l.position.y, c and (c.name .. "@" .. c.position.x .. "," .. c.position.y) or "nil",
        chest.position.x, chest.position.y, names(nb.inputs), names(nb.outputs), tostring(ok)))
      if ok then return l, chest end
      l.destroy()
    else
      log_(string.format("%s loader dir=%d type=%s create failed", mode, try[1], try[2]))
    end
  end
  return nil, chest
end

script.on_init(function()
  storage.log = {}
  game.map_settings.pollution.enabled = false
  game.map_settings.enemy_expansion.enabled = false
  game.map_settings.enemy_evolution.enabled = false
  local surface = game.create_surface("bps", {no_enemies_mode = true, peaceful_mode = true,
    default_enable_all_autoplace_controls = false})
  surface.generate_with_lab_tiles = true
  surface.always_day = true
  surface.request_to_generate_chunks({0, 0}, 6)
  surface.force_generate_chunk_requests()
  local force = game.forces.player
  force.research_all_technologies()

  local inv = game.create_inventory(1)
  local stack = inv[1]
  local empty_rc = stack.import_stack(job.blueprint)      -- does it work on an empty slot?
  log_("import_stack on empty slot rc=" .. tostring(empty_rc) .. " is_blueprint=" .. tostring(stack.valid_for_read and stack.is_blueprint))
  if not (stack.valid_for_read and stack.is_blueprint) then
    stack.set_stack("blueprint")
    log_("import_stack after set_stack rc=" .. tostring(stack.import_stack(job.blueprint)))
  end
  local ghosts = stack.build_blueprint{surface = surface, force = force, position = {0, 0},
    build_mode = defines.build_mode.forced, skip_fog_of_war = true}
  log_("ghosts built=" .. #ghosts)
  local built, proxies = {}, 0
  for _, g in pairs(ghosts) do
    local _, ent, proxy = g.silent_revive()
    if ent then table.insert(built, ent) end
    if proxy then proxies = proxies + 1 end
  end
  inv.destroy()
  local ox, oy = math.huge, math.huge
  for _, e in pairs(built) do
    ox = math.min(ox, math.floor(e.bounding_box.left_top.x)); oy = math.min(oy, math.floor(e.bounding_box.left_top.y))
  end
  local origin = {ox, oy}
  log_(string.format("revived=%d origin=(%d,%d) proxies=%d ghosts_left=%d", #built, ox, oy, proxies,
    surface.count_entities_filtered{type = "entity-ghost"}))

  -- Do splitter priority and pole wires survive?
  local pri, wired = {}, 0
  for _, e in pairs(built) do
    if e.type == "splitter" then pri[e.splitter_output_priority] = (pri[e.splitter_output_priority] or 0) + 1 end
    if e.type == "electric-pole" then
      local c = e.get_wire_connector(defines.wire_connector_id.pole_copper, false)
      if c and #c.real_connections > 0 then wired = wired + 1 end
    end
  end
  log_("splitter priorities=" .. serpent.line(pri) .. " poles with real copper wires=" .. wired)

  for _, p in pairs(job.ports) do
    local l, chest = place_loader(surface, force, p, origin, p.role == "input" and "feed" or "sink")
    p.loader, p.chest = l, chest
    if p.role == "output" then
      p.belt_entity = surface.find_entities_filtered{position = {ox + p.tile[1] + 0.5, oy + p.tile[2] + 0.5}, type = "transport-belt"}[1]
      log_("output belt entity found=" .. tostring(p.belt_entity ~= nil))
    end
  end
  storage.ports = job.ports

  -- Power: energy interface + pole wired to the nearest blueprint pole.
  local eei = surface.create_entity{name = "electric-energy-interface", force = force, position = {ox - 6, oy + 2}}
  local pole = surface.create_entity{name = "medium-electric-pole", force = force, position = {ox - 4.5, oy + 2.5}}
  local target = surface.find_entities_filtered{type = "electric-pole", position = {ox, oy}, radius = 12, limit = 2}
  local linked = false
  for _, t in pairs(target) do
    if t ~= pole and not linked then
      linked = pole.get_wire_connector(defines.wire_connector_id.pole_copper, true)
        .connect_to(t.get_wire_connector(defines.wire_connector_id.pole_copper, true), false)
    end
  end
  log_(string.format("eei=%s pole=%s linked=%s eei.power_production=%s", tostring(eei ~= nil), tostring(pole ~= nil),
    tostring(linked), tostring(eei and eei.power_production)))

  storage.machines = surface.find_entities_filtered{type = {"furnace", "assembling-machine"}}
  storage.tally = {}
  storage.series = {}
  storage.out_count, storage.lane_count, storage.prev_ids = 0, {0, 0}, {{}, {}}
  storage.chunk = 0
end)

script.on_event(defines.events.on_tick, function(ev)
  local t = ev.tick
  local W, N = job.warmup_ticks, job.window_ticks
  for _, p in pairs(storage.ports) do
    if p.role == "output" and p.chest and p.chest.valid then
      local n = p.chest.get_item_count()
      if n > 0 then p.chest.clear_items_inside() end
      storage.chunk = storage.chunk + n
      if t >= W and t < W + N then storage.out_count = storage.out_count + n end
      if t >= W and t < W + N and p.belt_entity then
        for lane = 1, 2 do
          local cur = {}
          for _, it in pairs(p.belt_entity.get_transport_line(lane).get_detailed_contents()) do
            cur[it.unique_id] = true
            if not storage.prev_ids[lane][it.unique_id] then storage.lane_count[lane] = storage.lane_count[lane] + 1 end
          end
          storage.prev_ids[lane] = cur
        end
      end
    end
  end
  if t % 600 == 599 then table.insert(storage.series, storage.chunk / 10); storage.chunk = 0 end
  if t >= W and t < W + N then
    for i, m in pairs(storage.machines) do
      local s = STATUS[m.status] or tostring(m.status)
      storage.tally[i] = storage.tally[i] or {}
      storage.tally[i][s] = (storage.tally[i][s] or 0) + 1
    end
  end
  if t == W + N then
    local machines = {}
    for i, m in pairs(storage.machines) do
      local tl = storage.tally[i] or {}
      table.insert(machines, {name = m.name, position = {m.position.x, m.position.y},
        working = ((tl.working or 0) + (tl.normal or 0)) / N, statuses = tl})
    end
    local res = {log = storage.log, ticks = {warmup = W, window = N}, series_per_s = storage.series,
      outputs = {{count = storage.out_count, rate = storage.out_count * 60 / N,
        lane_rates = {storage.lane_count[1] * 60 / N, storage.lane_count[2] * 60 / N}}},
      machines = machines}
    helpers.write_file("bps-result.json", helpers.table_to_json(res), false)
  end
end)
