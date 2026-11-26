"""Unit tests for scripts/build_rent_drops.py. Synthetic fixture only; run: python -m unittest discover -s tests"""
import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_rent_drops as B  # noqa: E402

D = "2026-11-26"
METHOD = {"label": "Publicly advertised asking rents and move-in specials. Not signed lease transactions, "
                   "not private rent-roll data, not pricing or legal advice.",
          "net_effective_formula": "f", "concession_value": "v", "already_net": "a", "concession_share_basis": "b",
          "bedroom_floor_n": 20, "per_bed_filter": "p", "rent_cuts": "r"}


def bucket(label, n, head=None, net=None):
    e = {"label": label, "n": n, "published": n >= 20}
    if n >= 20:
        e.update({"headline_median": head, "net_effective_median": net,
                  "headline": {"n": n, "p25": head - 100, "median": head, "p75": head + 200},
                  "rent_per_sqft_median": 2.1, "sqft_median": 700})
    return e


def locked():
    return {"weeks_collected": 1, "weeks_needed": 4, "unlocked": False, "baseline_date": None, "span_days": 0,
            "count": None, "n_matched": None, "share_pct": None, "median_cut_pct": None, "plan_cuts": None,
            "n_plans_matched": None}


def row(i, src="apartments-com", fw=8.0, asking=1500, net=1300, name="Test Place", url=None):
    return {"listing_id": f"id{i}", "source": src, "property_name": name, "city": "Testville", "zip": "78701",
            "beds": 1, "sqft": 700, "asking_rent": asking, "rent_per_sqft": 2.14,
            "concession_verified": "yes" if fw else "no", "concession_type": "free_time" if fw else "",
            "free_weeks": fw if fw else "", "net_effective_rent": net, "snapshot_date": D,
            "listing_url": url or f"https://www.apartments.com/test-{i}/abc{i}/"}


def full_metro():
    return {
        "slug": "testville-tx", "label": "Testville, TX", "city": "Testville", "state": "TX", "location": "Testville, TX",
        "snapshot_date": D, "n_apartments_com": 99, "n_zumper": 100, "n_priced": 199, "n_floor_plans": 900,
        "n_plans_removed_per_bed": 4,
        "concessions": {"basis": "apartments-com properties", "n_properties": 99, "n_with_specials_text": 80,
                        "n_verified": 70, "share_pct": 70.7, "kinds": {"free_time": 60, "dollar_off": 10},
                        "median_free_weeks": 8.0, "max_free_weeks": 12.0, "median_effective_discount_pct": 15.38,
                        "n_already_net": 2},
        "bedrooms": {"0": bucket("Studio", 40, 1300, 1150), "1": bucket("1BR", 300, 1500, 1320),
                     "2": bucket("2BR", 200, 1900, 1700), "3": bucket("3BR", 50, 2300, 2100)},
        "rent_per_sqft_median": 2.0,
        "zumper_spread": {"0": None, "1": {"label": "1BR", "n_apartments_com": 40, "n_zumper": 45,
                                           "apartments_com_median": 1500, "zumper_median": 1400, "spread_pct": -6.7},
                          "2": None, "3": None},
        "rent_cuts_30d": locked(),
        "sample_rows": [row(i) for i in range(18)] + [row(100 + i, src="zumper", fw=None, net="") for i in range(7)],
    }


def sparse_metro():
    m = full_metro()
    m.update({"slug": "smallton-oh", "label": "Smallton, OH", "city": "Smallton", "state": "OH",
              "location": "Smallton, OH", "n_apartments_com": 30, "n_zumper": 31, "n_priced": 61})
    m["concessions"] = {"basis": "apartments-com properties", "n_properties": 30, "n_with_specials_text": 3,
                        "n_verified": 0, "share_pct": 0.0, "kinds": {}, "median_free_weeks": None,
                        "max_free_weeks": None, "median_effective_discount_pct": None, "n_already_net": 0}
    m["bedrooms"] = {"0": bucket("Studio", 3), "1": bucket("1BR", 25, 1100, 1100), "2": bucket("2BR", 12),
                     "3": bucket("3BR", 0)}
    m["zumper_spread"] = {b: None for b in "0123"}
    return m


def snap(*metros):
    return {"snapshot_date": D, "method": METHOD, "metros": list(metros) or [full_metro(), sparse_metro()]}


