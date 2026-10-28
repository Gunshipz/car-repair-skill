---
name: car-repair
description: Use when the user wants to diagnose, research, or plan a repair on any car, truck or motorcycle — a symptom ("won't shift", "pops out of gear", "no start", "noise"), "is this a common problem", "what parts do I need / what will it cost", "find me the procedure / torque spec", or "build a troubleshooting guide". Also for adding a vehicle note or logging a repair. Free sources only.
---

# Car Repair

Diagnose a vehicle problem from free sources, prove the cause with the cheapest test that
tells causes apart, then price the fix. The output a person uses at the car is a **test
guide**: an HTML page that works at phone width, with real photos and numbered pins. A
**vehicle note** in the user's notes backs it up.

Worked example of the finished product: `examples/accent_guide_example.html` (2010 Hyundai
Accent, manual transmission won't go into gear). Open it before building a new guide. Reuse
its CSS tokens, pin markup (`.shot` + `.pinm`), test-card structure and appendix layout.

## Hard rules

1. **Every number comes from a page you fetched, cited with its URL.** That covers torque,
   capacity, fluid spec, part number and labor time. If the manual doesn't have it, write
   "not in the manual". Never fill a spec from memory. That is the known LLM failure in
   this field.
2. **Free sources by default.** No paid services (ALLDATA, OEM tech-info subscriptions,
   paid APIs) unless the user asks.
3. **Library databases at human pace.** Chilton Library, reached through a public library card, is licensed
   to the library. Fetch only the documents this car needs (stay under about 40 per job) and
   never crawl.
4. **An absence needs a positive control.** Report "no TSB", "no complaints" or "none in
   the yard" only after the same search finds something you know exists. `carkit
   selftest` covers the APIs; for a one-off, search a common car the same way.
5. **No visible windows.** Scripts run hidden (carkit uses CREATE_NO_WINDOW on Windows).
   Don't pop browsers or consoles on the user's screen unless they ask.
6. **Explain what parts ARE** before naming them. For example: "the select cable moves
   when the stick goes side to side".
7. Research fan-out uses cheaper subagents (Sonnet), one per topic, in parallel. Keep the
   synthesis and the guide in the main session.

## Workflow

### 0. What do we already know?
- If the user keeps a case index (one row per past problem: vehicle, symptom, root cause, the test that proved
  it) and vehicle notes with **Open symptoms**, **Observations** and **Baseline** sections, search them first.
  Someone may have seen this before, and last month's reading may already answer it.

### 1. Identify the exact vehicle
- `python -I scripts/carkit.py vin <VIN>` gives the year, engine, transmission style and
  plant. **No VIN?** Carry on with year, model and engine, take the drivetrain codes from
  the manual's Specifications pages, and put "VIN + door-jamb build date" on the guide's
  questions list. The build date decides which part numbers apply.
- Find the drivetrain codes (engine, transmission) and the **platform siblings** that share
  the failing part. For example, Accent MC = Kia Rio JB = M5CF1 gearbox. Search across all
  of them.
- Vehicle note: one Markdown note per vehicle in the user's notes (template in
  `references/vehicle-note.md`). Ask once where notes live, then record that in CLAUDE.md.

### 2. What do other owners see?
- NHTSA: `carkit complaints MAKE MODEL 2006-2011 --component "POWER TRAIN" --grep "..."`
  and `carkit recalls MAKE MODEL YEAR`. Repeat for each platform sibling. `--grep` is a
  regex on the complaint text, so anchor short terms: use `"\b2nd gear\b"`, not `"2nd"`. A
  misspelled make or model fails with HTTP 400; that means a typo, not "none".
- Forums and Q&A: use whatever web search you have (WebSearch, or Exa/Tavily MCP if
  installed). Reddit: search with `site:reddit.com`, or use the Arctic Shift archive API.
- **Record outcomes, not just symptoms**: what fixed it, the mileage and the cost. A thread
  with no resolution counts for less. Count a cause only when the poster says it fixed the
  problem.
- Videos: `carkit yt "QUERY" --n 6` prints captions. Pick timestamps, grab frames with
  ffmpeg, and look at every frame before using it.

### 3. Factory facts
- **Local library first.** If the vehicle has one (`carkit lib stats MAKE YEAR "MODEL"`), search it with
  `carkit lib search MAKE YEAR "MODEL" "P0A80"` (or `"wheel nut"`, `"shift cable"`). Each hit prints
  `SOURCE <url>`; cite that. A library covers the whole manual, so 0 hits is a real "not in this manual"; still
  widen the words once. No library means no ZIP was imported, not that the page is missing.
- Manuals: `carkit models MAKE YEAR`, then `carkit find MAKE YEAR "MODEL" "REGEX"`, then
  `carkit page MAKE YEAR "MODEL" "<path printed by find>" --img <dir>`. charm.li covers
  1982–2013; add `--site lemon` for newer years.
  - **Folder names are the manual's, not yours.** Transaxles live under
    `Manual Transmission%2FTransaxle`, so search with loose words (`"Manual
    Trans.*Symptom"`, `"Shift"`, `"Torque|Mechanical Spec"`). On a 0-match result, widen
    the regex before deciding the page doesn't exist.
  - **Most tables are images.** Troubleshooting, torque and spec tables print as
    `[FIGURE n]`. Always pass `--img`, then open each saved figure and quote it.
  - For labor times and part numbers, run `find ... --section "Parts and Labor"`.
  - Each `page` call takes 2–10 s. Run loops of more than about 5 pages in the background.
- Chilton Library: required for TSBs, and for labor times or procedures the factory manual
  lacks. Login is in `references/sources.md`.
- Manuals sometimes contradict themselves. Report both values and where each came from.

### 4. Rank causes, then design the tests
- Rank the hypotheses by evidence: the factory troubleshooting table plus owner outcomes.
- Order the tests **cheapest first**, but lead with the one test that separates the
  expensive outcome from the cheap ones.
- Each test gets what to do, the time and tools, and a result table: reading, then what it
  means, then the next step. Label guesses as guesses.

### 5. Parts and prices
- Take the OEM part number from the manual's Parts Information or a dealer parts diagram
  first, then price it: RockAuto (curl works), car-part.com (used, by distance), local
  self-pull yard price lists and inventories, eBay. Note interchange caveats and core
  charges.
- Give totals by outcome, DIY vs shop. Shop cost = factory labor hours × a local rate,
  labelled as an estimate.

### 6. Build the guide
- Start from `examples/accent_guide_example.html`. Put images next to the page under
  `img/`, or embed them as base64 for a single shareable file. Place pins by `%` position
  after looking at each image.
- Sections: questions for the owner near the top, then how it works, the test order, the
  tests, parts and prices, then appendices (how common it is, R&R procedures, rebuild,
  things you might find).
- **Before calling a page ready, run `python -I scripts/guide_check.py <page.html> --lib MAKE YEAR "MODEL"
  --links`.** It fails on broken in-page links, missing images and dead external links (folder links on charm.li
  and LEMON 404: link real pages). It lists every N·m value and whether the manual text has the same range; one
  that doesn't must be labeled in the guide with its real source. A match is a number match only, so check the
  page is the same part. `--standalone OUT` writes one shareable file with every image embedded.
- **Then run `python -I scripts/render_check.py <page.html> --shots
  <dir>` and get `0 defect(s) total`.** It renders at 390/768/1280 px in light and dark and
  fails on sideways scrolling, text spilling out of its box, overlapping text, broken
  images, pins off their photo, tables or diagrams cut off on a phone, and tiny SVG text.
  Then look at the 390 px screenshot yourself, because the checker can't judge
  readability. Layout rules that keep it passing:
  - no `white-space:nowrap` on labels in grid columns
  - wide tables get `class="stack"` (they turn into cards below 520 px)
  - flow diagrams are HTML boxes, not wide SVG
- If your Claude has the Artifact tool (claude.ai), publish with it. Otherwise save the
  HTML and open it in the browser for the user.

### 7. Close the loop
- When results come back, update the guide's top callout, log the finding and the fix in
  the vehicle note's Repair Log, and correct any disproven claim where it lives.
- Every reading taken along the way (meter, scope, scan, photo, sound) goes in the note's **Observations**,
  dated and with mileage. When the problem is fixed, add its row to the case index.

## OBD-II (optional, not installed)
See `references/obd.md`. Don't buy or install anything until the user asks.

## Scripts
- `scripts/carkit.py`: data pulls (stdlib only). `python -I scripts/carkit.py --help`.
  `selftest` checks every source with a known-good query and exits nonzero on any failure.
- `scripts/render_check.py`: layout checker (Playwright + Chromium).
- `carkit lib add|search|stats|fig MAKE YEAR MODEL`: local factory-manual library (`carlib.py`), built from a complete
  LEMON ZIP the user downloads by hand from the vehicle's lemon-manuals.la page (the site asks people not to
  automate it). Then run `lib add Hyundai 2010 "Accent L4-1.6L" --zip FILE` and `lib search ... "P0A80"` or
  `"wheel nut"`. Each hit prints `SOURCE <url>` to cite, plus `FIGURE zip:...` refs (`lib fig` extracts one).
  The library covers the whole manual, so 0 hits means not in this manual; still widen the words once.
- `carkit yard search MAKE "Accent,Rio" 2006-2011`: Utah self-pull yards (Pick-n-Pull SLC, Tear-A-Part SLC and
  Ogden, Utah Pic-A-Part Ogden and Orem). Each yard is checked against a Honda Civic search first, so a `BROKEN`
  line means that yard wasn't checked. Pull N Save blocks scripts, so call it.
- `carkit yard watch WATCHLIST STATE`: the same search on a timer, with a Telegram message when a new car arrives
  (see `server/`). `carkit garage sessions|pull VIN`: drives and telemetry CSV from a self-hosted MyGarage
  (WiCAN OBD dongle live data). Both need `~/.config/carkit/config.json`; without it they exit 2 with
  `not configured`.
- `scripts/guide_check.py`: content checks before publishing (see step 6).
- Tests: `scripts/test_*.py` (carkit, carlib, yards, garage, guide_check, render_check). Full plan:
  `references/test-plan.md`.
