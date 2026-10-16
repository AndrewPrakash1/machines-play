"""Mesa island.

Geometry, object roster, and action rules follow the island in
Cloos et al., "Is this machine playing?" (arXiv:2610.07130): twelve cubes,
a rock that shatters into new cubes, a ring, and six text actions.

Character gravity is world gravity times the engine's character multiplier,
so JumpPower 50 reaches about 6.25 units — the six-unit jump the paper measures.
Throws add the thrower's velocity scaled by 0.35, which is the mid-air boost
agents found and the designers had not planned.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field

from eko.vec import add, clamp, dist, euler_matrix, length, mul, norm, rotate_euler, sub

DT = 1.0 / 60.0
WORLD_GRAVITY = 10.0
CHARACTER_GRAVITY = WORLD_GRAVITY * 20.0
WALK_SPEED = 16.0
JUMP_SPEED = 50.0
AIR_ACCEL = 220.0
TERMINAL_FALL = 100.0
MOVE_TIMEOUT = 8.0
MOVE_EPSILON = 0.5
AUTOSTEP = 1.05
PICKUP_RANGE = 6.0
PLACE_RANGE = 7.0
HOLD_OFFSET = (0.0, 3.5, 0.0)
THROW_SPAWN_Y = 2.5
THROW_FORWARD = 1.75
THROW_UP = 6.0
THROW_CARRY = 0.35
THROW_GRACE = 0.18
MIN_THROW_SPEED = 0.0
MAX_THROW_SPEED = 10.0
PLAYER_HALF = (0.5, 1.0, 0.5)
SPAWN = (0.0, 5.0, 0.0)
OOB_Y = -200.0
BLOCK = 0.75
ROCK_MIN_SPEED = 6.0
ROCK_MIN_ENERGY = 3000.0
ROCK_ENERGY_PER_CUBE = 3000.0
ROCK_MAX_CUBES = 8
ROCK_COOLDOWN = 0.35
MAX_BODIES = 220

SAND = (214 / 255, 186 / 255, 128 / 255)
SLATE = (148 / 255, 136 / 255, 124 / 255)
YELLOW = (232 / 255, 192 / 255, 74 / 255)
ROCK_COLOR = (52 / 255, 49 / 255, 44 / 255)
MESA_COLOR = (200 / 255, 160 / 255, 100 / 255)
GROUND_COLOR = (85 / 255, 239 / 255, 196 / 255)
OCEAN_COLOR = (52 / 255, 128 / 255, 168 / 255)
PLAYER_COLOR = (240 / 255, 230 / 255, 210 / 255)


def _rgb(r, g, b):
    return (r / 255, g / 255, b / 255)


@dataclass
class Body:
    name: str
    pos: list
    half: tuple
    size: tuple
    vel: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rot: list = field(default_factory=lambda: [0.0, 0.0, 0.0])  # pitch, yaw, roll degrees
    mass: float = 1.0
    friction: float = 0.9
    restitution: float = 0.03
    anchored: bool = False
    can_collide: bool = True
    solid: bool = True
    decorative: bool = False
    query: bool = True
    color: tuple = SLATE
    shape: str = "block"
    role: str = "Part"
    carryable: bool = False
    color_name: str = "Slate"
    spheres: list = field(default_factory=list)  # (ox, oy, oz, radius) in local space
    sleeping: bool = False
    supported: bool = False
    is_rock: bool = False
    impact_ignore_until: float = 0.0
    last_impact_at: float = -1e9
    grace_until: float = -1.0
    spin: float = 0.0
    alive: bool = True

    def aabb(self):
        if self.spheres and self.shape == "ring":
            r = 0.0
            for ox, oy, oz, rad in self.spheres:
                world = add(self.pos, rotate_euler((ox, oy, oz), *self.rot))
                r = max(r, abs(world[0] - self.pos[0]) + rad, abs(world[2] - self.pos[2]) + rad)
            hy = max(abs(rotate_euler((ox, oy, oz), *self.rot)[1]) + rad for ox, oy, oz, rad in self.spheres)
            return (
                (self.pos[0] - r, self.pos[1] - hy, self.pos[2] - r),
                (self.pos[0] + r, self.pos[1] + hy, self.pos[2] + r),
            )
        return (
            (self.pos[0] - self.half[0], self.pos[1] - self.half[1], self.pos[2] - self.half[2]),
            (self.pos[0] + self.half[0], self.pos[1] + self.half[1], self.pos[2] + self.half[2]),
        )

    def snapshot(self):
        return {
            "pos": list(self.pos),
            "vel": [0.0, 0.0, 0.0],
            "rot": list(self.rot),
            "anchored": self.anchored,
            "can_collide": True,
            "sleeping": self.sleeping,
            "grace_until": -1.0,
            "spin": 0.0,
        }

    def restore(self, snap):
        self.pos[:] = snap["pos"]
        self.vel[:] = [0.0, 0.0, 0.0]
        self.rot[:] = snap["rot"]
        self.anchored = snap["anchored"]
        self.can_collide = True
        self.sleeping = snap["sleeping"]
        self.grace_until = -1.0
        self.spin = 0.0
        self.alive = True
        self.supported = True


@dataclass
class Player:
    name: str = "Eko"
    pos: list = field(default_factory=lambda: list(SPAWN))
    vel: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    grounded: bool = False
    move_target: tuple | None = None
    move_deadline: float = 0.0
    jump_until: float = 0.0
    holding: Body | None = None
    last_action: str = "Ready"
    support_name: str = ""
    support_role: str = ""
    climbed_platform: bool = False
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class World:
    def __init__(self, settle=True):
        self.time = 0.0
        self.tick = 0
        self.player = Player()
        self.statics: list[Body] = []
        self.dynamics: list[Body] = []
        self._original_names: list[str] = []
        self._snapshots: dict[str, dict] = {}
        self.events: list[str] = []
        self.chat: list[dict] = []
        self._placing: list[dict] = []
        self._next_impact = 13
        self.session: str | None = None
        self._build()
        if settle:
            # Let the spilled block pile come to rest before the hour begins.
            # The rock is not armed until this is over, so the drop cannot mint cubes.
            self.advance(3.0)
            for body in self.dynamics:
                if body.supported or length(body.vel) < 0.4:
                    body.vel[:] = [0.0, 0.0, 0.0]
                    body.sleeping = True
            self._original_names = [b.name for b in self.dynamics]
            self._snapshots = {b.name: b.snapshot() for b in self.dynamics}
            rock = self.body("Rock_1")
            if rock:
                rock.impact_ignore_until = self.time
            self.player.pos[:] = list(SPAWN)
            self.player.vel[:] = [0.0, 0.0, 0.0]
            self.player.grounded = False
            self.advance(1.2)
            self.player.climbed_platform = False
            self.events.clear()

    # ------------------------------------------------------------------ build
    def _build(self):
        ocean = self._static(
            "Ocean", (600, 0.45, 600), (0, -0.5 - 0.225, 0), OCEAN_COLOR, "Ocean", solid=False, decorative=True
        )
        ocean.shape = "block"
        ground = [
            ("GroundCenter", (96, 10, 100), (-2, -5, 0)),
            ("GroundN", (42, 10, 14), (10, -5, 56)),
            ("GroundS", (36, 10, 14), (-12, -5, -55)),
            ("GroundW", (14, 10, 40), (-56, -5, -3)),
            ("GroundE", (10, 10, 58), (48, -5, 5)),
        ]
        for name, size, pos in ground:
            self._static(name, size, pos, GROUND_COLOR, "Ground")
        walls = [
            ("BoundaryNorth", (160, 80, 6), (0, 40, 83)),
            ("BoundarySouth", (160, 80, 6), (0, 40, -83)),
            ("BoundaryEast", (6, 80, 160), (83, 40, 0)),
            ("BoundaryWest", (6, 80, 160), (-83, 40, 0)),
        ]
        for name, size, pos in walls:
            self._static(name, size, pos, (1, 1, 1), "Boundary", query=False)
        mesas = [
            ("LowStep", (8, 2, 10), (8, 1, 18)),
            ("LargeMesa", (20, 4, 16), (20, 2, 20)),
            ("SmallPlateau", (10, 2, 8), (-30, 1, 28)),
            ("SteppingStone", (8, 2.5, 8), (-18, 1.25, -12)),
            ("Ridge", (6, 3, 25), (35, 1.5, -10)),
            ("TallMesa", (12, 6, 10), (-25, 3, -20)),
            ("HighShelf", (10, 7, 8), (25, 3.5, 28)),
            ("Peak", (5, 11, 5), (28, 5.5, 32)),
            ("TowerBase", (8, 7, 8), (-28, 3.5, -26)),
            ("Summit", (6, 10, 6), (-28, 5, -30)),
            ("Spire", (4, 20, 4), (-30, 10, -33)),
        ]
        for name, size, pos in mesas:
            self._static(name, size, pos, MESA_COLOR, "Mesa")

        pile = [
            (14.5, 6.5, -1.9),
            (15.2, 6.9, -1.3),
            (15.8, 7.3, -1.8),
            (14.8, 7.8, -0.9),
            (15.5, 8.2, -1.2),
            (15.0, 8.7, -1.6),
            (14.7, 9.1, -1.1),
            (15.6, 9.6, -1.5),
            (15.1, 10.0, -0.8),
            (15.3, 10.5, -1.3),
            (14.9, 11.0, -1.7),
            (15.4, 11.4, -1.0),
        ]
        for i, pos in enumerate(pile, start=1):
            self._block(f"Block_{i}", pos)

        rock = self._block("Rock_1", (-31.4, 3.05, 26.9), size=(3.2, 2.1, 2.8), color=ROCK_COLOR, role="Rock")
        rock.mass = 8.0 * 3.2 * 2.1 * 2.8
        rock.restitution = 0.0
        rock.is_rock = True
        rock.color_name = "Slate"
        rock.impact_ignore_until = 1.0e9  # armed after settle

        ring = self._block(
            "Ring_1",
            (40.0, 0.28, -42.0),
            size=(3.6, 0.56, 3.6),
            color=YELLOW,
            role="Ring",
            mass=2.0,
            friction=0.35,
            restitution=0.18,
        )
        ring.shape = "ring"
        ring.color_name = "Yellow"
        ring.rot[:] = [0.0, 32.0, 0.0]
        ring.half = (1.8, 0.28, 1.8)
        ring.spheres = []
        for i in range(16):
            ang = (i / 16) * math.tau
            ring.spheres.append((math.cos(ang) * 1.45, 0.0, math.sin(ang) * 1.45, 0.28))

    def _static(self, name, size, pos, color, role, solid=True, decorative=False, query=True):
        half = (size[0] / 2, size[1] / 2, size[2] / 2)
        body = Body(
            name=name,
            pos=list(pos),
            half=half,
            size=tuple(size),
            anchored=True,
            can_collide=solid and not decorative,
            solid=solid and not decorative,
            decorative=decorative,
            query=query,
            color=color,
            role=role,
            mass=0.0,
            sleeping=True,
        )
        self.statics.append(body)
        return body

    def _block(self, name, pos, size=(BLOCK, BLOCK, BLOCK), color=SLATE, role="PickupObject", mass=None, friction=0.9, restitution=0.03):
        half = (size[0] / 2, size[1] / 2, size[2] / 2)
        if mass is None:
            mass = 0.7 * size[0] * size[1] * size[2]
        body = Body(
            name=name,
            pos=list(pos),
            half=half,
            size=tuple(size),
            mass=mass,
            friction=friction,
            restitution=restitution,
            color=color,
            role=role,
            carryable=True,
            shape="block",
        )
        self.dynamics.append(body)
        return body

    # ------------------------------------------------------------------- queries
    def body(self, name) -> Body | None:
        for group in (self.dynamics, self.statics):
            for body in group:
                if body.name == name and body.alive:
                    return body
        return None

    def parts(self):
        return [b for b in self.statics + self.dynamics if b.alive]

    def _event(self, text):
        self.events.append(text)
        del self.events[:-12]

    def advance(self, seconds):
        steps = int(round(seconds / DT))
        for _ in range(max(0, steps)):
            self.step()

    def reset(self):
        """Restore the island. Workspace memory is not stored here, so it survives."""
        extras = [b for b in self.dynamics if b.name not in self._snapshots]
        self.dynamics = [b for b in self.dynamics if b.name in self._snapshots]
        for body in self.dynamics:
            body.restore(self._snapshots[body.name])
        for body in extras:
            body.alive = False
        self._placing.clear()
        self.player.holding = None
        self.player.pos[:] = list(SPAWN)
        self.player.vel[:] = [0.0, 0.0, 0.0]
        self.player.grounded = False
        self.player.move_target = None
        self.player.support_name = ""
        self.player.support_role = ""
        self.player.climbed_platform = False
        self.player.last_action = "Ready"
        self._next_impact = 13
        rock = self.body("Rock_1")
        if rock:
            rock.impact_ignore_until = self.time
            rock.last_impact_at = -1e9
        self.chat.clear()
        self._event("The island returned to its first morning.")
        self.advance(1.2)
        self.player.climbed_platform = False

    # -------------------------------------------------------------------- actions
    def act(self, action, data=None):
        data = data or {}
        kind = action or ""
        player = self.player
        if kind == "MoveTo":
            pos = _parse_vec(data.get("position"))
            if pos is None:
                player.last_action = "MoveToFailed:InvalidPosition"
                return
            player.move_target = pos
            player.move_deadline = self.time + MOVE_TIMEOUT
            player.last_action = "MoveToStarted"
        elif kind == "Stop":
            player.move_target = None
            player.vel[0] = 0.0
            player.vel[2] = 0.0
            player.last_action = "Stopped"
        elif kind == "Jump":
            player.jump_until = self.time + 0.20
            player.last_action = "Jump"
        elif kind == "Pickup":
            self._pickup(data)
        elif kind == "Place":
            self._place(data)
        elif kind == "Throw":
            self._throw(data)
        else:
            player.last_action = "InvalidAction"

    def say(self, content):
        text = str(content or "").strip()
        if not text:
            return
        self.chat.append({"id": len(self.chat) + 1, "name": self.player.name, "content": text[:500], "time": round(self.time, 3)})
        del self.chat[:-40]
        self._event(f"{self.player.name}: {text[:140]}")

    def _pickup(self, data):
        player = self.player
        if player.holding is not None:
            player.last_action = "PickupFailed:AlreadyHolding"
            return
        if "position" not in data:
            player.last_action = "PickupFailed:MissingPosition"
            return
        target = _parse_vec(data.get("position"))
        if target is None:
            player.last_action = "PickupFailed:InvalidPosition"
            return
        if dist(player.pos, target) > PICKUP_RANGE:
            player.last_action = "PickupFailed:OutOfRange"
            return
        found = None
        found_d = 1.5
        for body in self.dynamics:
            if not body.alive or not body.carryable:
                continue
            d = dist(body.pos, target)
            if d <= found_d:
                found = body
                found_d = d
        if found is None:
            player.last_action = "PickupFailed:NoBlock"
            return
        self._placing = [p for p in self._placing if p["body"] is not found]
        player.holding = found
        found.can_collide = False
        found.anchored = False
        found.sleeping = False
        found.vel[:] = [0.0, 0.0, 0.0]
        found.grace_until = -1.0
        if found.is_rock:
            found.impact_ignore_until = self.time + 0.25
        self._wake_all()
        player.last_action = "PickupSuccess"

    def _place(self, data):
        player = self.player
        block = player.holding
        if block is None:
            player.last_action = "PlaceFailed:EmptyHands"
            return
        if "position" not in data:
            player.last_action = "PlaceFailed:MissingPosition"
            return
        target = _parse_vec(data.get("position"))
        if target is None:
            player.last_action = "PlaceFailed:InvalidPosition"
            return
        if dist(player.pos, target) > PLACE_RANGE:
            player.last_action = "PlaceFailed:OutOfRange"
            return
        rot = _parse_rotation(data.get("rotation"), block.rot)
        if rot is None:
            player.last_action = "PlaceFailed:InvalidRotation"
            return
        if self._occupied(block, target, rot):
            player.last_action = "PlaceFailed:Occupied"
            return
        player.holding = None
        block.can_collide = False
        block.anchored = True
        self._placing.append({
            "body": block,
            "start": list(block.pos),
            "start_rot": list(block.rot),
            "target": target,
            "rot": rot,
            "elapsed": 0.0,
            "duration": 0.30,
        })
        player.last_action = "PlaceSuccess"

    def _throw(self, data):
        player = self.player
        block = player.holding
        if block is None:
            player.last_action = "ThrowFailed:EmptyHands"
            return
        if "direction" not in data:
            player.last_action = "ThrowFailed:MissingDirection"
            return
        direction = _parse_vec(data.get("direction"))
        if direction is None:
            player.last_action = "ThrowFailed:InvalidDirection"
            return
        direction = norm(direction)
        if direction is None:
            player.last_action = "ThrowFailed:InvalidDirection"
            return
        speed = data.get("speed", MAX_THROW_SPEED)
        try:
            speed = float(speed)
        except (TypeError, ValueError):
            speed = MAX_THROW_SPEED
        if speed != speed:
            speed = MAX_THROW_SPEED
        speed = clamp(speed, MIN_THROW_SPEED, MAX_THROW_SPEED)
        player.holding = None
        block.anchored = False
        block.can_collide = False
        block.sleeping = False
        block.pos[:] = list(add(add(player.pos, (0.0, THROW_SPAWN_Y, 0.0)), mul(direction, THROW_FORWARD)))
        carried = mul(tuple(player.vel), THROW_CARRY)
        launch = add(add(mul(direction, speed), (0.0, THROW_UP, 0.0)), carried)
        block.vel[:] = list(launch)
        block.grace_until = self.time + THROW_GRACE
        block.spin = 8.0
        if block.is_rock:
            block.impact_ignore_until = self.time + THROW_GRACE
        self._wake_all()
        player.last_action = "ThrowSuccess"
        self._event(f"Threw {block.name}")

    def _occupied(self, block, target, rot):
        saved_pos, saved_rot = list(block.pos), list(block.rot)
        block.pos[:] = list(target)
        block.rot[:] = list(rot)
        hit = False
        for other in self.parts():
            if other is block or not other.solid or not other.can_collide:
                continue
            if other is self.player.holding:
                continue
            if _overlap_amount(block, other) > 0.04:
                hit = True
                break
        block.pos[:] = saved_pos
        block.rot[:] = saved_rot
        return hit

    def _wake_all(self):
        for body in self.dynamics:
            if body.alive:
                body.sleeping = False

    # ----------------------------------------------------------------------- step
    def step(self):
        self.time += DT
        self.tick += 1
        self._step_player(DT)
        self._integrate_dynamics(DT)
        for _ in range(6):
            self._resolve_dynamics()
        self._sleep_dynamics()
        self._update_held()
        self._update_placing(DT)
        self._end_grace()
        self._cull()
        self._track_climb()

    def _step_player(self, dt):
        player = self.player
        self._steer(player, dt)
        if player.jump_until >= self.time and player.grounded:
            player.vel[1] = JUMP_SPEED
            player.grounded = False
            player.jump_until = 0.0
            player.support_name = ""
        sub = dt / 4.0
        for _ in range(4):
            if not player.grounded:
                player.vel[1] -= CHARACTER_GRAVITY * sub
                if player.vel[1] < -TERMINAL_FALL:
                    player.vel[1] = -TERMINAL_FALL
            else:
                player.vel[1] = 0.0
            self._move_player_xz(sub)
            self._move_player_y(sub)
        self._separate_player()
        if player.move_target is not None:
            flat = math.hypot(player.move_target[0] - player.pos[0], player.move_target[2] - player.pos[2])
            if flat <= MOVE_EPSILON:
                player.move_target = None
                player.vel[0] = 0.0
                player.vel[2] = 0.0
                player.last_action = "MoveToFinished"
            elif self.time > player.move_deadline:
                player.move_target = None
                player.vel[0] = 0.0
                player.vel[2] = 0.0
                player.last_action = "MoveToTimeout"
        if player.pos[1] < OOB_Y:
            player.pos[:] = list(SPAWN)
            player.vel[:] = [0.0, 0.0, 0.0]
            player.grounded = False
            player.move_target = None
            player.last_action = "Respawned"
            self._event("Fell into the ocean and woke at spawn.")

    def _steer(self, player, dt):
        if player.move_target is None:
            if player.grounded:
                player.vel[0] *= 0.5
                player.vel[2] *= 0.5
            return
        dx = player.move_target[0] - player.pos[0]
        dz = player.move_target[2] - player.pos[2]
        mag = math.hypot(dx, dz)
        if mag < 1e-6:
            return
        wish_x = dx / mag * WALK_SPEED
        wish_z = dz / mag * WALK_SPEED
        if player.grounded:
            player.vel[0] = wish_x
            player.vel[2] = wish_z
            return
        # Air control is what makes a jump land on a ledge instead of a wall.
        ax = wish_x - player.vel[0]
        az = wish_z - player.vel[2]
        amag = math.hypot(ax, az)
        if amag > 1e-6:
            cap = AIR_ACCEL * dt
            scale = min(1.0, cap / amag)
            player.vel[0] += ax * scale
            player.vel[2] += az * scale

    def _move_player_xz(self, sub):
        player = self.player
        nx = player.pos[0] + player.vel[0] * sub
        nz = player.pos[2] + player.vel[2] * sub
        if not self._player_hits(nx, player.pos[1], nz):
            player.pos[0] = nx
            player.pos[2] = nz
            return
        if player.grounded:
            for lift in (0.25, 0.5, 0.75, 1.0, AUTOSTEP):
                raised = player.pos[1] + lift
                if self._player_hits(nx, raised, nz):
                    continue
                feet = raised - PLAYER_HALF[1]
                surface = self._surface_y(nx, nz, feet + 0.2)
                if surface is None or feet < surface - 0.05 or feet > surface + 0.35:
                    continue
                player.pos[0] = nx
                player.pos[1] = surface + PLAYER_HALF[1]
                player.pos[2] = nz
                return
        if not self._player_hits(nx, player.pos[1], player.pos[2]):
            player.pos[0] = nx
        elif not self._player_hits(player.pos[0], player.pos[1], nz):
            player.pos[2] = nz

    def _move_player_y(self, sub):
        player = self.player
        ny = player.pos[1] + player.vel[1] * sub
        if not self._player_hits(player.pos[0], ny, player.pos[2]):
            player.pos[1] = ny
            if player.vel[1] <= 0:
                surface = self._surface_y(player.pos[0], player.pos[2], player.pos[1] - PLAYER_HALF[1] + 0.05)
                feet = player.pos[1] - PLAYER_HALF[1]
                if surface is not None and 0 <= feet - surface <= 0.25:
                    player.pos[1] = surface + PLAYER_HALF[1]
                    player.vel[1] = 0.0
                    player.grounded = True
                    return
            player.grounded = False
            return
        if player.vel[1] <= 0:
            surface = self._surface_y(player.pos[0], player.pos[2], ny - PLAYER_HALF[1] + 0.4)
            if surface is None:
                surface = ny - PLAYER_HALF[1]
            player.pos[1] = surface + PLAYER_HALF[1]
            player.vel[1] = 0.0
            player.grounded = True
        else:
            player.vel[1] = 0.0

    def _separate_player(self):
        """Push the body out of a ledge it has clipped, so walking can resume."""
        player = self.player
        for _ in range(3):
            pmin = (player.pos[0] - PLAYER_HALF[0], player.pos[1] - PLAYER_HALF[1], player.pos[2] - PLAYER_HALF[2])
            pmax = (player.pos[0] + PLAYER_HALF[0], player.pos[1] + PLAYER_HALF[1], player.pos[2] + PLAYER_HALF[2])
            best = None
            solids = [body for body in self.statics if body.solid]
            solids += [
                body for body in self.dynamics
                if body.alive and body.can_collide and body.solid and not body.spheres and body is not self.player.holding
            ]
            for body in solids:
                found = _aabb_mtv_boxes(pmin, pmax, *body.aabb())
                if found and found[1] > 0.02 and (best is None or found[1] > best[1]):
                    best = found
            if best is None:
                return
            normal, pen = best
            player.pos[0] += normal[0] * pen
            player.pos[1] += normal[1] * pen
            player.pos[2] += normal[2] * pen

    def _player_hits(self, x, y, z):
        pmin = (x - PLAYER_HALF[0], y - PLAYER_HALF[1], z - PLAYER_HALF[2])
        pmax = (x + PLAYER_HALF[0], y + PLAYER_HALF[1], z + PLAYER_HALF[2])
        held = self.player.holding
        for body in self.statics:
            if not body.solid:
                continue
            if _aabb_pen(pmin, pmax, *body.aabb()) > 0.001:
                return True
        for body in self.dynamics:
            if body is held or not body.alive or not body.can_collide or not body.solid:
                continue
            if body.spheres:
                for center, radius in self._world_spheres(body):
                    if _sphere_aabb(center, radius, pmin, pmax):
                        return True
            elif _aabb_pen(pmin, pmax, *body.aabb()) > 0.02:
                return True
        return False

    def _surface_y(self, x, z, under):
        """Highest solid top at (x, z) that is at or just below `under`."""
        best = None
        best_role = ""
        best_name = ""
        foot = (x, under, z)
        for body in self.statics:
            if not body.solid:
                continue
            mn, mx = body.aabb()
            if x < mn[0] - 0.05 or x > mx[0] + 0.05 or z < mn[2] - 0.05 or z > mx[2] + 0.05:
                continue
            top = mx[1]
            if top <= under + 0.08 and (best is None or top > best):
                best = top
                best_role = body.role
                best_name = body.name
        for body in self.dynamics:
            if body is self.player.holding or not body.alive or not body.can_collide:
                continue
            if body.spheres:
                for center, radius in self._world_spheres(body):
                    dx = x - center[0]
                    dz = z - center[2]
                    horizontal = math.hypot(dx, dz)
                    if horizontal > radius:
                        continue
                    top = center[1] + math.sqrt(max(0.0, radius * radius - horizontal * horizontal))
                    if top <= under + 0.08 and (best is None or top > best):
                        best = top
                        best_role = body.role
                        best_name = body.name
                continue
            mn, mx = body.aabb()
            if x < mn[0] - 0.05 or x > mx[0] + 0.05 or z < mn[2] - 0.05 or z > mx[2] + 0.05:
                continue
            top = mx[1]
            if top <= under + 0.08 and (best is None or top > best):
                best = top
                best_role = body.role
                best_name = body.name
        if best is not None and self.player.grounded:
            self.player.support_name = best_name
            self.player.support_role = best_role
        return best

    def _track_climb(self):
        player = self.player
        if not player.grounded:
            return
        if player.support_role == "Mesa" and (player.pos[1] - PLAYER_HALF[1]) > 1.2:
            player.climbed_platform = True

    def _integrate_dynamics(self, dt):
        for body in self.dynamics:
            if not body.alive or body.anchored or body.sleeping or body is self.player.holding:
                continue
            if not body.can_collide and body.grace_until < self.time and body is not self.player.holding:
                body.can_collide = True
            body.vel[1] -= WORLD_GRAVITY * dt
            if body.vel[1] < -80:
                body.vel[1] = -80
            body.pos[0] += body.vel[0] * dt
            body.pos[1] += body.vel[1] * dt
            body.pos[2] += body.vel[2] * dt
            if body.spin:
                body.rot[1] = (body.rot[1] + body.spin * dt * 40) % 360
            body.supported = False

    def _resolve_dynamics(self):
        dynamics = [b for b in self.dynamics if b.alive and b.can_collide and not b.anchored and b is not self.player.holding]
        solids = [b for b in self.statics if b.solid]
        for body in dynamics:
            for static in solids:
                self._collide(body, static, static_b=True)
        for i, a in enumerate(dynamics):
            for b in dynamics[i + 1 :]:
                self._collide(a, b, static_b=False)

    def _collide(self, a: Body, b: Body, static_b: bool):
        if a.spheres and not b.spheres:
            for center, radius in self._world_spheres(a):
                self._sphere_box(a, center, radius, b, static_b, sphere_is_a=True)
            return
        if b.spheres and not a.spheres:
            for center, radius in self._world_spheres(b):
                self._sphere_box(b, center, radius, a, static_b=False, sphere_is_a=True)
            return
        if a.spheres and b.spheres:
            return
        npen = _box_mtv(a, b)
        if npen is None:
            return
        normal, pen = npen
        self._apply_contact(a, b, normal, pen, static_b, length(a.vel))

    def _sphere_box(self, sphere_body, center, radius, box_body, static_b, sphere_is_a):
        mn, mx = box_body.aabb()
        closest = (
            clamp(center[0], mn[0], mx[0]),
            clamp(center[1], mn[1], mx[1]),
            clamp(center[2], mn[2], mx[2]),
        )
        delta = sub(center, closest)
        mag = length(delta)
        if mag >= radius:
            return
        if mag > 1e-6:
            normal = (delta[0] / mag, delta[1] / mag, delta[2] / mag)
            pen = radius - mag
        else:
            # Center is inside the box: leave along the nearest face.
            faces = [
                (mn[0] - center[0], (-1.0, 0.0, 0.0)),
                (center[0] - mx[0], (1.0, 0.0, 0.0)),
                (mn[1] - center[1], (0.0, -1.0, 0.0)),
                (center[1] - mx[1], (0.0, 1.0, 0.0)),
                (mn[2] - center[2], (0.0, 0.0, -1.0)),
                (center[2] - mx[2], (0.0, 0.0, 1.0)),
            ]
            pen_face, normal = min(faces, key=lambda item: abs(item[0]))
            pen = abs(pen_face) + radius
        # normal points from the box toward the sphere center.
        if sphere_is_a:
            self._apply_contact(sphere_body, box_body, normal, pen, static_b, length(sphere_body.vel))
        else:
            flipped = mul(normal, -1)
            self._apply_contact(box_body, sphere_body, flipped, pen, False, length(box_body.vel))

    def _apply_contact(self, a: Body, b: Body, normal, pen, static_b, speed_a):
        if pen <= 0:
            return
        inv_a = 0.0 if a.anchored or a.mass <= 0 else 1.0 / a.mass
        inv_b = 0.0 if static_b or b.anchored or b.mass <= 0 else 1.0 / b.mass
        inv = inv_a + inv_b
        if inv <= 0:
            return
        corr = min(pen, 0.12)
        share_a = inv_a / inv
        a.pos[0] += normal[0] * corr * share_a
        a.pos[1] += normal[1] * corr * share_a
        a.pos[2] += normal[2] * corr * share_a
        if not static_b:
            b.pos[0] -= normal[0] * corr * (inv_b / inv)
            b.pos[1] -= normal[1] * corr * (inv_b / inv)
            b.pos[2] -= normal[2] * corr * (inv_b / inv)
        rel = (
            a.vel[0] - (0 if static_b else b.vel[0]),
            a.vel[1] - (0 if static_b else b.vel[1]),
            a.vel[2] - (0 if static_b else b.vel[2]),
        )
        approach = rel[0] * normal[0] + rel[1] * normal[1] + rel[2] * normal[2]
        if approach < 0:
            e = 0.0 if pen < 0.03 and abs(approach) < 1.2 else min(a.restitution, b.restitution if not static_b else a.restitution)
            if static_b:
                e = a.restitution
            j = -(1 + e) * approach / inv
            a.vel[0] += normal[0] * j * inv_a
            a.vel[1] += normal[1] * j * inv_a
            a.vel[2] += normal[2] * j * inv_a
            if not static_b:
                b.vel[0] -= normal[0] * j * inv_b
                b.vel[1] -= normal[1] * j * inv_b
                b.vel[2] -= normal[2] * j * inv_b
                if abs(j) > 0.2:
                    b.sleeping = False
            if abs(j) > 0.2:
                a.sleeping = False
        if normal[1] > 0.55:
            a.supported = True
            if a.vel[1] < 0.4:
                a.vel[1] = 0.0
            damp = min(0.45, a.friction * 6 * DT)
            a.vel[0] *= 1 - damp
            a.vel[2] *= 1 - damp
        if a.is_rock and b.role != "Boundary":
            self._rock_impact(a, speed_a)

    def _rock_impact(self, rock: Body, speed):
        now = self.time
        if now < rock.impact_ignore_until or now - rock.last_impact_at < ROCK_COOLDOWN:
            return
        if speed < ROCK_MIN_SPEED:
            return
        energy = 0.5 * rock.mass * speed * speed
        if energy < ROCK_MIN_ENERGY:
            return
        count = int(max(1, min(ROCK_MAX_CUBES, math.floor(energy / ROCK_ENERGY_PER_CUBE))))
        rock.last_impact_at = now
        self._spawn_impact(tuple(rock.pos), count)
        self._event(f"Rock impact spawned {count} cube{'s' if count != 1 else ''}.")

    def _spawn_impact(self, origin, count):
        for i in range(1, count + 1):
            if len(self.dynamics) >= MAX_BODIES:
                return
            ang = (i / count) * math.tau
            radius = 1.1 + 0.35 * ((i - 1) % 3)
            offset = (math.cos(ang) * radius, 0.9 + 0.15 * ((i - 1) % 2), math.sin(ang) * radius)
            name = f"ImpactBlock_{self._next_impact}"
            self._next_impact += 1
            cube = self._block(name, add(origin, offset))
            cube.vel[:] = [
                math.cos(ang) * (2.5 + i * 0.2),
                4.5 + i * 0.25,
                math.sin(ang) * (2.5 + i * 0.2),
            ]
            cube.sleeping = False

    def _sleep_dynamics(self):
        for body in self.dynamics:
            if not body.alive or body.anchored or body is self.player.holding:
                continue
            if body.grace_until >= self.time:
                continue
            if not body.supported:
                body.sleeping = False
                continue
            if length(body.vel) < 0.28:
                body.vel[:] = [0.0, 0.0, 0.0]
                body.sleeping = True
                body.spin = 0.0

    def _update_held(self):
        held = self.player.holding
        if held is None or not held.alive:
            self.player.holding = None
            return
        held.pos[:] = list(add(self.player.pos, HOLD_OFFSET))
        held.vel[:] = [0.0, 0.0, 0.0]
        held.can_collide = False
        held.sleeping = False

    def _update_placing(self, dt):
        keep = []
        for place in self._placing:
            body = place["body"]
            if not body.alive:
                continue
            place["elapsed"] += dt
            alpha = min(1.0, place["elapsed"] / place["duration"])
            t = 1 - (1 - alpha) * (1 - alpha)
            body.pos[:] = [a + (b - a) * t for a, b in zip(place["start"], place["target"])]
            body.rot[:] = [a + (b - a) * t for a, b in zip(place["start_rot"], place["rot"])]
            if alpha >= 1:
                body.anchored = False
                body.can_collide = True
                body.sleeping = False
                body.vel[:] = [0.0, 0.0, 0.0]
                if body.is_rock:
                    body.impact_ignore_until = self.time + 0.15
            else:
                keep.append(place)
        self._placing = keep

    def _end_grace(self):
        for body in self.dynamics:
            if body.alive and not body.can_collide and body is not self.player.holding and body.grace_until >= 0 and self.time >= body.grace_until and not body.anchored:
                body.can_collide = True

    def _cull(self):
        for body in self.dynamics:
            if body.alive and body.pos[1] < OOB_Y and body is not self.player.holding:
                body.alive = False
                if self.player.holding is body:
                    self.player.holding = None
                self._event(f"{body.name} fell into the ocean.")
        self.dynamics = [b for b in self.dynamics if b.alive]
        self._placing = [p for p in self._placing if p["body"].alive]

    def _world_spheres(self, body):
        out = []
        for ox, oy, oz, radius in body.spheres:
            out.append((add(body.pos, rotate_euler((ox, oy, oz), *body.rot)), radius))
        return out

    # ------------------------------------------------------------------ observation
    def observe(self):
        entities = []
        for index, body in enumerate(self.parts()):
            if not body.query:
                continue
            entities.append(self._entity(index, body))
        holding = self.player.holding.name if self.player.holding else None
        return {
            "tick": self.tick,
            "time": round(self.time, 3),
            "game_status": "running",
            "player": {
                "id": self.player.agent_id,
                "name": self.player.name,
                "position": _round(self.player.pos),
                "velocity": _round(self.player.vel),
                "grounded": self.player.grounded,
                "holding": holding,
                "support": self.player.support_name,
                "last_action_result": self.player.last_action,
                "climbed_platform": self.player.climbed_platform,
            },
            "entities": entities,
            "events": list(self.events),
        }

    def spectate(self):
        view = []
        for body in self.parts():
            if not body.query and body.role == "Boundary":
                continue
            view.append({
                "name": body.name,
                "position": _round(body.pos),
                "size": [round(v, 3) for v in body.size],
                "rotation": [round(v, 2) for v in body.rot],
                "color": [round(c, 4) for c in body.color],
                "shape": body.shape,
                "role": body.role,
                "anchored": body.anchored,
            })
        return {
            "tick": self.tick,
            "time": round(self.time, 3),
            "player": {
                "name": self.player.name,
                "position": _round(self.player.pos),
                "velocity": _round(self.player.vel),
                "holding": self.player.holding.name if self.player.holding else None,
                "last_action_result": self.player.last_action,
                "grounded": self.player.grounded,
                "support": self.player.support_name,
            },
            "chat": list(self.chat[-12:]),
            "events": list(self.events[-8:]),
            "bodies": view,
        }

    def _entity(self, index, body: Body):
        mn, mx = body.aabb()
        return {
            "id": index,
            "name": body.name,
            "entity_type": "part",
            "position": _round(body.pos),
            "size": [round(v, 3) for v in body.size],
            "rotation": [[round(n, 4) for n in row] for row in euler_matrix(*body.rot)],
            "aabb": {"min": _round(mn), "max": _round(mx)},
            "obb": {
                "center": _round(body.pos),
                "half_extents": [round(v, 3) for v in body.half],
            },
            "color": [round(c, 4) for c in body.color],
            "shape": "ring" if body.shape == "ring" else "block",
            "anchored": body.anchored or not body.carryable,
            "attributes": {
                "RenderRole": body.role,
                "IsCarryable": body.carryable,
                "ItemColorName": body.color_name,
            },
        }


def _parse_vec(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        out = (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError):
        return None
    if any(v != v or abs(v) > 1e6 for v in out):
        return None
    return out


def _parse_rotation(value, current):
    if value is None:
        return list(current)
    if isinstance(value, (int, float)):
        if value != value:
            return None
        return [0.0, float(value), 0.0]
    if not isinstance(value, dict):
        return None
    try:
        pitch = float(value.get("pitch", value.get("x", 0.0)) or 0.0)
        yaw = float(value.get("yaw", value.get("y", 0.0)) or 0.0)
        roll = float(value.get("roll", value.get("z", 0.0)) or 0.0)
    except (TypeError, ValueError):
        return None
    if any(v != v for v in (pitch, yaw, roll)):
        return None
    return [pitch, yaw, roll]


def _round(v):
    return [round(float(n), 3) for n in v]


def _aabb_pen(amin, amax, bmin, bmax):
    ox = min(amax[0], bmax[0]) - max(amin[0], bmin[0])
    oy = min(amax[1], bmax[1]) - max(amin[1], bmin[1])
    oz = min(amax[2], bmax[2]) - max(amin[2], bmin[2])
    if ox <= 0 or oy <= 0 or oz <= 0:
        return 0.0
    return min(ox, oy, oz)


def _aabb_mtv_boxes(amin, amax, bmin, bmax):
    ox = min(amax[0], bmax[0]) - max(amin[0], bmin[0])
    oy = min(amax[1], bmax[1]) - max(amin[1], bmin[1])
    oz = min(amax[2], bmax[2]) - max(amin[2], bmin[2])
    if ox <= 0 or oy <= 0 or oz <= 0:
        return None
    ac = ((amin[0] + amax[0]) * 0.5, (amin[1] + amax[1]) * 0.5, (amin[2] + amax[2]) * 0.5)
    bc = ((bmin[0] + bmax[0]) * 0.5, (bmin[1] + bmax[1]) * 0.5, (bmin[2] + bmax[2]) * 0.5)
    if ox <= oy and ox <= oz:
        sign = 1.0 if ac[0] >= bc[0] else -1.0
        return (sign, 0.0, 0.0), ox
    if oy <= ox and oy <= oz:
        sign = 1.0 if ac[1] >= bc[1] else -1.0
        return (0.0, sign, 0.0), oy
    sign = 1.0 if ac[2] >= bc[2] else -1.0
    return (0.0, 0.0, sign), oz


def _box_mtv(a: Body, b: Body):
    return _aabb_mtv_boxes(*a.aabb(), *b.aabb())


def _overlap_amount(a: Body, b: Body):
    if b.spheres or a.spheres:
        # Rim versus box: any sphere intersection counts.
        spheres = a.spheres if a.spheres else b.spheres
        owner = a if a.spheres else b
        other = b if owner is a else a
        mn, mx = other.aabb()
        amount = 0.0
        for ox, oy, oz, radius in spheres:
            center = add(owner.pos, rotate_euler((ox, oy, oz), *owner.rot))
            if _sphere_aabb(center, radius, mn, mx):
                amount = max(amount, radius)
        return amount
    return _aabb_pen(*a.aabb(), *b.aabb())


def _sphere_aabb(center, radius, mn, mx):
    closest = (
        clamp(center[0], mn[0], mx[0]),
        clamp(center[1], mn[1], mx[1]),
        clamp(center[2], mn[2], mx[2]),
    )
    return length(sub(center, closest)) < radius - 1e-4
