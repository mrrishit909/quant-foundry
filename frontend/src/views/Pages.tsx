import { Icon } from "../components/Icon";
import type { AppConfig } from "../config";

export function RequestView({ config }: { config: AppConfig }) {
  const form = `${config.repoUrl}/issues/new?template=run-request.yml`;
  return (
    <div style={{ display: "grid", gap: 36, maxWidth: 820 }}>
      <header style={{ display: "grid", gap: 14 }}>
        <h1 className="qf-h1">Request a research run.</h1>
        <p className="qf-prose">
          This site is static and read-only. A new run is a GitHub issue: you pick the synthetic market, the
          strategies and the costs from fixed options, and a GitHub Actions workflow computes and publishes the
          result. Opening an issue needs a GitHub account.
        </p>
      </header>
      <section className="qf-section" aria-labelledby="qf-req-who">
        <h2 className="qf-h2" id="qf-req-who">Who can start a run</h2>
        <p className="qf-prose">
          Requests from the repository owner start automatically. Anyone else's request waits, labelled blocked,
          until the owner reviews it and adds an approval label. No request, from anyone, can start paid AI
          inference: runs are deterministic Python.
        </p>
      </section>
      <section className="qf-section" aria-labelledby="qf-req-next">
        <h2 className="qf-h2" id="qf-req-next">What happens after you submit</h2>
        <ol className="qf-steps">
          <li><p className="qf-prose">The intake workflow checks every field against the request schema and labels the issue requested, or blocked with the reason.</p></li>
          <li><p className="qf-prose">If the same parameters were already run, the issue links the existing run instead of computing again.</p></li>
          <li><p className="qf-prose">The run computes on a GitHub-hosted runner (usually under five minutes), its outputs are validated, then written to the state branch.</p></li>
          <li><p className="qf-prose">The site redeploys with the new run and the issue gets a link to it, completed or failed, with the evidence kept either way.</p></li>
        </ol>
      </section>
      <div className="qf-toolbar">
        <a className="qf-btn qf-btn-primary" href={form}>
          <Icon name="github" /> Open the run request form on GitHub
        </a>
        <a className="qf-btn" href={`${config.repoUrl}/issues?q=label%3Atype%3Arun`}>See existing requests</a>
      </div>
      <p className="qf-small">
        Limits keep the lab inside GitHub's free tier: at most 40 runs a month, 5 at a time, 2 MB of results per
        run. A request over a limit is blocked with an explanation, never silently dropped.
      </p>
    </div>
  );
}

export function MethodView({ config }: { config: AppConfig }) {
  const rows: [string, string, string][] = [
    ["Published runs, charts, tables, downloads", "Cached", "A static snapshot of the state branch, rebuilt when a run completes. Its time is shown at the top of every page."],
    ["Cost sensitivity sliders", "Simulated in your browser", "Re-prices the published trades; nothing is saved or sent."],
    ["New runs", "Live, owner-authorized", "Through GitHub Issues and Actions. Not possible from this page."],
    ["AI grading of the site", "Unavailable", "Optional; it runs only if the owner configures inference credentials. Release records say whether it ran."],
    ["Live market data and trading", "Not supported", "By design. There is no brokerage connection."],
  ];
  return (
    <div style={{ display: "grid", gap: 40, maxWidth: 860 }}>
      <header style={{ display: "grid", gap: 14 }}>
        <h1 className="qf-h1">Method, and what it cannot tell you.</h1>
        <p className="qf-prose">
          Quant Foundry is built to make it hard for a backtest to fool its author. It tests three textbook strategy
          families on synthetic markets with walk-forward selection, a sealed holdout and explicit costs, and it
          publishes the rejections as prominently as any success.
        </p>
      </header>
      <section className="qf-section" aria-labelledby="qf-m-protocol">
        <h2 className="qf-h2" id="qf-m-protocol">Protocol</h2>
        <ol className="qf-steps">
          <li><p className="qf-prose">Generate a deterministic synthetic market from a seed, validate it, and record its hash.</p></li>
          <li><p className="qf-prose">Seal the last part of the timeline as the holdout before any strategy sees data.</p></li>
          <li><p className="qf-prose">Walk forward through the rest: choose each strategy's parameters on a training window by in-sample Sharpe, then trade the next window untouched.</p></li>
          <li><p className="qf-prose">Freeze the final parameters and evaluate the holdout once. Compare against buy-and-hold and cash with the same costs.</p></li>
          <li><p className="qf-prose">Accept a strategy only if it clears every check; record every evaluation, including the ones that lose.</p></li>
        </ol>
      </section>
      <section className="qf-section" aria-labelledby="qf-m-guards">
        <h2 className="qf-h2" id="qf-m-guards">Guarantees checked on every release</h2>
        <p className="qf-prose">
          Accounting reconciles to a millionth of a unit; future prices cannot change earlier decisions; the same request
          reproduces byte-identical outputs; costs are always charged; every experiment is written down; rejected
          strategies stay visible; the holdout is never used for tuning, across runs as well as within one.
        </p>
      </section>
      <section className="qf-section" aria-labelledby="qf-m-limits">
        <h2 className="qf-h2" id="qf-m-limits">Limitations</h2>
        <ul style={{ listStyle: "disc", paddingLeft: 20, display: "grid", gap: 8 }} className="qf-prose">
          <li>The markets are synthetic. Results describe these generated series, not any real exchange or asset.</li>
          <li>The calendar is Monday to Friday with no holidays; there are no dividends, splits or delistings.</li>
          <li>Long only. Fills at the next open with a fixed slippage; no market impact beyond that, no partial fills.</li>
          <li>Three strategy families with small parameter grids. A rejection here says nothing about strategies not tested.</li>
          <li>Statistics come from a few years of daily bars, so Sharpe estimates are noisy; the verdict rules are deliberately strict.</li>
        </ul>
      </section>
      <section className="qf-section" aria-labelledby="qf-m-status">
        <h2 className="qf-h2" id="qf-m-status">What on this site is live, cached, simulated or unavailable</h2>
        <div className="qf-table-wrap" tabIndex={0} role="region" aria-label="Table, scrolls sideways when narrow">
          <table className="qf-table">
            <thead><tr><th scope="col">Capability</th><th scope="col" style={{ textAlign: "left" }}>Status</th><th scope="col" style={{ textAlign: "left" }}>Detail</th></tr></thead>
            <tbody>
              {rows.map(([a, b, c]) => (
                <tr key={a}><th scope="row" style={{ fontWeight: 500 }}>{a}</th><td style={{ textAlign: "left" }}>{b}</td><td style={{ textAlign: "left" }}>{c}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <p className="qf-small">
        Source, workflows and documentation: <a href={config.repoUrl}>{config.repoUrl.replace("https://", "")}</a>
      </p>
    </div>
  );
}
