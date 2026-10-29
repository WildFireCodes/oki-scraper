"""Testy jednostkowe (bez sieci): python -m unittest discover -s tests"""
import json
import os
import tempfile
import unittest
from unittest import mock

from scraper import __main__ as cli
from scraper.notify import Notifier, build_summary_message
from scraper.sources import Entry, SourceError, parse_listing
from scraper.state import load_state, source_key
from scraper.text import canonical_link, extract_details, fold, match_keywords
from scraper.fetch import looks_blocked


class TextTests(unittest.TestCase):
    def test_fold(self):
        self.assertEqual(fold("Łódź ŻÓŁĆ Kraków"), "lodz zolc krakow")

    def test_keywords_case_and_diacritics(self):
        kws = [{"word": "KONFERENCJA", "message": "x"}, {"word": "zolc", "message": ""}, {"word": " ", "message": ""}]
        hit = match_keywords(kws, "Nowa konferencja o żółci")
        self.assertEqual([k["word"] for k in hit], ["KONFERENCJA", "zolc"])

    def test_canonical_link(self):
        self.assertEqual(
            canonical_link("http://OILKrakow.pl/kursy/abc/#form"), "https://oilkrakow.pl/kursy/abc"
        )

    def test_extract_details(self):
        text = ("Zapraszamy Termin : 12 – 13.12.2026 godz. 08.00 – 19.00 Miejsce: Balice, Cholerzyn 445 "
                "Koszt: 2400 zł. Dla członków OIL: 720 zł. Punkty edukacyjne: 18 O szkoleniu Data urodzenia: x")
        d = extract_details(text)
        self.assertEqual(d["termin"], "12 – 13.12.2026 godz. 08.00 – 19.00")
        self.assertEqual(d["miejsce"], "Balice, Cholerzyn 445")
        self.assertEqual(d["koszt"], "2400 zł. Dla członków OIL: 720 zł.")

    def test_block_detection(self):
        self.assertTrue(looks_blocked(403, ""))
        self.assertTrue(looks_blocked(200, "<title>Just a moment...</title>"))
        self.assertFalse(looks_blocked(200, "<html>" + "x" * 70000 + "challenge-platform</html>"))
        self.assertFalse(looks_blocked(200, "<html>google recaptcha widget</html>"))

    def test_listing_generic_fallback(self):
        html = ("<html><body><nav><a href='/a'>Nawigacja długi tekst</a></nav><main>"
                "<a href='/kursy-i-szkolenia/jakis-kurs/'>Jakiś długi kurs dla lekarzy</a>"
                "<a href='/x'>krótki</a></main><footer><a href='/f'>Stopka długi tekst tutaj</a></footer></body></html>")
        es = parse_listing(html, "https://oilkrakow.pl/kursy-i-szkolenia/")
        self.assertEqual([e.title for e in es], ["Jakiś długi kurs dla lekarzy"])


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


class Sink(Notifier):
    def __init__(self):
        super().__init__(None, None, dry_run=True)
        self.sent = []

    def send(self, text):
        self.sent.append(text)


def entries(n, prefix="k"):
    return [Entry(id=f"https://x.pl/{prefix}{i}", title=f"Wpis {prefix}{i}", link=f"https://x.pl/{prefix}{i}/",
                  text="konferencja" if i == 0 else "") for i in range(n)]


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cfgp = os.path.join(self.dir, "c.json")
        self.sp = os.path.join(self.dir, "s.json")
        write_json(self.cfgp, {"sources": [{"name": "A", "url": "https://x.pl/a/"}, {"name": "B", "url": "https://x.pl/b/"}],
                   "keywords": [{"word": "konferencja", "message": "Jest nowa konferencja!"}],
                   "notifyAllNew": True, "defaultMessage": ""})
        self.sink = Sink()
        self.data = {}

    def run_cli(self):
        def fake(src, fetcher, force=None):
            d = self.data[src["name"]]
            if d is None:
                raise SourceError("boom")
            return d, "api"
        with mock.patch.object(cli, "fetch_source", fake), \
             mock.patch.object(cli, "notifier_from_env", lambda dry: self.sink), \
             mock.patch.object(cli, "Fetcher"):
            return cli.main(["--config", self.cfgp, "--state", self.sp])

    def test_seed_new_cap_and_dedupe(self):
        shared = Entry("https://x.pl/shared", "Wspólny", "https://x.pl/shared/")
        self.data = {"A": entries(3) + [shared], "B": entries(2, "b")}
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(len(self.sink.sent), 2)  # dwie wiadomości startowe
        self.assertTrue(all("Zaczynam obserwować" in m for m in self.sink.sent))
        self.sink.sent.clear()
        self.data = {"A": entries(20, "n") + [shared], "B": entries(2, "b") + [shared]}
        self.run_cli()
        a = [m for m in self.sink.sent if "📂 A" in m]
        self.assertEqual(len(a), 15)
        self.assertTrue(any("…i jeszcze 5 nowych wpisów" in m for m in self.sink.sent))
        self.assertFalse(any("Wspólny" in m for m in self.sink.sent))  # już widziany w innym źródle
        self.assertTrue(any("Jest nowa konferencja!" in m and "🔑 Słowo kluczowe: konferencja" in m for m in a))
        self.assertTrue(any("<b>Jest nowy wpis</b>" in m for m in a))  # pusty defaultMessage -> domyślny
        self.assertEqual(len(load_state(self.sp)["recent"]), 15)

    def test_failures_warning_and_recovery(self):
        self.data = {"A": entries(2), "B": entries(2, "b")}
        self.run_cli()
        self.sink.sent.clear()
        self.data = {"A": None, "B": entries(2, "b")}
        for _ in range(3):
            self.run_cli()
        warns = [m for m in self.sink.sent if "Problem z obserwowaniem" in m]
        self.assertEqual(len(warns), 1)
        key = source_key("https://x.pl/a/")
        st = load_state(self.sp)["sources"][key]
        self.assertEqual(st["failures"], 3)
        self.assertEqual(len(st["seen"]), 2)  # seen nietknięte
        self.data = {"A": entries(2), "B": entries(2, "b")}
        self.run_cli()
        self.assertTrue(any("znów działa" in m for m in self.sink.sent))

    def test_summary_plural(self):
        self.assertIn("1 nowy wpis", build_summary_message("A", 1, "u"))
        self.assertIn("3 nowe wpisy", build_summary_message("A", 3, "u"))
        self.assertIn("12 nowych wpisów", build_summary_message("A", 12, "u"))

    def test_notify_all_off(self):
        write_json(self.cfgp, {"sources": [{"name": "A", "url": "https://x.pl/a/"}], "keywords": [{"word": "konferencja"}],
                   "notifyAllNew": False})
        self.data = {"A": entries(1)}
        self.run_cli()
        self.sink.sent.clear()
        self.data = {"A": entries(3, "n")}
        self.run_cli()
        self.assertEqual(len(self.sink.sent), 1)  # tylko n0 (zawiera "konferencja")

    def test_missing_secrets(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(cli.main(["--config", self.cfgp, "--state", self.sp]), 2)


if __name__ == "__main__":
    unittest.main()
