import { useMemo, useRef } from "react";
import type { RunBundle } from "../data/types";
import { countWord, day } from "../lib/format";
import { useKinetic } from "../lib/useKinetic";
import { routeHref } from "../routing";
import { useWidth } from "../charts/EquityChart";
import { Disclosure } from "./Controls";

let entered = false; // the entry sequence plays once per page load, not on every navigation

function wobble(width: number, seed: number): string {
  // A slightly uneven pen stroke, deterministic per strategy so it never jitters between renders.
  const r = (k: number) => Math.sin(seed * 12.9898 + k * 78.233) * 0.5;
  const y0 = 9 + r(1) * 3;
  const y1 = 9 + r(2) * 4;
  const y2 = 9 + r(3) * 3;
  return `M2 ${y0.toFixed(1)} C ${(width * 0.3).toFixed(1)} ${(y1 - 3).toFixed(1)}, ${(width * 0.62).toFixed(1)} ${(y2 + 3).toFixed(1)}, ${(width - 2).toFixed(1)} ${(9 + r(4) * 2).toFixed(1)}`;
}

function PenMark({ seed, accepted }: { seed: number; accepted: boolean }) {
  const [ref, width] = useWidth<HTMLSpanElement>();
  const path = useRef<SVGPathElement>(null);
  const w = Math.max(20, width * 1.06);
  const mounted = width > 0;
  // The referee's strike draws itself when its row scrolls in (once). Reduced motion: drawn already.
  useKinetic(({ gsap, MOTION_OK }) => {
    const p = path.current;
    if (!mounted || !p) return;
    const mm = gsap.matchMedia();
    mm.add(MOTION_OK, () => {
      const len = p.getTotalLength();
      gsap.fromTo(
        p,
        { strokeDasharray: len, strokeDashoffset: len },
        {
          strokeDashoffset: 0,
          duration: 0.75,
          ease: "power2.inOut",
          delay: 0.15 * seed,
          immediateRender: false,
          clearProps: "strokeDasharray,strokeDashoffset",
          scrollTrigger: { trigger: p.closest("li") ?? p, start: "top 88%", once: true },
        },
      );
    });
    return () => mm.revert();
  }, [mounted, seed]);
  return (
    <span ref={ref} aria-hidden style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      {mounted && (
        <svg
          className={`qf-strike${accepted ? " qf-accept-mark" : ""}`}
          width={w}
          height={18}
          viewBox={`0 0 ${w} 18`}
          style={accepted ? { top: "auto", bottom: -12, transform: "none" } : undefined}
          data-pen
        >
          <path ref={path} d={wobble(w, seed)} />
        </svg>
      )}
    </span>
  );
}

export function headline(total: number, accepted: number): string {
  const tested = `${countWord(total)} ${total === 1 ? "strategy" : "strategies"} tested.`;
  if (total === 1) return `${tested} ${accepted ? "It survived." : "It did not survive."}`;
  if (accepted === 0) return `${tested} None survived.`;
  if (accepted === total) return `${tested} All survived.`;
  return `${tested} ${countWord(accepted)} survived.`;
}

/** Decorative backdrop: the run's own out-of-sample equity curves, drawn huge and faint. */
function HeroCurves({ run }: { run: RunBundle }) {
  const keys = [...run.results.strategies.map((s) => s.id), "buyhold"];
  const paths = useMemo(() => {
    const rows = run.equity;
    const vals = rows.flatMap((r) => keys.map((k) => r.values[k] ?? NaN)).filter(Number.isFinite);
    if (rows.length < 2 || !vals.length) return [];
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    return keys.map((k) => {
      let d = "";
      rows.forEach((r, i) => {
        const v = r.values[k];
        if (v === undefined || !Number.isFinite(v)) return;
        d += `${d ? "L" : "M"}${((i / (rows.length - 1)) * 1000).toFixed(1)} ${(290 - ((v - lo) / (hi - lo || 1)) * 280).toFixed(1)}`;
      });
      return { k, d };
    });
  }, [run]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <svg className="qf-hero-curves" viewBox="0 0 1000 300" preserveAspectRatio="none" aria-hidden focusable="false">
      {paths.map(({ k, d }, i) => (
        <path key={k} d={d} data-curve={i} pathLength={1} className={k === "buyhold" ? "qf-curve-bench" : undefined} vectorEffect="non-scaling-stroke" />
      ))}
    </svg>
  );
}

