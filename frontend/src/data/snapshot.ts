import { useCallback, useEffect, useRef, useState } from "react";
import { num, parseCsv } from "./csv";
import { fetchJson, fetchText, LoadError } from "./load";
import type { EquityRow, IndexEntry, Release, RunBundle, Snapshot, Trade } from "./types";

export type LoadState<T> =
  | { status: "loading" }
  | { status: "error"; error: LoadError | Error }
  | { status: "empty" }
  | { status: "ready"; data: T; stale: boolean };

export interface SiteData {
  snapshot: Snapshot;
  index: IndexEntry[];
  release: Release | null;
}

export function isStale(snapshot: Snapshot, now = Date.now()): boolean {
  const generated = Date.parse(snapshot.generated_at);
  return Number.isFinite(generated) && now - generated > snapshot.stale_after_hours * 3600_000;
}

async function optional<T>(url: string, signal: AbortSignal): Promise<T | null> {
  try {
    return await fetchJson<T>(url, signal);
  } catch (err) {
    if (err instanceof LoadError && err.status === 404) return null;
    throw err;
  }
}

/** Loads snapshot + run index. `reload()` refetches without a page reload. */
export function useSiteData(dataUrl: string): { state: LoadState<SiteData>; reload: () => void } {
  const [state, setState] = useState<LoadState<SiteData>>({ status: "loading" });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const ctrl = new AbortController();
    setState({ status: "loading" });
    (async () => {
      try {
        const snapshot = await fetchJson<Snapshot>(`${dataUrl}snapshot.json`, ctrl.signal);
        const index = await fetchJson<{ runs: IndexEntry[] }>(`${dataUrl}index.json`, ctrl.signal);
        // Only fetch optional files the snapshot says exist (static hosts may answer anything with 200).
        const release = snapshot.files?.release ? await optional<Release>(`${dataUrl}release.json`, ctrl.signal) : null;
        if (!snapshot.latest_run_id) {
          setState({ status: "empty" });
          return;
        }
        setState({ status: "ready", data: { snapshot, index: index.runs, release }, stale: isStale(snapshot) });
      } catch (err) {
        if (!ctrl.signal.aborted) setState({ status: "error", error: err as Error });
      }
    })();
    return () => ctrl.abort();
  }, [dataUrl, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { state, reload };
}

export function parseEquity(text: string): EquityRow[] {
  return parseCsv(text).map((row) => {
    const { date = "", segment = "", ...rest } = row;
    const values: Record<string, number> = {};
    for (const [key, value] of Object.entries(rest)) values[key] = num(value);
    return { date, segment: segment as EquityRow["segment"], values };
  });
}

export function parseTrades(text: string): Trade[] {
  return parseCsv(text).map((r) => ({
    date: r.date ?? "",
    strategy: r.strategy ?? "",
    symbol: r.symbol ?? "",
    side: (r.side ?? "buy") as Trade["side"],
    qty: num(r.qty),
    ref_open: num(r.ref_open),
    fill_price: num(r.fill_price),
    fee: num(r.fee),
    slippage_cost: num(r.slippage_cost),
    segment: r.segment ?? "",
    window: r.window ?? "",
  }));
}

export async function loadRun(dataUrl: string, runId: string, signal: AbortSignal): Promise<RunBundle> {
  const base = `${dataUrl}runs/${encodeURIComponent(runId)}/`;
  const j = <T,>(name: string) => fetchJson<T>(base + name, signal);
  const [record, manifest, results, walkforward, sensitivity, holdout, quality, assumptions, strategies, checks] =
    await Promise.all([
      j<RunBundle["record"]>("run.json"),
      j<RunBundle["manifest"]>("manifest.json"),
      j<RunBundle["results"]>("results.json"),
      j<RunBundle["walkforward"]>("walkforward.json"),
      j<RunBundle["sensitivity"]>("sensitivity.json"),
      j<RunBundle["holdout"]>("holdout.json"),
      j<RunBundle["quality"]>("data_quality.json"),
      j<RunBundle["assumptions"]>("assumptions.json"),
      j<{ strategies: RunBundle["strategies"] }>("strategies.json"),
      j<RunBundle["checks"]>("checks.json"),
    ]);
  const hasAudit = record.result_paths.some((p) => p.endsWith("/holdout_audit.json"));
  const [equityText, tradesText, audit] = await Promise.all([
    fetchText(base + "equity.csv", signal),
    fetchText(base + "trades.csv", signal),
    hasAudit ? optional<RunBundle["audit"]>(base + "holdout_audit.json", signal) : Promise.resolve(null),
  ]);
  return {
    record, manifest, results, walkforward, sensitivity, holdout, quality, assumptions,
    strategies: strategies.strategies, checks, audit,
    equity: parseEquity(equityText), trades: parseTrades(tradesText), reportUrl: base + "report.md",
  };
}

/** Per-run loader with an in-memory cache (cleared on reload; never persisted). */
export function useRun(dataUrl: string, runId: string | null, tick: number): LoadState<RunBundle> {
  const cache = useRef(new Map<string, RunBundle>());
  const [state, setState] = useState<LoadState<RunBundle>>({ status: "loading" });
  useEffect(() => {
    cache.current.clear();
  }, [tick]);
  useEffect(() => {
    if (!runId) {
      setState({ status: "empty" });
      return;
    }
    const hit = cache.current.get(runId);
    if (hit) {
      setState({ status: "ready", data: hit, stale: false });
      return;
    }
    const ctrl = new AbortController();
    setState({ status: "loading" });
    loadRun(dataUrl, runId, ctrl.signal).then(
      (bundle) => {
        cache.current.set(runId, bundle);
        setState({ status: "ready", data: bundle, stale: false });
      },
      (err) => {
        if (!ctrl.signal.aborted) setState({ status: "error", error: err as Error });
      },
    );
    return () => ctrl.abort();
  }, [dataUrl, runId, tick]);
  return state;
}
