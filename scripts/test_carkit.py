"""Offline tests for carkit's parsing (no network). Run: python -I test_carkit.py"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carkit as ck


class Parsing(unittest.TestCase):
    def test_model_folders_absolute_double_quoted(self):  # charm.li year page, 2026-10
        page = '<a href="/Hyundai/2010/">2010</a><li><a href="/Hyundai/2010/Accent%20L4-1.6L/">Accent L4-1.6L</a><li><a href="/Hyundai/2010/Sonata%20V6-3.3L/">V6</a>'
        self.assertEqual(ck.model_folders(page, "Hyundai", "2010"), ["Accent L4-1.6L", "Sonata V6-3.3L"])

    def test_model_folders_relative_single_quoted(self):
        page = "<a href='Rio%20L4-1.6L/'>Rio</a><a href='/style.css'>"
        self.assertEqual(ck.model_folders(page, "Kia", "2008"), ["Rio L4-1.6L"])

    def test_tree_keeps_encoded_slash(self):
        page = "<li><a href='Transmission%20and%20Drivetrain/Manual%20Transmission%2FTransaxle/Shifter%20M%2FT/' name='x'>"
        self.assertEqual(ck.tree_hrefs(page), ["Transmission and Drivetrain/Manual Transmission%2FTransaxle/Shifter M%2FT/"])

    def test_page_url_round_trip(self):
        path = "Repair and Diagnosis/Transmission and Drivetrain/Manual Transmission%2FTransaxle/Shifter M%2FT/"
        self.assertEqual(
            ck.page_url("charm", "Hyundai", "2010", "Accent L4-1.6L", path),
            "https://charm.li/Hyundai/2010/Accent%20L4-1.6L/Repair%20and%20Diagnosis/Transmission%20and%20Drivetrain/Manual%20Transmission%2FTransaxle/Shifter%20M%2FT/",
        )

    def test_page_text_and_figures(self):
        p = ck.PageText()
        p.feed("<div class='header'>skip</div><div class='main'><h1>Title</h1><table><tr><td>Bolt</td><td>20-27</td></tr></table>"
               "<div class='oxe-image'><img src='/images/X/1/'></div></div><div class='footer'>skip</div>")
        text = "".join(p.out)
        self.assertIn("Title", text)
        self.assertIn("| Bolt | 20-27", text)
        self.assertIn("[FIGURE 1]", text)
        self.assertNotIn("skip", text)
        self.assertEqual(p.imgs, ["/images/X/1/"])

    def test_complaint_filter(self):
        r = {"components": "POWER TRAIN", "summary": "MANUAL TRANSMISSION JUMPED OUT OF GEAR"}
        self.assertTrue(ck.keep(r, "power train", "out of gear"))
        self.assertFalse(ck.keep(r, "AIR BAGS", None))
        self.assertFalse(ck.keep(r, None, "stall"))
        self.assertTrue(ck.keep({"components": None, "summary": None}))

    def test_years(self):
        self.assertEqual(list(ck.years("2006-2008")), [2006, 2007, 2008])
        self.assertEqual(list(ck.years("2010")), [2010])

    def test_svg_icons_are_not_figures(self):
        p = ck.PageText()
        p.feed("<div class='main'><img src='/icons/expand.svg'><img src='/images/IMP06Q313/asian230/146388670/'></div>")
        self.assertEqual(p.imgs, ["/images/IMP06Q313/asian230/146388670/"])

    def test_figure_names_unique_and_typed(self):
        self.assertEqual(ck.figure_name("fsm_", "/images/IMP06Q313/asian230/146388670/", 1), "fsm_230146388670.png")
        self.assertEqual(ck.figure_name("fsm_", "/img/diagram.jpg", 2), "fsm_02.jpg")

    def test_http_4xx_fails_fast_5xx_retries(self):
        import urllib.error
        calls = []
        def fake(code):
            def urlopen(req, timeout=0):
                calls.append(code)
                raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
            return urlopen
        real_open, real_sleep = ck.urllib.request.urlopen, ck.time.sleep
        ck.time.sleep = lambda s: None
        try:
            for code, expected_calls in ((404, 1), (429, 4), (502, 4)):
                calls.clear()
                ck.urllib.request.urlopen = fake(code)
                with self.assertRaises(SystemExit):
                    ck.get("https://example.invalid/")
                self.assertEqual(len(calls), expected_calls, code)
        finally:
            ck.urllib.request.urlopen, ck.time.sleep = real_open, real_sleep

    def test_vtt_dedupes_rolling_captions(self):
        self.assertTrue(ck._vtt_ok())


class Fetch(unittest.TestCase):
    def test_get_size_cap(self):  # LEMON streamed endless whitespace to a generic UA (20 GB)
        import http.server, threading
        hits = []

        class Big(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(1)
                self.send_response(200)
                self.end_headers()
                chunk = b" " * 1_000_000
                try:
                    for _ in range(26):
                        self.wfile.write(chunk)
                except OSError:
                    pass

            def log_message(self, *a):
                pass

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Big)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(SystemExit) as cm:
                ck.get(f"http://127.0.0.1:{srv.server_port}/")
            self.assertIn("over 25 MB", str(cm.exception))
            self.assertEqual(len(hits), 1)  # oversize is not transient: no retry
        finally:
            srv.shutdown()


class Config(unittest.TestCase):
    def setUp(self):
        self.old = os.environ.get("CARKIT_CONFIG")
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        if self.old is None:
            os.environ.pop("CARKIT_CONFIG", None)
        else:
            os.environ["CARKIT_CONFIG"] = self.old

    def test_config_get_silent_default(self):
        import contextlib, io
        os.environ["CARKIT_CONFIG"] = os.path.join(self.dir, "missing.json")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertIsNone(ck.config_get("library_dir"))
        self.assertEqual(err.getvalue(), "")

    def test_load_config_missing_exits_2(self):
        os.environ["CARKIT_CONFIG"] = os.path.join(self.dir, "missing.json")
        with self.assertRaises(SystemExit) as cm:
            ck.load_config("mygarage_url")
        self.assertEqual(cm.exception.code, 2)

    def test_load_config_reads(self):
        path = os.path.join(self.dir, "c.json")
        with open(path, "w") as f:
            f.write('{"mygarage_url": "http://x"}')
        os.environ["CARKIT_CONFIG"] = path
        self.assertEqual(ck.load_config("mygarage_url"), "http://x")


class Cli(unittest.TestCase):
    def test_cli_runs_isolated(self):  # -I drops the script's folder from sys.path
        import subprocess
        r = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "carkit.py"), "--help"],
                           capture_output=True, text=True, creationflags=0x08000000 if os.name == "nt" else 0)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
