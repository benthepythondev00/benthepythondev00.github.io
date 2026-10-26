import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_germany_jobs as b  # noqa: E402


class WhoCanApply(unittest.TestCase):
    def status(self, text):
        return b.who_can_apply(text)["status"]

    def test_abroad_from_employer_sentence(self):
        for text in [
            "Alternativ: Ausbildung aus dem Ausland mit in Deutschland anerkanntem Gleichwertigkeitsbescheid",
            "Wir unterstützen Sie beim Anerkennungsverfahren.",
            "Bewerbungen aus dem Ausland sind willkommen.",
            "Wir helfen bei Visum und Wohnung.",
            "Wir unterstützen dich bei der Arbeitserlaubnis.",
            "Teilnahme am Anpassungslehrgang möglich.",
        ]:
            self.assertEqual(self.status(text), "abroad", text)

    def test_boilerplate_is_not_an_invitation(self):
        for text in [
            "Heute beschäftigen wir weltweit mehr als 9.300 Mitarbeiter.",
            "Wir sind ein internationaler Personaldienstleister.",
            "Digitales Arbeiten ist Standard, sogar aus dem europäischen Ausland.",
            "Workation ist bis zu 30 Tage aus dem EU-Ausland möglich.",
            "Wir freuen uns über alle Bewerbungen unabhängig von Herkunft und Nationalität.",
            "Respekt und Anerkennung für Ihre Leistungen.",
            "Bereitschaft zu Auslandsreisen.",
            "Verkehrsmodellierung mit PTV-Visum und PTV Visum.",
        ]:
            self.assertEqual(self.status(text), "unknown", text)

    def test_permit_and_eu(self):
        self.assertEqual(self.status("Eine gültige Arbeitserlaubnis ist erforderlich."), "permit")
        self.assertEqual(self.status("Voraussetzung: EU-Staatsangehörigkeit."), "eu")
        self.assertEqual(self.status("Visumanforderungen: Gültiges Visum für Deutschland"), "permit")

    def test_restrictive_wins_and_sentence_is_quoted(self):
        r = b.who_can_apply("Bewerbungen aus dem Ausland willkommen.\nEine gültige Arbeitserlaubnis ist erforderlich.")
        self.assertEqual(r["status"], "permit")
        self.assertEqual(r["sentence"], "Eine gültige Arbeitserlaubnis ist erforderlich.")

    def test_markdown_table_cells_are_sentences(self):
        r = b.who_can_apply("Standort: **Berlin** | Benefits: **Visum und Flug** | Team: **IT**")
        self.assertEqual(r["sentence"], "Benefits: Visum und Flug")

    def test_entities_are_decoded(self):
        self.assertEqual(b.who_can_apply("Wir&nbsp;helfen beim Visum.")["sentence"], "Wir helfen beim Visum.")

    def test_long_sentence_is_shortened(self):
        r = b.who_can_apply("Bewerbungen aus dem Ausland " + "sehr " * 80 + "willkommen.")
        self.assertLessEqual(len(r["sentence"]), 220)


class GermanLevel(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(b.german_level("Deutschkenntnisse auf B2-Niveau")["level"], "B2")
        self.assertEqual(b.german_level("Sprachkenntnisse der deutschen Sprache (Sprachniveau C 1)")["level"], "C1")
        self.assertEqual(b.german_level("Sehr gute Deutschkenntnisse in Wort und Schrift")["level"], "Fluent")
        self.assertEqual(b.german_level("Gute Deutschkenntnisse")["level"], "Good")
        self.assertEqual(b.german_level("Arbeiten in ganz Deutschland")["level"], None)


class Salary(unittest.TestCase):
    def test_yearly_monthly_hourly(self):
        self.assertEqual(b.annual_salary({"verguetungsangabe": "JAHRESGEHALT", "gehaltsspanneVon": 48000.0, "gehaltsspanneBis": 56000.0}), (48000, 56000))
        self.assertEqual(b.annual_salary({"verguetungsangabe": "MONATSGEHALT", "gehaltsspanneVon": 4000.0}), (48000, 48000))
        self.assertEqual(b.annual_salary({"verguetungsangabe": "STUNDENLOHN", "gehaltsspanneVon": 20.0, "gehaltsspanneBis": 25.0}), (41600, 52000))
        self.assertEqual(b.annual_salary({"verguetungsangabe": "KEINE_ANGABEN"}), (None, None))


class Rendering(unittest.TestCase):
    job = {
        "ref": "1-2-3", "url": b.SITE + "1-2-3", "title_de": "Pflegefachkraft <Intensiv>", "title_en": "Nurse <ICU>",
        "occupation_de": None, "occupation_en": None, "field": "Nursing", "employer": "Klinik & Co", "city": "Köln",
        "region": None, "published": "2026-10-26", "full_time": True, "permanent": True, "home_office": False,
        "salary_min": 41600, "salary_max": 52000, "salary_hourly": True, "who": "abroad",
        "who_de": "Bewerbungen aus dem Ausland willkommen.", "who_en": "Applications from abroad welcome.",
        "german": "B2", "german_de": None, "part_time": False,
    }

    def test_summary(self):
        self.assertEqual(b.summary(self.job), "Full-time, permanent. €41,600 to €52,000 a year (from the hourly rate, 40 h a week). German B2.")

    def test_part_time_hourly_stays_hourly(self):
        self.assertIn("€20.00 to €25.00 an hour", b.summary({**self.job, "full_time": False}))

    def test_blue_card(self):
        full = {**self.job, "salary_hourly": False}
        self.assertEqual(b.blue_card({**full, "salary_min": 50700}), "yes")
        self.assertEqual(b.blue_card({**full, "salary_min": 46000, "field": "IT"}), "shortage")
        self.assertEqual(b.blue_card({**full, "salary_min": 46000, "field": "Skilled trades"}), "below")
        self.assertEqual(b.blue_card({**full, "salary_min": None}), None)
        self.assertEqual(b.blue_card({**self.job, "full_time": False}), None)  # part-time hourly: no yearly figure

    def test_opportunity_card(self):
        self.assertTrue(b.opportunity_card({**self.job, "part_time": True}))
        self.assertFalse(b.opportunity_card({**self.job, "part_time": True, "who": "eu"}))
        self.assertFalse(b.opportunity_card(self.job))

    def test_card_escapes_and_links_original(self):
        html = b.card(self.job)
        self.assertIn("Nurse &lt;ICU&gt;", html)
        self.assertIn("Klinik &amp; Co", html)
        self.assertIn('data-who="abroad"', html)
        self.assertIn('href="https://www.arbeitsagentur.de/jobsuche/jobdetail/1-2-3" target="_blank"', html)
        self.assertNotIn("<Intensiv>", html)

    def test_render_fills_every_placeholder(self):
        out = b.render([self.job], "2026-10-27")
        self.assertNotRegex(out, r"__[A-Z_]+__")
        self.assertNotIn("<!--JOBS-->", out)
        self.assertIn('<option value="Nursing">Nursing</option>', out)

    def test_field_and_gender_suffix(self):
        self.assertEqual(b.field_of("Gesundheits- und Krankenpfleger/in"), "Nursing")
        self.assertEqual(b.field_of("Elektroniker/in - Energie- und Gebäudetechnik"), "Skilled trades")
        self.assertEqual(b.field_of("Bürokaufmann"), "Other")
        self.assertEqual(b.strip_gender("Pflegefachkraft (m/w/d)"), "Pflegefachkraft")


if __name__ == "__main__":
    unittest.main()
