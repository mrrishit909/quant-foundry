import type { Trade, WalkForward } from "../data/types";

export interface CostEstimate {
  oosReturn: number;
  holdoutReturn: number;
  costDelta: number;
}

/**
 * First-order cost sensitivity, computed in the browser from the published trade ledger.
 *
 * Every trade is held fixed and re-priced: fee = notional * fee_bps and slippage =
 * qty * reference open * slippage_bps. Each walk-forward window and the holdout started from
 * `initialCash`, so the change in costs is converted to a change in that window's return and
 * the out-of-sample windows are re-chained. It ignores how different costs would have changed
 * share counts and cash constraints, so it is an estimate, never a re-run.
 */
export function repriceCosts(
  trades: Trade[],
  walk: WalkForward,
  strategy: string,
  holdoutReturn: number,
  feeBps: number,
  slipBps: number,
  initialCash: number,
): CostEstimate {
  const deltaByWindow = new Map<string, number>();
  let holdoutDelta = 0;
  let total = 0;
  for (const t of trades) {
    if (t.strategy !== strategy) continue;
    const notional = Math.abs(t.qty * t.ref_open);
    const newCost = (notional * feeBps) / 1e4 + (notional * slipBps) / 1e4;
    const delta = newCost - (t.fee + t.slippage_cost);
    total += delta;
    if (t.segment === "holdout") holdoutDelta += delta;
    else deltaByWindow.set(t.window, (deltaByWindow.get(t.window) ?? 0) + delta);
  }
  let growth = 1;
  for (const w of walk.strategies[strategy] ?? []) {
    const r = w.out_of_sample.total_return - (deltaByWindow.get(String(w.window)) ?? 0) / initialCash;
    growth *= 1 + r;
  }
  return { oosReturn: growth - 1, holdoutReturn: holdoutReturn - holdoutDelta / initialCash, costDelta: total };
}

/** Chain the published per-window returns (used to check the estimator reproduces the original). */
export function chainedOos(walk: WalkForward, strategy: string): number {
  return (walk.strategies[strategy] ?? []).reduce((g, w) => g * (1 + w.out_of_sample.total_return), 1) - 1;
}
