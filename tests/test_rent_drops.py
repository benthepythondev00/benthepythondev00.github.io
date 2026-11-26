"""Unit tests for the /rent-drops/ snapshot pipeline (offline, fixtures only)."""
import csv
import io
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import rent_drops_lib as R  # noqa: E402

OUT_DIR = ROOT / "data" / "rent-drops"

# (special text, verified, free_weeks, dollar_off, already_net) — real Apartments.com Austin strings, 2026-11-26
GOLDEN = [
    ("Receive up to 6 weeks of free rent! *Select apartment homes qualify.", True, 6.0, None, False),
    ("Get up to Six Weeks OFF on Select Homes *Limited time offer.", True, 6.0, None, False),
    ("For a limited time, enjoy up to ONE MONTH FREE when you join our grand community!", True, 4.33, None, False),
    ("Get up to 12 weeks free! Contact the office for more details!; Get up to 12 weeks free! Contact the office!", True, 12.0, None, False),
    ("Up to 10 WEEKS FREE BASE RENT with Brand New Residences!", True, 10.0, None, False),
    ("Enjoy 3 Months Free, move-in by 11/30", True, 13.0, None, False),
    ("8 Weeks free base Rent on Single-Family homes & 6 Weeks free base Rent on Apartments", True, 8.0, None, False),
    ("??6–8 weeks free on select units ?? Limited availability", True, 8.0, None, False),
    ("Up to 12 WEEKS FREE + $1,000 Look & Lease Incentive!", True, 12.0, 1000.0, False),
    ("$1000 OFF the first full month on all move ins by December 5th!", True, None, 1000.0, False),
    ("$250 Off Select Apartment Homes! Restrictions apply", True, None, 250.0, False),
    ("ENJOY FIRST FULL MONTH OF RENT OFF! | *Terms and conditions may apply.", True, 4.33, None, False),
    ("2nd full month free on top of your discounted rent!", True, 4.33, None, False),
    # Already-net: the advertised rent already includes the concession
    ("Now Offering 10 Weeks FREE! 1 Bedrooms from $1,184. Advertised rates reflect 10 weeks free.", True, 10.0, None, True),
    ("2 Months Free - Rolled into 12 month lease for lower monthly payment", True, 8.67, None, True),
    ("* Advertised rates include 2.5 months off! * Terms and conditions apply.", True, 10.83, None, True),
    # Generic taglines / non-rent offers: NOT concessions
    ("*Terms and conditions apply—contact the leasing office for details.", False, None, None, False),
    ("Ask about our current Move In Specials!", False, None, None, False),
    ("Austin’s Largest Award-Winning Floor Plans - Luxury Living with Breathtaking Skyline Views!", False, None, None, False),
    ("Shorter Leases. Better Rates. Enjoy great rates on lease terms as short as 7 months.", False, None, None, False),
    ("$299 Total Move In!", False, None, None, False),
    ("Move-In By 12/30 To Take Advantage Of This Limited-Time Offer!", False, None, None, False),
    ("Save big! Don’t pay rent till 2027 on select 4-bedroom homes. 12-month+ lease terms only.", False, None, None, False),
    ("IDEAL LOCATION NEAR UT AUSTIN | WAITLIST OPTIONS AVAILABLE", False, None, None, False),
    ("$50 off application fee", False, None, None, False),
    ("Terms apply. Limited time only!", False, None, None, False),
]


