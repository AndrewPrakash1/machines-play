import math
import unittest

from eko.world import BLOCK, JUMP_SPEED, CHARACTER_GRAVITY, World


def _gain():
    return (JUMP_SPEED * JUMP_SPEED) / (2 * CHARACTER_GRAVITY)


class IslandTests(unittest.TestCase):
    def test_roster_and_spawn(self):
        world = World()
        names = {body.name for body in world.dynamics}
        self.assertTrue({f"Block_{i}" for i in range(1, 13)} <= names)
        self.assertIn("Rock_1", names)
        self.assertIn("Ring_1", names)
        self.assertLess(world.player.pos[1], 2.5)
        self.assertGreater(world.player.pos[1], 0.5)
        rock = world.body("Rock_1")
        plateau = world.body("SmallPlateau")
        self.assertGreater(rock.pos[1] - rock.half[1], plateau.pos[1] + plateau.half[1] - 0.2)

    def test_jump_is_about_six_units(self):
        world = World()
        world.player.vel[:] = [0, 0, 0]
        start = world.player.pos[1]
        world.act("Jump")
        peak = start
        for _ in range(240):
            world.step()
            peak = max(peak, world.player.pos[1])
        gained = peak - start
        self.assertAlmostEqual(gained, _gain(), delta=0.45)

    def test_jump_move_lands_on_low_step(self):
        world = World()
        # Just south of LowStep, on the ground.
        world.player.pos[:] = [8.0, 1.0, 11.2]
        world.player.vel[:] = [0, 0, 0]
        world.player.grounded = True
        world.act("Jump")
        world.act("MoveTo", {"position": [8, 3, 18]})
        landed = False
        for _ in range(200):
            world.step()
            feet = world.player.pos[1] - 1
            if world.player.grounded and feet > 1.6 and abs(world.player.pos[2] - 18) < 4:
                landed = True
                break
        self.assertTrue(landed, msg=f"player ended at {world.player.pos} support={world.player.support_name}")

    def test_blocks_stack_by_place(self):
        world = World()
        block = world.body("Block_1")
        world.player.pos[:] = [0.0, 1.0, 2.0]
        world.player.grounded = True
        world.player.holding = block
        block.can_collide = False
        world.act("Place", {"position": [0, 0.375, 4]})
        world.advance(0.4)
        self.assertIsNone(world.player.holding)
        self.assertAlmostEqual(block.pos[1], 0.375, delta=0.15)
        other = world.body("Block_2")
        world.player.holding = other
        other.can_collide = False
        world.act("Place", {"position": [0, 1.125, 4]})
        world.advance(1.0)
        self.assertGreater(other.pos[1], 0.9)
        self.assertLess(abs(other.pos[0] - 0), 0.4)

    def test_throw_inherits_upward_velocity(self):
        world = World()
        block = world.body("Block_1")
        world.player.pos[:] = [0.0, 1.0, 0.0]
        world.player.vel[:] = [0, 0, 0]
        world.player.grounded = True
        world.player.holding = block
        block.can_collide = False
        world.act("Throw", {"direction": [0, 1, 0], "speed": 10})
        ground_peak = block.pos[1]
        for _ in range(240):
            world.step()
            ground_peak = max(ground_peak, block.pos[1])

        world = World()
        block = world.body("Block_1")
        world.player.pos[:] = [0.0, 1.0, 0.0]
        world.player.vel[:] = [0, 0, 0]
        world.player.grounded = True
        world.player.holding = block
        block.can_collide = False
        world.act("Jump")
        world.step()
        world.act("Throw", {"direction": [0, 1, 0], "speed": 10})
        air_peak = block.pos[1]
        for _ in range(300):
            world.step()
            air_peak = max(air_peak, block.pos[1])
        self.assertGreater(air_peak, ground_peak + 4.0, msg=f"ground {ground_peak:.2f} air {air_peak:.2f}")

    def test_hard_rock_impact_mints_cubes(self):
        world = World()
        before = {body.name for body in world.dynamics}
        rock = world.body("Rock_1")
        rock.pos[:] = [0.0, 6.0, 0.0]
        rock.vel[:] = [0.0, -14.0, 0.0]
        rock.sleeping = False
        rock.can_collide = True
        rock.impact_ignore_until = 0
        world.advance(2.0)
        after = {body.name for body in world.dynamics}
        minted = [name for name in after - before if name.startswith("ImpactBlock_")]
        self.assertGreaterEqual(len(minted), 1)
        self.assertLessEqual(len(minted), 8)

    def test_ring_hole_lets_a_cube_fall_through(self):
        world = World()
        ring = world.body("Ring_1")
        ring.pos[:] = [0.0, 2.0, 6.0]
        ring.rot[:] = [0.0, 0.0, 0.0]
        ring.vel[:] = [0, 0, 0]
        ring.sleeping = True
        block = world.body("Block_1")
        block.pos[:] = [0.0, 4.0, 6.0]
        block.vel[:] = [0, 0, 0]
        block.sleeping = False
        world.advance(2.0)
        self.assertLess(block.pos[1], 1.2, msg=f"block stuck at {block.pos}")

    def test_reset_removes_impact_cubes_and_restores_the_pile(self):
        world = World()
        rock = world.body("Rock_1")
        saved = list(rock.pos)
        rock.pos[:] = [0.0, 8.0, 0.0]
        rock.vel[:] = [0.0, -16.0, 0.0]
        rock.sleeping = False
        rock.impact_ignore_until = 0
        world.advance(1.5)
        self.assertTrue(any(body.name.startswith("ImpactBlock_") for body in world.dynamics))
        world.reset()
        names = {body.name for body in world.dynamics}
        self.assertFalse(any(name.startswith("ImpactBlock_") for name in names))
        self.assertEqual(len([n for n in names if n.startswith("Block_")]), 12)
        restored = world.body("Rock_1")
        self.assertAlmostEqual(restored.pos[0], saved[0], delta=0.35)
        self.assertAlmostEqual(restored.pos[2], saved[2], delta=0.35)

    def test_observation_lists_the_spire(self):
        world = World()
        obs = world.observe()
        names = {entity["name"] for entity in obs["entities"]}
        self.assertIn("Spire", names)
        self.assertIn("Ring_1", names)
        spire = next(entity for entity in obs["entities"] if entity["name"] == "Spire")
        self.assertEqual(len(spire["rotation"]), 3)
        self.assertIn("min", spire["aabb"])


if __name__ == "__main__":
    unittest.main()
