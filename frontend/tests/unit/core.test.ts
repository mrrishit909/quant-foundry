import { describe, expect, it } from "vitest";
import { parseCsv } from "../../src/data/csv";
import { isStale } from "../../src/data/snapshot";
import type { Snapshot, Trade, WalkForward } from "../../src/data/types";
import { chainedOos, repriceCosts } from "../../src/lib/costs";
import { parseRoute, routeHref, type Route } from "../../src/routing";

describe("parseCsv", () => {
  it("handles quoted fields with commas and doubled quotes", () => {
    const rows = parseCsv('a,b\n1,"{""x"":1,""y"":2}"\r\n2,plain\n');
    expect(rows).toEqual([
      { a: "1", b: '{"x":1,"y":2}' },
      { a: "2", b: "plain" },
    ]);
  });
});

describe("routing", () => {
  const routes: Route[] = [
    { view: "overview" },
    { view: "overview", runId: "qf-1" },
    { view: "strategy", runId: "qf-1", strategyId: "trend" },
    { view: "runs" },
    { view: "compare", a: "x", b: "y" },
    { view: "request" },
    { view: "about" },
  ];
  it.each(routes)("round-trips %o", (r) => {
    expect(parseRoute(routeHref(r))).toEqual(r);
  });
  it("falls back to the overview for unknown paths", () => {
    expect(parseRoute("#/nope/really")).toEqual({ view: "overview" });
  });
});

describe("staleness", () => {
  const snap = { generated_at: "2026-10-01T00:00:00Z", stale_after_hours: 336 } as Snapshot;
  it("is fresh inside the window and stale after it", () => {
    expect(isStale(snap, Date.parse("2026-10-10T00:00:00Z"))).toBe(false);
    expect(isStale(snap, Date.parse("2026-10-20T00:00:00Z"))).toBe(true);
  });
});

describe("cost re-pricing", () => {
  const trades: Trade[] = [
    { date: "2020-01-02", strategy: "trend", symbol: "A", side: "buy", qty: 100, ref_open: 100, fill_price: 100.05, fee: 1, slippage_cost: 5, segment: "out_of_sample", window: "0" },
    { date: "2021-01-02", strategy: "trend", symbol: "A", side: "sell", qty: 100, ref_open: 110, fill_price: 109.95, fee: 1.1, slippage_cost: 5.5, segment: "holdout", window: "holdout" },
  ];
  const walk = { windows: [], strategies: { trend: [{ window: 0, chosen_params: {}, in_sample: {}, out_of_sample: { total_return: 0.1 } }] } } as unknown as WalkForward;
  it("reproduces the published returns at the run's own costs", () => {
    const est = repriceCosts(trades, walk, "trend", 0.05, 1, 5, 100_000);
    expect(est.oosReturn).toBeCloseTo(chainedOos(walk, "trend"), 10);
    expect(est.holdoutReturn).toBeCloseTo(0.05, 10);
  });
  it("lowers returns when costs rise", () => {
    const est = repriceCosts(trades, walk, "trend", 0.05, 10, 50, 100_000);
    expect(est.oosReturn).toBeLessThan(0.1);
    expect(est.holdoutReturn).toBeLessThan(0.05);
  });
});
