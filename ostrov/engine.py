"""World rules. Distances are metres and time is game seconds."""
from dataclasses import asdict, dataclass, field
import math
import random


@dataclass
class Creature:
    id: str
    name: str
    x: float = 0
    y: float = 0
    health: float = 100
    memory: list[str] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)
    relationships: dict[str, float] = field(default_factory=dict)
    knows_safe_zone: bool = False
    status: str = "active"


class World:
    SAFE_RADIUS = 30.0
    MAX_CREATURES = 10
    SPEEDS = (1, 5, 10, 100)
    DISSOLVE_SECONDS = 30.0

    def __init__(self, seed: int = 1):
        self.seed = seed
        self.rng = random.Random(seed)
        self.time = 0.0
        self.speed = 1
        self.paused = False
        self.ended = False
        self.end_reason = None
        self.generation = 0
        self.events = []
        self.creatures = {"rosmontis": Creature("rosmontis", "Росмонтис")}
        self.boundary = self._boundary()
        self._schedule()

    def _boundary(self):
        return [self.rng.uniform(85, 115) for _ in range(64)]

    def _schedule(self):
        self.shift_at = self.time + self.rng.uniform(3600, 10800)
        self.warning_at = self.shift_at - self.rng.uniform(60, 300)

    def radius_at(self, angle):
        index = (angle % math.tau) / math.tau * len(self.boundary)
        low = int(index)
        fraction = index - low
        return self.boundary[low] * (1 - fraction) + self.boundary[(low + 1) % len(self.boundary)] * fraction

    def contains(self, x, y):
        return math.hypot(x, y) <= self.radius_at(math.atan2(y, x))

    @property
    def phase(self):
        if self.time >= self.shift_at - self.DISSOLVE_SECONDS:
            return "dissolving"
        return "warning" if self.time >= self.warning_at else "stable"

    @property
    def dissolution(self):
        return max(0.0, min(1.0, 1 - (self.shift_at - self.time) / self.DISSOLVE_SECONDS))

    def _editable(self):
        if self.ended:
            raise ValueError("Завершённый мир доступен только для просмотра")

    def add_creature(self, creature):
        self._editable()
        if creature.id in self.creatures:
            raise ValueError("Идентификатор уже существует")
        if creature.status != "active" or not math.isfinite(creature.health) or creature.health <= 0:
            raise ValueError("Требуется живое существо")
        if sum(c.status == "active" for c in self.creatures.values()) >= self.MAX_CREATURES:
            raise ValueError("Достигнут лимит 10 существ")
        if not all(math.isfinite(v) for v in (creature.x, creature.y)) or not self.contains(creature.x, creature.y):
            raise ValueError("Существо должно появиться на острове")
        self.creatures[creature.id] = creature

    def kill(self, creature_id, reason):
        self._editable()
        creature = self.creatures[creature_id]
        if creature.status != "active":
            raise ValueError("Существо уже не активно")
        creature.health = 0
        creature.status = "dead"
        self.events.append({"time": self.time, "kind": "death", "creature": creature_id, "reason": reason})
        if creature_id == "rosmontis":
            self.ended = True
            self.end_reason = reason

    def move(self, creature_id, x, y):
        self._editable()
        creature = self.creatures[creature_id]
        if creature.status != "active" or not all(math.isfinite(v) for v in (x, y)):
            raise ValueError("Недопустимое перемещение")
        # Observer placement, not autonomous pathfinding or a model action.
        creature.x, creature.y = x, y
        if not self.contains(x, y):
            self.kill(creature_id, "Падение в пустоту")

    def advance(self, real_seconds):
        if not math.isfinite(real_seconds) or real_seconds < 0 or self.speed not in self.SPEEDS:
            raise ValueError("Недопустимое время или скорость")
        if self.paused or self.ended:
            return
        target = self.time + real_seconds * self.speed
        while self.shift_at <= target and not self.ended:
            self.time = self.shift_at
            self._shift()
        if not self.ended:
            self.time = target

    def _shift(self):
        for creature in self.creatures.values():
            if creature.status == "active" and math.hypot(creature.x, creature.y) > self.SAFE_RADIUS:
                creature.status = "lost"
                if creature.id == "rosmontis":
                    self.ended = True
                    self.end_reason = "Росмонтис исчезла при сдвиге"
        self.generation += 1
        self.boundary = self._boundary()
        self.events.append({"time": self.time, "kind": "shift", "generation": self.generation})
        self._schedule()

    def snapshot(self):
        data = {k: v for k, v in vars(self).items() if k not in ("rng", "creatures")}
        data["creatures"] = {k: asdict(v) for k, v in self.creatures.items()}
        data["rng_state"] = self.rng.getstate()
        return data

    @classmethod
    def restore(cls, data):
        data = dict(data)
        state = data.pop("rng_state")
        creatures = data.pop("creatures")
        world = cls(data["seed"])
        world.__dict__.update(data)
        world.creatures = {k: Creature(**v) for k, v in creatures.items()}
        world.rng.setstate((state[0], tuple(state[1]), state[2]))
        return world
