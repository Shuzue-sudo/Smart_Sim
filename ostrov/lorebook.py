"""NeraAI-compatible lorebook JSON and activation (MIT; see THIRD_PARTY.md)."""
import json
import re
from uuid import uuid4


def units(text):
    return len(text.encode('utf-16-le', errors='surrogatepass')) // 2


def prefix(text, maximum):
    return text.encode('utf-16-le', errors='surrogatepass')[:maximum*2].decode('utf-16-le', errors='surrogatepass')


def parse(text, existing=(), require_entries=False):
    if units(text) > 2_000_000:
        raise ValueError('JSON слишком большой')
    entries = json.loads(text)
    if not isinstance(entries, list) or len(entries) > 400:
        raise ValueError('Ожидается JSON-массив, максимум 400 записей')
    if require_entries and not entries:
        raise ValueError('Добавьте хотя бы одну запись')
    seen = {entry['id'] for entry in existing}
    result = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError('Запись должна быть объектом')
        for name, limit in (('id', 100), ('keys', 2000), ('content', 30000)):
            if name in item and (not isinstance(item[name], str) or units(item[name]) > limit):
                raise ValueError(f'{name}: требуется строка длиной до {limit}')
        for name in ('enabled', 'alwaysActive', 'global'):
            if name in item and type(item[name]) is not bool:
                raise ValueError(f'{name}: требуется true или false')
        entry = {'id': item.get('id', str(uuid4())), 'keys': item.get('keys', ''),
                 'content': item.get('content', ''), 'enabled': item.get('enabled', True),
                 'alwaysActive': item.get('alwaysActive', not item.get('keys', '').strip()),
                 'global': item.get('global', False)}
        if not entry['content'].strip() or not entry['id'].strip() or entry['id'] in seen:
            raise ValueError('Пустое содержимое либо пустой/повторяющийся id')
        seen.add(entry['id'])
        result.append(entry)
    return result


def encode(local, global_entries):
    return json.dumps([{**entry, 'global': False} for entry in local] +
                      [{**entry, 'global': True} for entry in global_entries], ensure_ascii=False, indent=2)


def matches(entry, scan):
    if not entry['enabled'] or not entry['content'].strip():
        return False
    if entry['alwaysActive']:
        return True
    return any(key.strip() and key.strip().lower() in scan.lower()
               for key in re.split('[,;\n]', entry['keys']))


def activate(scopes, history, shared_world):
    scan = '\n'.join(history[-12:]) + '\n' + shared_world
    text, ids, seen = '', [], set()
    for scope, entries in scopes:
        for entry in entries:
            identity = (scope, entry['id'])
            if identity in seen:
                continue
            seen.add(identity)
            if not matches(entry, scan) or units(text) >= 12000:
                continue
            separator = '\n\n' if text else ''
            room = 12000 - units(text) - units(separator)
            if room <= 0:
                continue
            text += separator + prefix(entry['content'].strip(), room)
            ids.append(f'{scope}:{entry["id"]}')
    return text, ids
