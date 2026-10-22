# Design contract: Quant Foundry

The transferable design rules for this site. Graders and repair workers read this file; it
contains no private preferences or credentials.

## Character

An **editorial research terminal**: a research note you can interrogate. Prose is set like a
working paper; numbers are set like a terminal (dense, condensed, tabular). The site's one
bold move is the **referee's verdict**: each strategy is listed in the headline and rejected
strategies carry a hand-drawn red-pen strike with the rejection reason in the margin, because
in this lab rejection is the expected, honest outcome. Everything else stays quiet.

Second motif: the **sealed holdout**. Wherever time is plotted, the holdout span is a hatched
band labelled "Holdout, evaluated once"; it is never mixed with development data.

## Process record

| Directive stage | Playbook steps | Done here |
|---|---|---|
| 1 Discovery | 1 brief, 3 direction | Character given by the brief; direction delegated, chosen above |
| 2 Content | 2 audience and content | Audience: technical reviewers, quant-curious engineers, recruiters judging rigor. Primary action: open a strategy's evidence. Copy uses only computed values; nothing invented |
| 3 Staging | 4 references, 5 design plan, 6 assets | No external visual references adopted (the named motion reference could not be verified). Tokens below. No generated imagery: the data is the imagery |
| 4 Component adaptation | 7 architecture | Hand-built SVG charts and components (no chart or UI library) to keep the bundle small and the look specific |
| (build) | 8 build and debug | Interactions verified in a browser before claiming fixes |
| 5 Batch polish | 9 batch, 10 section by section | One coordinated batch after the first browser review, then one restrained treatment per flat section |
| 6 Mobile pass | 11 | Deliberate 390 px composition (see Responsive) |
| 7 Browser evidence | 12 | Playwright at 390 / 768 / 1440 in CI and against the live site; screenshots read by a person |
| 8 Deployment | 13 | GitHub Pages from Actions; live URL verified |

Skills actually invoked for this design: `website-playbook`, `frontend-design:frontend-design`,
`ui-ux-pro-max` (design-system, typography and chart searches; its navy palette and
portfolio-grid pattern were rejected as off-brief, its Swiss-grid rationality and
Newsreader suggestion were kept).

## Tokens (semantic; components never use raw hex)

| Token | Light | Dark | Role |
|---|---|---|---|
| canvas | #FFF6E8 ivory | #1C1612 | page |
| raised | #FFFCF7 | #261E19 | figure plates, popovers |
| sunken | #F6EAD7 | #15100D | table headers, code, inputs |
| oat | #E8D7BF | #3A2F28 | decorative fills, low heatmap cells, hairlines |
| text | #29201B charcoal | #FFF6E8 | primary text (14.9:1 / 16.7:1) |
| text-2 | #5F4F45 | #CFBDA8 | secondary text (>= 6.5:1 on every surface) |
| border-strong | #8A7560 | #7D6A59 | control boundaries (>= 3:1) |
| action | #5A171B burgundy, ivory text (12.5:1) | #E8D7BF, charcoal text (11.3:1) | primary buttons, current nav |
| pen | #A6422A terracotta | #E08A6E | the referee mark, links |
| focus | 2 px text-coloured outline + 2 px canvas offset | same | keyboard focus on any surface |
| success | #4F5236 olive | #B4B78A | passed checks (always with icon + word) |
| warning | #7A5410 | #E3B65E | warnings (icon + word) |
| danger | #9A2E20 | #EC8F7B | failures (icon + word) |
| series | trend #5A171B solid, meanrev #A6422A long-dash, breakout #646548 dot-dash, buy-and-hold text colour dashed, cash #8A7560 dotted | lightened equivalents | every series also has a distinct dash pattern and a direct end label |

All listed text pairs were computed at >= 4.5:1 and all non-text boundaries at >= 3:1 on canvas,
raised and sunken. Meaning is never carried by colour alone.

## Type

- **Newsreader Variable** (optical sizes 6 to 72): headlines, prose, verdicts. Headline set at
  large optical size, regular weight, tight leading; prose 17 px / 1.6 with a 68ch measure.
- **IBM Plex Sans Condensed**: every number, table, axis, control and label, with tabular
  figures. Condensed width is what lets the ledger and comparison stay dense on a phone.
- No all-caps labels, no tracked-out eyebrows, no monospace label face, no single-word
  accent colouring, no middle-dot meta strings, no arrows appended to link text.
- Scale (px): 13, 15, 17, 21, 27, 36, 52 (desktop headline 52, mobile 34).

## Layout

- Desktop 1440: masthead; left "Contents" rail (sticky, 200 px) that tracks the current section;
  report column on a 12-column grid, prose max 68ch, figures may span the full column; margin
  notes sit in a right gutter beside the verdict.
- Tablet 768: rail becomes a sticky "Contents" disclosure under the masthead; figures full width;
  margin notes become indented notes under each struck strategy.
- Mobile 390: compact masthead with a menu button; comparison table becomes one definition
  block per strategy; ledger rows become two-line entries with expandable detail; charts get a
  taller aspect ratio and the legend moves below as toggle buttons.
- Left aligned throughout. Surfaces: radius 4 px on controls, 10 px on figure plates, none on
  tables. No drop shadows except a faint one on popovers. A barely visible paper grain on the
  canvas (static SVG noise, 3 % opacity, removed in forced-colors mode).

## Motion (all from the brief; durations in ms)

| Moment | Treatment | Duration |
|---|---|---|
| Page entry (once per load) | headline lines rise 8 px and fade in, then each rejection strike draws left to right, then margin notes fade in | 240 + 60 stagger; strike 420; total under 1 s |
| Chart series change | new path draws in (stroke-dashoffset), old fades out | 360 in, 180 out |
| Drawdown toggle | area grows from the zero line (scaleY) | 280 |
| Expand / collapse | grid-row 0fr to 1fr height transition, chevron rotates | 220 open, 160 close |
| Nav state | current-section indicator slides along the rail (transform) | 200 |
| Controls | press scale 0.98, background ease | 120 |

Easing: decelerate `cubic-bezier(.2,.7,.2,1)` for arrivals, accelerate `cubic-bezier(.4,0,1,1)`
for exits. Reduced motion: every duration becomes 0 and draw-ins render final state. Content is
never hidden waiting for animation; no scroll hijacking, no intro screen, no perpetual
background motion, no hover-only controls.

## States (every data view)

loading (skeleton matching final layout), empty ("No completed runs yet" + how to request one),
error (what failed, which file, Retry), stale (snapshot older than 14 days: banner with age +
Refresh), fixture (CI fixture data notice), success. Live, cached, simulated and unavailable
capabilities are labelled where they appear.