class TestConcessionParser(unittest.TestCase):
    def test_golden_table(self):
        for text, verified, weeks, dollars, net in GOLDEN:
            with self.subTest(text=text):
                c = R.parse_concession([text])
                self.assertEqual(c["verified"], verified)
                self.assertEqual(c["free_weeks"], weeks)
                self.assertEqual(c["dollar_off"], dollars)
                self.assertEqual(c["already_net"], net)

    def test_dollar_amounts_that_are_not_rent_off(self):
        for text in ["One-Bedroom Homes Starting at $1,195!", "PLUS, up to a $1,000 GIFT CARD when you tour today!",
                     "Only $25 to apply", "up to $2000 for employer partnerships", "Must select 13-18 months"]:
            with self.subTest(text=text):
                c = R.parse_concession([text])
                self.assertIsNone(c["dollar_off"])
                self.assertIsNone(c["free_weeks"])

    def test_reduced_fee_is_not_waived(self):
        c = R.parse_concession(["Plus REDUCED $99 APP/ADMIN FEES"])
        self.assertFalse(c["waived_fees"])
        self.assertFalse(c["verified"])
        self.assertTrue(R.parse_concession(["Waived Application Fee"])["waived_fees"])
        self.assertTrue(R.parse_concession(["$0 admin fee this week"])["waived_fees"])

    def test_look_and_lease_fee_special_has_no_rent_value(self):
        c = R.parse_concession(["Look and Lease $99 app/admin special!"])
        self.assertIn("look_and_lease", c["kinds"])
        self.assertIsNone(c["dollar_off"])

    def test_percent_off(self):
        c = R.parse_concession(["UP TO 50% OFF RENT SAVINGS FOR 5 MONTHS*"])
        self.assertEqual(c["pct_off_months"], 2.5)
        c = R.parse_concession(["Enjoy up to 1/2 off Base Rent for 4 Months!"])
        self.assertEqual(c["pct_off_months"], 2.0)

    def test_matched_phrases_are_short(self):
        c = R.parse_concession(["Lease today and receive up to 10 weeks free!* Schedule a tour today! " * 5])
        self.assertTrue(all(len(x) <= 60 for x in c["matched"]))
        self.assertLessEqual(len(c["matched"]), 4)

    def test_empty(self):
        self.assertFalse(R.parse_concession(None)["verified"])
        self.assertFalse(R.parse_concession([])["verified"])


class TestNetEffective(unittest.TestCase):
    def test_weeks_free(self):
        c = R.parse_concession(["6 weeks free"])
        self.assertAlmostEqual(R.net_effective(1300, c), round(1300 * (1 - 6 / 52), 2))

    def test_dollar_off(self):
        c = R.parse_concession(["$600 off"])
        self.assertEqual(R.net_effective(1200, c), 1150.0)

    def test_already_net_not_discounted_twice(self):
        c = R.parse_concession(["Advertised rates reflect 10 weeks free"])
        self.assertEqual(R.net_effective(1184, c), 1184.0)
        self.assertEqual(R.discount_pct(1184, c), 0.0)

    def test_waived_fees_only_no_rent_change(self):
        c = R.parse_concession(["Waived application fee"])
        self.assertTrue(c["verified"])
        self.assertEqual(R.net_effective(1500, c), 1500.0)

    def test_none_concession(self):
        self.assertEqual(R.net_effective(1000, R.parse_concession(["Ask about specials"])), 1000.0)


def apt(i, price, plans, specials=None, region="TX", title=None, beds=1):
    return {
        "id": f"a{i}", "url": f"https://www.apartments.com/p/a{i}/", "source": "apartments-com",
        "title": title or f"Prop {i}", "city": "Austin", "region": region, "postal_code": "78701",
        "price": price, "beds": beds, "area": 700, "property_type": "Apartment Community",
        "agent": {"name": "Leasing Agent", "phone": "(512) 555-0101", "company": "X"},
        "raw": {"moveInSpecials": specials or [], "phone": "(512) 555-0101", "email": "leasing@example.com",
                "floorPlans": [{"name": f"P{j}", "beds": b, "rentMin": r, "sqftMin": s} for j, (b, r, s) in enumerate(plans)]},
    }


def zum(i, price, beds=1, region="TX"):
    return {"id": f"z{i}", "url": f"https://www.zumper.com/x/z{i}", "title": f"Z {i}", "city": "Austin",
            "region": region, "postal_code": "78702", "price": price, "beds": beds, "area": None,
            "agent": {"phone": "(512) 555-0199"}, "raw": {"phone": "(512) 555-0199", "agent_name": "Jane"}}


