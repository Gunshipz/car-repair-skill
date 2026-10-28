"""carkit: free data pulls for diagnosing a car. Standard library only.

  vin VIN                               decode a VIN (NHTSA vPIC)
  recalls MAKE MODEL YEAR               NHTSA recalls
  complaints MAKE MODEL Y1[-Y2] [--grep RE] [--component RE] [--show N]
                                        NHTSA owner complaints, filtered
  models MAKE YEAR                      model folders in the factory-manual archive
  find MAKE YEAR MODEL REGEX            search that car's manual tree; prints page paths
  page MAKE YEAR MODEL PATH [--img DIR] fetch one manual page: text + figure URLs (+download)
  yt "QUERY" [--n 5] [--out DIR]        YouTube search + English captions as plain text
  selftest                              hit every source with a known-good query

Manuals: charm.li covers 1982-2013; --site lemon uses lemon-manuals.la (adds newer years).
Every printed number should be cited to the URL this prints, never retyped from memory.
"""
import argparse, html.parser, json, os, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # `python -I` drops it; sibling modules live here

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) carkit/1.0"
SITES = {"charm": "https://charm.li", "lemon": "https://lemon-manuals.la"}
NHTSA = "https://api.nhtsa.gov"


def config_get(key, default=None):
    """Silent lookup in ~/.config/carkit/config.json (or $CARKIT_CONFIG)."""
    path = os.environ.get("CARKIT_CONFIG") or os.path.expanduser("~/.config/carkit/config.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get(key, default)
    except (OSError, ValueError):
        return default


def load_config(key):
    v = config_get(key)
    if v is None:
        print(f"not configured: {key}", file=sys.stderr)
        raise SystemExit(2)
    return v


def get(url, binary=False, tries=4, max_bytes=25_000_000):
    last = None
    for i in range(tries):  # charm.li 502s on big pages under load, then works
        if i:
            time.sleep(5 * i)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                buf = bytearray()
                while chunk := r.read(1 << 20):
                    buf += chunk
                    if len(buf) > max_bytes:  # not transient: a generic UA once got 20 GB of whitespace from LEMON
                        raise SystemExit(f"fetch failed: {url}\n  response over {max_bytes // 1_000_000} MB")
                data = bytes(buf)
            return data if binary else data.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429:  # 400/404 won't fix themselves; 429 = slow down, retry
                raise SystemExit(f"fetch failed: {url}\n  {e}")
            last = e
        except Exception as e:  # retry network errors
            last = e
    raise SystemExit(f"fetch failed: {url}\n  {last}")


def q(s):
    return urllib.parse.quote(s, safe="")


def car_base(site, make, year, model):
    return f"{SITES[site]}/{q(make)}/{year}/{q(model)}/"


# ---------- NHTSA ----------
def cmd_vin(a):
    d = json.loads(get(f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{a.vin}?format=json"))["Results"][0]
    keys = ["ModelYear", "Make", "Model", "Trim", "Series", "BodyClass", "DisplacementL", "EngineCylinders",
            "EngineModel", "TransmissionStyle", "TransmissionSpeeds", "DriveType", "PlantCountry", "ErrorText"]
    for k in keys:
        if d.get(k):
            print(f"{k:18} {d[k]}")


def cmd_recalls(a):
    d = json.loads(get(f"{NHTSA}/recalls/recallsByVehicle?make={q(a.make)}&model={q(a.model)}&modelYear={a.year}"))
    rs = d.get("results", [])
    print(f"{len(rs)} recall(s) for {a.year} {a.make} {a.model}")
    for r in rs:
        print(f"- {r['NHTSACampaignNumber']}  {r['Component']}\n  {r['Summary'][:300]}")


def years(spec):
    lo, _, hi = spec.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def keep(r, component=None, grep=None):
    if component and not re.search(component, r.get("components") or "", re.I):
        return False
    return not grep or bool(re.search(grep, r.get("summary") or "", re.I))


def cmd_complaints(a):
    total, hits = 0, []
    for y in years(a.years):
        rs = json.loads(get(f"{NHTSA}/complaints/complaintsByVehicle?make={q(a.make)}&model={q(a.model)}&modelYear={y}")).get("results", [])
        total += len(rs)
        hits += [(y, r) for r in rs if keep(r, a.component, a.grep)]
    print(f"{total} complaints total for {a.make} {a.model} {a.years}; {len(hits)} match the filters")
    if total == 0:
        print("WARNING: zero total complaints. Check make/model spelling before reading this as 'none'.")
    for y, r in hits[: a.show]:
        print(f"\n[{y}] ODI {r.get('odiNumber')}  {r.get('components')}  incident={r.get('dateOfIncident') or '?'}\n  {r.get('summary', '')[:600]}")


# ---------- factory manuals ----------
def model_folders(page, make, year):
    """Model folder names from a make/year index page (links may be absolute or relative, ' or ")."""
    hrefs = re.findall(rf"href=[\"'](?:/{q(make)}/{year}/)?([^\"'/#]+)/[\"']", page)
    return sorted({urllib.parse.unquote(h) for h in hrefs} - {make, str(year), ""})


def tree_hrefs(page):
    # keep %2F literal: it is a slash inside one folder name, e.g. "Manual Transmission%2FTransaxle"
    return [urllib.parse.unquote(h.replace("%2F", "%252F")) for h in re.findall(r"<a href='([^']+/)'", page)]


def page_url(site, make, year, model, path):
    segs = path.strip("/").split("/")
    return car_base(site, make, year, model) + "/".join(q(urllib.parse.unquote(s)) for s in segs) + "/"


def cmd_models(a):
    for m in model_folders(get(f"{SITES[a.site]}/{q(a.make)}/{a.year}/"), a.make, a.year):
        print(m)


def cmd_find(a):
    pat = re.compile(a.regex, re.I)
    paths = tree_hrefs(get(car_base(a.site, a.make, a.year, a.model) + q(a.section) + "/"))
    found = [p for p in paths if pat.search(p)]
    print(f"{len(found)} of {len(paths)} pages match")
    for p in found:
        print(f"{a.section}/{p}")  # paste straight into `page`


class PageText(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.inmain, self.depth, self.out, self.imgs = False, 0, [], []

    def handle_starttag(self, tag, attrs):
        at = dict(attrs)
        if tag == "div" and at.get("class") == "main":
            self.inmain, self.depth = True, 0
        if not self.inmain:
            return
        if tag == "div":
            self.depth += 1
        if tag == "img" and at.get("src") and not at["src"].endswith(".svg"):  # .svg = site UI icons
            self.imgs.append(at["src"])
            self.out.append(f"[FIGURE {len(self.imgs)}]")
        if tag in ("br", "p", "tr", "li", "h1", "h2", "h3"):
            self.out.append("\n")
        if tag in ("td", "th"):
            self.out.append(" | ")

    def handle_endtag(self, tag):
        if self.inmain and tag == "div":
            self.depth -= 1
            if self.depth <= 0:
                self.inmain = False

    def handle_data(self, d):
        if self.inmain:
            self.out.append(d)


def figure_name(prefix, src, i):
    """charm.li figures are /images/<book>/<set>/<id>/ (PNG); keep the id so names are stable."""
    path = urllib.parse.urlparse(src).path.rstrip("/")
    ext = os.path.splitext(path)[1] or ".png"
    ident = re.sub(r"[^0-9]", "", path)[-12:] or f"{i:02d}"
    return f"{prefix}{ident}{ext}"


def cmd_page(a):
    url = page_url(a.site, a.make, a.year, a.model, a.path)
    p = PageText()
    p.feed(get(url))
    text = re.sub(r"\n\s*\n+", "\n\n", "".join(p.out)).strip()
    print(f"SOURCE {url}\n\n{text}\n")
    for i, src in enumerate(p.imgs, 1):
        full = urllib.parse.urljoin(SITES[a.site], src)
        print(f"FIGURE {i}: {full}")
        if a.img:
            os.makedirs(a.img, exist_ok=True)
            name = os.path.join(a.img, figure_name(a.prefix, src, i))
            with open(name, "wb") as f:
                f.write(get(full, binary=True))
            print(f"  saved {name}")


# ---------- YouTube ----------
def vtt_text(path):
    seen, lines = set(), []
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read().splitlines()
    for ln in raw:
        ln = re.sub(r"<[^>]+>", "", ln).strip()
        if not ln or "-->" in ln or ln.startswith(("WEBVTT", "Kind:", "Language:")) or ln in seen:
            continue
        seen.add(ln)
        lines.append(ln)
    return " ".join(lines)


def cmd_yt(a):
    os.makedirs(a.out, exist_ok=True)
    base = [sys.executable, "-m", "yt_dlp", "--skip-download", "--write-auto-subs", "--write-subs",
            "--sub-langs", "en.*", "--sub-format", "vtt", "--print", "%(id)s\t%(duration_string)s\t%(channel)s\t%(title)s",
            "--no-simulate", "-o", os.path.join(a.out, "%(id)s.%(ext)s")]
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    r = subprocess.run(base + [f"ytsearch{a.n}:{a.query}"], capture_output=True, text=True, creationflags=flags)
    if not r.stdout.strip():  # a broken yt-dlp must not look like "no videos"
        raise SystemExit(f"yt-dlp returned no results (exit {r.returncode}):\n{r.stderr[-800:]}")
    for row in r.stdout.splitlines():
        vid, dur, ch, title = (row.split("\t") + ["", "", ""])[:4]
        subs = [f for f in os.listdir(a.out) if f.startswith(vid) and f.endswith(".vtt")]
        txt = vtt_text(os.path.join(a.out, subs[0])) if subs else "(no English captions)"
        print(f"\n=== https://youtu.be/{vid}  [{dur}]  {ch}\n{title}\n{txt[: a.chars]}")


def cmd_selftest(a):
    checks = [
        ("vPIC decode", lambda: "HONDA" in get("https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/1HGCM82633A004352?format=json")),
        ("NHTSA complaints (2010 Civic > 100)", lambda: json.loads(get(f"{NHTSA}/complaints/complaintsByVehicle?make=honda&model=civic&modelYear=2010"))["count"] > 100),
        ("NHTSA recalls (2010 Accent >= 1)", lambda: json.loads(get(f"{NHTSA}/recalls/recallsByVehicle?make=hyundai&model=accent&modelYear=2010"))["Count"] >= 1),
        ("charm.li model list", lambda: "Accent L4-1.6L" in urllib.parse.unquote(get("https://charm.li/Hyundai/2010/"))),
        ("charm.li page parse", lambda: "Troubleshooting" in "".join(_parse("https://charm.li/Hyundai/2010/Accent%20L4-1.6L/Repair%20and%20Diagnosis/Transmission%20and%20Drivetrain/Manual%20Transmission%2FTransaxle/Testing%20and%20Inspection/Symptom%20Related%20Diagnostic%20Procedures/").out)),
        ("vtt cleaner", _vtt_ok),
    ]
    bad = 0
    for name, fn in checks:
        try:
            ok = fn()
        except SystemExit as e:
            ok = False
            print(e)
        bad += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    sys.exit(bad)


def _parse(url):
    p = PageText()
    p.feed(get(url))
    return p


def _vtt_ok():
    import tempfile
    f = tempfile.NamedTemporaryFile("w", suffix=".vtt", delete=False, encoding="utf-8")
    f.write("WEBVTT\n\n00:00.000 --> 00:01.000\nunclip the <c>cable</c>\n\n00:01.000 --> 00:02.000\nunclip the cable\nthen the pin\n")
    f.close()
    out = vtt_text(f.name)
    os.unlink(f.name)
    return out == "unclip the cable then the pin"


# ---------- local manual library (carlib.py) ----------
def _libdb(a, must_exist=True):
    import carlib
    key = carlib.vehicle_key(a.make, a.year, a.model)
    if must_exist and not os.path.exists(os.path.join(carlib.library_root(), f"{key}.sqlite")):
        raise SystemExit(f"no library for {key}: download its LEMON ZIP and run `carkit lib add ... --zip FILE`")
    return carlib, carlib.open_db(key)


def cmd_lib(a):
    carlib, db = _libdb(a, must_exist=a.op != "add")
    if a.op == "add":
        import shutil
        dest = os.path.join(carlib.library_root(), "zips", os.path.basename(a.zip))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.abspath(a.zip) != os.path.abspath(dest):
            shutil.copy2(a.zip, dest)
        stored, dupes, tree = carlib.import_zip(db, dest, car_base("lemon", a.make, a.year, a.model),
                                               expect=f"{a.year} {a.make} {a.model}")
        print(f"stored {stored}, duplicate bodies skipped {dupes}, folder pages skipped {tree}")
    if a.op in ("add", "stats"):
        n, figs = db.execute("SELECT count(*), coalesce(sum(json_array_length(figures)), 0) FROM pages").fetchone()
        meta = dict(db.execute("SELECT key, value FROM meta"))
        print(f"{n} pages, {figs} figure refs, import_complete={meta.get('import_complete', 'NO')}, "
              f"pages without an online URL={meta.get('fallback_urls', '?')}, source={meta.get('source_zip', '?')}")
    elif a.op == "search":
        try:
            hits = carlib.search(db, a.query, a.limit)
        except (carlib.IncompleteLibrary, ValueError) as e:
            raise SystemExit(str(e))
        print(f"{len(hits)} hit(s) for {a.query!r}")
        for h in hits:
            print(f"\nSOURCE {h['url']}\nPATH   {h['path']}\n  {h['snippet']}")
            for f in h["figures"]:
                print(f"FIGURE {f}")
    elif a.op == "fig":
        print(carlib.figure(db, a.ref, a.out))


# ---------- Utah yards (yards.py) ----------
def cmd_yard(a):
    import yards
    if a.op == "search":
        y = years(a.years)
        cars, errors = yards.search(a.make, a.models.split(","), y.start, y.stop - 1, a.sources.split(","))
        print(f"{len(cars)} car(s) for {a.make} {a.models} {a.years} at {a.sources}")
        for c in sorted(cars, key=lambda c: (c["source"], c["year"])):
            print("  " + yards.line(c))
        for s, err in errors.items():
            print(f"BROKEN {s}: {err} (its cars were not checked; this is not 'no cars')")
    else:
        send = print if a.dry_run else yards.send_telegram
        sent, failed = yards.watch(a.watchlist, a.state, send, save_state=not a.dry_run)
        print(f"messages sent: {sent}, failed: {failed}" + (" (dry run: state not saved)" if a.dry_run else ""))
        if failed:  # a dead Telegram token must not look like "no new cars"
            raise SystemExit(1)


# ---------- MyGarage LiveLink (garage.py) ----------
def cmd_garage(a):
    import garage
    c = garage.Client(load_config("mygarage_url"), load_config("mygarage_user"), load_config("mygarage_password"))
    try:
        c.login()
        if a.op == "sessions":
            ss, total = c.sessions(a.vin)
            print(f"{len(ss)} of {total} drive(s) for {a.vin} (idle or garage data has no drive: use `pull --start/--end`)")
            for s in ss:
                print(f"  id {s['id']}  {s['started_at']} -> {s.get('ended_at') or 'open'}  "
                      f"{s.get('distance_km') or 0} km  max coolant {s.get('max_coolant_temp')}")
        else:
            if a.session:
                s = c.session(a.vin, a.session)
                import datetime  # a drive still in progress has no end yet: take everything up to now
                now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                start, end, name = s["started_at"], s.get("ended_at") or now, f"livelink-{a.session}.csv"
            elif a.start and a.end:
                start, end, name = a.start, a.end, f"livelink-{garage.stamp(a.start)}.csv"
            else:
                raise SystemExit("pull needs --session ID, or --start and --end (ISO times)")
            out = c.export_csv(a.vin, start, end, os.path.join(a.out, name), a.params.split(",") if a.params else None)
            print(f"saved {out}: {garage.describe_csv(out)}")
    except garage.GarageError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    gar = sp.add_parser("garage", help="MyGarage LiveLink: drives and telemetry CSV").add_subparsers(dest="op", required=True)
    s = gar.add_parser("sessions"); s.add_argument("vin"); s.set_defaults(f=cmd_garage)
    s = gar.add_parser("pull"); s.add_argument("vin"); s.add_argument("--session"); s.add_argument("--start")
    s.add_argument("--end"); s.add_argument("--params", help="comma list of param keys"); s.add_argument("--out", default=".")
    s.set_defaults(f=cmd_garage)
    yard =sp.add_parser("yard", help="Utah self-pull yard search and watch").add_subparsers(dest="op", required=True)
    s = yard.add_parser("search"); s.add_argument("make"); s.add_argument("models", help="comma list: Accent,Rio")
    s.add_argument("years", help="2006-2011"); s.add_argument("--sources", default="picknpull_slc,tearapart_slc,tearapart_ogden,utpap_ogden,utpap_orem")
    s.set_defaults(f=cmd_yard)
    s = yard.add_parser("watch"); s.add_argument("watchlist"); s.add_argument("state"); s.add_argument("--dry-run", action="store_true")
    s.set_defaults(f=cmd_yard)
    lib = sp.add_parser("lib", help="local manual library from a LEMON ZIP").add_subparsers(dest="op", required=True)
    for op in ("add", "search", "stats", "fig"):
        s = lib.add_parser(op); [s.add_argument(x) for x in ("make", "year", "model")]
        if op == "add":
            s.add_argument("--zip", required=True)
        if op == "search":
            s.add_argument("query"); s.add_argument("--limit", type=int, default=10)
        if op == "fig":
            s.add_argument("ref"); s.add_argument("--out", default=".")
        s.set_defaults(f=cmd_lib)
    s = sp.add_parser("vin"); s.add_argument("vin"); s.set_defaults(f=cmd_vin)
    s = sp.add_parser("recalls"); [s.add_argument(x) for x in ("make", "model", "year")]; s.set_defaults(f=cmd_recalls)
    s = sp.add_parser("complaints"); [s.add_argument(x) for x in ("make", "model", "years")]
    s.add_argument("--grep"); s.add_argument("--component"); s.add_argument("--show", type=int, default=20); s.set_defaults(f=cmd_complaints)
    for name, fn in (("models", cmd_models), ("find", cmd_find), ("page", cmd_page)):
        s = sp.add_parser(name); s.add_argument("make"); s.add_argument("year")
        if name != "models":
            s.add_argument("model")
            s.add_argument("regex" if name == "find" else "path")
        s.add_argument("--site", default="charm", choices=SITES)
        if name == "find":
            s.add_argument("--section", default="Repair and Diagnosis", help="or 'Parts and Labor'")
        if name == "page":
            s.add_argument("--img"); s.add_argument("--prefix", default="fsm_")
        s.set_defaults(f=fn)
    s = sp.add_parser("yt"); s.add_argument("query"); s.add_argument("--n", type=int, default=5)
    s.add_argument("--out", default=os.path.join(os.environ.get("TEMP", "."), "carkit_yt")); s.add_argument("--chars", type=int, default=4000)
    s.set_defaults(f=cmd_yt)
    sp.add_parser("selftest").set_defaults(f=cmd_selftest)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
