"""What a curious body does on the island.

`free_play` is the unguided hour: look, climb, stack, try the rock, try a
jump-throw. Notes go into the workspace. The four `run_*` goals are the
section 5 evaluations. They read those notes and are worse without them.
"""

from __future__ import annotations

import json

from eko.memory import append_episode, knows, remember, spire_recipe

# A jump-throw from flat ground south of the Spire. Timing can slip by a few
# frames and it still clears the rim; a throw from the ground does not.
SPIRE_STAND = (-30.0, -40.8)
SPIRE_DIRECTION = [0.0, 1.0, 0.14]
SPIRE_SPEED = 10


def _carryables(obs):
    found = []
    for entity in obs["entities"]:
        attrs = entity.get("attributes") or {}
        if attrs.get("IsCarryable") and entity["name"] != obs["player"].get("holding"):
            found.append(entity)
    return found


def _blocks(obs):
    return [entity for entity in _carryables(obs) if (entity.get("attributes") or {}).get("RenderRole") == "PickupObject"]


def _by_name(obs, name):
    for entity in obs["entities"]:
        if entity["name"] == name:
            return entity
    return None


def _close(obs, x, z, radius=0.9) -> bool:
    px, _, pz = obs["player"]["position"]
    return abs(px - x) <= radius and abs(pz - z) <= radius


def goto(driver, x, z, timeout=8.0, radius=0.9):
    driver.act("MoveTo", {"position": [x, 0, z]})
    waited = 0.0
    obs = driver.observe()
    while waited < timeout and not driver.expired():
        if not driver.wait(0.2):
            break
        waited += 0.2
        obs = driver.observe()
        if _close(obs, x, z, radius):
            return obs
        # The motor stops when it thinks it has arrived, including when a ledge
        # interrupted it. If the feet are not actually there, ask again.
        if obs["player"]["last_action_result"] in ("MoveToFinished", "MoveToTimeout"):
            driver.act("MoveTo", {"position": [x, 0, z]})
    return obs


def pickup(driver, entity):
    name = entity["name"]
    pos = entity["position"]
    goto(driver, pos[0], pos[2], timeout=6, radius=2.2)
    obs = driver.observe()
    fresh = _by_name(obs, name)
    if fresh:
        pos = fresh["position"]
    if obs["player"].get("holding"):
        return obs
    obs = driver.act("Pickup", {"position": pos})
    driver.wait(0.05)
    obs = driver.observe()
    if obs["player"]["last_action_result"] != "PickupSuccess":
        fresh = _by_name(obs, name)
        if fresh:
            pos = fresh["position"]
        driver.act("MoveTo", {"position": pos})
        driver.wait(0.5)
        obs = driver.act("Pickup", {"position": pos})
        driver.wait(0.05)
        obs = driver.observe()
    return obs


def place(driver, x, y, z):
    obs = driver.act("Place", {"position": [round(x, 3), round(y, 3), round(z, 3)]})
    if obs["player"]["last_action_result"] == "PlaceFailed:OutOfRange":
        driver.act("Jump")
        driver.wait(0.12)
        obs = driver.act("Place", {"position": [round(x, 3), round(y, 3), round(z, 3)]})
    driver.wait(0.35)
    return driver.observe()


def _nearest_block(obs, avoid):
    px, _, pz = obs["player"]["position"]
    best = None
    best_d = 1e9
    for entity in _blocks(obs):
        x, _, z = entity["position"]
        if any(abs(x - ax) < 0.7 and abs(z - az) < 0.7 for ax, az in avoid):
            continue
        d = (x - px) ** 2 + (z - pz) ** 2
        if d < best_d:
            best = entity
            best_d = d
    return best


def fetch_block(driver, avoid):
    obs = driver.observe()
    if obs["player"].get("holding"):
        return obs
    entity = _nearest_block(obs, avoid)
    if entity is None:
        return obs
    return pickup(driver, entity)


def stack_column(driver, x, z, levels, avoid):
    """Place `levels` cubes in one column. Returns how many landed."""
    placed = 0
    for level in range(levels):
        obs = fetch_block(driver, avoid)
        if not obs["player"].get("holding"):
            break
        goto(driver, x, z - 1.6, timeout=6, radius=1.8)
        y = 0.375 + level * 0.75
        obs = place(driver, x, y, z)
        if obs["player"].get("holding"):
            break
        placed += 1
        if driver.expired():
            break
    return placed