def visible_text(page):
    page = re.sub(r"<script.*?</script>|<style.*?</style>|<head>.*?</head>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


def jsonld(page):
    return [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]


class Validation(unittest.TestCase):
    def test_mismatched_metro_date_aborts(self):
        s = snap()
        s["metros"][1]["snapshot_date"] = "2026-11-19"
        with self.assertRaisesRegex(B.SnapshotError, "snapshot_date"):
            B.validate(s)

    def test_mismatched_sample_row_date_aborts(self):
        s = snap()
        s["metros"][0]["sample_rows"][3]["snapshot_date"] = "2026-11-19"
        with self.assertRaisesRegex(B.SnapshotError, "sample row dated"):
            B.validate(s)

    def test_unexpected_sample_field_aborts(self):
        s = snap()
        s["metros"][0]["sample_rows"][0]["agent_phone"] = "x"
        with self.assertRaisesRegex(B.SnapshotError, "unexpected fields"):
            B.validate(s)

    def test_locked_cuts_with_count_aborts(self):
        s = snap()
        s["metros"][0]["rent_cuts_30d"]["count"] = 5
        with self.assertRaisesRegex(B.SnapshotError, "locked"):
            B.validate(s)

    def test_published_bucket_below_20_aborts(self):
        s = snap()
        s["metros"][0]["bedrooms"]["0"].update({"n": 12, "published": True})
        with self.assertRaisesRegex(B.SnapshotError, "n=12"):
            B.validate(s)

    def test_missing_key_aborts(self):
        s = snap()
        del s["metros"][0]["concessions"]
        with self.assertRaisesRegex(B.SnapshotError, "concessions"):
            B.validate(s)


class Rounding(unittest.TestCase):
    def test_half_up_matches_browser_math_round(self):
        self.assertEqual(B.usd(1378.5), "$1,379")
        self.assertEqual(B.usd(1377.5), "$1,378")
        self.assertEqual(B.pct(62.5), "63%")
        self.assertEqual(B.pct(10.25, 1), "10.3%")
        self.assertEqual(B.pct(0.0), "0%")


class Summary(unittest.TestCase):
    def test_summary_word_range_full_and_sparse(self):
        for m in snap()["metros"]:
            n = B.words(B.summary_text(m, D))
            self.assertTrue(130 <= n <= 170, (m["slug"], n))

    def test_hub_summary_range(self):
        n = B.words(B.hub_summary(snap()))
        self.assertTrue(130 <= n <= 170, n)

    def test_summary_in_first_30_percent(self):
        s = snap()
        for m in s["metros"]:
            t = visible_text(B.metro_page(m, s))
            start = t.index(B.esc(B.summary_text(m, D))[:60])
            self.assertLess(start / len(t), 0.30, m["slug"])
        t = visible_text(B.hub_page(s))
        self.assertLess(t.index(B.hub_summary(s)[:60]) / len(t), 0.30)


class RedLines(unittest.TestCase):
    def setUp(self):
        self.s = snap()
        self.full = B.metro_page(self.s["metros"][0], self.s)
        self.sparse = B.metro_page(self.s["metros"][1], self.s)

    def test_held_bucket_shows_count_not_number(self):
        self.assertIn("Not shown: 3 floor plans in the sample, below the 20 needed", self.sparse)
        self.assertIn("Not shown: 12 floor plans", self.sparse)
        beds = re.search(r'<section id="bedrooms".*?</section>', self.sparse, re.S).group(0)
        studio = re.search(r"<tr class=\"held\">\s*<th scope=\"row\">Studio</th>.*?</tr>", beds, re.S).group(0)
        self.assertNotIn("$", studio)

    def test_locked_cuts_publish_no_count_anywhere(self):
        t = visible_text(self.full)
        self.assertIn("1 of 4 weekly snapshots collected", t)
        self.assertIn("December 17, 2026", t)
        self.assertNotRegex(t, r"\d+ of \d+ repeat listings")
        for o in jsonld(self.full):
            self.assertNotIn("repeat listings", json.dumps(o))

    def test_unlocked_cuts_shown(self):
        s = snap()
        s["metros"][0]["rent_cuts_30d"].update({"weeks_collected": 4, "unlocked": True, "baseline_date": "2026-10-29",
                                                "count": 17, "n_matched": 150, "share_pct": 11.3,
                                                "median_cut_pct": 3.2})
        t = visible_text(B.metro_page(s["metros"][0], s))
        self.assertIn("17 of 150 repeat listings", t)
        self.assertIn("median cut of 3.2%", t)

    def test_label_on_every_page(self):
        for page in (self.full, self.sparse, B.hub_page(self.s)):
            self.assertIn(METHOD["label"], page)
            self.assertIn("not signed lease", visible_text(page).lower())

    def test_portal_text_is_escaped(self):
        s = snap()
        s["metros"][0]["sample_rows"][0]["property_name"] = '<script>alert(1)</script> & "Co"'
        page = B.metro_page(s["metros"][0], s)
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;Co&quot;", page)

    def test_non_portal_url_not_linked(self):
        s = snap()
        s["metros"][0]["sample_rows"][0]["listing_url"] = "javascript:alert(1)"
        page = B.metro_page(s["metros"][0], s)
        self.assertNotIn("javascript:alert", page)

    def test_contact_text_blocks_build(self):
        s = snap()
        s["metros"][0]["sample_rows"][0]["property_name"] = "Call 512-555-0100"
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(B.SnapshotError, "contact-like"):
            B.build(s, Path(tmp))

    def test_spread_null_buckets_render_note(self):
        self.assertIn("Not compared: fewer than 20 listings", self.sparse)
        self.assertIn("-6.7%", self.full)

    def test_zero_share_metro_renders(self):
        t = visible_text(self.sparse)
        self.assertIn("0%", t)
        self.assertNotIn("None", t)
        self.assertNotIn("nan", t.lower().split())


class Schema(unittest.TestCase):
    def test_faq_jsonld_equals_visible_faq(self):
        s = snap()
        for m in s["metros"]:
            page = B.metro_page(m, s)
            faq = next(o for o in jsonld(page) if o["@type"] == "FAQPage")
            vis = re.findall(r"<details><summary>(.*?)</summary><p>(.*?)</p></details>", page, re.S)
            vis = [(B.html.unescape(q), B.html.unescape(a)) for q, a in vis]
            ld = [(q["name"], q["acceptedAnswer"]["text"]) for q in faq["mainEntity"]]
            self.assertEqual(vis, ld)

    def test_dataset_jsonld(self):
        s = snap()
        page = B.metro_page(s["metros"][0], s)
        ds = next(o for o in jsonld(page) if o["@type"] == "Dataset")
        self.assertEqual(ds["dateModified"], D)
        self.assertEqual(ds["distribution"][0]["contentUrl"],
                         "https://benthepythondev00.github.io/data/rent-drops/samples/testville-tx.csv")
        self.assertEqual(ds["spatialCoverage"]["name"], "Testville, TX")

    def test_one_snapshot_date_everywhere(self):
        s = snap()
        page = B.metro_page(s["metros"][0], s)
        dates = set(re.findall(r'datetime="(\d{4}-\d{2}-\d{2})"', page)) - {B.unlock_date(D, s["metros"][0]["rent_cuts_30d"])}
        self.assertEqual(dates, {D})
        self.assertNotRegex(visible_text(page), r"November (?!26, 2026)\d+, 2026")

    def test_noindex_by_default(self):
        s = snap()
        self.assertIn('<meta name="robots" content="noindex,follow"', B.metro_page(s["metros"][0], s))

    def test_title_length(self):
        s = snap()
        for m in s["metros"]:
            title = re.search(r"<title>(.*?)</title>", B.metro_page(m, s)).group(1)
            self.assertTrue(15 <= len(B.html.unescape(title)) <= 70, title)


class Ctas(unittest.TestCase):
    def test_utm_tagged_ctas(self):
        s = snap()
        page = B.metro_page(s["metros"][0], s)
        self.assertIn("/feeds/?utm_source=rent_drops&amp;utm_medium=cta&amp;utm_campaign=testville-tx#real-estate", page)
        self.assertIn("https://listingrail.com/pricing/?utm_source=rent_drops&amp;utm_medium=cta&amp;utm_campaign=testville-tx", page)
        self.assertIn("https://apify.com/benthepythondev/zumper-rental-scraper?utm_source=rent_drops", page)
        self.assertIn("$199, $499 or $999 a month", page)
        self.assertIn("$10, $49 or $149 a month", page)

    def test_csv_link_and_snippet(self):
        s = snap()
        page = B.metro_page(s["metros"][0], s)
        self.assertIn('href="/data/rent-drops/samples/testville-tx.csv"', page)
        self.assertIn("&quot;location&quot;:&quot;Testville, TX&quot;", page)


class Build(unittest.TestCase):
    def test_build_writes_pages_and_drops_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            stale = out / "gone-xx" / "index.html"
            stale.parent.mkdir(parents=True)
            stale.write_text("old")
            paths = B.build(snap(), out)
            self.assertEqual(len(paths), 3)
            self.assertTrue((out / "testville-tx" / "index.html").is_file())
            self.assertFalse(stale.exists())

    def test_main_errors_without_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(B.main(["--snapshot", str(Path(tmp) / "nope.json"), "--out", tmp]), 1)

    def test_neighbours_prefer_same_state(self):
        a, b = full_metro(), copy.deepcopy(full_metro())
        b.update({"slug": "other-tx", "label": "Other, TX"})
        c = sparse_metro()
        self.assertEqual([x["slug"] for x in B.neighbours(a, [a, c, b])][:1], ["other-tx"])


if __name__ == "__main__":
    unittest.main()
