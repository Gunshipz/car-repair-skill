"""Utah self-pull yard search and watch. Standard library only.

Sources: Pick-n-Pull SLC (JSON API), Tear-A-Part SLC and Ogden (WordPress admin-ajax), Utah Pic-A-Part
Ogden and Orem (GET search page). Pull N Save is not here: it serves a bot challenge to scripts, so
it's browser only (call 801-508-1002).

Every source is checked with a control search (Honda Civic) before its answer counts, so a broken
source is reported as broken, never as "no cars".
"""
import html, json, os, re, sys, urllib.error, urllib.parse, urllib.request

from carkit import UA, config_get, get

CONTROL = ("Honda", ["Civic"], 1996, 2015)
MAX_MSG = 4000


class SourceError(Exception):
    def __init__(self, cls, detail=""):
        super().__init__(f"{cls}: {detail}")
        self.cls = cls


def check_body(body):
    if re.search(r"sgcaptcha|cf-chl|challenge-platform", body[:5000], re.I):  # not bare "captcha": real pages load recaptcha
        raise SourceError("challenge", body[:200])
    return body


def fetch(url, data=None):
    if data is None:
        return check_body(get(url, tries=2))
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return check_body(r.read(5_000_000).decode("utf-8", "replace"))


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def pick(names, wanted):
    """Source model names matching the wanted models, ignoring case, spaces and hyphens."""
    w = {norm(m) for m in wanted}
    return [n for n in names if norm(n) in w]


def _car(source, location, year, make, model, row, arrived, stock, vin="", url=""):
    return {"source": source, "location": location, "year": int(year), "make": make.title(), "model": model.title(),
            "row": str(row), "arrived": arrived, "stock": stock, "vin": vin or "", "url": url}


# ---------- parsers (fed saved responses in tests) ----------
def parse_picknpull(text, source):
    cars = []
    for loc in json.loads(text):
        for v in loc.get("vehicles") or []:
            if v.get("state") in ("Utah", "UT"):
                cars.append(_car(source, v["locationName"], v["year"], v["make"], v["model"], v["row"],
                                 (v.get("dateAdded") or "")[:10], v.get("barCodeNumber") or str(v["id"]), v.get("vin")))
    return cars


def parse_tearapart(text, source):
    d = json.loads(text)
    return [_car(source, p["yard_name"], p["iyear"], p["make"], p["model"], p["vehicle_row"], p.get("yard_date", ""),
                 p["stocknumber"], p.get("vin", ""))
            for p in (d.get("products") or []) if p.get("yard_state") == "UT"]


def parse_utpap(text, source):
    table = re.search(r"<table[^>]*id=.cars-table.*?</table>", text, re.S)
    if not table:
        raise SourceError("parse", "no cars-table")
    cars = []
    for row in re.findall(r"<tr>(.*?)</tr>", table.group(0), re.S)[1:]:
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td>(.*?)</td>", row, re.S)]
        if len(cells) >= 7 and cells[0].isdigit():
            year, make, model, stock, _engine, vrow, date = cells[:7]
            cars.append(_car(source, source.replace("utpap_", "Utah Pic-A-Part ").title(), year, make, model, vrow, date, stock))
    return cars


# ---------- live sources ----------
PNP = "https://www.picknpull.com/api/vehicle"


def picknpull_slc(make, models, y1, y2):
    mk = [m["id"] for m in json.loads(fetch(f"{PNP}/makes")) if norm(m["name"]) == norm(make)]
    if not mk:
        return []
    names = {m["name"]: m["id"] for m in json.loads(fetch(f"{PNP}/makes/{mk[0]}/models"))}
    cars = []
    for name in pick(names, models):
        cars += parse_picknpull(fetch(f"{PNP}/search?makeId={mk[0]}&modelId={names[name]}&zip=84115&distance=50&language=english"),
                                "picknpull_slc")
    return [c for c in cars if y1 <= c["year"] <= y2]


def _tearapart(store, source):
    def fn(make, models, y1, y2):
        page = fetch("https://tearapart.com/inventory/")
        nonce = re.search(r'sif_ajax_nonce":"(\w+)', page)
        if not nonce:
            raise SourceError("parse", "no nonce")
        ajax = "https://tearapart.com/wp-admin/admin-ajax.php"
        opts = fetch(ajax, {"action": "sif_update_models", "sif_verify_request": nonce.group(1), "make": make.upper(), "state": 0})
        cars = []
        for model in pick(re.findall(r'<option value="([^"]+)"', opts), models):
            cars += parse_tearapart(fetch(ajax, {"action": "sif_search_products", "sif_verify_request": nonce.group(1),
                                                 "sif_form_field_store": store, "sif_form_field_make": make.upper(),
                                                 "sif_form_field_model": model, "makes-sorting-order": 0,
                                                 "models-sorting-order": 0, "sorting": ""}), source)
        return [c for c in cars if y1 <= c["year"] <= y2]
    return fn


def _utpap(city, source):
    base = f"https://utpap.com/search-inventory_{city}.php"

    def fn(make, models, y1, y2):
        page = fetch(f"{base}?make={urllib.parse.quote(make.upper())}")
        sel = re.search(r'name="model".*?</select>', page, re.S)
        names = re.findall(r"<option value='([^']+)'", sel.group(0)) if sel else []
        cars = []
        for model in pick(names, models):
            cars += parse_utpap(fetch(f"{base}?make={urllib.parse.quote(make.upper())}&model={urllib.parse.quote(model)}"), source)
        return [c for c in cars if y1 <= c["year"] <= y2]
    return fn


