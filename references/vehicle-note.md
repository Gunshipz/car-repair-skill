# Vehicle note template

One Markdown note per vehicle, wherever the user keeps notes (an Obsidian vault works well):
`<Year> <Model>.md`, or `<Year> <Model> - <Owner>.md` for someone else's car. Frontmatter, then sections.

```markdown
---
title: <Year> <Make> <Model>
created: YYYY-MM-DD
updated: YYYY-MM-DD
category: personal
tags: [car, <make>, <model>]
---

# <Year> <Make> <Model>

<Whose car, one line of context.>

## Vehicle Identity
- VIN:
- Engine: <code, displacement>
- Transmission: <code, type>
- Trim / build date:
- Platform siblings (share parts): 
- Factory manual: <charm.li URL>; local library: `carkit lib stats MAKE YEAR "MODEL"`

## Open symptoms
<one line each: YYYY-MM-DD · symptom · status (open / fixed YYYY-MM-DD). For the problem being worked: what's
been ruled out, the leading hypothesis (labeled), and a link to the test guide.>

## Specs (each with source URL)
| Item | Value | Source |

## Repair Log
| Date | Mileage | Work | Parts (number, source, price) | Result |

## Observations
<one line each: YYYY-MM-DD · <miles> mi · <scan|livelink|meter|scope|photo|sound|owner> · <reading> · [[raw file]].
Scans, LiveLink pulls, meter and scope readings, photos and sounds all go here, dated and with mileage.>

## Baseline
<the healthy reference: a link to the baseline scan or drive, plus key healthy values (idle coolant, fuel trims,
battery and charging volts). Later readings are compared against this.>

## Parts & Sources
## To-Do
```
