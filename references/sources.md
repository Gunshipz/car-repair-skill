# Free sources, how to reach each

| Source | What it gives | Access | Notes |
|---|---|---|---|
| charm.li (Operation CHARM) | Factory service manuals 1982–2013: procedures, torque, specs, troubleshooting tables, wiring, parts numbers, labor times, TSB links | Free, no login. `carkit models/find/page` | Big tree pages 502 under load; carkit retries with backoff. Folder names include the engine ("Accent L4-1.6L"). A `/` inside a folder name is `%2F` (keep it encoded in paths). |
| LEMON (lemon-manuals.la) | Same as charm.li plus newer years | Free. `carkit ... --site lemon` | Site notes some networks can't reach it. |
| Chilton Library (Gale) | OEM-sourced procedures, TSBs, labor times, wiring, maintenance | A public library card from a library that subscribes (in Utah, any public library card through Utah's Online Library: card number only, no PIN). Utah's login: POST `https://login.ulc.idm.oclc.org/login` with `user=<card>` and `url=r0$https://link.gale.com/apps/CHLL?u=uspl` (keep cookies); it redirects into the Chilton app. Session ~1 h. | Licensed to the state: human pace, only this car's documents. |
| NHTSA vPIC | VIN decode | Free, no key. `carkit vin` | |
| NHTSA recalls / complaints | Recalls; owner complaints with text, component, mileage | Free, no key. `carkit recalls`, `carkit complaints` | Complaints are keyword-filterable; component field e.g. "POWER TRAIN". |
| NHTSA manufacturer communications | TSB summaries (bulk CSV) | Free download from nhtsa.gov/nhtsa-datasets-and-apis | Not every bulletin; zip URLs change. The page returns 403 to curl (bot block, 2026-10-27); use Exa fetch or the automation Chrome. Chilton's TSB list is usually faster. |
| Utah junkyard inventories | Donor cars on lots, row, date set; fixed self-pull prices | picknpull.com (JSON API behind its search page), pullnsave.com, tearapart.com, utpap.com (Ogden/Orem) | Feeds rarely say manual vs automatic: decode donor VINs with `carkit vin`, which sometimes shows `TransmissionStyle`. |
| Forums | Owner reports with outcomes | Exa → Tavily → Brave | hyundai-forums.com Cloudflare-blocks curl; Exa fetch works. |
| Reddit | Owner reports | `arctic-shift` skill (archive API) | reddit.com itself blocks fetches. |
| YouTube | Procedures on video, real photos (frames) | `carkit yt`, yt-dlp, ffmpeg | Captions often missing on non-English channels. |
| RockAuto | New parts, prices, OE cross-refs | curl with browser UA; catalog URLs `rockauto.com/en/catalog/<make>,<year>,<model>,<engine>,<id>,...` | No API; prices before shipping. |
| car-part.com | Used parts at yards, by distance, Hollander interchange | Manual searches (zip 84101) | Terms forbid bulk scraping. |
| Pick-n-Pull SLC | Fixed self-pull prices + lot inventory | picknpull.com/part-pricing/74 | 585 W 3300 S, SLC. |
| Dealer parts sites (hyundaipartsdeal, kiapartsnow...) | OEM numbers, exploded diagrams | Free | Good for exact part numbers by VIN. |
| SLC Public Library ProDemand | Pro shop database | In-branch computers only | Manual use only; can't be automated. |

Excluded (paid): ALLDATA DIY, Mitchell DIY, HyundaiTechInfo, PartsTech, ACES/PIES data.
