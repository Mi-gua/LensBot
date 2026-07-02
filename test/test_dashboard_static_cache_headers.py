from __future__ import annotations

import http.client
import re
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from src.ui.gui import DashboardHandler, build_index_html


class DashboardStaticCacheHeadersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _request(self, method: str, path: str) -> http.client.HTTPResponse:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request(method, path)
        response = conn.getresponse()
        response.read()
        return response

    def test_ui_javascript_get_is_not_cached(self) -> None:
        response = self._request("GET", "/ui/dashboard.js")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store, max-age=0")
        self.assertEqual(response.getheader("Pragma"), "no-cache")

    def test_ui_javascript_head_is_not_cached(self) -> None:
        response = self._request("HEAD", "/ui/dashboard.js")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Cache-Control"), "no-store, max-age=0")
        self.assertEqual(response.getheader("Pragma"), "no-cache")

    def test_index_uses_versioned_ui_assets(self) -> None:
        html = build_index_html()

        self.assertRegex(html, r'href="/ui/dashboard\.css\?v=\d+"')
        self.assertRegex(html, r'src="/ui/dashboard\.js\?v=\d+"')
        self.assertNotRegex(html, r'href="/ui/dashboard\.css"')
        self.assertNotRegex(html, r'src="/ui/dashboard\.js"')


if __name__ == "__main__":
    unittest.main()