class TestCleaningAndAggregates(unittest.TestCase):
    def setUp(self):
        self.props = []
        for i in range(30):
            spec = ["Up to 8 weeks free!"] if i % 2 == 0 else ["Ask about our specials!"]
            plans = [(0, 1000 + i, 450), (1, 1300 + i, 700), (2, 1800 + i, 1000), (3, 2400 + i, 1300)]
            self.props.append(R.clean_apartments_property(apt(i, 1000 + i, plans, spec, beds=0), "TX"))
        # per-bed priced student property: 4BR at $700 and 2BR at $650 must be filtered
        self.props.append(R.clean_apartments_property(apt(98, 650, [(1, 900, 500), (2, 650, 900), (4, 700, 1400)]), "TX"))
        self.props.append(R.clean_apartments_property(apt(99, 800, [(2, 800, 900)], title="Campus Student Living"), "TX"))

    def test_whitelist_drops_pii_and_raw(self):
        p = self.props[0]
        blob = json.dumps(p)
        self.assertNotIn("555-0101", blob)
        self.assertNotIn("leasing@example.com", blob)
        self.assertNotIn("raw", p)
        self.assertNotIn("agent", p)
        z = R.clean_zumper(zum(1, 1200), "TX")
        self.assertNotIn("555-0199", json.dumps(z))
        self.assertNotIn("Jane", json.dumps(z))

    def test_wrong_state_dropped(self):
        self.assertIsNone(R.clean_apartments_property(apt(1, 1000, [(1, 1000, 700)], region="CA"), "TX"))
        self.assertIsNone(R.clean_zumper(zum(1, 1000, region="CA"), "TX"))

    def test_duplicate_plans_deduped(self):
        p = R.clean_apartments_property(apt(1, 1000, [(1, 1000, 700), (1, 1000, 700)]), "TX")
        # names differ (P0, P1) so both stay; identical name rows collapse
        raw = apt(2, 1000, [])
        raw["raw"]["floorPlans"] = [{"name": "A", "beds": 1, "rentMin": 1000, "sqftMin": 700}] * 3
        self.assertEqual(len(R.clean_apartments_property(raw, "TX")["plans"]), 1)
        self.assertEqual(len(p["plans"]), 2)

    def test_bedroom_floor_and_per_bed_filter(self):
        table, removed = R.bedroom_table(self.props)
        for b in ("0", "1", "2", "3"):
            self.assertTrue(table[b]["published"])
            self.assertEqual(table[b]["n"], 30 if b != "1" else 31)
        self.assertGreaterEqual(removed, 3)  # student property plan + 2BR/4BR per-bed plans
        self.assertEqual(table["1"]["headline_median"], 1314.0)  # 900 + 1300..1329: 16th of 31 values
        # half the properties have 8 weeks free -> net-effective median below headline
        self.assertLess(table["2"]["net_effective_median"], table["2"]["headline_median"])

    def test_bucket_under_20_not_published(self):
        table, _ = R.bedroom_table(self.props[:10])
        self.assertFalse(table["1"]["published"])
        self.assertNotIn("headline_median", table["1"])

    def test_concession_share_counts_all_properties(self):
        s = R.concession_summary(self.props)
        self.assertEqual(s["n_properties"], 32)
        self.assertEqual(s["n_verified"], 15)
        self.assertEqual(s["share_pct"], round(15 / 32 * 100, 1))
        self.assertEqual(s["median_free_weeks"], 8.0)

    def test_spread_requires_n20_both(self):
        apts = self.props[:30]  # listing-level beds=0
        zs = [R.clean_zumper(zum(i, 1100, beds=0), "TX") for i in range(25)]
        sp = R.cross_portal_spread(apts, zs)
        self.assertIsNotNone(sp["0"])
        self.assertEqual(sp["0"]["zumper_median"], 1100)
        self.assertIsNone(sp["1"])
        sp2 = R.cross_portal_spread(apts, zs[:10])
        self.assertIsNone(sp2["0"])

    def test_sample_rows_25_sanitized(self):
        zs = [R.clean_zumper(zum(i, 1100 + i), "TX") for i in range(10)]
        rows = R.sample_rows(self.props, zs, "2026-11-26")
        self.assertEqual(len(rows), 25)
        self.assertEqual(sum(1 for r in rows if r["source"] == "zumper"), 7)
        for r in rows:
            self.assertEqual(set(r), set(R.CSV_FIELDS))
            self.assertNotIn("555", json.dumps(r))


class TestRentCuts(unittest.TestCase):
    cur = {"apartments-com": {"a1": 1000.0, "a2": 1500.0}, "zumper": {"z1": 900.0}, "plans": {"a1|1|A": 1000.0}}
    old = {"apartments-com": {"a1": 1100.0, "a2": 1500.0}, "zumper": {"z1": 950.0}, "plans": {"a1|1|A": 1100.0}}

    def test_locked_before_four_weeks(self):
        r = R.rent_cuts("2026-12-10", self.cur, {"2026-11-26": self.old, "2026-12-03": self.old})
        self.assertFalse(r["unlocked"])
        self.assertEqual(r["weeks_collected"], 3)
        self.assertIsNone(r["count"])
        self.assertIsNone(r["median_cut_pct"])

    def test_same_week_files_count_once(self):
        r = R.rent_cuts("2026-12-17", self.cur,
                        {"2026-11-26": self.old, "2026-11-27": self.old, "2026-12-03": self.old})
        self.assertEqual(r["weeks_collected"], 3)
        self.assertFalse(r["unlocked"])

    def test_unlocked_at_week_four(self):
        prior = {"2026-11-26": self.old, "2026-12-03": self.old, "2026-12-10": self.old}
        r = R.rent_cuts("2026-12-17", self.cur, prior)
        self.assertTrue(r["unlocked"])
        self.assertEqual(r["count"], 2)
        self.assertEqual(r["n_matched"], 3)
        self.assertEqual(r["plan_cuts"], 1)
        self.assertEqual(r["baseline_date"], "2026-11-26")
        self.assertEqual(r["span_days"], 21)
        self.assertEqual(r["median_cut_pct"], round(((100 / 1100 * 100) + (50 / 950 * 100)) / 2, 1))

    def test_older_than_30_days_ignored(self):
        prior = {"2026-10-01": self.old, "2026-12-03": self.old, "2026-12-10": self.old}
        r = R.rent_cuts("2026-12-17", self.cur, prior)
        self.assertEqual(r["weeks_collected"], 3)
        self.assertIsNone(r["count"])

    def test_iso_week(self):
        self.assertEqual(R.iso_week("2026-11-26"), "2026-W48")


