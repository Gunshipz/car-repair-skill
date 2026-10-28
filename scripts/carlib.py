"""Local factory-manual library: one SQLite FTS5 file per vehicle, built only from a complete LEMON ZIP.

Only complete ZIPs make a library, so "not found" means "not in this manual", never "not cached yet".
Quoted FTS5 terms already match codes (P0A80 vs P0A8F), connectors (IP-3), part numbers and torque
units exactly and ignore case; bm25 ranks pages that repeat a term higher.
"""
import hashlib, html, json, os, posixpath, re, shutil, sqlite3, urllib.parse, zipfile

from carkit import PageText, config_get


class IncompleteLibrary(Exception):
    pass


def vehicle_key(make, year, model):
    return re.sub(r"[^a-z0-9.]+", "-", f"{make} {year} {model}".lower()).strip("-")


def library_root():
    return config_get("library_dir") or os.path.expanduser("~/carkit-library")


def open_db(key, root=None):
    root = root or library_root()
    os.makedirs(root, exist_ok=True)
    db = sqlite3.connect(os.path.join(root, f"{key}.sqlite"))
    db.executescript("""
        CREATE TABLE IF NOT EXISTS pages(id INTEGER PRIMARY KEY, url TEXT UNIQUE, path TEXT, text TEXT,
                                         body_hash TEXT UNIQUE, figures TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(path, text, content='pages', content_rowid='id');
        CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
          INSERT INTO pages_fts(rowid, path, text) VALUES (new.id, new.path, new.text); END;
        CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
          INSERT INTO pages_fts(pages_fts, rowid, path, text) VALUES ('delete', old.id, old.path, old.text); END;
        CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
          INSERT INTO pages_fts(pages_fts, rowid, path, text) VALUES ('delete', old.id, old.path, old.text);
          INSERT INTO pages_fts(rowid, path, text) VALUES (new.id, new.path, new.text); END;
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
    """)
    return db


def store_page(db, url, path, text, figures):
    """Upsert by url. Returns False (and stores nothing) when another url already has this exact body.

    The body is text plus figures: many wiring pages share one caption but show different diagrams.
    """
    h = hashlib.sha1((text + "\0" + json.dumps(figures)).encode()).hexdigest()
    if db.execute("SELECT 1 FROM pages WHERE body_hash = ? AND url != ?", (h, url)).fetchone():
        return False  # TSBs are copied under several folders; one copy is enough
    db.execute("""INSERT INTO pages(url, path, text, body_hash, figures) VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT(url) DO UPDATE SET path=excluded.path, text=excluded.text,
                  body_hash=excluded.body_hash, figures=excluded.figures""",
               (url, path, text, h, json.dumps(figures)))
    return True


def _fts(terms, phrase):
    esc = [t.replace('"', '""') for t in terms]
    return f'"{" ".join(esc)}"' if phrase else " ".join(f'"{t}"' for t in esc)


def search(db, query, limit=10):
    row = db.execute("SELECT value FROM meta WHERE key = 'import_complete'").fetchone()
    if not row or row[0] != "1":
        raise IncompleteLibrary("library import never finished; re-run `carkit lib add`")
    if not re.search(r"\w", query):  # "0 hits" must only ever mean "not in this manual"
        raise ValueError(f"query {query!r} has no letters or digits to search for")
    terms = query.split()
    hits, seen = [], set()
    for phrase in (True, False):  # exact phrase first, then all terms anywhere on the page
        rows = db.execute("""SELECT p.id, p.url, p.path, snippet(pages_fts, 1, '[', ']', '…', 16), p.figures
                             FROM pages_fts JOIN pages p ON p.id = pages_fts.rowid
                             WHERE pages_fts MATCH ? ORDER BY bm25(pages_fts) LIMIT ?""",
                          (_fts(terms, phrase), limit)).fetchall()
        for pid, url, path, snip, figs in rows:
            if pid not in seen and len(hits) < limit:
                seen.add(pid)
                hits.append({"url": url, "path": path, "snippet": snip, "figures": json.loads(figs)})
    return hits


LINK = re.compile(r"<a href='\.\./pages/(\d+)\.html'(?: name='([^']*)')?>([^<]*)</a>")
CRUMB = re.compile(r'class="breadcrumb-part" href="[^"]*">([^<]*)</a>')


def import_zip(db, zip_path, base, expect=None):
    """Load every page of a LEMON ZIP in one transaction. Returns (stored, duplicates_skipped, tree_pages_skipped).

    A page's online URL is its parent's URL plus the parent's encoded `name='…'` for it, so a "/" inside a
    name stays %2F (about 1 in 4 Accent pages). Pages linked only without a name keep a zip: URL.
    """
    with zipfile.ZipFile(zip_path) as z:
        members = [n for n in z.namelist() if re.search(r"/pages/\d+\.html$", n)]
        top = members[0].rsplit("pages/", 1)[0]
        if expect and top.rstrip("/") != expect:  # the URLs are built from the typed name, so it must be the manual's
            raise SystemExit(f'this ZIP is "{top.rstrip("/")}", not "{expect}": pass YEAR MAKE MODEL exactly as in that name')
        raw = {re.search(r"(\d+)\.html$", n).group(1): z.read(n).decode("utf-8", "replace") for n in members}

    parent = {}
    for src, s in raw.items():
        for n, name, text in LINK.findall(s):
            if name and n not in parent:
                parent[n] = (src, name)
            elif src == "1" and n not in parent:  # the vehicle index links its sections by text only
                parent[n] = ("1", urllib.parse.quote(html.unescape(text).strip(), safe="") + "/")

    paths = {"1": ""}

    def path_of(n, depth=0):
        if n not in paths:
            paths[n] = None  # cycle guard
            if n in parent and depth < 50:
                up = path_of(parent[n][0], depth + 1)
                paths[n] = None if up is None else up + parent[n][1]
        return paths[n]

    stored = dupes = tree = fallback = 0
    with db:
        db.execute("DELETE FROM meta")
        db.execute("DELETE FROM pages")
        for n, s in raw.items():
            if "li-folder" in s:
                tree += 1
                continue
            p = PageText()
            p.feed(s)
            text = re.sub(r"\n\s*\n+", "\n\n", "".join(p.out)).strip()
            crumbs = [html.unescape(c).strip() for c in CRUMB.findall(s)][4:]  # drop Home, make, year, model
            figs = ["zip:" + posixpath.normpath(posixpath.join(top + "pages", src)) for src in p.imgs]
            rel = path_of(n)
            url = base + rel if rel is not None else f"zip:{top}pages/{n}.html"
            fallback += rel is None
            if store_page(db, url, " > ".join(crumbs), text, figs):
                stored += 1
            else:
                dupes += 1
        db.executemany("INSERT INTO meta VALUES (?, ?)", [("source_zip", os.path.abspath(zip_path)),
                                                         ("fallback_urls", str(fallback)), ("import_complete", "1")])
    return stored, dupes, tree


def figure(db, ref, out_dir):
    """Extract one zip: figure from the library's source ZIP; returns the file path."""
    src = db.execute("SELECT value FROM meta WHERE key = 'source_zip'").fetchone()[0]
    member = ref[len("zip:"):]
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, posixpath.basename(member))
    with zipfile.ZipFile(src) as z, z.open(member) as f, open(out, "wb") as o:
        shutil.copyfileobj(f, o)
    return out
