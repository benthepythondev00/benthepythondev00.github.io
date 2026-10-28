import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_denmark_jobs as b  # noqa: E402

SIRI_ROWS = """<table><tbody>
<tr><td><h4>Name of company</h4></td><td><h4>CVR no.</h4></td></tr>
<tr><td><p class="bodycopy-small">&amp;TRADITION A/S</p></td><td><p>18169304</p></td></tr>
<tr><td><p>3Shape A/S&nbsp;</p></td><td><p>25553489&nbsp;</p></td></tr>
<tr><td><p class="black">Aalborg Universitet&nbsp;</p></td><td><p><span>29102384&nbsp;</span>&nbsp;</p></td></tr>
<tr><td><p>3Shape A/S</p></td><td><p>25553489</p></td></tr>
<tr><td><p>No CVR here</p></td><td><p>n/a</p></td></tr>
</tbody></table>"""


class ParseSiri(unittest.TestCase):
    def test_rows_are_cleaned_and_deduplicated(self):
        self.assertEqual(b.parse_siri(SIRI_ROWS), [
            {"name": "&TRADITION A/S", "cvr": "18169304"},
            {"name": "3Shape A/S", "cvr": "25553489"},
            {"name": "Aalborg Universitet", "cvr": "29102384"},
        ])


class Slugs(unittest.TestCase):
    def test_legal_forms_and_danish_letters(self):
        self.assertEqual(b.slugs("Pleo Technologies A/S"), ["pleotechnologies", "pleo-technologies", "pleo"])
        self.assertEqual(b.slugs("3Shape A/S"), ["3shape"])
        self.assertEqual(b.slugs("Ørsted Wind Power A/S")[0], "orstedwindpower")
        self.assertEqual(b.slugs("Lunar Bank A/S, filial af Lunar AB"), ["lunarbank", "lunar-bank", "lunar"])
        self.assertEqual(b.slugs("A/S"), [])


class English(unittest.TestCase):
    def test_language(self):
        self.assertTrue(b.is_english("We are looking for a Senior Engineer to join our team in Copenhagen and you will work with the product."))
        self.assertFalse(b.is_english("Vi søger en erfaren ingeniør til vores team i Aarhus, og du skal arbejde med produktet hos os."))
        self.assertFalse(b.is_english("Engineer"))  # too little text to tell

    def test_english_ad_with_danish_place_names(self):
        self.assertTrue(b.is_english("Join us in Søborg. You will be part of the team and work with the best people at our site."))


class Denmark(unittest.TestCase):
    def test_places(self):
        for p in ["Copenhagen", "København S", "Aarhus, Denmark", "Søborg", "Remote - Denmark", "Kgs. Lyngby", "Billund, DK"]:
            self.assertTrue(b.in_denmark(p), p)
        for p in ["London", "Stockholm, Sweden", "Remote", None, ""]:
            self.assertFalse(b.in_denmark(p), p)


    def test_danish_part_of_a_multi_city_place(self):
        self.assertEqual(b.dk_place("Amsterdam, Netherlands; København, Capital Region, Denmark; Paris"), "København, Capital Region, Denmark")
        self.assertEqual(b.dk_place("Copenhagen"), "Copenhagen")
        self.assertEqual(b.dk_place(None), "")


class Fresh(unittest.TestCase):
    def test_old_postings_are_dropped(self):
        today = b.date(2026, 10, 28)
        jobs = [{"published": "2026-10-01"}, {"published": "2022-05-09"}, {"published": None}]
        self.assertEqual(b.fresh(jobs, today), [jobs[0], jobs[2]])
        self.assertEqual(b.fresh(None, today), [])


class Pay(unittest.TestCase):
    def test_annualised_dkk_only(self):
        self.assertEqual(b.annual_dkk(50000, 60000, "DKK", "1 MONTH"), (600000, 720000))
        self.assertEqual(b.annual_dkk(600000, None, "dkk", "per-year-salary"), (600000, 600000))
        self.assertEqual(b.annual_dkk(90000, 100000, "EUR", "1 YEAR"), (None, None))
        self.assertEqual(b.annual_dkk(50000, 60000, "DKK", None), (None, None))

    def test_check_against_the_limit(self):
        self.assertEqual(b.pay_check(552000, 600000), "clears")
        self.assertEqual(b.pay_check(500000, 560000), "maybe")
        self.assertEqual(b.pay_check(400000, 450000), "below")
        self.assertIsNone(b.pay_check(None, None))


class SmartRecruiters(unittest.TestCase):
    def test_language_comes_from_the_posting_field(self):
        class Resp:
            status_code = 200
            def json(self):
                return {"totalFound": 2, "content": [
                    {"id": "1", "name": "Software Engineer", "language": {"code": "en"}, "location": {"city": "Aarhus"}, "releasedDate": "2026-10-20T10:00:00Z"},
                    {"id": "2", "name": "Sælger", "language": {"code": "da"}, "location": {"city": "Slagelse"}}]}
        class Client:
            def get(self, *a, **k):
                return Resp()
        jobs = b.smartrecruiters(Client(), "jysk")
        self.assertEqual([j["english"] for j in jobs], [True, False])
        self.assertEqual(jobs[0]["url"], "https://jobs.smartrecruiters.com/jysk/1")


class Render(unittest.TestCase):
    def test_card_escapes_and_links_original(self):
        j = {"title": "Engineer <Data>", "url": "https://boards.greenhouse.io/x/jobs/1", "place": "Copenhagen", "published": "2026-10-20",
             "salary_min": 600000, "salary_max": 720000, "employer": "Foo & Bar A/S", "cvr": "12345678", "board": "greenhouse", "pay": "clears"}
        html = b.card(j)
        self.assertIn("Engineer &lt;Data&gt;", html)
        self.assertIn('data-employer="foo &amp; bar a/s"', html)
        self.assertIn("DKK 600,000 to DKK 720,000 a year", html)
        self.assertIn("Salary clears the DKK 552,000 pay limit", html)
        self.assertIn('href="https://boards.greenhouse.io/x/jobs/1"', html)

    def test_page_has_no_placeholders_left(self):
        j = {"title": "Engineer", "url": "https://x", "place": "", "published": None, "salary_min": None, "salary_max": None,
             "employer": "Foo A/S", "cvr": "12345678", "board": "lever", "pay": None}
        page = b.render([j], 982, 120, "2026-10-28")
        self.assertNotIn("__", page.replace("__init__", ""))
        self.assertIn("Salary not posted", page)
        self.assertIn("120</b> of 982", page)


if __name__ == "__main__":
    unittest.main()
