import { useMemo, useState } from "react";
import { EquityChart, Legend, SERIES } from "../charts/EquityChart";
import { ParamGrid } from "../charts/ParamGrid";
import { Disclosure } from "../components/Controls";
import { Icon } from "../components/Icon";
import type { Params, RunBundle } from "../data/types";
import { day, fixed, money, paramsText, pct, signedPct } from "../lib/format";
import { routeHref } from "../routing";

const PAGE = 20;

function Ledger({ run, strategyId }: { run: RunBundle; strategyId: string }) {
  const trades = useMemo(() => run.trades.filter((t) => t.strategy === strategyId), [run, strategyId]);
  const symbols = useMemo(() => [...new Set(trades.map((t) => t.symbol))].sort(), [trades]);
  const [segment, setSegment] = useState("all");
  const [side, setSide] = useState("all");
  const [symbol, setSymbol] = useState("all");
  const [page, setPage] = useState(0);
  const filtered = trades.filter(
    (t) => (segment === "all" || t.segment === segment) && (side === "all" || t.side === side) && (symbol === "all" || t.symbol === symbol),
  );
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const current = Math.min(page, pages - 1);
  const rows = filtered.slice(current * PAGE, current * PAGE + PAGE);
  const reset = (fn: (v: string) => void) => (e: React.ChangeEvent<HTMLSelectElement>) => {
    fn(e.target.value);
    setPage(0);
  };
  const costs = filtered.reduce((s, t) => s + t.fee + t.slippage_cost, 0);
  return (
    <section className="qf-section" aria-labelledby="qf-ledger">
      <div className="qf-section-head">
        <h2 className="qf-h2" id="qf-ledger">Trade ledger</h2>
        <p className="qf-prose">
          Every fill out of sample (with the parameters chosen in each window) and in the holdout. Orders are decided
          at a close and filled at the next open, with slippage applied against the trade.
        </p>
      </div>
      <div className="qf-toolbar">
        <div className="qf-field">
          <label htmlFor="qf-seg">Segment</label>
          <select id="qf-seg" value={segment} onChange={reset(setSegment)}>
            <option value="all">All</option>
            <option value="out_of_sample">Out of sample</option>
            <option value="holdout">Holdout</option>
          </select>
        </div>
        <div className="qf-field">
          <label htmlFor="qf-side">Side</label>
          <select id="qf-side" value={side} onChange={reset(setSide)}>
            <option value="all">Buys and sells</option>
            <option value="buy">Buys</option>
            <option value="sell">Sells</option>
          </select>
        </div>
        <div className="qf-field">
          <label htmlFor="qf-sym">Symbol</label>
          <select id="qf-sym" value={symbol} onChange={reset(setSymbol)}>
            <option value="all">All symbols</option>
            {symbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <p className="qf-small" aria-live="polite" style={{ alignSelf: "end" }}>
          {filtered.length.toLocaleString("en-US")} fills, {money(costs)} in fees and slippage
        </p>
      </div>
      {filtered.length === 0 ? (
        <p className="qf-prose">No fills match these filters. This strategy may simply not have traded in that segment.</p>
      ) : (
        <>
          <div className="qf-table-wrap qf-wide-only" tabIndex={0} role="region" aria-label="Table, scrolls sideways when narrow">
            <table className="qf-table">
              <caption className="qf-sr-only">Trade ledger, page {current + 1} of {pages}</caption>
              <thead>
                <tr>
                  <th scope="col">Date</th><th scope="col">Symbol</th><th scope="col">Side</th><th scope="col">Shares</th>
                  <th scope="col">Open</th><th scope="col">Fill</th><th scope="col">Fee</th><th scope="col">Slippage</th><th scope="col">Segment</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t, i) => (
                  <tr key={`${t.date}-${t.symbol}-${i}`}>
                    <td>{day(t.date)}</td><td>{t.symbol}</td><td>{t.side === "buy" ? "Buy" : "Sell"}</td>
                    <td className="qf-num">{t.qty.toLocaleString("en-US")}</td>
                    <td className="qf-num">{fixed(t.ref_open)}</td><td className="qf-num">{fixed(t.fill_price)}</td>
                    <td className="qf-num">{fixed(t.fee)}</td><td className="qf-num">{fixed(t.slippage_cost)}</td>
                    <td>{t.segment === "holdout" ? "Holdout" : `Window ${Number(t.window) + 1}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="qf-cards" aria-label={`Trade ledger, page ${current + 1} of ${pages}`}>
            {rows.map((t, i) => (
              <li key={`${t.date}-${t.symbol}-${i}`} className="qf-card">
                <p><strong>{t.side === "buy" ? "Buy" : "Sell"} {t.qty.toLocaleString("en-US")} {t.symbol}</strong> on {day(t.date)}</p>
                <Disclosure summary={<span className="qf-small">Fill {fixed(t.fill_price)}, costs {fixed(t.fee + t.slippage_cost)}</span>}>
                  <dl>
                    {[
                      ["Next open", fixed(t.ref_open)],
                      ["Fill price", fixed(t.fill_price)],
                      ["Fee", fixed(t.fee)],
                      ["Slippage", fixed(t.slippage_cost)],
                      ["Segment", t.segment === "holdout" ? "Holdout" : `Window ${Number(t.window) + 1}`],
                    ].map(([k, v]) => (
                      <div key={k}><dt>{k}</dt><dd className="qf-num">{v}</dd></div>
                    ))}
                  </dl>
                </Disclosure>
              </li>
            ))}
          </ul>
          <div className="qf-toolbar" role="navigation" aria-label="Ledger pages">
            <button type="button" className="qf-btn" disabled={current === 0} onClick={() => setPage(current - 1)}>Previous page</button>
            <span className="qf-small qf-num">Page {current + 1} of {pages}</span>
            <button type="button" className="qf-btn" disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>Next page</button>
          </div>
        </>
      )}
    </section>
  );
}

export function StrategyView({ run, strategyId }: { run: RunBundle; strategyId: string }) {
  const result = run.results.strategies.find((s) => s.id === strategyId);
  const spec = run.strategies.find((s) => s.id === strategyId);
  const sens = run.sensitivity.strategies[strategyId];
  const [selected, setSelected] = useState<Params | null>(sens?.frozen_params ?? null);
  const keys = [strategyId, "buyhold", "cash"];
  const series = keys.map((k) => SERIES[k]!).filter(Boolean);
  const [visible, setVisible] = useState(() => new Set(keys));

  if (!result || !spec || !sens) {
    return (
      <div className="qf-state">
        <h1 className="qf-h1">This run has no strategy called "{strategyId}".</h1>
        <p className="qf-prose"><a href={routeHref({ view: "overview", runId: run.record.run_id })}>Back to the report for this run</a></p>
      </div>
    );
  }
  const combo = sens.combos.find((c) => selected && Object.keys(c.params).every((k) => c.params[k] === selected[k]));
  const windows = run.walkforward.strategies[strategyId] ?? [];
  const accepted = result.verdict === "accepted";

  return (
    <div style={{ display: "grid", gap: 64, maxWidth: 1160 }}>
      <header style={{ display: "grid", gap: 14 }}>
        <p className="qf-meta">
          <a href={routeHref({ view: "overview", runId: run.record.run_id })}>Report for {run.record.run_id}</a>
        </p>
        <h1 className="qf-h1">{result.name}</h1>
        <p className="qf-prose">{spec.description} {spec.signal_timing.charAt(0).toUpperCase() + spec.signal_timing.slice(1)}. Warm-up: {spec.warmup_rule}.</p>
        <div className={`qf-margin-note${accepted ? " qf-accepted" : ""}`} style={{ maxWidth: "68ch" }}>
          <p style={{ fontStyle: "normal", fontFamily: "var(--qf-sans)", fontWeight: 600, marginBottom: 4 }}>
            {accepted ? "Accepted" : "Rejected"}, frozen at {paramsText(result.frozen_params)}
          </p>
          {accepted ? <p>It cleared every check.</p> : (
            <ul style={{ paddingLeft: 18, listStyle: "disc", display: "grid", gap: 2 }}>
              {result.reasons.map((r) => <li key={r}>{r}.</li>)}
            </ul>
          )}
        </div>
      </header>

      <section className="qf-section" aria-labelledby="qf-s-equity">
        <h2 className="qf-h2" id="qf-s-equity">Equity against the benchmarks</h2>
        <div className="qf-plate" style={{ display: "grid", gap: 14 }}>
          <Legend series={series} visible={visible} onToggle={(k) => setVisible((v) => { const n = new Set(v); if (n.has(k) && n.size > 1) n.delete(k); else n.add(k); return n; })} />
          <EquityChart rows={run.equity} series={series} visible={visible} title={`${result.name}: portfolio value out of sample then holdout, with drawdown`} />
        </div>
        <div className="qf-grid-3">
          {[
            ["OOS Sharpe", fixed(result.oos_metrics.sharpe)],
            ["OOS return", signedPct(result.oos_metrics.total_return)],
            ["OOS max drawdown", pct(result.oos_metrics.max_drawdown)],
            ["Holdout return", signedPct(result.holdout_metrics.total_return)],
            ["Exposure", pct(result.oos_metrics.exposure, 0)],
            ["Costs paid out of sample", money(result.oos_metrics.fees_paid + result.oos_metrics.slippage_paid)],
          ].map(([k, v]) => (
            <div key={k} style={{ borderTop: "1px solid var(--qf-border-strong)", paddingTop: 10 }}>
              <p className="qf-small">{k}</p>
              <p className="qf-num" style={{ fontSize: 24, fontFamily: "var(--qf-sans)" }}>{v}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="qf-section" aria-labelledby="qf-s-params">
        <div className="qf-section-head">
          <h2 className="qf-h2" id="qf-s-params">Parameter explorer</h2>
          <p className="qf-prose">
            Out-of-sample Sharpe for every combination in the grid, each re-run across all walk-forward test windows
            with fixed parameters. A robust edge would show a broad neighbourhood of similar values; {Math.round(sens.stability * 100)}% of
            combinations here sit within {sens.tolerance} of the best ({fixed(sens.best_oos_sharpe)}). The frozen choice ranks {sens.chosen_rank} of {sens.grid_size}.
          </p>
        </div>
        <div className="qf-grid-2" style={{ alignItems: "start" }}>
          <ParamGrid combos={sens.combos} frozen={sens.frozen_params} selected={selected} onSelect={setSelected} />
          <div className="qf-plate" aria-live="polite">
            {combo ? (
              <>
                <p className="qf-h3">{paramsText(combo.params)}</p>
                <dl className="qf-kv" style={{ marginTop: 12 }}>
                  <dt>Sharpe</dt><dd className="qf-num">{fixed(combo.metrics.sharpe)}</dd>
                  <dt>Return</dt><dd className="qf-num">{signedPct(combo.metrics.total_return)}</dd>
                  <dt>Max drawdown</dt><dd className="qf-num">{pct(combo.metrics.max_drawdown)}</dd>
                  <dt>Fills</dt><dd className="qf-num">{combo.metrics.trades}</dd>
                  <dt>Turnover</dt><dd className="qf-num">{fixed(combo.metrics.turnover, 1)}</dd>
                  <dt>Costs paid</dt><dd className="qf-num">{money(combo.metrics.fees_paid + combo.metrics.slippage_paid)}</dd>
                </dl>
                <p className="qf-small" style={{ marginTop: 12 }}>
                  Choosing this combination after seeing this grid would be selection on test data; that is why the
                  frozen choice comes from in-sample results only.
                </p>
              </>
            ) : <p className="qf-small">Select a cell to see its full out-of-sample metrics.</p>}
          </div>
        </div>
      </section>

      <section className="qf-section" aria-labelledby="qf-s-windows">
        <h2 className="qf-h2" id="qf-s-windows">Choices per walk-forward window</h2>
        <div className="qf-table-wrap" tabIndex={0} role="region" aria-label="Table, scrolls sideways when narrow">
          <table className="qf-table">
            <caption className="qf-sr-only">In-sample and out-of-sample results per window</caption>
            <thead>
              <tr><th scope="col">Window</th><th scope="col">Chosen on training data</th><th scope="col">In-sample Sharpe</th><th scope="col">Test Sharpe</th><th scope="col">Test return</th><th scope="col">Test fills</th></tr>
            </thead>
            <tbody>
              {windows.map((w) => (
                <tr key={w.window}>
                  <th scope="row" style={{ fontWeight: 400 }}>{w.window + 1}</th>
                  <td>{paramsText(w.chosen_params)}</td>
                  <td className="qf-num">{fixed(w.in_sample.sharpe)}</td>
                  <td className="qf-num">{fixed(w.out_of_sample.sharpe)}</td>
                  <td className="qf-num">{signedPct(w.out_of_sample.total_return)}</td>
                  <td className="qf-num">{w.out_of_sample.trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="qf-small">
          The gap between in-sample and test Sharpe is the cost of choosing parameters on the past. Large gaps mean the
          in-sample winner did not carry forward.
        </p>
      </section>

      <Ledger run={run} strategyId={strategyId} />

      <p className="qf-small">
        <Icon name="info" /> Synthetic data. Historical simulation only: no orders were placed and nothing here is
        investment advice.
      </p>
    </div>
  );
}