class TestRoster(unittest.TestCase):
    def test_failure_outside_roster_is_ignored_inside_aborts(self):
        import fetch_rent_drops as F
        metros = [F.metro_dict(f"m{i}", f"C{i}", "TX") for i in range(55)]
        ok = ({"n_priced": 100}, {})
        small = ({"n_priced": 59}, {})
        results = {m["slug"]: (small if m["slug"] == "m3" else ok) for m in metros if m["slug"] != "m52"}
        kept, _ = F.select_roster(metros, results, {"m52": "502"})
        self.assertEqual(len(kept), 50)  # m3 below the 60 gate, m51 takes its place, m52 never needed
        results.pop("m10")
        with self.assertRaises(F.FetchError):
            F.select_roster(metros, results, {"m10": "502", "m52": "502"})


PHONE_RE = re.compile(r"\(\d{3}\)\s?\d{3}-\d{4}|\b\d{3}[-.]\d{3}[-.]\d{4}\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


@unittest.skipUnless((OUT_DIR / "latest.json").is_file(), "no snapshot committed yet")
class TestCommittedSnapshot(unittest.TestCase):
    """The committed outputs are public on GitHub Pages: no PII, no raw blobs, red lines held."""

    def setUp(self):
        self.data = json.loads((OUT_DIR / "latest.json").read_text())

    def test_no_pii_or_raw_in_any_written_file(self):
        files = [OUT_DIR / "latest.json", *sorted((OUT_DIR / "history").glob("*.json")),
                 *sorted((OUT_DIR / "samples").glob("*.csv"))]
        self.assertGreater(len(files), 2)
        for f in files:
            text = f.read_text()
            with self.subTest(file=f.name):
                self.assertIsNone(PHONE_RE.search(text), "phone number found")
                self.assertIsNone(EMAIL_RE.search(text), "email found")
                for key in ('"raw"', '"agent"', '"phone"', '"email"', '"moveInSpecials"', '"description"'):
                    self.assertNotIn(key, text)

    def test_metro_gate_and_count(self):
        metros = self.data["metros"]
        self.assertLessEqual(len(metros), 50)
        self.assertGreaterEqual(len(metros), 40)
        self.assertEqual(len({m["slug"] for m in metros}), len(metros))
        for m in metros:
            self.assertGreaterEqual(m["n_priced"], 60, m["slug"])
            self.assertEqual(m["snapshot_date"], self.data["snapshot_date"])

    def test_bedroom_medians_respect_floor(self):
        for m in self.data["metros"]:
            for b, e in m["bedrooms"].items():
                if e["n"] < 20:
                    self.assertFalse(e["published"])
                    self.assertNotIn("headline_median", e)
                else:
                    self.assertLessEqual(e["net_effective_median"], e["headline_median"])

    def test_rent_cuts_locked_until_week_four(self):
        for m in self.data["metros"]:
            rc = m["rent_cuts_30d"]
            if rc["weeks_collected"] < 4:
                self.assertFalse(rc["unlocked"])
                self.assertIsNone(rc["count"])

    def test_csv_samples(self):
        for m in self.data["metros"]:
            path = OUT_DIR / "samples" / f"{m['slug']}.csv"
            rows = list(csv.DictReader(io.StringIO(path.read_text())))
            self.assertEqual(len(rows), 25, path.name)
            self.assertEqual(list(rows[0].keys()), R.CSV_FIELDS)

    def test_label_present(self):
        self.assertIn("Publicly advertised asking rents", self.data["method"]["label"])


if __name__ == "__main__":
    unittest.main()
