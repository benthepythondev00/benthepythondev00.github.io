import csv
import io
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YIELD_DIR = ROOT / "yield"
SNAP_PATH = ROOT / "data" / "yield-snapshots" / "latest.json"


class TestYieldDirectory(unittest.TestCase):
    def test_snapshot_and_pages_exist(self):
        self.assertTrue(SNAP_PATH.is_file(), "latest.json snapshot missing")
        data = json.loads(SNAP_PATH.read_text())
        markets = data["markets"]
        self.assertGreaterEqual(len(markets), 40)
        self.assertTrue((YIELD_DIR / "index.html").is_file())
        self.assertTrue((YIELD_DIR / "summary.csv").is_file())
        self.assertTrue((YIELD_DIR / "style.css").is_file())

        for m in markets:
            mdir = YIELD_DIR / m["country"] / m["slug"]
            html_path = mdir / "index.html"
            csv_path = mdir / "sample.csv"
            self.assertTrue(html_path.is_file(), f"missing {html_path}")
            self.assertTrue(csv_path.is_file(), f"missing {csv_path}")

            html_text = html_path.read_text()
            self.assertIn('content="index,follow"', html_text)
            self.assertIn('"@type": "Dataset"', html_text)
            self.assertIn('"@type": "FAQPage"', html_text)
            self.assertNotIn('"@type": "Product"', html_text)
            self.assertIn(f'href="https://benthepythondev00.github.io/yield/{m["country"]}/{m["slug"]}/"', html_text)
            self.assertIn("calc-panel", html_text)

            rows = list(csv.DictReader(io.StringIO(csv_path.read_text())))
            self.assertEqual(len(rows), 25, f"{csv_path} should have 25 rows")
            for r in rows:
                self.assertNotIn("agent", r)
                self.assertTrue(float(r["price"]) > 0)

    def test_sitemap_includes_approved_yield_pages(self):
        sm = (ROOT / "sitemap.xml").read_text()
        self.assertIn("https://benthepythondev00.github.io/yield/", sm)
        self.assertIn("https://benthepythondev00.github.io/yield/es/madrid-salamanca/", sm)


if __name__ == "__main__":
    unittest.main()
