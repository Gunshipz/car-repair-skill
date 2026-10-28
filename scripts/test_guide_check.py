"""Offline tests for guide_check. Run: python -I test_guide_check.py"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carlib, guide_check


class GuideCheck(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.dir, "img"))
        open(os.path.join(self.dir, "img", "ok.jpg"), "wb").write(b"x")
        self.page = os.path.join(self.dir, "g.html")
        with open(self.page, "w", encoding="utf-8") as f:
            f.write('<a href="#tests">t</a><a href="#nowhere">n</a><h2 id="tests">T</h2>'
                    '<img src="img/ok.jpg"><img src="img/missing.jpg"><img src="data:image/png;base64,AA">'
                    '<p>Wheel nuts 90–110 N·m. Shift cable nut 11.8–14.7 N·m. Made up 77–88 N·m.</p>')
        self.db = carlib.open_db("t", self.dir)
        with self.db:
            carlib.store_page(self.db, "https://x/lug", "Lug Nut", "Tightening torque 90 - 110 N.m (9 - 11 kgf.m)", [])
            carlib.store_page(self.db, "https://x/cable", "Cable", "Shift cable nut 11.8 ~ 14.7 N.m", [])
            self.db.execute("INSERT INTO meta VALUES ('import_complete', '1')")

    def test_broken_anchor_and_missing_image(self):
        r = guide_check.check_local(self.page)
        self.assertEqual(r["bad_anchors"], ["nowhere"])
        self.assertEqual(r["missing_images"], ["img/missing.jpg"])

    def test_only_clickable_links_checked(self):  # a font preconnect is not a link anyone follows
        page = '<link rel="preconnect" href="https://fonts.googleapis.com"><a href="https://x.test/a">a</a><a href="#t">t</a>'
        self.assertEqual(guide_check.external_links(page), ["https://x.test/a"])

    def test_standalone_embeds_images(self):  # one file to email: no img/ folder beside it
        page = os.path.join(self.dir, "s.html")
        with open(page, "w", encoding="utf-8") as f:
            f.write('<title>T</title><img src="img/ok.jpg"><p>hi</p>')
        out = os.path.join(self.dir, "out.html")
        guide_check.standalone(page, out)
        html_out = open(out, encoding="utf-8").read()
        self.assertTrue(html_out.startswith("<!doctype html>"))
        self.assertIn('src="data:image/jpeg;base64,eA=="', html_out)  # b"x"
        self.assertNotIn('src="img/', html_out)

    def test_standalone_refuses_missing_image(self):
        page = os.path.join(self.dir, "m.html")
        with open(page, "w", encoding="utf-8") as f:
            f.write('<img src="img/missing.jpg">')
        with self.assertRaises(SystemExit):
            guide_check.standalone(page, os.path.join(self.dir, "o.html"))

    def test_torques_found_and_not_found(self):
        r = guide_check.check_torques(self.page, self.db)
        found = {t: urls for t, urls in r}
        self.assertEqual(found["90–110 N·m"], ["https://x/lug"])
        self.assertEqual(found["11.8–14.7 N·m"], ["https://x/cable"])  # the manual writes "~" for ranges too
        self.assertEqual(found["77–88 N·m"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
