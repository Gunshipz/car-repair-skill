"""Content checks for a test guide, run before publishing (render_check.py covers layout).

    python -I scripts/guide_check.py PAGE.html [--lib MAKE YEAR MODEL] [--links]

- in-page links (#id) point at an element that exists
- every local image file exists (data: URIs are skipped)
- every torque value (N·m) in the guide appears in the vehicle's factory-manual library, with the page it came
  from; one that doesn't must be cited to another source in the guide, or it's a number from nowhere
- --links: every external link answers (one polite request each)
- --standalone OUT: one shareable file, the page plus the artifact viewer's skeleton with every image embedded
Exits 1 when an anchor, image or link is broken. Torques not in the manual are listed, not failed: Chilton and
owner sources are legitimate, but each one needs its own citation.
"""
import argparse, base64, html, mimetypes, os, re, sys, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

NUM = r"\d+(?:\.\d+)?"
TORQUE = re.compile(rf"({NUM})(?:\s*[-–~]\s*({NUM}))?\s*N\s*[.·]?\s*m\b")


def _text(page_html):
    return html.unescape(re.sub(r"<[^>]+>", " ", page_html))


def check_local(path):
    s = open(path, encoding="utf-8").read()
    ids = set(re.findall(r'\sid="([^"]+)"', s))
    base = os.path.dirname(os.path.abspath(path))
    imgs = [i for i in re.findall(r'<img[^>]+src="([^"]+)"', s) if not i.startswith(("data:", "http"))]
    return {"bad_anchors": sorted({a for a in re.findall(r'href="#([^"]+)"', s) if a not in ids}),
            "missing_images": [i for i in imgs if not os.path.exists(os.path.join(base, i))],
            "images": len(imgs)}


def check_torques(path, db):
    """[(value as written, [manual URLs containing the same range])] for every N·m value in the guide."""
    pages = db.execute("SELECT url, text FROM pages").fetchall()
    out = []
    for m in sorted({m.group(0) for m in TORQUE.finditer(_text(open(path, encoding="utf-8").read()))}):
        lo, hi = TORQUE.match(m).groups()
        pat = re.compile(rf"(?<![\d.]){re.escape(lo)}" + (rf"\s*[-–~]\s*{re.escape(hi)}(?![\d.])" if hi else r"(?![\d.])")
                         + r"\s*N\s*[.·]?\s*m")
        out.append((m, [u for u, t in pages if pat.search(t)][:3]))
    return out


def external_links(page_html):
    """Links a reader can click (<a href>), not <link rel=preconnect/stylesheet> hints."""
    return sorted({html.unescape(u) for u in re.findall(r'<a\s[^>]*href="(https?://[^"]+)"', page_html)})


def check_links(path):
    from carkit import UA
    bad = []
    for url in external_links(open(path, encoding="utf-8").read()):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                r.read(1024)
        except urllib.error.HTTPError as e:
            if e.code not in (401, 403, 429):  # sites that block scripts but work in a browser
                bad.append(f"{url} -> HTTP {e.code}")
        except Exception as e:
            bad.append(f"{url} -> {type(e).__name__}: {e}")
    return bad


SKELETON = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width,initial-scale=1,viewport-fit=cover"><style>:root{color-scheme:light;'
            'box-sizing:border-box}body{margin:0;padding:0;font:14px sans-serif}img{max-width:100%}</style></head><body>')


def standalone(path, out):
    """Write OUT: the page in the same skeleton the artifact viewer adds, local images as data: URIs."""
    base = os.path.dirname(os.path.abspath(path))

    def embed(m):
        f = os.path.join(base, m.group(1))
        if not os.path.exists(f):
            raise SystemExit(f"standalone: image missing: {m.group(1)}")
        mime = mimetypes.guess_type(f)[0] or "application/octet-stream"
        with open(f, "rb") as fh:
            return f'src="data:{mime};base64,{base64.b64encode(fh.read()).decode()}"'
    body = re.sub(r'src="(?!data:|https?:)([^"]+)"', embed, open(path, encoding="utf-8").read())
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(SKELETON + body + "</body></html>\n")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page")
    ap.add_argument("--lib", nargs=3, metavar=("MAKE", "YEAR", "MODEL"))
    ap.add_argument("--links", action="store_true")
    ap.add_argument("--standalone", metavar="OUT")
    a = ap.parse_args()
    fails = 0
    r = check_local(a.page)
    print(f"anchors: {len(r['bad_anchors'])} broken {r['bad_anchors']}; images: {r['images']} local, "
          f"{len(r['missing_images'])} missing {r['missing_images']}")
    fails += len(r["bad_anchors"]) + len(r["missing_images"])
    if a.lib:
        import carlib
        db = carlib.open_db(carlib.vehicle_key(*a.lib))
        rows = check_torques(a.page, db)
        print(f"torques: {sum(1 for _, u in rows if u)} of {len(rows)} ranges appear in the factory-manual text "
              "(a number match: check the page is the same part)")
        for t, urls in rows:
            if urls:
                print(f"  SAME RANGE ON  {t}  " + "  |  ".join(urls))
            else:
                print(f"  NOT IN MANUAL TEXT  {t}  (may be in a figure or a bulletin: the guide must cite where)")
    if a.links:
        bad = check_links(a.page)
        print(f"links: {len(bad)} broken")
        for b in bad:
            print("  " + b)
        fails += len(bad)
    if a.standalone and not fails:
        print(f"standalone: {standalone(a.page, a.standalone)} ({os.path.getsize(a.standalone) / 1e6:.2f} MB)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
