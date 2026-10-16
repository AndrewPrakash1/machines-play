"""Ways of poking the island: in-process for tests, HTTP when a viewer is watching."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class WorldDriver:
    def __init__(self, world, seconds=None):
        self.world = world
        self.t0 = world.time
        self.budget = seconds

    def expired(self) -> bool:
        return self.budget is not None and (self.world.time - self.t0) >= self.budget

    def observe(self):
        return self.world.observe()

    def act(self, kind, data=None):
        if not self.expired():
            self.world.act(kind, data or {})
        return self.observe()

    def chat(self, text):
        if text:
            self.world.say(text)

    def wait(self, seconds) -> bool:
        if self.expired():
            return False
        remain = seconds
        if self.budget is not None:
            remain = min(seconds, self.budget - (self.world.time - self.t0))
        if remain <= 0:
            return False
        self.world.advance(remain)
        return not self.expired()

    @property
    def elapsed(self) -> float:
        return self.world.time - self.t0


class HttpDriver:
    def __init__(self, base_url, session, seconds=None):
        self.base = base_url.rstrip("/")
        self.session = session
        self.t0 = time.monotonic()
        self.budget = seconds

    def expired(self) -> bool:
        return self.budget is not None and (time.monotonic() - self.t0) >= self.budget

    def _request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"X-Session": self.session, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}

    def observe(self):
        return self._request("GET", "/observe")

    def act(self, kind, data=None):
        if self.expired():
            return self.observe()
        return self._request("POST", "/input", {"type": kind, "data": data or {}})

    def chat(self, text):
        if text and not self.expired():
            self._request("POST", "/chat", {"content": text})

    def wait(self, seconds) -> bool:
        if self.expired():
            return False
        remain = seconds
        if self.budget is not None:
            remain = min(seconds, self.budget - (time.monotonic() - self.t0))
        if remain <= 0:
            return False
        time.sleep(remain)
        return not self.expired()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.t0


def join(base_url, name="Eko"):
    req = urllib.request.Request(base_url.rstrip("/") + f"/join?name={name}", method="POST")
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read())
