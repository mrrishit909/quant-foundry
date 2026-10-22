import { useEffect, useState } from "react";
import { EquityChart, SERIES } from "../charts/EquityChart";
import { ErrorState, LoadingState } from "../components/Controls";
import type { AppConfig } from "../config";
import { loadRun, type SiteData } from "../data/snapshot";
import type { IndexEntry, RunBundle } from "../data/types";
import { day, fixed, signedPct, timestamp } from "../lib/format";
import { type Route, routeHref } from "../routing";

const STATUS_TONE: Record<IndexEntry["status"], string> = {
  completed: "qf-tone-success",
  failed: "qf-tone-danger",
  blocked: "qf-tone-warning",
  cancelled: "qf-tone-muted",
  running: "qf-tone-muted",
  queued: "qf-tone-muted",
};

export function RunsView({ site, config }: { site: SiteData; config: AppConfig }) {
  const included = new Set(site.snapshot.runs_included);
  const completed = site.index.filter((r) => r.status === "completed" && included.has(r.run_id));
  return (
    <div style={{ display: "grid", gap: 40, maxWidth: 1160 }}>
      <header style={{ display: "grid", gap: 12 }}>
        <h1 className="qf-h1">Every run, including the failures.</h1>
        <p className="qf-prose">
          The ledger below lists every recorded attempt. Failed, blocked and cancelled runs stay listed with their
          reasons. The {completed.length} most recent completed runs are included in this site's snapshot; older
          results remain on the state branch.
        </p>
        {completed.length >= 2 && (
          <p>
            <a className="qf-btn qf-btn-primary" href={routeHref({ view: "compare", a: completed[1]!.run_id, b: completed[0]!.run_id })}>
              Compare the two latest completed runs
            </a>
          </p>
        )}
      </header>
      <ol style={{ listStyle: "none", display: "grid" }} aria-label="Run ledger, newest first">
        {site.index.map((r) => (
          <li key={r.run_id} className="qf-card" style={{ padding: "14px 0", gap: 6 }}>
            <div className="qf-toolbar" style={{ justifyContent: "space-between" }}>
              {included.has(r.run_id) ? (
                <a className="qf-h3 qf-wrap-anywhere" href={routeHref({ view: "overview", runId: r.run_id })}>{r.run_id}</a>
              ) : (
                <span className="qf-h3 qf-wrap-anywhere">{r.run_id}</span>
              )}
              <span className={`qf-chip ${STATUS_TONE[r.status]}`}>{r.status}</span>
            </div>
            <p className="qf-small">
              Attempt {r.attempt}, created {timestamp(r.created_at)}, source {r.source}
              {r.issue ? <> from <a href={`${config.repoUrl}/issues/${r.issue}`}>issue #{r.issue}</a></> : null}
              {!included.has(r.run_id) && r.status === "completed" ? (
                <> (results on the <a href={`${config.repoUrl}/tree/state/runs/${r.run_id}`}>state branch</a>)</>
              ) : null}
            </p>
            {r.headline && <p className="qf-prose" style={{ fontSize: 16 }}>{r.headline}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function usePair(dataUrl: string, a?: string, b?: string) {
  const [state, setState] = useState<{ status: "loading" | "error" | "ready"; runs?: [RunBundle, RunBundle]; error?: Error }>({ status: "loading" });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!a || !b) return;
    const ctrl = new AbortController();
    setState({ status: "loading" });
    Promise.all([loadRun(dataUrl, a, ctrl.signal), loadRun(dataUrl, b, ctrl.signal)]).then(
      (runs) => setState({ status: "ready", runs }),
      (error) => !ctrl.signal.aborted && setState({ status: "error", error }),
    );
    return () => ctrl.abort();
  }, [dataUrl, a, b, tick]);
  return { state, retry: () => setTick((t) => t + 1) };
}

export function CompareView({ site, config, a, b, navigate }: {
  site: SiteData; config: AppConfig; a?: string; b?: string; navigate: (r: Route) => void;
}) {
  const options = site.index.filter((r) => r.status === "completed" && site.snapshot.runs_included.includes(r.run_id));
  const left = a ?? options[1]?.run_id;
  const right = b ?? options[0]?.run_id;
  const { state, retry } = usePair(config.dataUrl, left, right);
  const [strategy, setStrategy] = useState("trend");
  const go = (x?: string, y?: string) => navigate({ view: "compare", a: x, b: y });
  if (options.length < 2) {
    return (
      <div className="qf-state">
        <h1 className="qf-h1">Comparison needs two completed runs.</h1>
        <p className="qf-prose">This snapshot holds {options.length}. A comparison appears here once another run completes.</p>
      </div>
    );
  }
  return (
    <div style={{ display: "grid", gap: 36, maxWidth: 1160 }}>
      <header style={{ display: "grid", gap: 16 }}>
        <h1 className="qf-h1">Two runs, side by side.</h1>
        <div className="qf-grid-2">
          {[["qf-cmp-a", "First run", left, (v: string) => go(v, right)], ["qf-cmp-b", "Second run", right, (v: string) => go(left, v)]].map(([id, label, value, onChange]) => (
            <div key={id as string} className="qf-field">
              <label htmlFor={id as string}>{label as string}</label>
              <select id={id as string} value={value as string} onChange={(e) => (onChange as (v: string) => void)(e.target.value)}>
                {options.map((o) => <option key={o.run_id} value={o.run_id}>{o.run_id}</option>)}
              </select>
            </div>
          ))}
        </div>
      </header>
      {state.status === "loading" && <LoadingState what="both runs" />}
      {state.status === "error" && <ErrorState title="One of the runs could not be loaded" error={state.error!} onRetry={retry} />}
      {state.status === "ready" && state.runs && (() => {
        const [ra, rb] = state.runs;
        const pa = ra.manifest.params;
        const pb = rb.manifest.params;
        const diffs = [
          ["Seed", pa.dataset.seed, pb.dataset.seed],
          ["Symbols", pa.dataset.symbols, pb.dataset.symbols],
          ["Trading days", pa.dataset.days, pb.dataset.days],
          ["Regimes", pa.dataset.regime_mix, pb.dataset.regime_mix],
          ["Fee bps", pa.costs.fee_bps, pb.costs.fee_bps],
          ["Slippage bps", pa.costs.slippage_bps, pb.costs.slippage_bps],
          ["Train / test days", `${pa.walk_forward.train_days} / ${pa.walk_forward.test_days}`, `${pb.walk_forward.train_days} / ${pb.walk_forward.test_days}`],
          ["Holdout", pa.holdout_fraction, pb.holdout_fraction],
        ];
        const ids = [...new Set([...ra.results.strategies, ...rb.results.strategies].map((s) => s.id))];
        const same = ra.manifest.dataset.sha256 === rb.manifest.dataset.sha256;
        const merged = ra.equity.length === rb.equity.length && same
          ? ra.equity.map((row, i) => ({ ...row, values: { first: row.values[strategy] ?? NaN, second: rb.equity[i]?.values[strategy] ?? NaN } }))
          : null;
        return (
          <>
            <section className="qf-section" aria-labelledby="qf-cmp-params">
              <h2 className="qf-h2" id="qf-cmp-params">What differed</h2>
              <div className="qf-table-wrap" tabIndex={0} role="region" aria-label="Table, scrolls sideways when narrow">
                <table className="qf-table">
                  <thead><tr><th scope="col">Setting</th><th scope="col">First</th><th scope="col">Second</th></tr></thead>
                  <tbody>
                    {diffs.map(([k, x, y]) => (
                      <tr key={k as string}><th scope="row" style={{ fontWeight: 400 }}>{k}</th><td>{String(x)}</td><td style={{ fontWeight: x === y ? 400 : 600 }}>{String(y)}{x === y ? "" : " (changed)"}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="qf-small">{same ? "Both runs used the identical dataset (same sha256)." : "The runs used different datasets, so their numbers describe different synthetic markets."}</p>
            </section>
            <section className="qf-section" aria-labelledby="qf-cmp-results">
              <h2 className="qf-h2" id="qf-cmp-results">Results</h2>
              <div className="qf-table-wrap" tabIndex={0} role="region" aria-label="Table, scrolls sideways when narrow">
                <table className="qf-table">
                  <thead><tr><th scope="col">Strategy</th><th scope="col">Verdict, first</th><th scope="col">Verdict, second</th><th scope="col">OOS Sharpe</th><th scope="col">Holdout return</th></tr></thead>
                  <tbody>
                    {ids.map((id) => {
                      const x = ra.results.strategies.find((s) => s.id === id);
                      const y = rb.results.strategies.find((s) => s.id === id);
                      return (
                        <tr key={id}>
                          <th scope="row" style={{ fontWeight: 500 }}>{SERIES[id]?.label ?? id}</th>
                          <td>{x?.verdict ?? "not run"}</td><td>{y?.verdict ?? "not run"}</td>
                          <td className="qf-num">{x ? fixed(x.oos_metrics.sharpe) : "n/a"} then {y ? fixed(y.oos_metrics.sharpe) : "n/a"}</td>
                          <td className="qf-num">{x ? signedPct(x.holdout_metrics.total_return) : "n/a"} then {y ? signedPct(y.holdout_metrics.total_return) : "n/a"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
            {merged && (
              <section className="qf-section" aria-labelledby="qf-cmp-eq">
                <h2 className="qf-h2" id="qf-cmp-eq">One strategy, both runs</h2>
                <div className="qf-field" style={{ maxWidth: 280 }}>
                  <label htmlFor="qf-cmp-s">Strategy</label>
                  <select id="qf-cmp-s" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                    {ids.map((id) => <option key={id} value={id}>{SERIES[id]?.label ?? id}</option>)}
                  </select>
                </div>
                <div className="qf-plate">
                  <EquityChart
                    rows={merged}
                    series={[{ ...SERIES[strategy]!, key: "first", label: "First run" }, { key: "second", label: "Second run", color: "var(--qf-s-meanrev)", dash: "9 4" }]}
                    visible={new Set(["first", "second"])}
                    title={`${SERIES[strategy]?.label ?? strategy}: both runs on the same dataset`}
                  />
                </div>
              </section>
            )}
            <p className="qf-small">First run completed {ra.record.completed_at ? day(ra.record.completed_at) : "n/a"}; second {rb.record.completed_at ? day(rb.record.completed_at) : "n/a"}.</p>
          </>
        );
      })()}
    </div>
  );
}
