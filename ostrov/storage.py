"""Versioned, transactional SQLite snapshots; no API credentials are stored."""
import json
import sqlite3
from .engine import World


def save(world: World, path):
    payload = json.dumps(world.snapshot(), ensure_ascii=False, allow_nan=False)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO snapshot VALUES (1, 1, ?) ON CONFLICT(id) DO UPDATE SET version=excluded.version, payload=excluded.payload", (payload,))


def load(path):
    with sqlite3.connect(f"file:{__import__('pathlib').Path(path).resolve().as_posix()}?mode=ro", uri=True) as connection:
        row = connection.execute("SELECT version, payload FROM snapshot WHERE id=1").fetchone()
    if row is None or row[0] != 1:
        raise ValueError("Неизвестный формат сохранения")
    return World.restore(json.loads(row[1]))
