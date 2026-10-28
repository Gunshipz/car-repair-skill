"""MyGarage LiveLink client: list drives and save telemetry as CSV. Standard library only.

MyGarage's "sessions" are drives built from movement, so an idling car never opens one. For garage or
idle data, pull by time window. Trouble codes don't come from here: stock WiCAN firmware doesn't send
them, so an empty list would read as "no codes". They come from `carkit scan`.
"""
import http.client, json, os, re, urllib.error, urllib.parse, urllib.request


class GarageError(Exception):
    def __init__(self, status, body):
        super().__init__(f"MyGarage {status}: {body[:200]}")
        self.status, self.body = status, body


class Client:
    def __init__(self, base_url, user, password):
        self.base, self.user, self.password, self.token = base_url.rstrip("/"), user, password, None

    def _req(self, method, path, body=None, raw=False):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.base + path, method=method, headers=headers,
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            raise GarageError(e.code, e.read().decode("utf-8", "replace")) from None
        except urllib.error.URLError as e:
            raise GarageError(0, f"cannot reach {self.base}: {e.reason}") from None
        except (OSError, http.client.HTTPException) as e:  # accept-then-close while the container restarts, timeouts
            raise GarageError(0, f"cannot reach {self.base}: {type(e).__name__}: {e}") from None
        if raw:
            return data.decode("utf-8")
        try:
            return json.loads(data)
        except ValueError:
            raise GarageError(200, "not JSON: " + data[:200].decode("utf-8", "replace")) from None

    def login(self):
        self.token = self._req("POST", "/api/auth/login", {"username": self.user, "password": self.password})["access_token"]

    def sessions(self, vin):
        """(up to 100 drives as the server orders them, total count)."""
        d = self._req("GET", f"/api/vehicles/{vin}/livelink/sessions?include_stationary=true&limit=100")
        return d["sessions"], d.get("total", len(d["sessions"]))

    def session(self, vin, sid):
        return self._req("GET", f"/api/vehicles/{vin}/livelink/sessions/{sid}")

    def export_csv(self, vin, start, end, out_path, params=None):
        q = {"start": start, "end": end, "format": "csv"}
        if params:
            q["param_keys"] = ",".join(params)
        text = self._req("GET", f"/api/vehicles/{vin}/livelink/export/telemetry?{urllib.parse.urlencode(q)}", raw=True)
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return out_path


def describe_csv(path):
    """'N rows, params: A, B' for a long-format (timestamp,param_key,value) export."""
    with open(path, encoding="utf-8") as f:
        rows = [ln.split(",") for ln in f.read().splitlines()[1:] if ln]
    params = sorted({r[1] for r in rows if len(r) > 1})
    return f"{len(rows)} rows, params: {', '.join(params) or '(none)'}"


def stamp(iso):
    return re.sub(r"[^0-9TZ]", "", iso)
