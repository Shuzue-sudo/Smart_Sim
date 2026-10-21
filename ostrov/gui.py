"""Tk desktop observer. All world mutations go through the simulation core."""
import math
import sqlite3
import time
import tkinter as tk
from tkinter import filedialog, font, messagebox, simpledialog, ttk
from uuid import uuid4

from .engine import Creature, World
from .storage import load, save


class Observer:
    def __init__(self, root, world=None):
        self.root = root
        # Prefer Unicode fonts; some minimal X11 builds expose only bitmap fonts.
        families = set(font.families(root))
        preferred = next((name for name in ('Segoe UI', 'DejaVu Sans', 'Noto Sans', 'fixed') if name in families), None)
        if preferred:
            for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont', 'TkCaptionFont', 'TkSmallCaptionFont', 'TkIconFont', 'TkTooltipFont'):
                font.nametofont(name, root=root).configure(family=preferred)
        self.world = world or World()
        self.world.paused = True
        self.selected = 'rosmontis'
        self.last_tick = time.monotonic()
        self.timer = None
        root.title('Остров 2.0 — наблюдатель')
        root.geometry('1100x780')
        root.minsize(850, 620)
        root.protocol('WM_DELETE_WINDOW', self.close)
        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill='x')
        self.pause_button = ttk.Button(toolbar, text='Продолжить', command=self.toggle_pause)
        self.pause_button.pack(side='left')
        self.speed = tk.StringVar(value=str(self.world.speed))
        speed = ttk.Combobox(toolbar, textvariable=self.speed, values=World.SPEEDS, width=5, state='readonly')
        speed.pack(side='left', padx=8)
        speed.bind('<<ComboboxSelected>>', self.set_speed)
        ttk.Label(toolbar, text='× скорость').pack(side='left')
        for label, command in [('Новый мир', self.new_world), ('Сохранить', self.save_world), ('Загрузить', self.load_world), ('Создать существо', self.create_creature)]:
            ttk.Button(toolbar, text=label, command=command).pack(side='left', padx=5)
        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status, padding=8).pack(fill='x')
        body = ttk.Frame(root)
        body.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(body, bg='#101b2d', highlightthickness=0)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda event: self.render())
        self.canvas.bind('<Button-1>', self.select_at)
        self.canvas.bind('<Button-3>', self.move_at)
        side = ttk.Frame(body, padding=10, width=280)
        side.pack(side='right', fill='y')
        ttk.Label(side, text='Существа (включая погибших)').pack(anchor='w')
        self.roster = tk.Listbox(side, width=30, height=10, exportselection=False)
        self.roster.pack(fill='x', pady=8)
        self.roster.bind('<<ListboxSelect>>', self.select_roster)
        self.details = tk.StringVar()
        ttk.Label(side, textvariable=self.details, wraplength=260, justify='left').pack(anchor='w')
        ttk.Label(side, text='ЛКМ — выбрать\nПКМ — перенести выбранное существо\nЗа краем острова — смертельное падение.', wraplength=260).pack(anchor='w', pady=16)
        ttk.Label(root, text='Журнал мира', padding=5).pack(anchor='w')
        self.log = tk.Text(root, height=6, state='disabled', wrap='word')
        self.log.pack(fill='x')
        self.log_signature = None
        self.render()
        self.tick()

    def transform(self):
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        return width / 2, height / 2, min(width, height) / 260

    def screen(self, x, y):
        cx, cy, scale = self.transform()
        return cx + x * scale, cy - y * scale

    def coordinates(self, event):
        cx, cy, scale = self.transform()
        return (event.x - cx) / scale, (cy - event.y) / scale

    def toggle_pause(self):
        if not self.world.ended:
            self.world.paused = not self.world.paused
            self.last_tick = time.monotonic()
        self.render()

    def set_speed(self, event=None):
        self.world.speed = int(self.speed.get())

    def tick(self):
        now = time.monotonic()
        self.world.advance(now - self.last_tick)
        self.last_tick = now
        self.render()
        self.timer = self.root.after(50, self.tick)

    def render(self):
        world = self.world
        self.canvas.delete('all')
        points = []
        # Sample the same polar interpolation as the engine, rather than joining
        # just the radial control points with straight chords.
        for i in range(512):
            angle = i * math.tau / 512
            radius = world.radius_at(angle)
            points.extend(self.screen(radius * math.cos(angle), radius * math.sin(angle)))
        fade = world.dissolution
        color = '#%02x%02x%02x' % (int(72 - 45 * fade), int(110 - 65 * fade), int(76 - 25 * fade))
        self.canvas.create_polygon(points, fill=color, outline='#b3bc8a', width=2)
        cx, cy, scale = self.transform()
        r = world.SAFE_RADIUS * scale
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill='#638c50', outline='#e0d29c', dash=(5, 4))
        self.canvas.create_oval(cx-9, cy-9, cx+9, cy+9, fill='#264d29', outline='#c2a56b', width=3)
        self.canvas.create_text(cx, cy-21, text='Древний дуб', fill='white')
        for creature in world.creatures.values():
            if creature.status == 'lost':
                continue
            x, y = self.screen(creature.x, creature.y)
            color = '#d8d8e8' if creature.id == 'rosmontis' else '#f4bd67'
            if creature.status == 'dead':
                color = '#787878'
            self.canvas.create_oval(x-5, y-5, x+5, y+5, fill=color, outline='#ffffff' if creature.id == self.selected else color, width=2)
            self.canvas.create_text(x, y+15, text=creature.name, fill='white')
        self.canvas.create_line(20, 25, 20+20*scale, 25, fill='white', width=2)
        self.canvas.create_text(20, 40, text='20 м', fill='white', anchor='w')
        phase = {'stable': 'стабильно', 'warning': 'предупреждение', 'dissolving': 'растворение'}[world.phase]
        state = 'МИР ЗАВЕРШЁН' if world.ended else ('пауза' if world.paused else 'идёт')
        self.status.set(f'{state} · {world.time/3600:.2f} игровых ч · ×{world.speed} · {phase} · до сдвига {max(0, world.shift_at-world.time):.0f} с · сдвигов {world.generation}')
        self.pause_button.configure(text='Продолжить' if world.paused else 'Пауза', state='disabled' if world.ended else 'normal')
        self.ids = list(world.creatures)
        rows = [f'{c.name} · {c.status}' for c in world.creatures.values()]
        if list(self.roster.get(0, 'end')) != rows:
            self.roster.delete(0, 'end')
            for row in rows:
                self.roster.insert('end', row)
        if self.selected in self.ids:
            self.roster.selection_clear(0, 'end')
            self.roster.selection_set(self.ids.index(self.selected))
        creature = world.creatures.get(self.selected)
        if creature:
            self.details.set(f'{creature.name}\nСостояние: {creature.status}\nЗдоровье: {creature.health:g}\nКоординаты: {creature.x:.1f}, {creature.y:.1f} м\nПамять: {", ".join(creature.memory) or "—"}\nИнвентарь: {", ".join(creature.inventory) or "—"}\nОтношения: {creature.relationships or "—"}')
        signature = (id(world), len(world.events), world.end_reason)
        if signature != self.log_signature:
            self.log.configure(state='normal')
            self.log.delete('1.0', 'end')
            for event in world.events[-100:]:
                description = f'Сдвиг №{event["generation"]}' if event['kind'] == 'shift' else f'{event["creature"]}: {event["reason"]}'
                self.log.insert('end', f'{event["time"]:.0f} с · {description}\n')
            if world.end_reason:
                self.log.insert('end', f'Мир завершён: {world.end_reason}\n')
            self.log.see('end')
            self.log.configure(state='disabled')
            self.log_signature = signature

    def select_at(self, event):
        x, y = self.coordinates(event)
        candidates = [c for c in self.world.creatures.values() if c.status != 'lost']
        if candidates:
            nearest = min(candidates, key=lambda c: math.hypot(c.x-x, c.y-y))
            if math.hypot(nearest.x-x, nearest.y-y) * self.transform()[2] <= 18:
                self.selected = nearest.id
                self.render()

    def select_roster(self, event=None):
        selection = self.roster.curselection()
        if selection:
            self.selected = self.ids[selection[0]]
            self.render()

    def move_at(self, event):
        x, y = self.coordinates(event)
        if not self.world.ended and not self.world.contains(x, y):
            if not messagebox.askyesno('Падение', 'Перенос за край убьёт существо. Продолжить?', parent=self.root):
                return
        try:
            self.world.move(self.selected, x, y)
        except ValueError as error:
            messagebox.showerror('Перемещение', str(error), parent=self.root)
        self.render()

    def create_creature(self):
        if self.world.ended:
            return
        name = simpledialog.askstring('Создать существо', 'Имя (появится у дуба):', parent=self.root)
        if not name or not name.strip():
            return
        creature = Creature(uuid4().hex, name.strip())
        try:
            self.world.add_creature(creature)
            self.selected = creature.id
        except ValueError as error:
            messagebox.showerror('Создание', str(error), parent=self.root)
        self.render()

    def replace_world(self, world):
        self.world = world
        world.paused = True
        self.selected = 'rosmontis'
        self.speed.set(str(world.speed))
        self.last_tick = time.monotonic()
        self.render()

    def new_world(self):
        if messagebox.askyesno('Новый мир', 'Несохранённое состояние будет потеряно. Создать мир?', parent=self.root):
            self.replace_world(World(time.time_ns()))

    def save_world(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension='.sqlite3', filetypes=[('Остров SQLite', '*.sqlite3')])
        if path:
            try:
                save(self.world, path)
            except (OSError, sqlite3.Error, ValueError) as error:
                messagebox.showerror('Сохранение', str(error), parent=self.root)

    def load_world(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[('Остров SQLite', '*.sqlite3')])
        if path and messagebox.askyesno('Загрузка', 'Заменить текущий мир? Несохранённое состояние будет потеряно.', parent=self.root):
            try:
                world = load(path)
                self.replace_world(world)
            except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as error:
                messagebox.showerror('Загрузка', f'Не удалось загрузить мир: {error}', parent=self.root)

    def close(self):
        if messagebox.askyesno('Выход', 'Закрыть приложение? Несохранённое состояние будет потеряно.', parent=self.root):
            if self.timer is not None:
                self.root.after_cancel(self.timer)
            self.root.destroy()


def run(world=None):
    root = tk.Tk()
    Observer(root, world)
    root.mainloop()
