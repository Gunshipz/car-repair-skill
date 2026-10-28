# car-repair: install and run (written for Claude Code)

You are Claude Code, installing this skill for the user. Do the steps yourself and tell the user what you did.
Ask them only for decisions or for clicks you can't do.

1. **Python 3.10 or newer.** Check with `python --version` (`py --version` on Windows).
2. **Packages for the optional tools:** `python -m pip install --user yt-dlp playwright pillow`, then
   `python -m playwright install chromium`. The core `carkit.py` is standard library only.
3. **Copy this repository's folder** to the user's skills folder as `car-repair`:
   `%USERPROFILE%\.claude\skills\car-repair\` on Windows, `~/.claude/skills/car-repair/` on macOS and Linux.
   If a `car-repair` skill already exists there, ask before overwriting it.
4. **Check it works,** from the installed folder, and show the user the output:
   - `python -I scripts/test_carkit.py`, `test_carlib.py`, `test_yards.py`, `test_garage.py` and
     `test_guide_check.py`: each ends with `OK`
   - `python -I scripts/test_render_check.py`: `OK` (needs Playwright and Chromium)
   - `python -I scripts/carkit.py selftest`: 6 `PASS` lines (needs internet)
5. Tell the user to start a new Claude Code session, so the skill loads.

Optional: a factory-manual library for a vehicle. The user downloads the vehicle's ZIP from its lemon-manuals.la
page; the site asks that this be done by a person, not a script. Then run
`python -I scripts/carkit.py lib add MAKE YEAR "MODEL" --zip FILE`, with YEAR MAKE MODEL exactly as in the ZIP's
top folder name, e.g. `2010 Hyundai Accent L4-1.6L`.
