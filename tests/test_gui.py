"""Desktop integration checks. Run with DISPLAY (or Xvfb on Linux)."""
import os
import json
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ostrov.engine import World
from ostrov.gui import Observer
from ostrov.storage import load
from ostrov.brain import context
from ostrov.lore_editor import LoreEditor


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

    def test_deepseek_settings_dialog(self):
        self.app.configure_brain()
        dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel))
        frame = dialog.winfo_children()[0]
        children = frame.winfo_children()
        from tkinter import ttk
        check = next(w for w in children if isinstance(w, ttk.Checkbutton))
        key = next(w for w in children if isinstance(w, ttk.Entry) and w.cget('show') == '*')
        apply = next(w for w in children if isinstance(w, ttk.Button))
        check.invoke()
        key.delete(0, 'end')
        key.insert(0, 'test-key')
        apply.invoke()
        self.assertTrue(self.app.brain.settings.enabled)
        self.assertEqual(self.app.brain.settings.api_key, 'test-key')
        self.assertTrue(self.app.world.paused)
        self.assertNotIn('test-key', json.dumps(self.app.world.snapshot()))

    def test_lore_editor_import_layers_and_persistence(self):
        editor = LoreEditor(self.app)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'nera.json'
            source.write_text('[{"id":"g","content":"  Дуб\\nЛес  ","global":true}]', encoding='utf-8')
            with patch('ostrov.lore_editor.filedialog.askopenfilename', return_value=str(source)):
                editor.import_json()
            with patch('ostrov.lore_editor.filedialog.askopenfilename', return_value=str(source)), patch('ostrov.lore_editor.messagebox.showerror') as error:
                editor.import_json()
                error.assert_called_once()
            editor.mode.set('Инструкции модели')
            editor.switch()
            editor.editor.delete('1.0', 'end')
            editor.editor.insert('1.0', '[{"content":"Краткие реплики"}]')
            editor.apply()
            self.assertEqual(self.app.world.global_lore[0]['content'], '  Дуб\nЛес  ')
            self.assertEqual(context(self.app.world)['instruction_packs'], 'Краткие реплики')
            target = Path(directory) / 'world.sqlite3'
            from ostrov.storage import save
            save(self.app.world, target)
            self.assertEqual(load(target).global_lore, self.app.world.global_lore)
