import csv
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HomeHubsTest(unittest.TestCase):
    def test_build_is_idempotent(self):
        out = subprocess.run([sys.executable, "scripts/build_home_hubs.py", "--dry-run"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("index.html unchanged", out)

    def test_every_sitemap_url_within_two_clicks(self):
        r = subprocess.run([sys.executable, "scripts/check_reachability.py", "--max-depth", "2"], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_static_hubs_and_yield_markets(self):
        html = (ROOT / "index.html").read_text()
        for h2 in ["Managed B2B Data Feeds", "EU &amp; US Rental Yield Benchmarks", "Reddit Archive Data Samples",
                   "Paid Telegram Memberships", "Apify &amp; RapidAPI Scrapers"]:
            self.assertRegex(html, rf"<h2[^>]*>{re.escape(h2)}</h2>")
        self.assertIn('href="https://benthepythondev00.github.io/memberwall/"', html)
        for row in csv.DictReader((ROOT / "yield" / "summary.csv").open()):
            self.assertIn(row["page_url"].replace("https://benthepythondev00.github.io/", "./"), html)


if __name__ == "__main__":
    unittest.main()