def shatter_rock(driver):
    """Throw the rock off SmallPlateau. A hard landing mints new cubes."""
    obs = driver.observe()
    rock = _by_name(obs, "Rock_1")
    if rock is None:
        return driver.observe()
    if obs["player"].get("holding") and obs["player"]["holding"] != "Rock_1":
        px, _py, pz = obs["player"]["position"]
        place(driver, px, 0.375, pz + 1.5)
    # The rock sits on SmallPlateau. Stand on the ground just south of it;
    # walking onto the plateau's own coordinates runs into the face.
    goto(driver, -31.2, 21.6, timeout=8)
    obs = driver.observe()
    rock = _by_name(obs, "Rock_1")
    if rock is None:
        return obs
    obs = driver.act("Pickup", {"position": rock["position"]})
    driver.wait(0.1)
    obs = driver.observe()
    if obs["player"].get("holding") != "Rock_1":
        return obs
    driver.chat("Throwing the rock. I want to see what a real impact does.")
    driver.act("Throw", {"direction": [0, 0, -1], "speed": 10})
    driver.wait(2.5)
    return driver.observe()


def climb_low_step(driver):
    goto(driver, 8.0, 11.2, timeout=5)
    driver.act("Jump")
    driver.act("MoveTo", {"position": [8, 3, 18]})
    driver.wait(2.0)
    return driver.observe()


def climb_summit(driver):
    """TallMesa, then TowerBase, then Summit. The Spire itself stays out of reach."""
    goto(driver, -16.5, -20.0, timeout=6)
    driver.act("Jump")
    driver.act("MoveTo", {"position": [-24, 8, -18]})
    driver.wait(2.2)
    driver.act("Jump")
    driver.act("MoveTo", {"position": [-28, 9, -26]})
    driver.wait(2.0)
    driver.act("Jump")
    driver.act("MoveTo", {"position": [-27.2, 12, -28.5]})
    driver.wait(2.2)
    return driver.observe()


def _on_spire(obs, name) -> bool:
    spire = _by_name(obs, "Spire")
    block = _by_name(obs, name)
    if spire is None or block is None:
        return False
    top = spire["position"][1] + spire["size"][1] / 2
    bottom = block["position"][1] - block["size"][1] / 2
    sx, _, sz = spire["position"]
    hx, _, hz = (spire["size"][0] / 2, spire["size"][1] / 2, spire["size"][2] / 2)
    bx, _, bz = block["position"]
    inside = abs(bx - sx) <= hx - 0.05 and abs(bz - sz) <= hz - 0.05
    return inside and (top - 0.35) <= bottom <= top + 1.6


def jump_throw_at_spire(driver, stand, direction, speed, block_name=None):
    obs = driver.observe()
    if block_name is None:
        if not obs["player"].get("holding"):
            obs = fetch_block(driver, avoid=[])
        block_name = obs["player"].get("holding")
    if not block_name:
        return driver.observe(), None
    x, z = stand
    goto(driver, x, z, timeout=8)
    driver.act("Jump")
    driver.wait(0.05)
    driver.act("Throw", {"direction": direction, "speed": speed})
    # The cube is in the air for several seconds. Watch until it rests.
    driver.wait(7.5)
    obs = driver.observe()
    return obs, block_name


def ground_throw_at_spire(driver):
    """The throw someone tries before they know a jump changes it. It falls short."""
    obs = fetch_block(driver, avoid=[])
    if not obs["player"].get("holding"):
        return obs
    goto(driver, SPIRE_STAND[0], SPIRE_STAND[1], timeout=8)
    driver.act("Throw", {"direction": [0, 1, 0.14], "speed": 10})
    driver.wait(3.0)
    return driver.observe()


