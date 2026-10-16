"""Start an island, leave a body on it, and keep its notes."""

from __future__ import annotations

import argparse
import time
import urllib.request
from pathlib import Path

from eko.behaviors import free_play, run_many_towers, run_objects_on_spire, run_tallest_tower, run_throw_on_spire
from eko.driver import HttpDriver, WorldDriver, join
from eko.llm_agent import run_llm
from eko.memory import ensure_workspace
from eko.prompts import GOALS
from eko.scoring import many_five_towers, objects_on_spire, tallest_tower, throw_on_spire
from eko.server import serve
from eko.world import World

ROOT = Path(__file__).resolve().parents[1]


def _reset(base):
    req = urllib.request.Request(base.rstrip("/") + "/admin/reset", method="POST")
    with urllib.request.urlopen(req, timeout=10) as response:
        response.read()


def play(args):
    port = args.port
    workspace = ensure_workspace(Path(args.workspace), soul=not args.no_soul)
    world = World()
    server, _island = serve(port, world)
    base = f"http://127.0.0.1:{port}"
    print(f"island  {base}")
    print(f"notes   {workspace}")
    try:
        if args.backend == "llm":
            joined = join(base, args.name)
            run_llm(
                workspace,
                base,
                joined["session"],
                joined["name"],
                seconds=args.seconds,
                hour_seconds=args.hour_seconds,
                on_hour=lambda: _reset(base),
            )
        else:
            _play_demo(base, workspace, args)
    finally:
        _island = server.island  # noqa: F841
        server.island.running = False
        server.shutdown()


def _play_demo(base, workspace, args):
    joined = join(base, args.name)
    driver = HttpDriver(base, joined["session"], seconds=args.seconds)
    deadline = time.monotonic() + args.seconds
    hour = 0
    while time.monotonic() < deadline and not driver.expired():
        hour += 1
        print(f"hour {hour}")
        remaining = deadline - time.monotonic()
        driver.budget = driver.elapsed + remaining
        driver.t0 = time.monotonic()
        driver.budget = min(args.hour_seconds, remaining)
        free_play(driver, workspace)
        if time.monotonic() >= deadline:
            break
        if remaining > driver.budget:
            print("the island resets. the notes stay.")
            _reset(base)
            driver.t0 = time.monotonic()
    print("session over")


def evaluate(args):
    tasks = list(GOALS) if args.task == "all" else [args.task]
    workspace = ensure_workspace(Path(args.workspace), soul=True)
    print(f"notes  {workspace}")
    for task in tasks:
        world = World()
        driver = WorldDriver(world, seconds=args.seconds)
        print(f"\n{task}")
        print(GOALS[task])
        if task == "many-5-towers":
            run_many_towers(driver, workspace)
            print(f"score  {many_five_towers(world)} towers")
        elif task == "tallest-tower":
            run_tallest_tower(driver, workspace)
            print(f"score  {tallest_tower(world)} blocks")
        elif task == "objects-on-spire":
            run_objects_on_spire(driver, workspace)
            print(f"score  {objects_on_spire(world)} objects")
        elif task == "throw-on-spire":
            landed = run_throw_on_spire(driver, workspace)
            score = throw_on_spire(world, driver.elapsed, args.seconds, landed)
            print(f"score  {score:.1f} seconds left   climbed={world.player.climbed_platform}")
        else:
            raise SystemExit(f"unknown task {task}")


def serve_forever(args):
    world = World()
    server, island = serve(args.port, world)
    print(f"island  http://127.0.0.1:{args.port}")
    try:
        while island.running:
            time.sleep(0.4)
    except KeyboardInterrupt:
        pass
    finally:
        island.running = False
        server.shutdown()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Eko on the mesa island.")
    sub = parser.add_subparsers(dest="command", required=True)

    serving = sub.add_parser("serve", help="open the island in a browser")
    serving.add_argument("--port", type=int, default=8080)
    serving.set_defaults(func=serve_forever)

    playing = sub.add_parser("play", help="leave Eko on the island with no task")
    playing.add_argument("--backend", choices=("demo", "llm"), default="demo")
    playing.add_argument("--seconds", type=float, default=90)
    playing.add_argument("--hour-seconds", type=float, default=3600)
    playing.add_argument("--port", type=int, default=8080)
    playing.add_argument("--name", default="Eko")
    playing.add_argument("--workspace", default=str(ROOT / "runs" / "eko"))
    playing.add_argument("--no-soul", action="store_true")
    playing.set_defaults(func=play)

    grading = sub.add_parser("eval", help="run one of the four held-out goals")
    grading.add_argument("--task", default="all", choices=["all", *GOALS.keys()])
    grading.add_argument("--seconds", type=float, default=90)
    grading.add_argument("--workspace", default=str(ROOT / "runs" / "eko"))
    grading.set_defaults(func=evaluate)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
