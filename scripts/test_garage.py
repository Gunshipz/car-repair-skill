"""Offline tests for the MyGarage client, against a stub server with MyGarage 3.9.0's real shapes.
Run: python -I test_garage.py"""
import http.server, json, os, subprocess, sys, tempfile, threading, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import garage

VIN = "1HGCM82633A004352"
SESSIONS = {"sessions": [{"id": 7, "vin": VIN, "device_id": "deadbeef0001", "started_at": "2026-10-28T10:00:00",
                          "ended_at": "2026-10-28T10:20:00", "duration_seconds": 1200, "distance_km": 9.5,
                          "max_coolant_temp": 96.0}], "total": 1, "stationary_total": 0}
CSV = "timestamp,param_key,value\r\n2026-10-28T10:01:00,ENGINE_COOLANT_TEMP,88.0\r\n2026-10-28T10:01:00,ENGINE_RPM,750.0\r\n"


class Stub(http.server.BaseHTTPRequestHandler):
    login_status = 200
    seen = []

    def reply(self, status, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/api/auth/login":
            if Stub.login_status != 200:
                return self.reply(Stub.login_status, {"detail": "Incorrect username or password"})
            return self.reply(200, {"access_token": "tok", "csrf_token": "c", "token_type": "bearer", "expires_in": 3600})
        self.reply(404, {"detail": "nope"})

    def do_GET(self):
        Stub.seen.append(self.path)
        if self.headers.get("Authorization") != "Bearer tok":
            return self.reply(401, {"detail": "Not authenticated"})
        if self.path.startswith(f"/api/vehicles/{VIN}/livelink/sessions/7"):
            return self.reply(200, SESSIONS["sessions"][0])
        if self.path.startswith(f"/api/vehicles/{VIN}/livelink/sessions"):
            return self.reply(200, SESSIONS)
        if self.path.startswith(f"/api/vehicles/{VIN}/livelink/export/telemetry"):
            return self.reply(200, CSV, "text/csv; charset=utf-8")
        self.reply(404, {"detail": "nope"})

    def log_message(self, *a):
        pass


class GarageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Stub.login_status, Stub.seen[:] = 200, []
        self.dir = tempfile.mkdtemp()
        self.cfg = os.path.join(self.dir, "config.json")
        with open(self.cfg, "w") as f:
            json.dump({"mygarage_url": self.url, "mygarage_user": "user", "mygarage_password": "pw"}, f)

    def cli(self, *args, cfg=None):
        env = dict(os.environ, CARKIT_CONFIG=cfg or self.cfg)
        return subprocess.run([sys.executable, "-I", os.path.join(HERE, "carkit.py"), "garage", *args],
                              capture_output=True, text=True, env=env, cwd=self.dir,
                              creationflags=0x08000000 if os.name == "nt" else 0)

    def test_sessions_parsed(self):
        c = garage.Client(self.url, "user", "pw")
        c.login()
        s, total = c.sessions(VIN)
        self.assertEqual(total, 1)
        self.assertEqual([x["id"] for x in s], [7])
        self.assertTrue(any("include_stationary=true" in p for p in Stub.seen))  # idle data has no movement

    def test_sessions_says_when_list_is_cut(self):  # a daily driver passes 100 drives in a few months
        SESSIONS["total"] = 250
        try:
            r = self.cli("sessions", VIN)
        finally:
            SESSIONS["total"] = 1
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1 of 250", r.stdout)

    def test_pull_saves_export_csv(self):
        r = self.cli("pull", VIN, "--session", "7", "--out", self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        path = os.path.join(self.dir, "livelink-7.csv")
        with open(path, encoding="utf-8") as f:
            self.assertIn("ENGINE_COOLANT_TEMP,88.0", f.read())
        self.assertIn("2 rows", r.stdout)
        self.assertIn("ENGINE_COOLANT_TEMP", r.stdout)
        self.assertTrue(any("start=2026-10-28T10" in p and "end=2026-10-28T10" in p for p in Stub.seen))

    def test_pull_by_time_window(self):
        r = self.cli("pull", VIN, "--start", "2026-10-28T09:00:00Z", "--end", "2026-10-28T11:00:00Z", "--out", self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "livelink-20261028T090000Z.csv")))

    def test_401_clear_error(self):
        Stub.login_status = 401
        r = self.cli("sessions", VIN)
        self.assertEqual(r.returncode, 1)
        self.assertIn("MyGarage 401", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_dropped_connection_clear_error(self):  # review I-3: Docker's proxy accepts then closes while restarting
        import socket
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(5)
        def drop():
            for _ in range(3):
                try:
                    c, _ = srv.accept()
                    c.close()
                except OSError:
                    return
        threading.Thread(target=drop, daemon=True).start()
        with open(self.cfg, "w") as f:
            json.dump({"mygarage_url": f"http://127.0.0.1:{srv.getsockname()[1]}", "mygarage_user": "k", "mygarage_password": "p"}, f)
        r = self.cli("sessions", VIN)
        srv.close()
        self.assertEqual(r.returncode, 1)
        self.assertIn("MyGarage 0", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_unconfigured_exits_2(self):
        r = self.cli("sessions", VIN, cfg=os.path.join(self.dir, "missing.json"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("not configured", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