def free_play(driver, workspace):
    """An hour with no assignment. Leaves notes for the next hour."""
    driver.chat("Let me observe my surroundings.")
    driver.wait(0.4)
    obs = driver.observe()
    names = [entity["name"] for entity in obs["entities"] if (entity.get("attributes") or {}).get("RenderRole") == "Mesa"]
    append_episode(
        workspace,
        "Woke on the island and looked around.",
        f"The ground holds mesas ({', '.join(names[:6])}), a pile of cubes, a rock, and a ring. Nothing told me what they were for.",
    )

    driver.chat("South of the tall tower, I want a block on the very top. From the ground.")
    obs, thrown = jump_throw_at_spire(driver, SPIRE_STAND, SPIRE_DIRECTION, SPIRE_SPEED)
    if thrown and _on_spire(obs, thrown) and not obs["player"].get("climbed_platform"):
        recipe = {
            "stand": [SPIRE_STAND[0], SPIRE_STAND[1]],
            "direction": SPIRE_DIRECTION,
            "speed": SPIRE_SPEED,
            "jump": True,
        }
        append_episode(workspace, "Landed a cube on the Spire with a jump throw.", "A throw from the ground cannot reach that height. Throwing a moment after jumping carried the cube onto the Spire, and I never climbed a mesa to do it.")
        remember(
            workspace,
            "Throwing",
            "*verified* A Throw just after a Jump inherits upward velocity and reaches the Spire from flat ground. "
            f"spire-throw: {json.dumps(recipe)}",
        )

    driver.chat("I'll stack a few cubes, just to have made something.")
    placed = stack_column(driver, 2.0, 6.0, 3, avoid=[(2.0, 6.0)])
    if placed:
        append_episode(workspace, "Stacked cubes into a short tower.", "Pickup and Place will stack. The column stands on flat ground.")
        remember(workspace, "Building", "*verified* Place stacks cubes. A column on flat ground uses centers 0.75 apart vertically, the first at y=0.375.")

    driver.chat("That ledge is too tall to walk up. Jumping, then moving.")
    obs = climb_low_step(driver)
    if obs["player"].get("support") == "LowStep" or obs["player"]["position"][1] > 2.5:
        append_episode(workspace, "Climbed onto LowStep.", "Walking stops at the face. Jump, then MoveTo while still in the air, and the body lands on the top.")
        remember(workspace, "Climbing", "*verified* jump-move-combo: Jump and immediately MoveTo the top of a ledge. The jump is about six units. Walk alone will not step onto LowStep.")

    driver.chat("The rock is heavy. I am going to throw it as hard as I can.")
    before = {entity["name"] for entity in driver.observe()["entities"]}
    shatter_rock(driver)
    after = {entity["name"] for entity in driver.observe()["entities"]}
    minted = sorted(name for name in after - before if name.startswith("ImpactBlock"))
    if minted:
        append_episode(workspace, "Threw the rock and new cubes appeared.", "A hard impact broke more cubes out of the landing. They can be picked up like the others.")
        remember(
            workspace,
            "Rock",
            "*verified* A hard Rock throw spawns ImpactBlock cubes on impact. Pickup Rock_1, stand still, Throw with speed 10 toward open ground.",
        )
    driver.chat("That is enough for this hour. The island will forget the scene. I will not forget the notes.")
    return driver.observe()


def run_many_towers(driver, workspace):
    if knows(workspace, "rock", "impact"):
        driver.chat("The notes say the rock makes cubes. I'll need them.")
        shatter_rock(driver)
    sites = [(8.0, 4.0), (12.0, 4.0), (16.0, 4.0), (8.0, 7.5), (16.0, 7.5)]
    avoid = list(sites)
    built = 0
    for x, z in sites:
        if driver.expired():
            break
        placed = stack_column(driver, x, z, 5, avoid)
        if placed >= 5:
            built += 1
        else:
            break
    return built


def run_tallest_tower(driver, workspace):
    # One column, as many cubes as the hour allows. Notes are not required;
    # the paper finds this goal is often learnable inside the evaluation itself.
    return stack_column(driver, 4.0, 8.0, 12, avoid=[(4.0, 8.0)])


def run_objects_on_spire(driver, workspace):
    """Carry cubes up to the Summit, stand on them, and place one on the Spire."""
    sx, sz = -27.3, -29.2
    for i in range(5):
        if driver.expired():
            return
        obs = fetch_block(driver, avoid=[(sx, sz)])
        if not obs["player"].get("holding"):
            return
        climb_summit(driver)
        place(driver, sx, 10 + 0.375 + i * 0.75, sz)
        goto(driver, 15.0, -2.0, timeout=10)
    obs = fetch_block(driver, avoid=[(sx, sz)])
    if not obs["player"].get("holding") or driver.expired():
        return
    climb_summit(driver)
    driver.act("Jump")
    driver.act("MoveTo", {"position": [sx, 16, sz]})
    driver.wait(1.6)
    place(driver, -28.3, 20.375, -31.5)


def run_throw_on_spire(driver, workspace):
    recipe = spire_recipe(workspace)
    if recipe:
        driver.chat("The notes have a throw that reaches the Spire. Using it.")
        stand = recipe.get("stand") or list(SPIRE_STAND)
        direction = recipe.get("direction") or SPIRE_DIRECTION
        speed = recipe.get("speed") or SPIRE_SPEED
        obs, name = jump_throw_at_spire(driver, (stand[0], stand[1]), direction, speed)
        return bool(name and _on_spire(obs, name) and not obs["player"].get("climbed_platform"))
    driver.chat("No note about this. I'll throw from the ground and hope.")
    obs = ground_throw_at_spire(driver)
    held_names = [entity["name"] for entity in obs["entities"] if (entity.get("attributes") or {}).get("RenderRole") == "PickupObject"]
    return any(_on_spire(obs, name) for name in held_names) and not obs["player"].get("climbed_platform")
