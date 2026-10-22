# Design contract: Quant Foundry

The transferable design rules for this site. Graders and repair workers read this file; it
contains no private preferences or credentials.

## Character

A **kinetic editorial research note**: a broadsheet front page that happens to be a backtest. Bone
paper, ink and one vermilion pen. The first viewport is a full-bleed headline set in a huge
variable serif ("Three strategies tested. None survived."), with the run's own equity curves drawn
faint behind it. The site's one bold move is still the **referee's verdict**: every strategy is
listed at display size and rejected strategies carry a hand-drawn vermilion strike with the reason
in the margin, because in this lab rejection is the expected, honest outcome.

Second motif: the **sealed holdout**. Wherever time is plotted, the holdout span is a hatched
band labelled "Holdout, evaluated once"; it is never mixed with development data.

Third motif: **numbered chapters**. The report reads as nine numbered chapters (italic vermilion
numerals, ink rule above each). The evidence chapter (equity) is an inverted ink band that bleeds
to the right edge and opens like a curtain.

Redesigned 2026-10-22 at the owner's request, following the "Kinetic Editorial" direction
(asymmetric editorial grid, ultra-large variable serif, masked text reveals, magnetic actions,
curtain section transitions, inertial scroll).

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

| Token | Light (bone) | Dark (ink) | Role |
|---|---|---|---|
| canvas | #EDE7DC | #0F0E0C | page |
| raised | #F6F2EA | #191714 | figure plates |
| sunken | #E2DACB | #080706 | table headers, inputs |
| oat | #D3C8B5 | #2C2823 | hairlines, low heatmap cells |
| text | #15130F ink | #EDE7DC | primary text |
| text-2 | #514A40 | #B3AA9B | secondary text and micro labels |
| border-strong | #7E7262 | #7A7062 | control boundaries (>= 3:1) |
| action | ink, bone text | bone, ink text | primary buttons, segmented thumb |
| pen | #A82E17 vermilion | #FF7052 | the referee mark, chapter numerals, links, the verdict line |
| success / warning / danger | #48502E / #74500C / #A82E17 | #B5BC8C / #E3B65E / #FF8366 | always with icon + word |
| series | trend pen solid, meanrev umber long-dash, breakout slate dot-dash, buy-and-hold ink dashed, cash grey dotted | lightened equivalents | every series also has a dash pattern and a direct end label |

`.qf-invert` swaps the two token sets locally (light theme: an ink band; dark theme: a bone band).
Text pairs are >= 4.5:1 and non-text boundaries >= 3:1 in both sets; axe runs in both themes.

## Type

- **Fraunces Variable** (optical size 9 to 144, OFL): display at opsz 144 with negative tracking
  (hero 56 to 184 px, chapter titles 30 to 58 px, strategy names 30 to 76 px), prose at opsz 14,
  18 px / 1.6, 64ch measure. The verdict line and chapter numerals use the italic.
- **IBM Plex Sans Condensed**: every number, table, axis and control, with tabular figures, plus
  uppercase micro labels (11 to 12 px, 0.14 to 0.18em tracking) for metadata, table headers and nav.
- Two families only. Headings scale with clamp(); hero and outro wrap safely at 390 px.

## Layout

- Desktop 1440: masthead (wordmark + uppercase nav, hides while reading down, returns on scroll up
  or keyboard focus). Full-width hero: metadata strip, headline, then a 7/5 split of prose and
  actions against four counted figures. The referee's verdict as full-width ruled rows
  (number, struck name, margin note). Then a 200 px sticky "In this note" rail with numbered
  entries beside the chapters. Footer ends in an oversized "Quant Foundry" wordmark.
- Tablet 768: rail becomes a "Jump to a section" disclosure; hero foot stacks; margin notes sit
  under each struck name; the ink band bleeds to both edges.
- Mobile 390: menu button; two-column metadata; headline 50 to 60 px; stats in a 2 x 2 grid; tables
  become definition blocks; chart legend wraps as toggle buttons.
- Plates are crisp (3 px radius) with a cursor-lit border on fine pointers; buttons are pills.
  Paper grain overlay at 5 % (removed in forced-colors mode).

## Motion (GSAP + ScrollTrigger + SplitText, Lenis on the standalone site only)

| Layer | Treatment |
|---|---|
| Intro (once per load) | hero headline characters rise out of line masks (about 1 s), equity curves draw behind it, metadata and copy follow, the four figures count up |
| Navigation | masthead hides on scroll down and returns on scroll up; nav underline slides; on in-app navigation the view's headline rises out of a mask and the body eases in |
| Scroll storytelling | hero curves drift with scroll; chapter numerals parallax; each chapter title reveals line by line; the ink evidence band opens like a curtain; walk-forward bars grow; checklists slide in |
| Component interaction | magnetic primary actions; cursor-lit plate borders; legend toggles; pill buttons invert on hover |
| Data transitions | series draw in on toggle, drawdown grows from zero, cost estimates recompute live, figures count up |
| Microinteractions | press scale, link underline weight, chevron rotation, rail marker slide |

Rules: every tween is registered under `gsap.matchMedia("(prefers-reduced-motion: no-preference)")`
so reduced motion reverts it live and shows final states; scroll reveals use
`immediateRender: false` so content is never hidden while waiting for a trigger; cursor effects
only on fine pointers and never gate content; Lenis and pointer effects attach only when the app
owns the page (standalone, hash routing), never inside an embedding host.

## States (every data view)

loading (skeleton matching final layout), empty ("No completed runs yet" + how to request one),
error (what failed, which file, Retry), stale (snapshot older than 14 days: banner with age +
Refresh), fixture (CI fixture data notice), success. Live, cached, simulated and unavailable
capabilities are labelled where they appear.
