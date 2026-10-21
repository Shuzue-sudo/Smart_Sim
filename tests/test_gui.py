"""Desktop integration checks. Run with DISPLAY (or Xvfb on Linux)."""
import os
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ostrov.engine import World
from ostrov.gui import Observer
from ostrov.storage import load


@unittest.skipUnless(os.name == 'nt' or os.environ.get('DISPLAY'), 'Требуется графический дисплей')
class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.app = Observer(self.root, World(42))
        self.root.update()

    def tearDown(self):
        self.root.after_cancel(self.app.timer)
        self.root.destroy()

    def test_map_controls_and_selection(self):
        self.assertGreater(len(self.app.canvas.find_all()), 5)
        self.assertTrue(self.app.world.paused)
        self.app.toggle_pause()
        self.assertFalse(self.app.world.paused)
        self.app.speed.set('100')
        self.app.set_speed()
        self.assertEqual(self.app.world.speed, 100)
        with patch('ostrov.gui.simpledialog.askstring', return_value='Гость'):
            self.app.create_creature()
        guest_id = self.app.selected
        self.assertEqual(self.app.world.creatures[guest_id].name, 'Гость')
        x, y = self.app.screen(20, 10)
        self.app.move_at(SimpleNamespace(x=x, y=y))
        self.assertAlmostEqual(self.app.world.creatures[guest_id].x, 20)
        self.app.select_at(SimpleNamespace(x=x, y=y))
        self.assertEqual(self.app.selected, guest_id)

    def test_save_load_and_ended_world(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'gui.sqlite3')
            self.app.world.move('rosmontis', 20, 0)
            with patch('ostrov.gui.filedialog.asksaveasfilename', return_value=path):
                self.app.save_world()
            self.assertEqual(load(path).creatures['rosmontis'].x, 20)
            self.app.world.move('rosmontis', 10, 0)
            with patch('ostrov.gui.filedialog.askopenfilename', return_value=path), patch('ostrov.gui.messagebox.askyesno', return_value=True):
                self.app.load_world()
            self.assertEqual(self.app.world.creatures['rosmontis'].x, 20)
            self.assertTrue(self.app.world.paused)
        self.app.world.move('rosmontis', 200, 0)
        self.app.render()
        self.assertEqual(str(self.app.pause_button['state']), 'disabled')
        self.assertIn('МИР ЗАВЕРШЁН', self.app.status.get())

    def test_cancel_fatal_move_and_population_error(self):
        x, y = self.app.screen(200, 0)
        with patch('ostrov.gui.messagebox.askyesno', return_value=False):
            self.app.move_at(SimpleNamespace(x=x, y=y))
        self.assertFalse(self.app.world.ended)
        with patch('ostrov.gui.simpledialog.askstring', return_value='Гость'), patch('ostrov.gui.messagebox.showerror') as error:
            for _ in range(10):
                self.app.create_creature()
            self.assertEqual(len(self.app.world.creatures), 10)
            error.assert_called_once()
