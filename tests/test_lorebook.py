import json
from pathlib import Path
import tempfile
import unittest

from ostrov.brain import context
from ostrov.engine import World
from ostrov.lorebook import activate, encode, matches, parse, units
from ostrov.storage import load, save


class LorebookTests(unittest.TestCase):
    def test_nera_defaults_matching_and_disabled(self):
        always, keyed = parse('[{"content":"Постоянно"},{"keys":"ЛЕС; руины\\nдуб","content":"Контекст"}]')
        self.assertTrue(always['alwaysActive'])
        for text in ['Лесной', 'В РУИНЫ', 'Старый дуб']:
            self.assertTrue(matches(keyed, text))
        self.assertFalse(matches(keyed, 'Вода'))
        self.assertTrue(matches(always, ''))
        keyed['enabled'] = False
        self.assertFalse(matches(keyed, 'ЛЕС'))
        explicit = parse('[{"keys":"","alwaysActive":false,"content":"Нет"}]')[0]
        self.assertFalse(matches(explicit, ''))

    def test_nera_invalid_and_duplicate_batches(self):
        for text in ['{}', '[] garbage', '[null]', '[{"content":""}]',
                     '[{"content":"ok","enabled":"false"}]',
                     '[{"id":"same","content":"a"},{"id":"same","content":"b"}]',
                     '[{"id":" ","content":"a"}]',
                     json.dumps([{'content': 'a'*30001}]),
                     json.dumps([{'content': 'a'}]*401)]:
            with self.subTest(text=text[:50]), self.assertRaises(ValueError):
                parse(text)
        existing = parse('[{"id":"saved","content":"old"}]')
        with self.assertRaises(ValueError):
            parse('[{"id":"saved","content":"new"}]', existing)
        with self.assertRaises(ValueError):
            parse('[]', require_entries=True)
        self.assertEqual(existing[0]['content'], 'old')

    def test_roundtrip_preserves_text_scope_and_flags(self):
        local = parse(json.dumps([{'content': '  Лес\n"Руины"  ', 'enabled': False}]))
        global_entries = parse('[{"content":"Мир","alwaysActive":true}]')
        restored = parse(encode(local, global_entries))
        self.assertEqual(restored[0]['content'], local[0]['content'])
        self.assertFalse(restored[0]['enabled'])
        self.assertTrue(restored[1]['global'])
        self.assertFalse(global_entries[0]['global'])

    def test_order_history_budget_deduplication(self):
        local = parse('[{"id":"local","keys":"лес","content":"Локально"}]')
        global_entries = parse('[{"id":"global","content":"Глобально"}]')
        text, ids = activate([('c', local), ('c', local), ('global', global_entries)], ['Лес'], '')
        self.assertEqual(text, 'Локально\n\nГлобально')
        self.assertEqual(ids, ['c:local', 'global:global'])
        text, _ = activate([('c', local)], ['Лес'] + ['Вода']*12, '')
        self.assertEqual(text, '')
        text, _ = activate([('c', local)], [], 'Лес')
        self.assertEqual(text, 'Локально')
        huge = parse(json.dumps([{'content': 'я'*10000}, {'content': 'б'*5000}]))
        text, _ = activate([('global', huge)], [], '')
        self.assertEqual(units(text), 12000)

    def test_context_layers_and_save(self):
        world = World()
        world.shared_world = 'Лес'
        world.lore_entries['rosmontis'] = parse('[{"keys":"лес","content":"Факты мира"}]')
        world.instruction_packs = parse('[{"content":"Пиши кратко"}]')
        observation = context(world)
        self.assertEqual(observation['active_lore'], 'Факты мира')
        self.assertEqual(observation['instruction_packs'], 'Пиши кратко')
        self.assertNotIn('shift_at', observation)
        self.assertNotIn('safe_radius', observation)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'lore.sqlite3'
            save(world, path)
            self.assertEqual(context(load(path)), observation)
        old = world.snapshot()
        for name in ['lore_entries', 'global_lore', 'instruction_packs', 'shared_world', 'brain_history']:
            old.pop(name)
        self.assertEqual(World.restore(old).global_lore, [])
