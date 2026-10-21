"""Local/global lore and instruction packs: a lossless NeraAI JSON editor."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .lorebook import encode, parse


class LoreEditor:
    def __init__(self, observer):
        self.observer = observer
        self.world = observer.world
        self.owner = observer.selected
        self.world.paused = True
        observer.brain.reset()  # Any old response belongs to the previous configuration.
        self.dialog = tk.Toplevel(observer.root)
        self.dialog.title('Лорбуки — формат NeraAI')
        self.dialog.geometry('850x650')
        self.dialog.transient(observer.root)
        self.dialog.grab_set()
        self.mode = tk.StringVar(value='Лор персонажа и глобальный лор')
        self.selector = ttk.Combobox(self.dialog, textvariable=self.mode, state='readonly', values=('Лор персонажа и глобальный лор', 'Инструкции модели'))
        self.selector.pack(fill='x', padx=10, pady=8)
        self.selector.bind('<<ComboboxSelected>>', self.switch)
        self.description = tk.StringVar()
        ttk.Label(self.dialog, textvariable=self.description, wraplength=800).pack(fill='x', padx=10)
        ttk.Label(self.dialog, text='Общее описание мира (сканируется для активации ключей)').pack(anchor='w', padx=10, pady=(8, 0))
        self.shared = tk.StringVar(value=self.world.shared_world)
        ttk.Entry(self.dialog, textvariable=self.shared).pack(fill='x', padx=10)
        self.editor = tk.Text(self.dialog, wrap='word', undo=True)
        self.editor.pack(fill='both', expand=True, padx=10, pady=10)
        bar = ttk.Frame(self.dialog, padding=10)
        bar.pack(fill='x')
        for label, command in [('Новая запись', self.new_entry), ('Импорт JSON', self.import_json), ('Экспорт JSON', self.export_json), ('Применить', self.apply)]:
            ttk.Button(bar, text=label, command=command).pack(side='left', padx=4)
        ttk.Label(self.dialog, text='enabled — включена; alwaysActive — всегда; global — для всех существ мира.\nКлючи: запятая, ; или перенос строки. Для удаления уберите объект из массива.', padding=10).pack(anchor='w')
        self.drafts = {
            'Лор персонажа и глобальный лор': encode(self.world.lore_entries.get(self.owner, []), self.world.global_lore),
            'Инструкции модели': encode(self.world.instruction_packs, [])}
        self.current = self.mode.get()
        self.show()

    def show(self):
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', self.drafts[self.current])
        creature = self.world.creatures[self.owner]
        self.description.set(f'Локальные записи: {creature.name}. Глобальные: все существа текущего мира. Исходные тексты сохраняются без переписывания.' if self.current != 'Инструкции модели' else 'Отдельный слой пользовательских инструкций DeepSeek. Физика и контракт действий задаются движком.')

    def switch(self, event=None):
        self.drafts[self.current] = self.editor.get('1.0', 'end-1c')
        self.current = self.mode.get()
        self.show()

    def new_entry(self):
        try:
            entries = parse(self.editor.get('1.0', 'end-1c'))
            entries += parse('[{"keys":"","content":"Новая запись","enabled":true,"alwaysActive":true,"global":false}]')
            self.editor.delete('1.0', 'end')
            self.editor.insert('1.0', json.dumps(entries, ensure_ascii=False, indent=2))
        except ValueError as error:
            messagebox.showerror('JSON', str(error), parent=self.dialog)

    def import_json(self):
        path = filedialog.askopenfilename(parent=self.dialog, filetypes=[('NeraAI JSON', '*.json')])
        if not path:
            return
        try:
            with Path(path).open(encoding='utf-8-sig') as stream:
                text = stream.read(2_000_001)
            entries = parse(self.editor.get('1.0', 'end-1c'))
            imported = parse(text, existing=entries, require_entries=True)
            combined = entries + imported
            parse(json.dumps(combined))
            self.editor.delete('1.0', 'end')
            self.editor.insert('1.0', json.dumps(combined, ensure_ascii=False, indent=2))
        except (OSError, ValueError) as error:
            messagebox.showerror('Импорт', str(error), parent=self.dialog)

    def export_json(self):
        try:
            entries = parse(self.editor.get('1.0', 'end-1c'))
            payload = encode([e for e in entries if not e['global']], [e for e in entries if e['global']])
            path = filedialog.asksaveasfilename(parent=self.dialog, defaultextension='.json', filetypes=[('NeraAI JSON', '*.json')])
            if path:
                Path(path).write_text(payload, encoding='utf-8')
        except (OSError, ValueError) as error:
            messagebox.showerror('Экспорт', str(error), parent=self.dialog)

    def apply(self):
        self.drafts[self.current] = self.editor.get('1.0', 'end-1c')
        try:
            lore = parse(self.drafts['Лор персонажа и глобальный лор'])
            instructions = parse(self.drafts['Инструкции модели'])
            if len(self.shared.get()) > 6000:
                raise ValueError('Общее описание мира: максимум 6000 символов')
        except ValueError as error:
            messagebox.showerror('Лорбук', str(error), parent=self.dialog)
            return
        self.world.lore_entries[self.owner] = [e for e in lore if not e['global']]
        self.world.global_lore = [e for e in lore if e['global']]
        self.world.instruction_packs = instructions
        self.world.shared_world = self.shared.get()
        self.observer.brain.reset()
        self.dialog.destroy()
        self.observer.render()
