import { useEffect, useMemo, useRef, useState } from "react";
import { EquityChart, Legend, SERIES } from "../charts/EquityChart";
import { Disclosure, Segmented } from "../components/Controls";
import { Icon, StatusIcon } from "../components/Icon";
import { Verdict } from "../components/Verdict";
import type { AppConfig } from "../config";
import type { Metrics, RunBundle, Snapshot } from "../data/types";
import { chainedOos, repriceCosts } from "../lib/costs";
import { day, fixed, money, paramsText, pct, shortHash, signedPct, timestamp } from "../lib/format";
import { prefersReducedMotion } from "../lib/motion";
import { routeHref } from "../routing";

export const SECTIONS = [
  { id: "verdict", label: "Verdict" },
  { id: "equity", label: "Equity and drawdown" },
  { id: "comparison", label: "Comparison" },
  { id: "costs", label: "Cost sensitivity" },
  { id: "walkforward", label: "Walk-forward" },
  { id: "holdout", label: "Sealed holdout" },
  { id: "quality", label: "Data quality" },
  { id: "assumptions", label: "Assumptions" },
  { id: "provenance", label: "Provenance" },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

function scrollToSection(id: SectionId) {
  const el = document.getElementById(`qf-sec-${id}`);
  if (!el) return;
  el.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  el.focus({ preventScroll: true });
}

function useActiveSection(): SectionId {
  const [active, setActive] = useState<SectionId>("verdict");
  useEffect(() => {
    const els = SECTIONS.map((s) => document.getElementById(`qf-sec-${s.id}`)).filter(Boolean) as HTMLElement[];
    const io = new IntersectionObserver(
      (entries) => {
        const top = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (top) setActive(top.target.id.replace("qf-sec-", "") as SectionId);
      },
      { rootMargin: "-90px 0px -55% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
  return active;
}

function Contents({ active, variant }: { active: SectionId; variant: "rail" | "sheet" }) {
  const index = SECTIONS.findIndex((s) => s.id === active);
  const list = (
    <ol className="qf-toc">
        {SECTIONS.map((s) => (
          <li key={s.id}>
            <a
              href={`#qf-sec-${s.id}`}
              aria-current={s.id === active ? "true" : undefined}
              onClick={(e) => {
                e.preventDefault(); // hash routing owns the URL; scroll instead
                scrollToSection(s.id);
              }}
            >
              {s.label}
            </a>
          </li>
        ))}
    </ol>
  );
  if (variant === "sheet") {
    return (
      <nav aria-label="Report contents" className="qf-toc-sheet">
        <Disclosure summary="Jump to a section">{list}</Disclosure>
      </nav>
    );
  }
  return (
    <nav aria-label="Report contents" className="qf-rail">
      <p className="qf-rail-title">Contents</p>
      <div style={{ position: "relative" }}>
        <span className="qf-toc-marker" aria-hidden style={{ transform: `translateY(${index * 31}px)` }} />
        {list}
      </div>
    </nav>
  );
}

function Section({ id, title, lede, children }: { id: SectionId; title: string; lede?: string; children: React.ReactNode }) {
  return (
    <section className="qf-section" id={`qf-sec-${id}`} tabIndex={-1} aria-labelledby={`qf-h-${id}`}>
      <div className="qf-section-head">
        <h2 className="qf-h2" id={`qf-h-${id}`}>{title}</h2>
        {lede && <p className="qf-prose">{lede}</p>}
      </div>
      {children}
    </section>
  );
}

const strategyKeys = (run: RunBundle) => run.results.strategies.map((s) => s.id);

function EquitySection({ run }: { run: RunBundle }) {
  const keys = [...strategyKeys(run), "buyhold", "cash"];
  const series = keys.map((k) => SERIES[k]!).filter(Boolean);
  const [visible, setVisible] = useState(() => new Set(keys));
  const [dd, setDd] = useState<"both" | "equity">("both");
  return (
    <Section
      id="equity"
      title="Out-of-sample equity, then the sealed holdout"
      lede="Each walk-forward test window starts from 100,000 and the windows are chained by returns. The hatched span is the holdout: it was evaluated once, with parameters frozen before anyone saw it."
    >
      <div className="qf-plate" style={{ display: "grid", gap: 14 }}>
        <div className="qf-toolbar">
          <Legend
            series={series}
            visible={visible}
            onToggle={(k) =>
              setVisible((v) => {
                const next = new Set(v);
                if (next.has(k) && next.size > 1) next.delete(k);
                else next.add(k);
                return next;
              })
            }
          />
          <Segmented
            label="Panels"
            value={dd}
            options={[
              { value: "both", label: "Equity and drawdown" },
              { value: "equity", label: "Equity only" },
            ]}
            onChange={setDd}
          />
        </div>
        <EquityChart rows={run.equity} series={series} visible={visible} title="Portfolio value in currency units, out of sample then holdout" showDrawdown={dd === "both"} />
      </div>
    </Section>
  );
}

type SortKey = "sharpe" | "total_return" | "max_drawdown" | "holdout" | "trades" | "costs" | "stability";

function ComparisonSection({ run }: { run: RunBundle }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "sharpe", dir: -1 });
  const rows = run.results.strategies.map((s) => ({
    id: s.id,
    name: s.name,
    verdict: s.verdict,
    oos: s.oos_metrics,
    holdout: s.holdout_metrics.total_return,
    stability: s.stability as number | null,
  }));
  const bench = (["buyhold", "cash"] as const).map((k) => ({
    id: k,
    name: SERIES[k]!.label,
    oos: run.results.benchmarks[k].oos,
    holdout: run.results.benchmarks[k].holdout.total_return,
  }));
  const value = (r: { oos: Metrics; holdout: number; stability?: number | null }, key: SortKey) =>
    key === "holdout" ? r.holdout : key === "costs" ? r.oos.fees_paid + r.oos.slippage_paid : key === "stability" ? (r.stability ?? -1) : r.oos[key];
  const sorted = [...rows].sort((a, b) => (value(a, sort.key) - value(b, sort.key)) * sort.dir);
  const head = (key: SortKey, label: string) => {
    const active = sort.key === key;
    return (
      <th scope="col" aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
        <button type="button" onClick={() => setSort({ key, dir: active ? (sort.dir === 1 ? -1 : 1) : -1 })}>
          {label}
          <span aria-hidden className="qf-tone-muted">{active ? (sort.dir === 1 ? "▴" : "▾") : ""}</span>
        </button>
      </th>
    );
  };
  return (
    <Section
      id="comparison"
      title="Strategies against the benchmarks"
      lede="Out-of-sample figures come from the stitched walk-forward test windows; holdout return is the single sealed evaluation. Costs are fees plus slippage paid out of sample."
    >
      <div className="qf-table-wrap qf-wide-only" tabIndex={0} role="region" aria-label="Table, scrolls sideways when narrow">
        <table className="qf-table">
          <caption className="qf-sr-only">Strategy comparison, sortable by column</caption>
          <thead>
            <tr>
              <th scope="col">Strategy</th>
              <th scope="col">Verdict</th>
              {head("sharpe", "OOS Sharpe")}
              {head("total_return", "OOS return")}
              {head("max_drawdown", "Max drawdown")}
              {head("holdout", "Holdout return")}
              {head("trades", "Trades")}
              {head("costs", "Costs paid")}
              {head("stability", "Stability")}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.id}>
                <th scope="row" style={{ fontWeight: 500 }}>
                  <a href={routeHref({ view: "strategy", runId: run.record.run_id, strategyId: r.id })}>{r.name}</a>
                </th>
                <td>
                  <span className={`qf-chip ${r.verdict === "accepted" ? "qf-tone-success" : "qf-tone-danger"}`}>
                    <Icon name={r.verdict === "accepted" ? "check" : "cross"} />
                    {r.verdict === "accepted" ? "Accepted" : "Rejected"}
                  </span>
                </td>
                <td className="qf-num">{fixed(r.oos.sharpe)}</td>
                <td className="qf-num">{signedPct(r.oos.total_return)}</td>
                <td className="qf-num">{pct(r.oos.max_drawdown)}</td>
                <td className="qf-num">{signedPct(r.holdout)}</td>
                <td className="qf-num">{r.oos.trades}</td>
                <td className="qf-num">{money(r.oos.fees_paid + r.oos.slippage_paid)}</td>
                <td className="qf-num">{fixed(r.stability ?? NaN)}</td>
              </tr>
            ))}
            {bench.map((b) => (
              <tr key={b.id} className="qf-row-bench">
                <th scope="row" style={{ fontWeight: 400 }}>{b.name}</th>
                <td>Benchmark</td>
                <td className="qf-num">{fixed(b.oos.sharpe)}</td>
                <td className="qf-num">{signedPct(b.oos.total_return)}</td>
                <td className="qf-num">{pct(b.oos.max_drawdown)}</td>
                <td className="qf-num">{signedPct(b.holdout)}</td>
                <td className="qf-num">{b.oos.trades}</td>
                <td className="qf-num">{money(b.oos.fees_paid + b.oos.slippage_paid)}</td>
                <td className="qf-num">n/a</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="qf-cards" aria-label="Strategy comparison">
        {[...rows, ...bench.map((b) => ({ ...b, verdict: "benchmark" as const, stability: null }))].map((r) => (
          <li key={r.id} className="qf-card">
            <div className="qf-toolbar" style={{ justifyContent: "space-between" }}>
              {r.verdict === "benchmark" ? (
                <span className="qf-h3">{r.name}</span>
              ) : (
                <a className="qf-h3" href={routeHref({ view: "strategy", runId: run.record.run_id, strategyId: r.id })}>{r.name}</a>
              )}
              <span className={`qf-chip ${r.verdict === "accepted" ? "qf-tone-success" : r.verdict === "rejected" ? "qf-tone-danger" : "qf-tone-muted"}`}>
                {r.verdict === "benchmark" ? "Benchmark" : r.verdict === "accepted" ? "Accepted" : "Rejected"}
              </span>
            </div>
            <dl>
              {[
                ["OOS Sharpe", fixed(r.oos.sharpe)],
                ["OOS return", signedPct(r.oos.total_return)],
                ["Max drawdown", pct(r.oos.max_drawdown)],
                ["Holdout", signedPct(r.holdout)],
                ["Trades", String(r.oos.trades)],
                ["Stability", r.stability === null ? "n/a" : fixed(r.stability)],
              ].map(([k, v]) => (
                <div key={k}><dt>{k}</dt><dd className="qf-num">{v}</dd></div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function CostsSection({ run }: { run: RunBundle }) {
  const params = run.manifest.params;
  const [fee, setFee] = useState(params.costs.fee_bps);
  const [slip, setSlip] = useState(params.costs.slippage_bps);
  const initial = Number((run.assumptions.cash as { initial?: number } | undefined)?.initial ?? 100000);
  const rows = run.results.strategies.map((s) => {
    const est = repriceCosts(run.trades, run.walkforward, s.id, s.holdout_metrics.total_return, fee, slip, initial);
    const base = repriceCosts(run.trades, run.walkforward, s.id, s.holdout_metrics.total_return, params.costs.fee_bps, params.costs.slippage_bps, initial);
    return { s, est, drift: Math.abs(base.oosReturn - chainedOos(run.walkforward, s.id)) };
  });
  const drift = Math.max(...rows.map((r) => r.drift));
  return (
    <Section
      id="costs"
      title="What if trading cost more, or less?"
      lede="A browser-side estimate from the published trade ledger. It holds every trade fixed and re-prices its fee and slippage; it does not re-run the backtest, so changes in position sizes are ignored. Nothing here is saved."
    >
      <div className="qf-plate" style={{ display: "grid", gap: 20 }}>
        <div className="qf-grid-2">
          <div className="qf-field">
            <label htmlFor="qf-fee">Fee: <span className="qf-num">{fee} bps</span> per trade (run used {params.costs.fee_bps})</label>
            <input id="qf-fee" type="range" min={0} max={50} step={1} value={fee} onChange={(e) => setFee(Number(e.target.value))} />
          </div>
          <div className="qf-field">
            <label htmlFor="qf-slip">Slippage: <span className="qf-num">{slip} bps</span> (run used {params.costs.slippage_bps})</label>
            <input id="qf-slip" type="range" min={0} max={100} step={1} value={slip} onChange={(e) => setSlip(Number(e.target.value))} />
          </div>
        </div>
        <div className="qf-table-wrap" tabIndex={0} role="region" aria-label="Table, scrolls sideways when narrow">
          <table className="qf-table">
            <caption className="qf-sr-only">Estimated returns at the chosen costs</caption>
            <thead>
              <tr>
                <th scope="col">Strategy</th>
                <th scope="col">OOS return, published</th>
                <th scope="col">OOS return, estimated</th>
                <th scope="col">Holdout, published</th>
                <th scope="col">Holdout, estimated</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ s, est }) => (
                <tr key={s.id}>
                  <th scope="row" style={{ fontWeight: 500 }}>{s.name}</th>
                  <td className="qf-num">{signedPct(s.oos_metrics.total_return)}</td>
                  <td className="qf-num"><strong>{signedPct(est.oosReturn)}</strong></td>
                  <td className="qf-num">{signedPct(s.holdout_metrics.total_return)}</td>
                  <td className="qf-num"><strong>{signedPct(est.holdoutReturn)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="qf-toolbar">
          <button type="button" className="qf-btn" onClick={() => { setFee(params.costs.fee_bps); setSlip(params.costs.slippage_bps); }}>
            Reset to the run's costs
          </button>
          <p className="qf-small">
            Self-check: at the run's own costs the estimator reproduces the published out-of-sample returns to within{" "}
            {pct(drift, 3)}.
          </p>
        </div>
      </div>
    </Section>
  );
}

function WalkForwardSection({ run }: { run: RunBundle }) {
  const { windows } = run.walkforward;
  const all = [...windows.flatMap((w) => [w.train_start, w.test_end]), ...run.holdout.span].sort();
  const t0 = Date.parse(all[0]!);
  const t1 = Date.parse(all[all.length - 1]!);
  const pos = (d: string) => ((Date.parse(d) - t0) / (t1 - t0)) * 100;
  return (
    <Section
      id="walkforward"
      title="Walk-forward: choose on the past, test on what follows"
      lede={`${windows.length} windows of ${run.manifest.params.walk_forward.train_days} training days followed by ${run.manifest.params.walk_forward.test_days} test days. In every window each strategy picks its parameters by in-sample Sharpe, then trades the next test window untouched.`}
    >
      <div className="qf-plate" style={{ display: "grid", gap: 10 }}>
        <div className="qf-toolbar qf-small">
          <span><span style={{ display: "inline-block", width: 18, height: 10, background: "var(--qf-oat)", borderRadius: 2 }} /> training</span>
          <span><span style={{ display: "inline-block", width: 18, height: 10, background: "var(--qf-action)", borderRadius: 2 }} /> test</span>
          <span>hatched: sealed holdout</span>
        </div>
        {windows.map((w) => (
          <div key={w.index} className="qf-window-row">
            <span className="qf-small">Window {w.index + 1}</span>
            <div className="qf-window-bar" aria-label={`Window ${w.index + 1}: trains ${day(w.train_start)} to ${day(w.train_end)}, tests ${day(w.test_start)} to ${day(w.test_end)}`} role="img">
              <span className="qf-window-train" style={{ left: `${pos(w.train_start)}%`, width: `${pos(w.train_end) - pos(w.train_start)}%` }} />
              <span className="qf-window-test" style={{ left: `${pos(w.test_start)}%`, width: `${pos(w.test_end) - pos(w.test_start)}%` }} />
            </div>
          </div>
        ))}
        <div className="qf-window-row">
          <span className="qf-small">Holdout</span>
          <div className="qf-window-bar" role="img" aria-label={`Holdout ${day(run.holdout.span[0])} to ${day(run.holdout.span[1])}`}>
            <span style={{ left: `${pos(run.holdout.span[0])}%`, width: `${pos(run.holdout.span[1]) - pos(run.holdout.span[0])}%`, background: "repeating-linear-gradient(45deg, var(--qf-oat) 0 2px, transparent 2px 6px)", border: "1px solid var(--qf-border-strong)" }} />
          </div>
        </div>
      </div>
      <div className="qf-table-wrap" tabIndex={0} role="region" aria-label="Table, scrolls sideways when narrow">
        <table className="qf-table">
          <caption className="qf-sr-only">Chosen parameters and out-of-sample Sharpe per window</caption>
          <thead>
            <tr>
              <th scope="col">Window and test span</th>
              {run.results.strategies.map((s) => (
                <th key={s.id} scope="col">{s.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {windows.map((w) => (
              <tr key={w.index}>
                <th scope="row" style={{ fontWeight: 400 }}>
                  {w.index + 1}: {day(w.test_start)} to {day(w.test_end)}
                </th>
                {run.results.strategies.map((s) => {
                  const cell = run.walkforward.strategies[s.id]?.find((x) => x.window === w.index);
                  return (
                    <td key={s.id}>
                      {cell ? (
                        <>
                          <span className="qf-num">Sharpe {fixed(cell.out_of_sample.sharpe)}</span>
                          <br />
                          <span className="qf-small">{paramsText(cell.chosen_params)}</span>
                        </>
                      ) : "n/a"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function HoldoutSection({ run }: { run: RunBundle }) {
  const h = run.holdout;
  return (
    <Section
      id="holdout"
      title="The sealed holdout"
      lede={`The last ${Math.round(run.manifest.params.holdout_fraction * 100)}% of the data, ${day(h.span[0])} to ${day(h.span[1])}, was never used to choose anything. Parameters were frozen from the final walk-forward window, then the holdout was evaluated exactly once per strategy.`}
    >
      <ul className="qf-checklist">
        <li><StatusIcon status={h.sealed ? "pass" : "fail"} /><span>Holdout sealed during development: {h.sealed ? "yes" : "no"}</span></li>
        <li><StatusIcon status={h.selection_frozen_before_holdout ? "pass" : "fail"} /><span>Parameters frozen before the holdout was evaluated: {h.selection_frozen_before_holdout ? "yes" : "no"}</span></li>
        <li><StatusIcon status={run.checks.holdout.evaluated_once ? "pass" : "fail"} /><span>Evaluated once per strategy in this run: {run.checks.holdout.evaluated_once ? "yes" : "no"}</span></li>
        {run.audit ? (
          run.audit.strategies.map((a) => (
            <li key={a.strategy}>
              <StatusIcon status={a.contaminated ? "fail" : "pass"} />
              <span>
                {SERIES[a.strategy]?.label ?? a.strategy}: {a.contaminated
                  ? `contaminated. This dataset's holdout was already evaluated with different parameters in ${a.prior_runs.join(", ")}, so its holdout result here cannot count as unseen.`
                  : a.prior_evaluations
                    ? `evaluated before on this dataset ${a.prior_evaluations} time(s), always with the same frozen parameters.`
                    : "first evaluation of this dataset's holdout across all recorded runs."}
              </span>
            </li>
          ))
        ) : (
          <li><StatusIcon status="warn" /><span>Cross-run holdout audit unavailable for this run (it is written when a run is published).</span></li>
        )}
      </ul>
      <div className="qf-table-wrap" tabIndex={0} role="region" aria-label="Table, scrolls sideways when narrow">
        <table className="qf-table">
          <caption className="qf-sr-only">Holdout evaluations</caption>
          <thead>
            <tr><th scope="col">Strategy</th><th scope="col">Frozen parameters</th><th scope="col">Return</th><th scope="col">Sharpe</th><th scope="col">Max drawdown</th><th scope="col">Trades</th></tr>
          </thead>
          <tbody>
            {h.evaluations.map((e) => (
              <tr key={e.strategy}>
                <th scope="row" style={{ fontWeight: 500 }}>{SERIES[e.strategy]?.label ?? e.strategy}</th>
                <td>{paramsText(e.frozen_params)}</td>
                <td className="qf-num">{signedPct(e.metrics.total_return)}</td>
                <td className="qf-num">{fixed(e.metrics.sharpe)}</td>
                <td className="qf-num">{pct(e.metrics.max_drawdown)}</td>
                <td className="qf-num">{e.metrics.trades}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function describe(detail: unknown): string {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (typeof detail === "object") {
    const entries = Object.entries(detail as Record<string, unknown>).slice(0, 6);
    return entries
      .map(([k, v]) => `${k.replace(/_/g, " ")}: ${Array.isArray(v) ? (v.length > 6 ? `${v.length} items` : v.join(", ")) : typeof v === "object" && v ? JSON.stringify(v).slice(0, 120) : String(v)}`)
      .join("; ");
  }
  return String(detail);
}

function QualitySection({ run }: { run: RunBundle }) {
  const q = run.quality;
  return (
    <Section
      id="quality"
      title="Data quality"
      lede={`${q.rows.toLocaleString("en-US")} rows across ${q.symbols.length} synthetic symbols. Any failed check stops a run before research begins; warnings are reported here and carried into the results.`}
    >
      <ul className="qf-checklist">
        {q.checks.map((c) => (
          <li key={c.name}>
            <StatusIcon status={c.status} />
            <div>
              <p style={{ fontWeight: 500 }}>{c.name.replace(/_/g, " ")}: {c.status === "pass" ? "passed" : c.status === "warn" ? "warning" : "failed"}</p>
              <p className="qf-small qf-wrap-anywhere">{describe(c.detail)}</p>
            </div>
          </li>
        ))}
        <li>
          <StatusIcon status={run.checks.missing_data_events.length ? "warn" : "pass"} />
          <div>
            <p style={{ fontWeight: 500 }}>Missing bars met during trading: {run.checks.missing_data_events.length}</p>
            <p className="qf-small">On a missing bar a symbol is not traded that day and is marked at its last valid close.</p>
          </div>
        </li>
      </ul>
    </Section>
  );
}

function AssumptionsSection({ run }: { run: RunBundle }) {
  return (
    <Section id="assumptions" title="Assumptions" lede="Every modelling choice the results depend on, in plain words. Open any entry to see the exact values used by this run.">
      <div style={{ display: "grid" }}>
        {Object.entries(run.assumptions).map(([key, a]) => {
          const { text, ...raw } = a;
          return (
            <Disclosure key={key} summary={<span><strong style={{ fontWeight: 500 }}>{key.replace(/_/g, " ")}</strong></span>}>
              <p className="qf-prose" style={{ fontSize: 16 }}>{text}</p>
              {Object.keys(raw).length > 0 && (
                <dl className="qf-kv" style={{ marginTop: 10 }}>
                  {Object.entries(raw).map(([k, v]) => (
                    <div key={k} style={{ display: "contents" }}>
                      <dt>{k.replace(/_/g, " ")}</dt>
                      <dd className="qf-num">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </Disclosure>
          );
        })}
      </div>
    </Section>
  );
}

function ProvenanceSection({ run, snapshot, config }: { run: RunBundle; snapshot: Snapshot; config: AppConfig }) {
  const r = run.record;
  const repo = config.repoUrl;
  const p = run.manifest.params;
  const base = `${config.dataUrl}runs/${encodeURIComponent(r.run_id)}/`;
  const files = ["results.json", "equity.csv", "trades.csv", "experiments.csv", "walkforward.json", "sensitivity.json", "holdout.json", "data_quality.json", "assumptions.json", "manifest.json", "run.json"];
  return (
    <Section id="provenance" title="Provenance" lede="Where these numbers came from. The state branch on GitHub is the record of truth; this page shows a sanitized copy of it.">
      <dl className="qf-kv">
        <dt>Run</dt><dd>{r.run_id} (attempt {r.attempt}{r.parent_run_id ? `, retry of ${r.parent_run_id}` : ""})</dd>
        <dt>Status</dt><dd>{r.status}, completed {r.completed_at ? timestamp(r.completed_at) : "n/a"}</dd>
        <dt>Requested by</dt>
        <dd>
          {r.request_source.type}
          {r.request_source.issue_number ? <> via <a href={`${repo}/issues/${r.request_source.issue_number}`}>issue #{r.request_source.issue_number}</a></> : null}
          {r.request_source.actor && r.request_source.actor !== "fixture" ? ` (${r.request_source.actor})` : ""}
        </dd>
        <dt>Parameters</dt>
        <dd>
          seed {p.dataset.seed}, {p.dataset.symbols} symbols, {p.dataset.days.toLocaleString("en-US")} trading days, {p.dataset.regime_mix} regimes; fee {p.costs.fee_bps} bps, slippage {p.costs.slippage_bps} bps; train {p.walk_forward.train_days}, test {p.walk_forward.test_days}, holdout {pct(p.holdout_fraction, 0)}; long only
        </dd>
        <dt>Workflow run</dt>
        <dd>{r.workflow_run_id ? <a href={`${repo}/actions/runs/${r.workflow_run_id}`}>#{r.workflow_run_id}</a> : "none (fixture)"}</dd>
        <dt>Source commit</dt>
        <dd>{/^0+$/.test(r.source_commit) ? "fixture" : <a href={`${repo}/commit/${r.source_commit}`}>{r.source_commit.slice(0, 10)}</a>}</dd>
        <dt>Input manifest</dt><dd className="qf-wrap-anywhere">{shortHash(r.input_manifest_hash, 16)}</dd>
        <dt>Dataset sha256</dt><dd className="qf-wrap-anywhere">{shortHash(run.manifest.dataset.sha256, 16)} ({run.manifest.dataset.rows.toLocaleString("en-US")} rows, {day(run.manifest.dataset.start)} to {day(run.manifest.dataset.end)})</dd>
        <dt>Engine</dt><dd>quantfoundry {run.manifest.package_version}</dd>
        <dt>Accounting check</dt><dd>{run.checks.accounting.backtests_checked} backtests, largest error {run.checks.accounting.max_abs_error.toExponential(1)} (tolerance {run.checks.accounting.tolerance})</dd>
        <dt>Look-ahead probe</dt><dd>{run.checks.lookahead_probe.passed ? "passed" : "failed"}: signals recomputed on data cut at {day(run.checks.lookahead_probe.cutoff_date)} match the full-data signals</dd>
        <dt>Snapshot</dt>
        <dd>
          generated {timestamp(snapshot.generated_at)}
          {snapshot.mode === "fixture" ? " from CI fixture data" : <> from state commit <a href={`${repo}/tree/${snapshot.state_commit}`}>{snapshot.state_commit.slice(0, 10)}</a></>}
        </dd>
      </dl>
      <div className="qf-toolbar">
        <a className="qf-btn" href={run.reportUrl} download>Download the research report (Markdown)</a>
        <a className="qf-btn" href={`${repo}/tree/state/runs/${r.run_id}`}>
          <Icon name="github" /> Run record on the state branch
        </a>
      </div>
      <Disclosure summary="Raw published files for this run">
        <ul style={{ listStyle: "none", display: "grid", gap: 6 }}>
          {files.map((f) => (
            <li key={f}><a href={base + f}>{f}</a></li>
          ))}
        </ul>
      </Disclosure>
    </Section>
  );
}

export function Report({ run, snapshot, config, focus }: { run: RunBundle; snapshot: Snapshot; config: AppConfig; focus?: SectionId }) {
  const active = useActiveSection();
  const scrolled = useRef(false);
  useEffect(() => {
    if (focus && !scrolled.current) {
      scrolled.current = true;
      requestAnimationFrame(() => scrollToSection(focus));
    }
  }, [focus]);
  const p = run.manifest.params;
  const meta = useMemo(
    () =>
      `Run ${run.record.run_id}, ${run.record.completed_at ? `completed ${day(run.record.completed_at)}` : "not completed"}. Synthetic data: seed ${p.dataset.seed}, ${p.dataset.symbols} symbols, ${p.dataset.days.toLocaleString("en-US")} trading days, ${p.dataset.regime_mix} regimes.`,
    [run, p],
  );
  return (
    <div className="qf-report">
      <Contents active={active} variant="rail" />
      <div className="qf-main">
        <Contents active={active} variant="sheet" />
        <section className="qf-section" id="qf-sec-verdict" tabIndex={-1} aria-label="Verdict">
          <p className="qf-meta qf-wrap-anywhere">{meta}</p>
          <Verdict run={run} />
        </section>
        <EquitySection run={run} />
        <ComparisonSection run={run} />
        <CostsSection run={run} />
        <WalkForwardSection run={run} />
        <HoldoutSection run={run} />
        <QualitySection run={run} />
        <AssumptionsSection run={run} />
        <ProvenanceSection run={run} snapshot={snapshot} config={config} />
      </div>
    </div>
  );
}
