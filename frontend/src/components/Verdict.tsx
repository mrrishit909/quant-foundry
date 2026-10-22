import { useEffect, useRef } from "react";
import type { RunBundle } from "../data/types";
import { countWord } from "../lib/format";
import { animate, drawStroke, prefersReducedMotion } from "../lib/motion";
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
  const w = Math.max(20, width * 1.08);
  return (
    <span ref={ref} aria-hidden style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      {width > 0 && (
        <svg
          className={`qf-strike${accepted ? " qf-accept-mark" : ""}`}
          width={w}
          height={18}
          viewBox={`0 0 ${w} 18`}
          style={accepted ? { top: "auto", bottom: -12, transform: "none" } : undefined}
          data-pen
        >
          <path d={wobble(w, seed)} />
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

export function Verdict({ run }: { run: RunBundle }) {
  const root = useRef<HTMLDivElement>(null);
  const { strategies, summary } = run.results;

  useEffect(() => {
    const el = root.current;
    if (!el || entered) return;
    entered = true;
    if (prefersReducedMotion()) return;
    const lines = el.querySelectorAll("[data-enter]");
    lines.forEach((node, i) =>
      animate(node, [{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], {
        duration: 240,
        delay: i * 60,
      }),
    );
    // Strikes need their measured width; wait one frame for the pen SVGs to mount.
    requestAnimationFrame(() => {
      el.querySelectorAll<SVGPathElement>("[data-pen] path").forEach((p, i) => drawStroke(p, 420, 300 + i * 140));
      el.querySelectorAll("[data-note]").forEach((n, i) =>
        animate(n, [{ opacity: 0 }, { opacity: 1 }], { duration: 260, delay: 520 + i * 140 }),
      );
    });
  }, []);

  return (
    <div className="qf-verdict" ref={root}>
      <h1 className="qf-h1" data-enter>
        {headline(strategies.length, summary.accepted)}
      </h1>
      <p className="qf-prose" data-enter>
        {summary.headline} A strategy is accepted only if it clears every check: out-of-sample Sharpe above 0.30
        with a t-statistic of at least 2 and above buy-and-hold, a positive sealed holdout after selling everything
        at its last close, a stable parameter neighbourhood, and at least ten completed round trips.
      </p>
      <ol className="qf-verdict-list" aria-label="Verdict per strategy">
        {strategies.map((s, i) => {
          const accepted = s.verdict === "accepted";
          const [first, ...rest] = s.reasons;
          return (
            <li key={s.id} className="qf-verdict-item" data-enter>
              <span className="qf-struck">
                <a
                  className="qf-strategy-name"
                  href={routeHref({ view: "strategy", runId: run.record.run_id, strategyId: s.id })}
                >
                  {s.name}
                  <span className="qf-sr-only">, {accepted ? "accepted" : "rejected"}</span>
                </a>
                <PenMark seed={i + 1} accepted={accepted} />
              </span>
              <div className={`qf-margin-note${accepted ? " qf-accepted" : ""}`} data-note>
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
  );
}
