import unittest

from eko.behaviors import free_play, jump_throw_at_spire, run_many_towers, run_throw_on_spire, SPIRE_DIRECTION, SPIRE_SPEED, SPIRE_STAND
from eko.driver import WorldDriver
from eko.memory import ablate, ensure_workspace, knows, spire_recipe
from eko.scoring import many_five_towers, tallest_tower
from eko.world import World
from pathlib import Path
import tempfile


class LearningTests(unittest.TestCase):
    def test_jump_throw_lands_without_climbing(self):
        world = World()
        driver = WorldDriver(world, seconds=30)
        obs, name = jump_throw_at_spire(driver, SPIRE_STAND, SPIRE_DIRECTION, SPIRE_SPEED)
        self.assertIsNotNone(name)
        from eko.scoring import objects_on_spire
        self.assertGreaterEqual(objects_on_spire(world), 1)
        self.assertFalse(world.player.climbed_platform)
        self.assertLess(driver.elapsed, 30)

    def test_notes_change_what_the_next_hour_can_do(self):
        world = World()
        with tempfile.TemporaryDirectory() as tmp:
            workspace = ensure_workspace(Path(tmp))
            free_play(WorldDriver(world, seconds=80), workspace)
            self.assertTrue(knows(workspace, "rock", "impact"))
            self.assertIsNotNone(spire_recipe(workspace))

            blank = Path(tmp) / "blank"
            ensure_workspace(blank)
            fresh = World()
            run_many_towers(WorldDriver(fresh, seconds=40), blank)
            blank_towers = many_five_towers(fresh)

            learned = World()
            run_many_towers(WorldDriver(learned, seconds=70), workspace)
            learned_towers = many_five_towers(learned)
            self.assertGreaterEqual(blank_towers, 1)
            self.assertGreater(learned_towers, blank_towers)

            thrown = World()
            driver = WorldDriver(thrown, seconds=40)
            landed = run_throw_on_spire(driver, workspace)
            self.assertTrue(landed)
            self.assertFalse(thrown.player.climbed_platform)

            ablate(workspace, "spire-throw")
            self.assertIsNone(spire_recipe(workspace))
            missed = World()
            landed = run_throw_on_spire(WorldDriver(missed, seconds=25), workspace)
            self.assertFalse(landed)

    def test_a_column_can_be_tall(self):
        world = World()
        from eko.behaviors import run_tallest_tower
        run_tallest_tower(WorldDriver(world, seconds=40), Path("/tmp"))
        self.assertGreaterEqual(tallest_tower(world), 4)


if __name__ == "__main__":
    unittest.main()
