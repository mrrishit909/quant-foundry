import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const EVIDENCE = process.env.E2E_EVIDENCE_DIR ?? "../evidence/e2e";
const SCREENS = join(EVIDENCE, "screens");
mkdirSync(SCREENS, { recursive: true });

async function shot(page: Page, name: string, fullPage = true) {
  const project = test.info().project.name;
  await page.screenshot({ path: join(SCREENS, `${project}-${name}.jpg`), type: "jpeg", quality: 70, fullPage });
}

/** Fails the test on console errors, uncaught exceptions and failed same-origin requests. */
function watch(page: Page) {
  const problems: string[] = [];
  page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("response", (r) => {
    const url = new URL(r.url());
    if (r.status() >= 400 && url.origin === new URL(page.url() || r.url()).origin) problems.push(`HTTP ${r.status()} ${url.pathname}`);
  });
  return problems;
}

async function latestRunId(page: Page): Promise<string> {
  const res = await page.request.get("data/snapshot.json");
  return (await res.json()).latest_run_id;
}

async function noOverflow(page: Page) {
  const [scroll, inner] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(scroll, "page must not scroll horizontally").toBeLessThanOrEqual(inner + 1);
}

async function axe(page: Page) {
  // @axe-core/playwright is typed against its own Playwright Page version; the runtime object is the same.
  const results = await new AxeBuilder({ page: page as never }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  // Name every failing element and axe's reason so a CI-only failure can be diagnosed from the log alone.
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} (${(n.failureSummary ?? "").replace(/\s+/g, " ").slice(0, 160)})`).join("; ")}`)).toEqual([]);
}

test("report: verdict, chart, comparison, no overflow, accessible", async ({ page }) => {
  const problems = watch(page);
  await page.goto("./");
  await expect(page.locator("h1")).toContainText("tested.");
  await expect(page.getByRole("group", { name: /Portfolio value/ }).first()).toBeVisible();
  const wide = (page.viewportSize()?.width ?? 0) > 720;
  if (wide) await expect(page.getByRole("table", { name: /Strategy comparison/ })).toBeVisible();
  else await expect(page.getByRole("list", { name: "Strategy comparison" })).toBeVisible();
  await page.waitForTimeout(1200); // let the one entry sequence finish before capturing
  await noOverflow(page);
  await axe(page);
  await shot(page, "report");
  await shot(page, "report-first-viewport", false);
  expect(problems).toEqual([]);
});

test("deep link: strategy dossier, ledger filter and pagination, parameter explorer", async ({ page }) => {
  const problems = watch(page);
  const id = await latestRunId(page);
  await page.goto(`./#/runs/${id}/strategy/trend`);
  await expect(page.locator("h1")).toHaveText(/Trend following/);
  const count = page.getByText(/fills, .* in fees and slippage/);
  const before = await count.textContent();
  await page.getByLabel("Segment").selectOption("holdout");
  await expect(count).not.toHaveText(before ?? "");
  await page.getByLabel("Segment").selectOption("all");
  const next = page.getByRole("button", { name: "Next page" });
  if (await next.isEnabled()) {
    await next.click();
    await expect(page.getByText(/Page 2 of/)).toBeVisible();
  }
  const cell = page.locator(".qf-heat-cell").first();
  await cell.click();
  await expect(cell).toHaveAttribute("aria-pressed", "true");
  await noOverflow(page);
  await axe(page);
  await shot(page, "strategy");
  expect(problems).toEqual([]);
});

test("chart: legend toggles a series and the keyboard crosshair reads values", async ({ page }) => {
  await page.goto("./");
  const legend = page.getByRole("group", { name: "Series shown on the chart" }).first();
  const button = legend.getByRole("button", { name: "Cash" });
  const chart = page.getByRole("group", { name: /Portfolio value/ }).first();
  const paths = chart.locator("path.qf-series");
  await expect(paths).not.toHaveCount(0); // the chart draws after its width is measured
  const n = await paths.count();
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "false");
  await expect(paths).toHaveCount(n - 2); // equity and drawdown lines both disappear
  await chart.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator(".qf-readout").first()).toContainText(/\d{4}/);
});

test("controls: disclosure expands, cost sliders recompute, reset restores", async ({ page }) => {
  await page.goto("./");
  const disclosure = page.getByRole("button", { name: /Show the values as a table/ }).first();
  await disclosure.click();
  await expect(disclosure).toHaveAttribute("aria-expanded", "true");
  const fee = page.getByLabel(/^Fee:/);
  const cell = page.getByRole("table", { name: "Estimated returns at the chosen costs" }).locator("tbody tr").first().locator("td").nth(1);
  const original = await cell.textContent();
  await fee.fill("40");
  await expect(cell).not.toHaveText(original ?? "");
  await page.getByRole("button", { name: "Reset to the run's costs" }).click();
  await expect(cell).toHaveText(original ?? "");
});

