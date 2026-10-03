"""Offline rendering contracts for the website; no fabricated live readings."""
from __future__ import annotations

import json
import http.client
import http.server
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

import website
import stress


def payload(html: str) -> dict:
    return json.loads(html.split('<script id="site-data" type="application/json">', 1)[1].split('</script>', 1)[0])


class WebsiteTests(unittest.TestCase):
    def test_empty_page_has_no_made_up_reading(self) -> None:
        html = website.render(version="test", live=True)
        state = payload(html)
        self.assertIsNone(state["reading"])
        self.assertEqual(state["factors"], [])
        self.assertTrue(state["live"])
        self.assertIn('lang="he" dir="rtl"', html)
        self.assertNotIn('/* SITE_JS */', html)
        self.assertNotIn('/* SITE_CSS */', html)
        self.assertNotIn('/* PREMARKET_JS */', html)
        self.assertNotIn('/* PREMARKET_CSS */', html)

    def test_premarket_snapshot_is_preserved_without_affecting_reading(self) -> None:
        premarket = {"session": "פרימרקט", "is_stale": False,
                     "es": {"change_pct": -0.4, "at": "2026-09-14T12:45:00+03:00"},
                     "spy": {"change_pct": -0.8, "at": "2026-09-14T12:45:00+03:00"},
                     "historical": None, "score_input": False}
        state = payload(website.render(premarket=premarket))
        self.assertEqual(state["premarket"], premarket)
        self.assertIsNone(state["reading"])

    def test_model_values_and_gaps_are_preserved(self) -> None:
        idx = pd.bdate_range("2024-01-01", periods=3)
        export = pd.DataFrame({"chance_pct": [12.0, None, 25.0],
                               "percentile": [40.0, None, 73.0],
                               "regime": ["NORMAL", "NORMAL", "ELEVATED"]}, index=idx)
        res = pd.DataFrame({"MSS_5d": [None, None, 2.0], "vix_level": [20, 30, 81]}, index=idx)
        px = pd.DataFrame({"^GSPC": [100.0, 101.0, 102.0]}, index=idx)
        state = payload(website.render(export, res, px, ["vix_level"]))
        self.assertEqual(state["reading"]["chance"], 25)
        self.assertEqual(state["reading"]["mss"], 73)
        self.assertIsNone(state["history"]["chance"][1]["value"])
        self.assertEqual(state["factors"][0]["value"], 81)
        self.assertAlmostEqual(state["markets"][0]["change"], (102 / 101 - 1) * 100)
        self.assertIsNone(state["markets"][1]["value"])

    def test_untrusted_strings_cannot_close_json_element(self) -> None:
        attack = '</script><img src=x onerror=alert(1)>'
        html = website.render(notice=attack)
        self.assertNotIn(attack, html)
        self.assertEqual(payload(html)["notice"], attack)

    def test_nonfinite_values_become_null(self) -> None:
        for value in [float("nan"), float("inf"), -float("inf"), None, pd.NA]:
            self.assertIsNone(website.number(value))

    def test_server_rejects_overlapping_updates_and_keeps_page_on_failure(self) -> None:
        ready, started, release = threading.Event(), threading.Event(), threading.Event()
        servers: list[http.server.ThreadingHTTPServer] = []
        class TestServer(http.server.ThreadingHTTPServer):
            def serve_forever(self, poll_interval: float = 0.05) -> None:
                servers.append(self)
                ready.set()
                super().serve_forever(poll_interval)

        def failing_build(*args, **kwargs) -> str:
            started.set()
            if not release.wait(5):
                raise TimeoutError("test release timed out")
            raise RuntimeError("test data source unavailable")

        def request(method: str, route: str, origin: str | None = None) -> tuple[int, bytes]:
            conn = http.client.HTTPConnection("127.0.0.1", servers[0].server_port, timeout=5)
            try:
                conn.request(method, route, headers={"Origin": origin} if origin else {})
                result = conn.getresponse()
                return result.status, result.read()
            finally:
                conn.close()

        args = SimpleNamespace(preview=True, no_open=True)
        with patch.object(http.server, "ThreadingHTTPServer", TestServer), \
             patch.object(website, "cached_page", return_value="last good reading"), \
             patch.object(stress, "build", side_effect=failing_build):
            worker = threading.Thread(target=stress.serve, args=(args, 0), daemon=True)
            worker.start()
            self.assertTrue(ready.wait(5))
            first: list[tuple[int, bytes]] = []
            refresh = threading.Thread(target=lambda: first.append(request("POST", "/refresh")))
            try:
                self.assertEqual(request("POST", "/refresh", "https://unrelated.example")[0], 403)
                refresh.start()
                self.assertTrue(started.wait(5))
                self.assertEqual(request("POST", "/analyze")[0], 409)
                self.assertEqual(request("POST", "/refresh")[0], 409)
                self.assertEqual(request("GET", "/")[1], b"last good reading")
                release.set()
                refresh.join(5)
                self.assertEqual(first[0][0], 500)
                self.assertFalse(json.loads(request("GET", "/status")[1])["running"])
                self.assertEqual(request("GET", "/")[1], b"last good reading")
                with patch.object(stress, "build", return_value="new reading"):
                    self.assertEqual(request("POST", "/refresh")[0], 200)
                    self.assertEqual(request("GET", "/")[1], b"new reading")
            finally:
                release.set()
                if refresh.ident is not None:
                    refresh.join(5)
                servers[0].shutdown()
                servers[0].server_close()
                worker.join(5)


if __name__ == "__main__":
    unittest.main()
