# Portfolio integration

Three ways to show Quant Foundry inside another site. All read the same public snapshot; none
needs a token.

## 1. Link (simplest)

Use `portfolio-manifest.json` for the card: name, description, live URL, preview image, tags,
capabilities and limitations. Deep links work: `#/runs/<run_id>`, `#/runs/<run_id>/strategy/trend`,
`#/runs`, `#/request`, `#/about`.

## 2. Iframe

```html
<iframe src="https://mrrishit909.github.io/quant-foundry/#/" title="Quant Foundry research lab"
        style="width:100%;height:80vh;border:0" loading="lazy"></iframe>
```

The app is fully self-contained; its theme follows the visitor's system setting.

## 3. Embedded component

The Pages site also serves an ES module build with React kept external:

- `https://mrrishit909.github.io/quant-foundry/lib/quant-foundry.js`
- `https://mrrishit909.github.io/quant-foundry/lib/quant-foundry.css`

```tsx
import "https://mrrishit909.github.io/quant-foundry/lib/quant-foundry.css";
import { QuantFoundryApp } from "quant-foundry"; // or the URL above, with react/react-dom provided by the host

<QuantFoundryApp
  dataUrl="https://mrrishit909.github.io/quant-foundry/data/"
  showShell={false}       // host supplies header and footer
  routing="memory"        // never reads or writes the host's URL
  theme="auto"            // "light" | "dark" | "auto"
/>;
```

Or without React in the host page's own code: `mount(element, config)` returns an unmount
function.

| Config | Default | Meaning |
|---|---|---|
| `basePath` | build base | where the standalone site lives |
| `dataUrl` | `<basePath>data/` | snapshot directory (must allow CORS; GitHub Pages does) |
| `theme` | `auto` | colour theme |
| `showShell` | `true` | render the app's own masthead and footer |
| `routing` | `hash` | `memory` for embedding |

Isolation: every CSS rule is scoped under `.qf-root` and tokens are defined on that element, not
`:root`. Listeners (hashchange in hash mode, media queries, resize and intersection observers) are
registered in React effects and removed on unmount. Inertial scrolling (Lenis) and the
pointer flourishes attach only when the app owns the page (`showShell` with hash routing), so an
embedding host keeps its own scroll; GSAP motion is scoped to the app's elements and honours
reduced motion. Fonts are loaded only by the standalone site;
an embedded copy uses the host's fonts or the stylesheet's serif and condensed fallbacks.
