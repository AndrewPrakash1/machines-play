import json
import time
import unittest
import urllib.request

from eko.server import serve
from eko.world import World


class ApiTests(unittest.TestCase):
    def test_join_move_and_viewer(self):
        world = World()
        server, island = serve(0, world)
        port = server.server_address[1]
        base = f"http://127.0.0.1:{port}"
        try:
            page = urllib.request.urlopen(base + "/", timeout=5)
            html = page.read().decode()
            self.assertIn("Mesa", html)

            joined = json.loads(urllib.request.urlopen(urllib.request.Request(base + "/join?name=Eko", method="POST"), timeout=5).read())
            self.assertTrue(joined["session"])
            headers = {"X-Session": joined["session"], "Content-Type": "application/json"}
            start = json.loads(urllib.request.urlopen(urllib.request.Request(base + "/observe", headers=headers), timeout=5).read())
            urllib.request.urlopen(
                urllib.request.Request(
                    base + "/input",
                    data=json.dumps({"type": "MoveTo", "data": {"position": [8, 0, 0]}}).encode(),
                    headers=headers,
                    method="POST",
                ),
                timeout=5,
            )
            time.sleep(0.6)
            later = json.loads(urllib.request.urlopen(urllib.request.Request(base + "/observe", headers=headers), timeout=5).read())
            self.assertGreater(later["player"]["position"][0], start["player"]["position"][0] + 2)

            spec = json.loads(urllib.request.urlopen(base + "/spectate", timeout=5).read())
            self.assertIn("Spire", {body["name"] for body in spec["bodies"]})
            urllib.request.urlopen(
                urllib.request.Request(base + "/chat", data=json.dumps({"content": "hello island"}).encode(), headers=headers, method="POST"),
                timeout=5,
            )
            spec = json.loads(urllib.request.urlopen(base + "/spectate", timeout=5).read())
            self.assertTrue(any("hello island" in message["content"] for message in spec["chat"]))
        finally:
            island.running = False
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