SOURCES = {
    "picknpull_slc": picknpull_slc,
    "tearapart_slc": _tearapart("SALT LAKE CITY", "tearapart_slc"),
    "tearapart_ogden": _tearapart("OGDEN", "tearapart_ogden"),
    "utpap_ogden": _utpap("ogden", "utpap_ogden"),
    "utpap_orem": _utpap("orem", "utpap_orem"),
}


def classify(e):
    """A stable error class, so the same failure alerts once (a challenge URL changes every request)."""
    if isinstance(e, SourceError):
        return e.cls
    if isinstance(e, urllib.error.HTTPError):
        return f"http {e.code}"
    if isinstance(e, SystemExit):
        m = re.search(r"HTTP Error (\d+)", str(e))
        return f"http {m.group(1)}" if m else "fetch failed"
    if isinstance(e, (ValueError, KeyError, TypeError)):
        return "parse"
    return f"exception {type(e).__name__}"


def run(source, make, models, y1, y2):
    """(cars, None) or ([], error class). SystemExit is caught too: carkit.get raises it."""
    try:
        return SOURCES[source](make, models, y1, y2), None
    except (Exception, SystemExit) as e:
        return [], classify(e)


def control(source):
    cars, err = run(source, *CONTROL)
    return err or (None if cars else "control 0")


def search(make, models, y1, y2, sources):
    cars, errors = [], {}
    for s in sources:
        err = control(s)
        if not err:
            got, err = run(s, make, models, y1, y2)
            cars += got
        if err:
            errors[s] = err
    return cars, errors


def line(c):
    return f"{c['year']} {c['make']} {c['model']} - {c['location']} row {c['row']} (set {c['arrived']}) stock {c['stock']}"


def message(head, cars):
    out, lines = head, [line(c) for c in cars]
    for i, ln in enumerate(lines):
        if len(out) + len(ln) + 40 > MAX_MSG:
            return out + f"\n…and {len(lines) - i} more"
        out += "\n" + ln
    return out


def watch(watchlist_path, state_path, send, save_state=True):
    """One watch run. Returns (messages sent, sends failed).

    State is saved only after a send succeeds, and not at all with save_state=False (a dry run must not use up
    real alerts). Baselines are per watch entry *and* yard: a yard first seen working (on the first run, after an
    outage, or newly added) gets a "cars there now" summary, never an "N new" flood.
    """
    with open(watchlist_path, encoding="utf-8") as f:
        entries = json.load(f)
    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {"seen": {}, "errors": {}, "initialized": []}
    init = set(state["initialized"])
    for e in entries:  # state written before per-yard baselines named only the entry: every yard had one
        if e["name"] in init:
            init.discard(e["name"])
            init |= {f"{e['name']}|{s}" for s in e["sources"]}

    def save():
        if not save_state:
            return
        state["initialized"] = sorted(init)
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1)
        os.replace(tmp, state_path)

    sent = failed = 0

    def say(text):
        nonlocal sent, failed
        try:
            send(text)
        except Exception as e:  # leave state alone so the next run retries this message
            print(f"send failed: {e}", file=sys.stderr)
            failed += 1
            return False
        sent += 1
        return True

    sources = sorted({s for e in entries for s in e["sources"]})
    errors = {s: err for s in sources if (err := control(s))}
    found = {}
    for e in entries:
        for s in e["sources"]:
            if s not in errors:
                got, err = run(s, e["make"], e["models"], e["y1"], e["y2"])
                if err:
                    errors[s] = err
                else:
                    found[(e["name"], s)] = got

    for s in sources:  # alert once per error class, once on recovery
        new, old = errors.get(s), state["errors"].get(s)
        if new and new != old and say(f"Yard watch: {s} is broken ({new}). Its cars are not being checked."):
            state["errors"][s] = new
            save()
        elif not new and old and say(f"Yard watch: {s} recovered."):
            del state["errors"][s]
            save()

    def key(c):
        return f"{c['source']}|{c['stock'] or c['vin']}"

    for e in entries:
        name = e["name"]
        ok = [s for s in e["sources"] if s not in errors]
        fresh = [s for s in ok if f"{name}|{s}" not in init]
        seen = set(state["seen"].get(name, []))
        if fresh:
            cars = [c for s in fresh for c in found.get((name, s), [])]
            head = (f"Yard watch '{name}': watching {len(ok)} yards, {len(cars)} cars there now."
                    if len(fresh) == len(e["sources"]) or not init & {f"{name}|{s}" for s in e["sources"]}
                    else f"Yard watch '{name}': now also watching {', '.join(fresh)}, {len(cars)} cars there now.")
            if say(message(head, cars)):
                seen |= {key(c) for c in cars}
                init |= {f"{name}|{s}" for s in fresh}
                state["seen"][name] = sorted(seen)
                save()
        new = [c for s in ok if s not in fresh for c in found.get((name, s), []) if key(c) not in seen]
        if new and say(message(f"Yard watch '{name}': {len(new)} new.", new)):
            state["seen"][name] = sorted(seen | {key(c) for c in new})  # never removed: a car that left and came back stays quiet
            save()
    return sent, failed


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or config_get("telegram_bot_token")
    chat = os.environ.get("TELEGRAM_CHAT_ID") or config_get("telegram_chat_id")
    if not token or not chat:
        raise RuntimeError("not configured: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()  # plain text: no parse_mode to break
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=30) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(f"telegram refused: {body}")
    print(f"telegram message_id={body['result']['message_id']}")
    return body["result"]["message_id"]
