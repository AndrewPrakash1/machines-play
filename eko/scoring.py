"""Scores for the four held-out goals in section 5 of the paper."""

from __future__ import annotations


def _carryables(world):
    return [body for body in world.dynamics if body.alive and body.carryable and not body.is_rock and body.shape != "ring"]


def columns(world, xz_radius=0.42):
    """Vertical stacks. A block joins the nearest stack seed within xz_radius."""
    blocks = sorted(_carryables(world), key=lambda body: body.pos[1])
    stacks: list[dict] = []
    for body in blocks:
        placed = None
        for stack in stacks:
            if abs(body.pos[0] - stack["x"]) <= xz_radius and abs(body.pos[2] - stack["z"]) <= xz_radius:
                placed = stack
                break
        if placed is None:
            stacks.append({"x": body.pos[0], "z": body.pos[2], "blocks": [body]})
        else:
            placed["blocks"].append(body)
            n = len(placed["blocks"])
            placed["x"] = sum(b.pos[0] for b in placed["blocks"]) / n
            placed["z"] = sum(b.pos[2] for b in placed["blocks"]) / n
    return stacks


def _on_ground(stack) -> bool:
    bottom = min(body.pos[1] - body.half[1] for body in stack["blocks"])
    return bottom < 1.0


def many_five_towers(world) -> int:
    return sum(1 for stack in columns(world) if _on_ground(stack) and len(stack["blocks"]) >= 5)


def tallest_tower(world) -> int:
    stacks = [stack for stack in columns(world) if _on_ground(stack)]
    if not stacks:
        return 0
    return max(len(stack["blocks"]) for stack in stacks)


def objects_on_spire(world) -> int:
    spire = world.body("Spire")
    if spire is None:
        return 0
    top = spire.pos[1] + spire.half[1]
    count = 0
    for body in world.dynamics:
        if not body.alive or not body.carryable or body is world.player.holding:
            continue
        bottom = body.pos[1] - body.half[1]
        inside = abs(body.pos[0] - spire.pos[0]) <= spire.half[0] - 0.05 and abs(body.pos[2] - spire.pos[2]) <= spire.half[2] - 0.05
        resting = max(abs(v) for v in body.vel) < 1.0
        if inside and resting and (top - 0.35) <= bottom <= top + 2.5:
            count += 1
    return count


def throw_on_spire(world, elapsed, budget, landed) -> float:
    """Seconds still left when the first block rests on the Spire.

    Climbing a mesa first scores zero: the goal forbids using the platforms.
    """
    if world.player.climbed_platform or not landed:
        return 0.0
    return max(0.0, budget - elapsed)
