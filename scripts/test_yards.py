"""Offline tests for the yard watch. Run: python -I test_yards.py"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yards

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "yards")


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def car(stock, source="a", year=2008, model="Accent"):
    return {"source": source, "location": source.upper(), "year": year, "make": "Hyundai", "model": model,
            "row": "1", "arrived": "2026-10-01", "stock": stock, "vin": "", "url": ""}


class Parsers(unittest.TestCase):
    def test_parsers_on_fixtures(self):
        got = {
            "picknpull": yards.parse_picknpull(fixture("picknpull_slc.json"), "picknpull_slc"),
            "tearapart_slc": yards.parse_tearapart(fixture("tearapart_slc.json"), "tearapart_slc"),
            "tearapart_ogden": yards.parse_tearapart(fixture("tearapart_ogden.json"), "tearapart_ogden"),
            "utpap_ogden": yards.parse_utpap(fixture("utpap_ogden.html"), "utpap_ogden"),
            "utpap_orem": yards.parse_utpap(fixture("utpap_orem.html"), "utpap_orem"),
        }
        for name, cars in got.items():
            self.assertGreaterEqual(len(cars), 1, name)
            for c in cars:
                self.assertTrue(c["year"] and c["model"] and c["row"] and c["stock"], (name, c))
        self.assertIn("A039272", [c["stock"] for c in got["utpap_ogden"]])  # 2011 Accent, row 228

    def test_challenge_page_is_error(self):
        page = '<meta http-equiv="refresh" content="0;/.well-known/sgcaptcha/?r=%2Finventory-search%2F&y=ipc:1.2.3.4:179">'
        with self.assertRaises(yards.SourceError) as cm:
            yards.check_body(page)
        self.assertEqual(cm.exception.cls, "challenge")

    def test_normal_page_with_recaptcha_script_is_not_challenge(self):  # contact forms load recaptcha on real pages
        page = '<head><script src="https://www.google.com/recaptcha/api.js"></script></head><table id="cars-table">'
        self.assertEqual(yards.check_body(page), page)


class Watch(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.wl, self.st = os.path.join(d, "w.json"), os.path.join(d, "s.json")
        with open(self.wl, "w") as f:
            json.dump([{"name": "Accent donor", "make": "Hyundai", "models": ["Accent"], "y1": 2006, "y2": 2011,
                        "sources": ["a", "b"]}], f)
        self.inv = {"a": [car("A1"), car("A2"), car("A3")], "b": []}
        self.fail = {}
        self.real = yards.SOURCES
        yards.SOURCES = {k: self.src(k) for k in ("a", "b")}
        self.sent = []

    def tearDown(self):
        yards.SOURCES = self.real

    def src(self, k):
        def fn(make, models, y1, y2):
            if k in self.fail:
                raise self.fail[k]
            if make == yards.CONTROL[0]:
                return [car("civic", k, 2005, "Civic")]
            return list(self.inv[k])
        return fn

    def send(self, text):
        self.sent.append(text)
        return len(self.sent)

    def run_watch(self, send=None):
        self.sent.clear()
        return yards.watch(self.wl, self.st, send or self.send)[0]

    def test_first_run_sends_summary(self):
        self.assertEqual(self.run_watch(), 1)
        self.assertIn("Accent donor", self.sent[0])
        self.assertIn("3 cars", self.sent[0])

    def test_new_car_alerts_once(self):
        self.run_watch()
        self.inv["a"].append(car("A4", year=2010))
        self.run_watch()
        self.assertEqual(len(self.sent), 1)
        self.assertIn("A4", self.sent[0])
        self.assertEqual(self.run_watch(), 0)

    def test_send_failure_keeps_unseen(self):
        self.run_watch()
        self.inv["a"].append(car("A4"))

        def broken(text):
            raise OSError("telegram down")
        self.run_watch(broken)
        self.run_watch()
        self.assertTrue(any("A4" in m for m in self.sent))

    def test_source_systemexit_caught(self):
        self.run_watch()
        self.inv["a"].append(car("A4"))
        self.fail["b"] = SystemExit("fetch failed: https://b\n  HTTP Error 503: x")
        self.run_watch()
        self.assertEqual(sum("broken" in m for m in self.sent), 1)
        self.assertTrue(any("A4" in m for m in self.sent))  # the healthy source still reports
        self.assertFalse(any("no new" in m.lower() for m in self.sent))

    def test_recovery_no_flood(self):
        self.run_watch()
        self.fail["a"] = SystemExit("fetch failed: https://a\n  HTTP Error 500: x")
        self.run_watch()
        del self.fail["a"]
        self.run_watch()
        self.assertEqual(len(self.sent), 1)
        self.assertIn("recovered", self.sent[0])

    def test_error_class_dedup(self):
        self.run_watch()
        self.fail["b"] = yards.SourceError("challenge", "y=ipc:1.2.3.4:111")
        self.run_watch()
        self.fail["b"] = yards.SourceError("challenge", "y=ipc:1.2.3.4:222")
        self.run_watch()
        self.assertEqual(self.sent, [])

    def test_control_zero_is_broken_not_empty(self):
        self.real_b = yards.SOURCES["b"]
        yards.SOURCES["b"] = lambda make, models, y1, y2: []
        self.run_watch()
        self.assertTrue(any("b" in m and "control 0" in m for m in self.sent))

    def test_broken_at_first_run_no_flood_on_recovery(self):  # review I-1
        self.inv["b"] = [car("B1", "b"), car("B2", "b")]
        self.fail["b"] = yards.SourceError("challenge")
        self.run_watch()
        del self.fail["b"]
        self.run_watch()
        self.assertFalse(any(" new." in m for m in self.sent), self.sent)
        self.assertTrue(any("recovered" in m for m in self.sent))
        self.assertTrue(any("2 cars there now" in m for m in self.sent), self.sent)
        self.inv["b"].append(car("B3", "b"))
        self.run_watch()
        self.assertEqual(len(self.sent), 1)
        self.assertIn("B3", self.sent[0])

    def test_old_state_format_no_flood(self):  # state written before per-yard tracking
        self.run_watch()
        with open(self.st) as f:
            st = json.load(f)
        st["initialized"] = ["Accent donor"]
        with open(self.st, "w") as f:
            json.dump(st, f)
        self.assertEqual(self.run_watch(), 0)

    def test_dry_run_leaves_state_untouched(self):  # review I-2
        self.run_watch()
        with open(self.st, "rb") as f:
            before = f.read()
        self.inv["a"].append(car("A9"))
        yards.watch(self.wl, self.st, self.send, save_state=False)
        with open(self.st, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertTrue(any("A9" in m for m in self.sent))  # still shown

    def test_send_failure_counted(self):  # a revoked token must not look like "no new cars"
        def broken(text):
            raise OSError("telegram down")
        sent, failed = yards.watch(self.wl, self.st, broken)
        self.assertEqual((sent, failed), (0, 1))

    def test_long_message_truncated(self):
        self.inv["a"] = [car(f"S{i}") for i in range(300)]
        self.run_watch()
        self.assertEqual(len(self.sent), 1)
        self.assertLessEqual(len(self.sent[0]), 4096)
        self.assertIn("more", self.sent[0])
        with open(self.st) as f:
            self.assertEqual(len(json.load(f)["seen"]["Accent donor"]), 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)
