"""Headless smoke run. This is not an autonomous simulation."""
import argparse
from .engine import World
from .storage import load, save


def main():
    parser = argparse.ArgumentParser(description="Остров 2.0 — прототип ядра")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--save")
    parser.add_argument("--load")
    parser.add_argument("--gui", action="store_true", help="Открыть графический наблюдатель")
    args = parser.parse_args()
    world = load(args.load) if args.load else World(args.seed)
    if args.gui:
        from .gui import run
        run(world)
        return
    world.advance(args.seconds)
    if args.save:
        save(world, args.save)
    print(f"Время: {world.time:.1f} с; сдвигов: {world.generation}; фаза: {world.phase}; завершён: {world.ended}")


if __name__ == "__main__":
    main()
