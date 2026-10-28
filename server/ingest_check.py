"""End-to-end LiveLink check that can fail (a bare 202 proves nothing: MyGarage answers 202 even when it
drops the data). Creates a test vehicle and a fake WiCAN, links them, posts data the way a WiCAN does,
asserts the value reads back, then deletes both unless --keep.

Run from the PC after setup and after any move to a new host:
    python -I server/ingest_check.py [--keep]
Reads mygarage_url / mygarage_user / mygarage_password / wican_token from ~/.config/carkit/config.json.
"""
import json, os, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from carkit import load_config

VIN, DEV = "1HGCM82633A004352", "deadbeef0001"  # vPIC's sample Honda VIN; a 12-hex fake device id


def call(method, path, body=None, headers=None):
    req = urllib.request.Request(load_config("mygarage_url") + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def must(label, got, ok, show=True):
    status, body = got
    print(f"{'PASS' if ok(status, body) else 'FAIL'}  {label}: {status} {str(body)[:160] if show else ''}")
    if not ok(status, body):
        raise SystemExit(1)
    return body


def main(keep):
    t = must("login", call("POST", "/api/auth/login", {"username": load_config("mygarage_user"),
                                                      "password": load_config("mygarage_password")}),
             lambda s, b: s == 200, show=False)
    auth = {"Authorization": f"Bearer {t['access_token']}", "X-CSRF-Token": t["csrf_token"]}
    wican = {"Authorization": f"Bearer {load_config('wican_token')}"}
    must("create test vehicle", call("POST", "/api/vehicles", {"vin": VIN, "nickname": "ingest check",
                                                              "vehicle_type": "Car"}, auth),
         lambda s, b: s in (200, 201) or (s in (400, 409) and "exist" in str(b).lower()))
    try:
        status = {"device_id": DEV, "fw_version": "test", "ecu_status": "online"}
        must("WiCAN status (discovery)", call("POST", "/api/v1/livelink/ingest", {"status": status, "autopid_data": {}}, wican),
             lambda s, b: s == 202 and b.get("status") != "rejected")
        must("link device to vehicle", call("PUT", f"/api/livelink/devices/{DEV}", {"vin": VIN}, auth),
             lambda s, b: s == 200)
        data = {"status": status, "autopid_data": {"ENGINE_COOLANT_TEMP": 88, "ENGINE_RPM": 750},
                "config": {"ENGINE_COOLANT_TEMP": {"unit": "°C", "class": "temperature"},
                           "ENGINE_RPM": {"unit": "rpm", "class": "none"}}}
        must("WiCAN data stored", call("POST", "/api/v1/livelink/ingest", data, wican),
             lambda s, b: s == 202 and b.get("parameters_stored", 0) > 0 and not b.get("processing_error"))
        # read the value back (sessions are drives built from movement, so an idle check never opens one)
        q = "?start=2000-01-01T00:00:00Z&end=2100-01-01T00:00:00Z&param_keys=ENGINE_COOLANT_TEMP"
        must("coolant 88 reads back", call("GET", f"/api/vehicles/{VIN}/livelink/telemetry{q}", headers=auth),
             lambda s, b: s == 200 and 88 in [p.get("value") for x in b.get("series", []) for p in x.get("data", [])])
    finally:
        if not keep:
            print("cleanup: device", call("DELETE", f"/api/livelink/devices/{DEV}", headers=auth)[0],
                  "vehicle", call("DELETE", f"/api/vehicles/{VIN}", headers=auth)[0])
            must("vehicle gone", call("GET", f"/api/vehicles/{VIN}", headers=auth), lambda s, b: s == 404)


if __name__ == "__main__":
    main("--keep" in sys.argv)