test("navigation: current page state, runs ledger, back button, request link", async ({ page }) => {
  const preview = await page.request.get("./preview.jpg");
  expect(preview.status(), "portfolio preview image (portfolio-manifest.json preview_image)").toBe(200);
  const problems = watch(page);
  await page.goto("./");
  const wide = (page.viewportSize()?.width ?? 0) > 900; // the primary nav moves into a menu below 900 px
  if (!wide) {
    await page.getByRole("button", { name: "Menu" }).click();
    await shot(page, "menu-open", false);
  }
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Runs" }).click();
  await expect(page).toHaveURL(/#\/runs$/);
  // The mobile menu closes after navigating, so check the attribute without requiring visibility.
  await expect(page.locator('#qf-primary-nav a[aria-current="page"]')).toHaveText("Runs");
  await expect(page.locator("h1")).toContainText("Every run");
  await noOverflow(page);
  await shot(page, "runs");
  await page.goBack();
  await expect(page.locator("h1")).toContainText("tested.");
  await page.goto("./#/request");
  const form = page.getByRole("link", { name: /Open the run request form/ });
  await expect(form).toHaveAttribute("href", /\/issues\/new\?template=run-request\.yml$/);
  await noOverflow(page);
  await axe(page);
  await shot(page, "request");
  await page.goto("./#/about");
  await expect(page.locator("h1")).toContainText("Method");
  await noOverflow(page);
  expect(problems).toEqual([]);
});

test("dark theme: report and request pages stay accessible", async ({ page }) => {
  await page.goto("./");
  await page.getByRole("group", { name: "Colour theme" }).getByRole("button", { name: "Dark" }).click();
  await page.waitForTimeout(500); // theme transitions settle before the audit
  await expect(page.locator(".qf-root")).toHaveAttribute("data-theme", "dark");
  await axe(page);
  await shot(page, "dark", false);
  await page.goto("./#/request");
  await axe(page);
  // axe reports identical text and background colours as incomplete, not as a violation; check the primary action directly.
  const [fg, bg] = await page.locator(".qf-btn-primary").first().evaluate((el) => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]);
  expect(fg).not.toBe(bg);
});

test("keyboard: skip link and visible focus", async ({ page }) => {
  await page.goto("./");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Tab");
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement as Element).outlineStyle);
  expect(outline).not.toBe("none");
  await shot(page, "keyboard-focus", false);
});

test("reduced motion: no running animations and content fully visible", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("./");
  await expect(page.locator("h1")).toContainText("tested.");
  const running = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === "running").length);
  expect(running).toBe(0);
  const opacity = await page.locator(".qf-margin-note").first().evaluate((el) => getComputedStyle(el).opacity);
  expect(Number(opacity)).toBe(1);
  await shot(page, "reduced-motion", false);
});

test("states: loading, empty, error with retry, stale", async ({ page }) => {
  // Loading: hold the snapshot request so the skeleton is visible.
  let release: () => void = () => {};
  const gate = new Promise<void>((r) => (release = r));
  await page.route("**/data/snapshot.json", async (route) => {
    await gate;
    await route.continue();
  });
  await page.goto("./");
  await expect(page.getByRole("status").filter({ hasText: "Loading" })).toBeVisible();
  await shot(page, "state-loading", false);
  release();
  await expect(page.locator("h1")).toContainText("tested.");
  await page.unroute("**/data/snapshot.json");

  // Empty.
  await page.route("**/data/snapshot.json", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    await route.fulfill({ response: res, json: { ...body, latest_run_id: null, runs_included: [] } });
  });
  await page.goto("./?empty");
  await expect(page.locator("h1")).toHaveText("No completed runs yet.");
  await shot(page, "state-empty", false);
  await page.unroute("**/data/snapshot.json");

  // Error, then retry succeeds.
  let fail = true;
  await page.route("**/data/snapshot.json", async (route) => {
    if (fail) await route.fulfill({ status: 503, body: "unavailable" });
    else await route.continue();
  });
  await page.goto("./?error");
  await expect(page.getByRole("alert")).toContainText("The server answered 503");
  await shot(page, "state-error", false);
  fail = false;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.locator("h1")).toContainText("tested.");
  await page.unroute("**/data/snapshot.json");

  // Stale.
  await page.route("**/data/snapshot.json", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    await route.fulfill({ response: res, json: { ...body, generated_at: "2025-01-01T00:00:00Z" } });
  });
  await page.goto("./?stale");
  await expect(page.getByText(/older than its 14-day freshness window/)).toBeVisible();
  await shot(page, "state-stale", false);
});

test("compare: two runs side by side, or an explanation when only one exists", async ({ page }) => {
  await page.goto("./#/compare");
  await expect(page.locator("h1")).toContainText(/Two runs, side by side|Comparison needs two completed runs/);
  await noOverflow(page);
});
