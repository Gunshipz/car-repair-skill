"""Offline tests for the manual library. Run: python -I test_carlib.py"""
import os, sqlite3, subprocess, sys, tempfile, unittest, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carlib

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://lemon-manuals.la/Test/2010/Car%20L4/"
TOP = "2010 Test Car L4/"
CRUMBS = ('<a class="breadcrumb-part" href="../404.html">Home</a><a class="breadcrumb-part" href="../404.html">Test</a>'
          '<a class="breadcrumb-part" href="../404.html">2010</a><a class="breadcrumb-part" href="../pages/1.html">Car L4</a>')


def page(main, crumbs="", tree=False):
    cls = "<li class='li-folder'><a name='x/'>x</a>" if tree else ""
    return f'<html><body><div class="header">{CRUMBS}{crumbs}</div><div class="main">{cls}{main}</div></body></html>'


def crumb(n, text):
    return f'<a class="breadcrumb-part" href="../pages/{n}.html">{text}</a>'


def build_zip(path, corrupt=False):
    rd = crumb(2, "Repair and Diagnosis")
    files = {
        "pages/1.html": page("<a href='../pages/2.html'>Repair and Diagnosis</a>"),
        "pages/2.html": page("<a href='../pages/10.html' name='Lamps%2FSwitches/Fog%2FDriving%20Lamp%20Switch/'>Fog</a>"
                             "<a href='../pages/11.html' name='Wheels/Wheel%20Nut/'>Nut</a>"
                             "<a href='../pages/14.html' name='Wheels/Wheel%20Nut%20Copy/'>Copy</a>", rd, tree=True),
        "pages/10.html": page("<h1>Fog/Driving Lamp Switch</h1>Check connector IP-3 pin 4. <img src='../images/a/1.jpeg'>"
                              "<a href='../pages/12.html' name='Labor%20Times/'>Labor Times</a>",
                              rd + crumb(2, "Lamps/Switches") + crumb(10, "Fog/Driving Lamp Switch")),
        "pages/11.html": page("Wheel Nut Tightening. Tightening torque 90 - 110 N.m (9 - 11 kgf.m, 65 - 79 lb-ft)",
                              rd + crumb(11, "Wheel Nut")),
        "pages/12.html": page("<table><tr><td>Replace</td><td>0.5</td></tr></table>CORRUPTME",
                              rd + crumb(10, "Fog/Driving Lamp Switch") + crumb(12, "Labor Times")),
        "pages/13.html": page("orphan page P0705"),
        "pages/14.html": page("Wheel Nut Tightening. Tightening torque 90 - 110 N.m (9 - 11 kgf.m, 65 - 79 lb-ft)",
                              rd + crumb(14, "Wheel Nut Copy")),
        "images/a/1.jpeg": "JPEGDATA",
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for name, body in files.items():
            z.writestr(TOP + name, body)
    if corrupt:  # flip one byte inside a stored member: reading it fails its CRC check
        with open(path, "rb") as f:
            raw = f.read()
        with open(path, "wb") as f:
            f.write(raw.replace(b"CORRUPTME", b"CORRUPTMF"))


class Search(unittest.TestCase):
    def setUp(self):
        self.db = carlib.open_db("t", tempfile.mkdtemp())

    def add(self, url, text, path="p"):
        with self.db:
            carlib.store_page(self.db, url, path, text, [])
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('import_complete', '1')")

    def urls(self, q):
        return [r["url"] for r in carlib.search(self.db, q)]

    def test_exact_code_not_confused(self):
        self.add("a", "set code P0A80 when voltage low")
        self.add("b", "set code P0A8F when voltage high")
        self.assertEqual(self.urls("P0A80"), ["a"])

    def test_query_punctuation_no_crash(self):
        self.add("a", "connector IP-3 reads 21.6 V, code P0A80")
        for q in ("IP-3", "21.6", 'say "hi', "p0a80"):
            carlib.search(self.db, q)
        self.assertEqual(self.urls("p0a80"), ["a"])

    def test_query_without_letters_rejected(self):  # 0 hits must mean "not in the manual", never "bad query"
        self.add("a", "anything")
        for q in ("-", "*", '"'):
            with self.assertRaises(ValueError):
                carlib.search(self.db, q)

    def test_torque_units_found(self):
        self.add("a", "Wheel Nut Tightening torque 90 - 110 N.m (9 - 11 kgf.m, 65 - 79 lb-ft)")
        self.add("b", "unrelated page")
        for q in ("N.m", "lb-ft", "wheel nut"):
            self.assertEqual(self.urls(q), ["a"], q)

    def test_torque_angle_recall(self):
        self.add("a", "use the TORQUE-ANGLE method")
        self.assertEqual(self.urls("torque angle"), ["a"])

    def test_rank_by_count(self):
        self.add("one", "P0705 range sensor circuit check alpha beta gamma delta")
        self.add("five", "P0705 P0705 P0705 P0705 P0705 range sensor circuit")
        self.assertEqual(self.urls("P0705")[0], "five")

    def test_phrase_before_terms(self):
        self.add("apart", "the cable runs to the shift lever")
        self.add("phrase", "inspect the shift cable bushing")
        self.assertEqual(self.urls("shift cable"), ["phrase", "apart"])

    def test_duplicate_body_skipped(self):
        with self.db:
            self.assertTrue(carlib.store_page(self.db, "a", "p", "same body", []))
            self.assertFalse(carlib.store_page(self.db, "b", "p", "same body", []))
        self.assertEqual(self.db.execute("SELECT count(*) FROM pages").fetchone()[0], 1)

    def test_same_text_different_figures_both_kept(self):  # Accent: 131 wiring pages share a caption, not a diagram
        with self.db:
            self.assertTrue(carlib.store_page(self.db, "a", "p", "Circuit Diagram [FIGURE 1]", ["zip:x/1.jpeg"]))
            self.assertTrue(carlib.store_page(self.db, "b", "p", "Circuit Diagram [FIGURE 1]", ["zip:x/2.jpeg"]))
        self.assertEqual(self.db.execute("SELECT count(*) FROM pages").fetchone()[0], 2)

    def test_incomplete_library_refuses(self):
        with self.db:
            carlib.store_page(self.db, "a", "p", "P0705", [])
        with self.assertRaises(carlib.IncompleteLibrary):
            carlib.search(self.db, "P0705")


class ImportZip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.zip = os.path.join(self.tmp, "car.zip")

    def test_import_zip_fixture(self):
        build_zip(self.zip)
        db = carlib.open_db("t", self.tmp)
        self.assertEqual(carlib.import_zip(db, self.zip, BASE), (5, 1, 1))  # stored, duplicate, tree
        rows = {r[0]: (r[1], r[2]) for r in db.execute("SELECT url, path, figures FROM pages")}
        fog = BASE + "Repair%20and%20Diagnosis/Lamps%2FSwitches/Fog%2FDriving%20Lamp%20Switch/"
        self.assertIn(fog, rows)
        self.assertEqual(rows[fog][0], "Repair and Diagnosis > Lamps/Switches > Fog/Driving Lamp Switch")
        self.assertIn(fog + "Labor%20Times/", rows)  # child of a leaf page
        self.assertIn("zip:" + TOP + "pages/13.html", rows)  # never linked by name: falls back
        self.assertEqual(db.execute("SELECT value FROM meta WHERE key='fallback_urls'").fetchone()[0], "1")
        hit = carlib.search(db, "IP-3")[0]
        self.assertEqual(hit["url"], fog)
        self.assertEqual(hit["figures"], ["zip:" + TOP + "images/a/1.jpeg"])
        out = carlib.figure(db, hit["figures"][0], self.tmp)
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"JPEGDATA")

    def test_wrong_model_name_refused(self):  # "Accent" for "Car L4" would make every citation URL 404
        build_zip(self.zip)
        db = carlib.open_db("t", self.tmp)
        with self.assertRaises(SystemExit) as cm:
            carlib.import_zip(db, self.zip, BASE, expect="2010 Test Car")
        self.assertIn("Car L4", str(cm.exception))
        self.assertEqual(carlib.import_zip(db, self.zip, BASE, expect="2010 Test Car L4")[0], 5)

    def test_failed_import_refuses_search(self):
        build_zip(self.zip, corrupt=True)
        db = carlib.open_db("t", self.tmp)
        with self.assertRaises(zipfile.BadZipFile):
            carlib.import_zip(db, self.zip, BASE)
        with self.assertRaises(carlib.IncompleteLibrary):
            carlib.search(db, "Wheel")


class Misc(unittest.TestCase):
    def test_vehicle_key(self):
        self.assertEqual(carlib.vehicle_key("Hyundai", "2010", "Accent L4-1.6L"), "hyundai-2010-accent-l4-1.6l")

    def test_library_root_default_silent(self):
        old = os.environ.get("CARKIT_CONFIG")
        os.environ["CARKIT_CONFIG"] = os.path.join(tempfile.mkdtemp(), "missing.json")
        try:
            self.assertEqual(carlib.library_root(), os.path.expanduser("~/carkit-library"))
        finally:
            if old is None:
                os.environ.pop("CARKIT_CONFIG")
            else:
                os.environ["CARKIT_CONFIG"] = old

    def test_cli_lib_isolated(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "carkit.py"), "lib", "--help"],
                           capture_output=True, text=True, creationflags=0x08000000 if os.name == "nt" else 0)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
