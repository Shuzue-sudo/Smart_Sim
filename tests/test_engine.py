import math
from pathlib import Path
import tempfile
import unittest

from ostrov.engine import Creature, World
from ostrov.storage import load, save


class EngineTests(unittest.TestCase):
    def test_geometry(self):
        world = World()
        for i in range(360):
            angle = math.radians(i)
            self.assertTrue(world.contains(30 * math.cos(angle), 30 * math.sin(angle)))
            self.assertFalse(world.contains(116 * math.cos(angle), 116 * math.sin(angle)))
        self.assertAlmostEqual(world.radius_at(0), world.radius_at(math.tau))

    def test_fall_ends_world_and_cannot_be_undone(self):
        world = World()
        world.move('rosmontis', 200, 0)
        self.assertTrue(world.ended)
        self.assertEqual(world.creatures['rosmontis'].health, 0)
        world.advance(100)
        self.assertEqual(world.time, 0)
        with self.assertRaises(ValueError):
            world.move('rosmontis', 0, 0)

    def test_shift_preserves_safe_zone_and_state(self):
        world = World(7)
        resident = world.creatures['rosmontis']
        resident.x = 30
        resident.memory.append('Воспоминание')
        resident.inventory.append('Камень')
        resident.relationships['guest'] = 2
        resident.health = 42
        world.add_creature(Creature('guest', 'Гость', 50, 0))
        old_boundary = world.boundary[:]
        world.advance(world.shift_at)
        self.assertIs(world.creatures['rosmontis'], resident)
        self.assertEqual(resident.memory, ['Воспоминание'])
        self.assertEqual(resident.inventory, ['Камень'])
        self.assertEqual(resident.health, 42)
        self.assertEqual(resident.relationships, {'guest': 2})
        self.assertEqual(world.creatures['guest'].status, 'lost')
        self.assertFalse(world.creatures['guest'].knows_safe_zone)
        self.assertNotEqual(world.boundary, old_boundary)

    def test_phases_and_schedule(self):
        world = World()
        self.assertTrue(3600 <= world.shift_at <= 10800)
        self.assertTrue(60 <= world.shift_at - world.warning_at <= 300)
        world.advance(world.warning_at)
        self.assertEqual(world.phase, 'warning')
        world.advance(world.shift_at - world.time - 15)
        self.assertEqual(world.phase, 'dissolving')
        self.assertAlmostEqual(world.dissolution, .5)

    def test_population_limit(self):
        world = World()
        for i in range(9):
            world.add_creature(Creature(str(i), 'Гость'))
        with self.assertRaises(ValueError):
            world.add_creature(Creature('overflow', 'Гость'))

    def test_invalid_coordinates_and_pause(self):
        world = World()
        with self.assertRaises(ValueError):
            world.move('rosmontis', float('nan'), 0)
        world.paused = True
        world.advance(100)
        self.assertEqual(world.time, 0)
        world.paused = False
        world.speed = 100
        world.advance(2)
        self.assertEqual(world.time, 200)

    def test_save_restores_future_randomness_and_overwrites(self):
        world = World(42)
        world.advance(123)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'world.sqlite3'
            save(world, path)
            restored = load(path)
            self.assertEqual(world.snapshot(), restored.snapshot())
            world.advance(40000)
            restored.advance(40000)
            self.assertEqual(world.snapshot(), restored.snapshot())
            save(restored, path)
            self.assertEqual(load(path).snapshot(), restored.snapshot())

    def test_lost_rosmontis_stops_large_time_step(self):
        world = World()
        world.move('rosmontis', 50, 0)
        deadline = world.shift_at
        world.advance(50000)
        self.assertTrue(world.ended)
        self.assertEqual(world.time, deadline)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ended.sqlite3'
            save(world, path)
            restored = load(path)
            restored.advance(100)
            self.assertTrue(restored.ended)
            self.assertEqual(restored.time, deadline)


if __name__ == '__main__':
    unittest.main()
