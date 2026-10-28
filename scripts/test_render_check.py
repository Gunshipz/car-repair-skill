"""Proves render_check still catches defects (and passes a clean page). Run: python -I test_render_check.py"""
import os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE = "<style>body{background:#fff}.res{display:grid;grid-template-columns:120px 1fr}.box{width:200px;overflow:hidden}</style>"
BAD = STYLE + (
    "<div class='res'><span style='white-space:nowrap;display:block'>a very long label that will not fit here</span><span>text</span></div>"
    "<div class='box'><p style='white-space:nowrap'>clipped clipped clipped clipped clipped clipped</p></div>"
    "<div style='overflow-x:auto'><table><tr>" + "<td>wide&nbsp;cell&nbsp;content</td>" * 12 + "</tr></table></div>"
    "<img src='missing.png'>"
)
GOOD = STYLE + "<div class='res'><span>short</span><span>text that wraps normally inside its column</span></div><p>plain paragraph</p>"


def run(html):
    d = tempfile.mkdtemp()
    page = os.path.join(d, "t.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "render_check.py"), page, "--shots", d],
                       capture_output=True, text=True, creationflags=0x08000000 if os.name == "nt" else 0)
    return r.returncode, r.stdout


class RenderCheck(unittest.TestCase):
    def test_bad_page_fails_with_each_kind(self):
        code, out = run(BAD)
        self.assertEqual(code, 1, out)
        for kind in ("spill", "sideways", "image"):
            self.assertIn(kind, out)
        self.assertIn('"clipped clipped', out)  # overflow:hidden must not hide a clipped label

    def test_clean_page_passes(self):
        code, out = run(GOOD)
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
