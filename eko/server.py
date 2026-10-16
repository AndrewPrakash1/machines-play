"""HTTP body for the island. The agent never sees pixels; the browser does."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from eko.prompts import API_MD
from eko.world import DT, World

WEB_ROOT = Path(__file__).resolve().parents[1] / "web"


class Island:
    def __init__(self, world: World | None = None):
        self.world = world or World()
        self.lock = threading.Lock()
        self.running = True

    def loop(self):
        next_tick = time.perf_counter()
        while self.running:
            try:
                with self.lock:
                    self.world.step()
            except Exception:
                import traceback
                traceback.print_exc()
                self.running = False
                return
            next_tick += DT
            delay = next_tick - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.perf_counter()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    @property
    def island(self) -> Island:
        return self.server.island  # type: ignore[attr-defined]

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _send(self, code, payload=None, content_type="application/json", body=None):
        if body is None:
            body = json.dumps(payload if payload is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _session_ok(self) -> bool:
        token = self.headers.get("X-Session", "")
        with self.island.lock:
            expected = self.island.world.session
        if not expected or token != expected:
            self._send(401, {"error": "Join first and send that session as X-Session."})
            return False
        return True

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Session")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._file(WEB_ROOT / "index.html", "text/html; charset=utf-8")
            return
        if path == "/api.md":
            self._send(200, content_type="text/markdown; charset=utf-8", body=API_MD.encode())
            return
        if path == "/health":
            self._send(200, {"ok": True})
            return
        if path == "/spectate":
            with self.island.lock:
                payload = self.island.world.spectate()
            self._send(200, payload)
            return
        if path == "/observe":
            if not self._session_ok():
                return
            with self.island.lock:
                payload = self.island.world.observe()
            self._send(200, payload)
            return
        if path == "/chat/messages":
            if not self._session_ok():
                return
            with self.island.lock:
                messages = list(self.island.world.chat)
            self._send(200, {"messages": messages})
            return
        if path == "/observe/image":
            self._send(404, {"error": "This island gives text observations only."})
            return
        if path == "/favicon.ico":
            self._send(204, body=b"")
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/join":
            name = parse_qs(parsed.query).get("name", ["Eko"])[0] or "Eko"
            with self.island.lock:
                world = self.island.world
                if world.session is None:
                    import uuid
                    world.session = str(uuid.uuid4())
                    world.player.name = name[:32]
                payload = {"session": world.session, "agent_id": world.player.agent_id, "name": world.player.name}
            self._send(200, payload)
            return
        if path == "/admin/reset":
            with self.island.lock:
                self.island.world.reset()
                tick = self.island.world.tick
            self._send(200, {"ok": True, "tick": tick})
            return
        if not self._session_ok():
            return
        if path == "/input":
            body = self._read_json()
            kind = body.get("type") or body.get("input")
            data = body.get("data") or {}
            with self.island.lock:
                self.island.world.act(str(kind or ""), data)
                payload = self.island.world.observe()
            self._send(200, payload)
            return
        if path == "/chat":
            body = self._read_json()
            with self.island.lock:
                self.island.world.say(body.get("content", ""))
            self._send(200, {"ok": True})
            return
        self._send(404, {"error": "not found"})

    def _file(self, path: Path, content_type: str):
        if not path.exists():
            self._send(404, {"error": "missing viewer"})
            return
        body = path.read_bytes()
        self._send(200, content_type=content_type, body=body)


def serve(port=8080, world: World | None = None):
    island = Island(world)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.island = island  # type: ignore[attr-defined]
    physics = threading.Thread(target=island.loop, name="island-physics", daemon=True)
    physics.start()
    http = threading.Thread(target=server.serve_forever, name="island-http", daemon=True)
    http.start()
    return server, island
