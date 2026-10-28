"""render_check: render a guide page the way the artifact host will, and fail on layout defects.

  python -I render_check.py PAGE.html [--shots DIR]

Wraps the page in the same skeleton the Artifact publisher adds (doctype, viewport meta,
reset), loads it in headless Chromium at phone/tablet/desktop widths in light and dark,
and checks:
  overflow   the page scrolls sideways
  spill      an element's content is wider than its box (text running into a neighbour),
             outside containers meant to scroll (overflow-x: auto/scroll)
  overlap    two text elements in the same block draw on top of each other
  image      an <img> failed to load
  pin        a numbered pin sits outside its photo
  svg        SVG text runs outside the drawing
  sideways   a table or diagram only fits by scrolling sideways (cut off on a phone)
  tiny       SVG text drawn smaller than 10px (unreadable)
Writes full-page screenshots to --shots (look at them) and exits 1 if any defect is found.
"""
import argparse, os, pathlib, sys, tempfile

from playwright.sync_api import sync_playwright

SKELETON = ("<!doctype html><html><head><meta charset=utf8>"
            "<meta name=viewport content=\"width=device-width,initial-scale=1,viewport-fit=cover\">"
            "<style>:root{color-scheme:light;box-sizing:border-box}body{margin:0;padding:0;"
            "font:14px -apple-system,BlinkMacSystemFont,sans-serif}img{max-width:100%}"
            "[hidden]{display:none!important}</style></head><body>")

PROBE = r"""() => {
  const out = [];
  const W = document.documentElement.clientWidth;
  const label = el => (el.className && typeof el.className === 'string' ? el.tagName.toLowerCase() + '.' + el.className.split(' ')[0] : el.tagName.toLowerCase())
                     + ' "' + (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 50) + '"';
  // only real scroll boxes excuse wide content; overflow:hidden clips text, which is a defect
  const scrolls = el => { for (let p = el; p; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };
  if (document.documentElement.scrollWidth > W + 1) out.push(['overflow', `page is ${document.documentElement.scrollWidth}px wide in a ${W}px viewport`]);
  for (const el of document.body.querySelectorAll('*')) {
    if (['svg','path','text','tspan','rect','circle','g','img','script','style'].includes(el.tagName.toLowerCase())) continue;
    if (el.closest('.shot')) continue;  // photo frames clip images on purpose
    const cs = getComputedStyle(el);
    if (cs.display === 'inline' || cs.display === 'none') continue;
    if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0 && !scrolls(el.parentElement) && cs.overflowX === 'visible')
      out.push(['spill', `${label(el)} content ${el.scrollWidth}px in a ${el.clientWidth}px box`]);
  }
  // text runs that draw over each other: compare leaf text boxes within the same block parent
  const leaves = [...document.body.querySelectorAll('*')].filter(e => e.children.length === 0 && (e.textContent || '').trim() && !e.closest('svg') && getComputedStyle(e).display !== 'none');
  const boxes = leaves.map(e => [e, [...e.getClientRects()]]);
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const [a, ra] = boxes[i], [b, rb] = boxes[j];
    if (a.contains(b) || b.contains(a)) continue;
    if (a.closest('.shot') && b.closest('.shot')) continue;  // pins on photos may touch each other
    for (const x of ra) for (const y of rb) {
      const ix = Math.min(x.right, y.right) - Math.max(x.left, y.left), iy = Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top);
      if (ix > 3 && iy > 3) { out.push(['overlap', `${label(a)} overlaps ${label(b)} by ${Math.round(ix)}x${Math.round(iy)}px`]); break; }
    }
  }
  for (const img of document.images) if (!img.complete || img.naturalWidth === 0) out.push(['image', `failed to load ${img.getAttribute('src')}`]);
  for (const pin of document.querySelectorAll('.shot .pinm, .shot .ring')) {
    const s = pin.closest('.shot').getBoundingClientRect(), p = pin.getBoundingClientRect();
    const cx = (p.left + p.right) / 2, cy = (p.top + p.bottom) / 2;
    if (cx < s.left || cx > s.right || cy < s.top || cy > s.bottom) out.push(['pin', `${label(pin)} centre is outside its photo`]);
  }
  // content hidden behind a sideways scroll: readable only if you think to swipe
  for (const el of document.body.querySelectorAll('*')) {
    const o = getComputedStyle(el).overflowX;
    if ((o === 'auto' || o === 'scroll') && el.scrollWidth > el.clientWidth + 2)
      out.push(['sideways', `${label(el)} needs sideways scrolling (${el.scrollWidth}px in ${el.clientWidth}px)`]);
  }
  for (const t of document.querySelectorAll('svg text')) {
    const h = t.getBoundingClientRect().height;
    if (h > 0 && h < 10) out.push(['tiny', `SVG text "${t.textContent.slice(0, 40)}" renders ${h.toFixed(1)}px tall`]);
  }
  for (const svg of document.querySelectorAll('svg')) {
    const vb = svg.viewBox.baseVal;
    if (!vb || !vb.width) continue;
    for (const t of svg.querySelectorAll('text')) {
      const b = t.getBBox();
      if (b.x < vb.x - 1 || b.y < vb.y - 1 || b.x + b.width > vb.x + vb.width + 1 || b.y + b.height > vb.y + vb.height + 1)
        out.push(['svg', `text "${t.textContent.slice(0, 40)}" runs outside the drawing`]);
    }
  }
  return out;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("--shots", default=os.path.join(tempfile.gettempdir(), "render_check"))
    a = ap.parse_args()
    src = pathlib.Path(a.page).resolve()
    os.makedirs(a.shots, exist_ok=True)
    # written next to the page so relative img/ paths resolve the same as when published
    wrapped = src.with_name(f".render_{src.name}")
    wrapped.write_text(SKELETON + src.read_text(encoding="utf-8") + "</body></html>", encoding="utf-8")
    problems = 0
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()  # headless: no window on screen
            for width in (390, 768, 1280):
                for scheme in ("light", "dark"):
                    page = browser.new_page(viewport={"width": width, "height": 900}, color_scheme=scheme)
                    page.goto(wrapped.as_uri(), wait_until="networkidle")
                    page.evaluate("document.fonts.ready")
                    found = page.evaluate(PROBE)
                    shot = os.path.join(a.shots, f"{src.stem}_{width}_{scheme}.png")
                    page.screenshot(path=shot, full_page=True)
                    status = "FAIL" if found else "ok  "
                    print(f"{status} {width:>4}px {scheme:5}  {len(found)} defect(s)  {shot}")
                    for kind, msg in found[:25]:
                        print(f"       {kind:8} {msg}")
                    problems += len(found)
                    page.close()
            browser.close()
    finally:
        wrapped.unlink(missing_ok=True)
    print(f"\n{problems} defect(s) total")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
