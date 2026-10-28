# car-repair: a Claude Code skill for diagnosing cars from free sources

It turns "my car won't shift" into a tested, cited troubleshooting guide. Claude researches the problem the way
a careful mechanic would:

- what the factory manual says;
- what other owners saw and what actually fixed it;
- which cheap test tells the expensive cause from the cheap ones;
- what each fix costs, new and used.

The result is a phone-friendly HTML guide with photos, numbered pins and a result table for every test.

It came out of diagnosing a friend's 2010 Hyundai Accent that stopped going into gear. `examples/` holds that
guide (without its images).

## What's in it

| Piece | What it does |
|---|---|
| `SKILL.md` | The method Claude follows: hard rules (every spec cited to a page you fetched; an absence needs a positive control), workflow, guide layout. |
| `scripts/carkit.py` | Free data pulls, standard library only: VIN decode, NHTSA recalls and owner complaints, factory service manual pages and figures (charm.li 1982–2013, LEMON for newer), YouTube captions. |
| `carkit lib` (`carlib.py`) | A local, searchable copy of one vehicle's factory manual, built from its LEMON ZIP. SQLite full-text search matches codes (`P0A80` vs `P0A8F`), connector names and torque units exactly. Every hit cites its online page. |
| `carkit yard` (`yards.py`) | Searches Utah self-pull yards: Pick-n-Pull SLC, Tear-A-Part SLC/Ogden, Utah Pic-A-Part Ogden/Orem. Each yard is checked against a Honda Civic search first, so a broken site reads as broken, never as "no cars". `yard watch` sends a Telegram message on new arrivals. |
| `carkit garage` (`garage.py`) | Reads live OBD data (drives, telemetry CSV) from a self-hosted MyGarage fed by a WiCAN dongle. Optional; see `server/`. |
| `scripts/guide_check.py` | Before publishing a guide: in-page links, images, dead external links, and every torque value cross-checked against the manual. `--standalone` builds one shareable file. |
| `scripts/render_check.py` | Renders a guide at phone, tablet and desktop widths, light and dark, and fails on layout defects. |
| `server/` | Optional Docker and systemd pieces for MyGarage and the yard watch. |

## Install

Ask Claude Code to "install the skill in this repo using INSTALL-FOR-CLAUDE.md", or follow that file yourself.
Python 3.10+. The core needs nothing outside the standard library.

```
python -I scripts/carkit.py vin 1HGCM82633A004352
python -I scripts/carkit.py complaints Hyundai Accent 2006-2011 --component "POWER TRAIN" --grep "gear"
python -I scripts/carkit.py yard search Hyundai "Accent,Rio" 2006-2011
python -I scripts/carkit.py lib search Hyundai 2010 "Accent L4-1.6L" "wheel nut"
```

## Using the sources politely

- **Manual ZIPs** from lemon-manuals.la are downloaded by a person, one per vehicle, as the site asks. carkit
  never automates that download, and every fetch is capped at 25 MB.
- **Chilton Library** is licensed to libraries. Use it at human pace, for the documents one car needs, with your
  own library card.
- **The yard searches** make a few requests per run. The watch runs every 6 hours, not continuously.
- **car-part.com's terms forbid bulk scraping,** so this skill uses it only for searches by hand.

## Disclaimer

This is research help, not professional repair advice. Check every spec against the cited page before you put
a wrench on it. Support a car properly before working under it.

## License

MIT. See `LICENSE`.