export function Verdict({ run }: { run: RunBundle }) {
  const root = useRef<HTMLDivElement>(null);
  const { strategies, summary } = run.results;
  const p = run.manifest.params;
  const text = headline(strategies.length, summary.accepted);
  const cut = text.indexOf(". ") + 1;
  const [lead, verdict] = cut > 0 ? [text.slice(0, cut), text.slice(cut + 1)] : [text, ""];
  const oosDays = run.walkforward.windows.length * p.walk_forward.test_days;

  const stats: { value: number; label: string }[] = [
    { value: summary.accepted, label: `of ${strategies.length} accepted` },
    { value: p.dataset.days, label: "trading days simulated" },
    { value: oosDays, label: "days tested out of sample" },
    { value: p.dataset.symbols, label: "synthetic symbols" },
  ];

  useKinetic(({ gsap, MOTION_OK, SplitText, EXPO }, late) => {
    const el = root.current;
    if (!el) return;
    if (late) entered = true; // the headline is already on screen; never hide it to replay an intro
    const mm = gsap.matchMedia();
    mm.add(MOTION_OK, () => {
      const h1 = el.querySelector(".qf-hero-title");
      // Scroll storytelling: the backdrop curves drift and the headline eases back as you leave.
      gsap.to(el.querySelector(".qf-hero-curves"), {
        yPercent: 18,
        ease: "none",
        scrollTrigger: { trigger: el, start: "top top", end: "bottom top", scrub: true },
      });
      if (entered || !h1) return;
      entered = true;
      const split = SplitText.create(h1, { type: "lines,words,chars", mask: "lines", linesClass: "qf-line" });
      const tl = gsap.timeline({ defaults: { ease: EXPO } });
      tl.from(split.chars, { yPercent: 115, duration: 1.05, stagger: 0.014 })
        .fromTo(
          el.querySelectorAll("[data-curve]"),
          { strokeDasharray: 1, strokeDashoffset: 1 },
          { strokeDashoffset: 0, duration: 2.2, ease: "power2.inOut", stagger: 0.12, clearProps: "strokeDasharray,strokeDashoffset" },
          0,
        )
        .from(el.querySelectorAll("[data-enter]"), { y: 18, opacity: 0, duration: 0.8, stagger: 0.07 }, 0.35);
      // Count the at-a-glance figures up from zero to the published values.
      el.querySelectorAll<HTMLElement>("[data-count]").forEach((node, i) => {
        const target = Number(node.dataset.count);
        const n = { v: 0 };
        tl.to(n, {
          v: target, duration: 1.4, ease: "power2.out",
          onUpdate: () => { node.textContent = Math.round(n.v).toLocaleString("en-US"); },
        }, 0.45 + i * 0.08);
      });
      // If motion is switched off mid-count, leave the published values, never a partial count.
      return () => el.querySelectorAll<HTMLElement>("[data-count]").forEach((node) => {
        node.textContent = Number(node.dataset.count).toLocaleString("en-US");
      });
    });
    return () => mm.revert();
  }, []);

  return (
    <div className="qf-verdict" ref={root}>
      <div className="qf-hero">
        <dl className="qf-hero-meta" data-enter>
          <div><dt>Research note</dt><dd>{run.record.run_id.split("-").slice(-2, -1)[0]?.toUpperCase()}</dd></div>
          <div><dt>Market</dt><dd>Synthetic, seed {p.dataset.seed}</dd></div>
          <div><dt>Completed</dt><dd>{run.record.completed_at ? day(run.record.completed_at) : "Not completed"}</dd></div>
          <div><dt>Regimes</dt><dd>{p.dataset.regime_mix}</dd></div>
        </dl>
        <div className="qf-hero-stage">
          <HeroCurves run={run} />
          <h1 className="qf-hero-title">
            <span className="qf-hero-lead">{lead}</span>{" "}
            {verdict && <em className="qf-hero-verdict">{verdict}</em>}
          </h1>
        </div>
        <div className="qf-hero-foot">
          <div className="qf-hero-copy">
            <p className="qf-prose">
              {summary.headline} A strategy is accepted only if it clears every check: out-of-sample Sharpe above 0.30
              with a t-statistic of at least 2 and above buy-and-hold, a positive sealed holdout after selling everything
              at its last close, a stable parameter neighbourhood, and at least ten completed round trips.
            </p>
            <div className="qf-hero-actions" data-enter>
              <a className="qf-btn qf-btn-primary qf-magnetic" href="#qf-sec-equity" data-scroll-to="equity">Read the evidence</a>
              <a className="qf-btn qf-btn-line qf-magnetic" href={routeHref({ view: "request" })}>Request a run</a>
            </div>
          </div>
          <ul className="qf-stats" aria-label="Run at a glance">
            {stats.map((s) => (
              <li key={s.label} data-enter>
                <span className="qf-stat-value" data-count={s.value}>{s.value.toLocaleString("en-US")}</span>
                <span className="qf-stat-label">{s.label}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="qf-referee">
        <p className="qf-eyebrow">The referee's verdict</p>
        <ol className="qf-verdict-list" aria-label="Verdict per strategy">
          {strategies.map((s, i) => {
            const accepted = s.verdict === "accepted";
            const [first, ...rest] = s.reasons;
            return (
              <li key={s.id} className="qf-verdict-item">
                <span className="qf-verdict-no" aria-hidden>{String(i + 1).padStart(2, "0")}</span>
                <span className={`qf-struck${accepted ? " qf-struck-ok" : ""}`}>
                  <a
                    className="qf-strategy-name"
                    href={routeHref({ view: "strategy", runId: run.record.run_id, strategyId: s.id })}
                  >
                    {s.name}
                    <span className="qf-sr-only">, {accepted ? "accepted" : "rejected"}</span>
                  </a>
                  <PenMark seed={i + 1} accepted={accepted} />
                </span>
                <div className={`qf-margin-note${accepted ? " qf-accepted" : ""}`}>
                  {accepted ? (
                    <p>Accepted: it cleared every check.</p>
                  ) : (
                    <>
                      <p>{first}.</p>
                      {rest.length > 0 && (
                        <Disclosure summary={<span className="qf-more">{rest.length} more {rest.length === 1 ? "reason" : "reasons"}</span>}>
                          <ul style={{ listStyle: "disc", paddingLeft: 18, display: "grid", gap: 4 }}>
                            {rest.map((r) => (
                              <li key={r}>{r}.</li>
                            ))}
                          </ul>
                        </Disclosure>
                      )}
                    </>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
