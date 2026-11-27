"""Off-site links carry data-qa-skip so the QA crawler does not open hundreds of third-party
popups. This test checks each skipped control is what it claims to be: an https link to
another site that opens in a new tab with rel=noopener. Nothing on our own site is skipped."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["jobs-in-germany/index.html", "jobs-in-denmark/index.html", "jobs-in-germany/template.html",
         "jobs-in-denmark/template.html", "custom-apify-actor.html", "how-to-get-reddit-posts-and-comments-data.html"]
OWN = ("https://benthepythondev00.github.io",)


class Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skipped, self.blank_unskipped = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "data-qa-skip" in a:
            self.skipped.append((tag, a))
        elif tag == "a" and a.get("target") == "_blank":
            self.blank_unskipped.append(a)


class TestOutboundLinks(unittest.TestCase):
    def test_skipped_controls_are_external_new_tab_links(self):
        total = 0
        for rel in PAGES:
            p = Collect()
            p.feed((ROOT / rel).read_text())
            for tag, a in p.skipped:
                total += 1
                with self.subTest(page=rel, href=a.get("href")):
                    self.assertEqual(tag, "a")
                    href = a.get("href") or ""
                    self.assertTrue(href.startswith("https://") or href.startswith("__"), href)
                    self.assertFalse(href.startswith(OWN), href)
                    self.assertEqual(a.get("target"), "_blank")
                    self.assertIn("noopener", a.get("rel") or "")
            with self.subTest(page=rel):
                self.assertEqual(p.blank_unskipped, [], "new-tab link without data-qa-skip")
        self.assertGreater(total, 400)

    def test_builders_emit_the_skip_marker(self):
        for rel in ("scripts/build_germany_jobs.py", "scripts/build_denmark_jobs.py"):
            src = (ROOT / rel).read_text()
            self.assertRegex(src, r'class="orig" href="\{e\(j\["url"\]\)\}" target="_blank" rel="noopener" data-qa-skip')


if __name__ == "__main__":
    unittest.main()
