# car-repair test plan

Run all of it after any change to the skill or `carkit.py`. Record each run's results in
the table at the bottom (date, pass/fail per ID, notes).

## A. Offline unit tests (no network)
| ID | Test | Pass when |
|---|---|---|
| A2 | `python -I scripts/test_render_check.py` | a bad page (nowrap label in a narrow grid, text clipped by overflow:hidden, too-wide table, missing image) exits 1 and names spill, sideways, image; a clean page exits 0 |
| A1 | `python -I scripts/test_carkit.py` | all tests OK: model-list parsing (both quote styles), `%2F` kept in tree paths, page URL round trip, page text/table/figure extraction with header/footer excluded, complaint filter incl. null fields, year ranges, caption de-dupe |

## B. Live sources (positive controls)
| ID | Command | Pass when |
|---|---|---|
| B1 | `carkit selftest` | 6/6 PASS, exit 0 |
| B2 | `carkit vin 1HGCM82633A004352` | prints Make HONDA, Model Accord, ModelYear 2003 |
| B3 | `carkit recalls hyundai accent 2010` | ≥1 recall, includes 15V566000 |
| B4 | `carkit complaints hyundai accent 2006-2011 --component "POWER TRAIN" --grep "out of gear"` | total 458 (as of 2026-10-27, may grow), ≥1 match incl. ODI 10293389 |
| B5 | `carkit models Hyundai 2010` | list includes "Accent L4-1.6L" |
| B6 | `carkit find Hyundai 2010 "Accent L4-1.6L" "Manual Transmission.*Symptom"` | 1 path, containing `Manual Transmission%2FTransaxle` |
| B7 | `carkit page` on the B6 path with `--img <tmp>` | prints SOURCE URL, "Troubleshooting", ≥1 FIGURE, saves a PNG that opens as an image showing the troubleshooting table |
| B8 | `carkit find ... "Shift Cable/$" --section "Parts and Labor"` then `page` on the manual one | page lists "Parts Information" and "Labor Times" |
| B9 | `carkit models Hyundai 2018 --site lemon` | non-empty list (LEMON reachable for newer years) |
| B10 | `carkit yt "replace shift cable hyundai accent" --n 3` | 3 results with URL/duration/title; ≥1 has caption text or says "(no English captions)" |

## C. Negative controls (fails loudly, never silently "nothing")
| ID | Command | Pass when |
|---|---|---|
| C1 | `carkit vin 12345` | prints ErrorText (invalid VIN), not blank |
| C2 | `carkit complaints hyundia accent 2010` (misspelled) | exits 1 with "fetch failed ... HTTP Error 400" in under 5 s (NHTSA rejects unknown make/model; no retry) |
| C6 | `carkit page Hyundai 2010 "Accent L4-1.6L" "No/Such/Page"` timing | fails in under 5 s (404 is not retried) |
| C7 | `carkit yt "zzqqxx" --n 0` | exits 1 with yt-dlp's error text (a broken yt-dlp never looks like "no videos") |
| C3 | `carkit find Hyundai 2010 "Accent L4-1.6L" "zzzz"` | "0 of N pages match" with N > 1000 (proves the tree loaded) |
| C4 | `carkit page Hyundai 2010 "Accent L4-1.6L" "No/Such/Page"` | exits nonzero with "fetch failed" (no fake empty page) |
| C5 | `carkit models Hyundai 1975` | empty list, and `carkit models Hyundai 1990` non-empty (control) |

## D. Skill wiring
| ID | Check | Pass when |
|---|---|---|
| D1 | Skill appears in the session's skill list as `car-repair` | listed with its description |
| D2 | Every path the SKILL.md names exists (scripts, references, exemplar guide, docs folder, vault folder) | all exist |
| D3 | Every URL in `references/sources.md` and `references/obd.md` | HTTP < 400 (or a documented reason, e.g. Cloudflare) |
| D4 | Chilton login per sources.md (curl) | redirect to `app-chiltonlibrary-com.ulc.idm.oclc.org` with `product_id CHLL` in the token |
| D5 | Fresh-subagent scenario: a Sonnet agent with only the skill text works steps 1–3 for a different car (2008 Kia Rio 5-speed, "grinds going into 2nd") | uses carkit; every spec it reports carries a fetched URL; it labels guesses; it runs a control before any "none found" |

## E. Products
| ID | Check | Pass when |
|---|---|---|
| E1 | A vehicle note made from `references/vehicle-note.md` | frontmatter parses (YAML), all template sections present, links resolve |
| E2 | Accent guide artifact | `Artifact read` returns the page; files listing shows all 12+ images; each `img src` in the HTML has a published file |
| E4 | `scripts/render_check.py` on the guide | 0 defects at 390/768/1280 × light/dark; positive control: on the v3 guide it reported 72 spill defects (nowrap labels) and, after the sideways/tiny checks were added, 4 sideways defects (SVG flow, parts table), so it catches both kinds |
| E3 | Code review | `ponytail-review` run on carkit.py + test file; Must/Should findings fixed |

## F. Manual library (`carlib.py`, `carkit lib`)
- F1 `python -I scripts/test_carlib.py`: all pass. It covers exact codes, punctuation, torque units, ranking,
  duplicate and figure-different pages, the slash-in-name URL, the failed-import refusal, and the CLI under `-I`.
- F2 Import the Accent ZIP. Stored pages plus duplicates must equal 7,581, with 387 folder pages skipped and
  `import_complete=1`.
- F3 `lib search ... "wheel nut"`: the Mechanical Specifications > Wheel Stud / Lug Nut page (90 - 110 N.m) is
  in the top 5.
- F4 `lib search ... "Symptom Related"`: the Manual Transmission/Transaxle symptom page is among the hits.
- F5 Fetch one returned `SOURCE` URL containing `%2F`. Its title must match the PATH.

## G. Yard watch (`yards.py`, `carkit yard`)
- G1 `python -I scripts/test_yards.py`: all pass. It covers the parsers on saved responses, challenge pages, a source
  raising SystemExit, the first-run summary, alert-once, a failed send keeping cars unseen, recovery without a flood,
  error-class dedup, control 0, and truncation.
- G2 Run `carkit yard search Hyundai Accent 2006-2011` live. There must be no BROKEN lines (all 5 Civic controls
  pass), and the cars should match a hand check of the yard sites.

## H. MyGarage (`garage.py`, `carkit garage`, `server/ingest_check.py`)
- H1 `python -I scripts/test_garage.py`: all pass. It runs against a stub with the real 3.9.0 shapes: sessions ask for
  stationary sessions too, pull by session and by window, a 401 gives a clear error with no traceback, and an
  unconfigured run exits 2.
- H2 `python -I server/ingest_check.py`: every line must be PASS. The value must read back, because a bare 202
  proves nothing.
- H3 Live `garage pull VIN --start --end` on the ingest-check car saves a CSV with both parameters.

## I. Guide content (`guide_check.py`)
- I1 `python -I scripts/test_guide_check.py`: all pass. It covers a broken anchor, a missing image, torques found
  and not found (including "~" ranges), clickable links only, standalone embedding, and a refused missing image.
- I2 Run `guide_check.py` on the live guide with `--lib ... --links`. It must report 0 broken anchors, images and
  links, and every torque not in the manual text must be labeled with its source in the guide.
- I3 Run `render_check.py` on the `--standalone` output too, which tests the embedded images.

## Results
| Date | A | B | C | D | E | Notes |
|---|---|---|---|---|---|---|
