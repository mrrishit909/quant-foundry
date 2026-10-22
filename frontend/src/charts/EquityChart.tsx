import { type KeyboardEvent, type PointerEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import { Disclosure } from "../components/Controls";
import type { EquityRow } from "../data/types";
import { day, monthYear, money, pct } from "../lib/format";
import { animate, drawStroke } from "../lib/motion";

export interface SeriesDef {
  key: string;
  label: string;
  color: string;
  dash: string;
}

export const SERIES: Record<string, SeriesDef> = {
  trend: { key: "trend", label: "Trend following", color: "var(--qf-s-trend)", dash: "" },
  meanrev: { key: "meanrev", label: "Mean reversion", color: "var(--qf-s-meanrev)", dash: "9 4" },
  breakout: { key: "breakout", label: "Volatility breakout", color: "var(--qf-s-breakout)", dash: "6 3 1.5 3" },
  buyhold: { key: "buyhold", label: "Buy and hold", color: "var(--qf-s-buyhold)", dash: "3 3" },
  cash: { key: "cash", label: "Cash", color: "var(--qf-s-cash)", dash: "1 3" },
};

export function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.floor(entry?.contentRect.width ?? 0)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

function niceTicks(min: number, max: number, count: number): number[] {
  const span = max - min || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(Number(v.toFixed(10)));
  return out;
}

function drawdown(values: number[]): number[] {
  let peak = -Infinity;
  return values.map((v) => {
    peak = Math.max(peak, v);
    return peak > 0 ? v / peak - 1 : 0;
  });
}

function pathFor(values: number[], x: (i: number) => number, y: (v: number) => number): string {
  let d = "";
  values.forEach((v, i) => {
    if (!Number.isFinite(v)) return;
    d += `${d ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`;
  });
  return d;
}

export function EquityChart({
  rows,
  series,
  visible,
  title,
  showDrawdown = true,
}: {
  rows: EquityRow[];
  series: SeriesDef[];
  visible: Set<string>;
  title: string;
  showDrawdown?: boolean;
}) {
  const [wrap, width] = useWidth<HTMLDivElement>();
  const [cursor, setCursor] = useState<number | null>(null);
  const pathRefs = useRef(new Map<string, SVGPathElement>());
  const previous = useRef<Set<string>>(new Set());
  const hatchId = useId().replace(/:/g, "");
  const shown = series.filter((s) => visible.has(s.key));

  const compact = width < 560;
  const height = compact ? 260 : 340;
  const ddHeight = showDrawdown ? (compact ? 110 : 130) : 0;
  const m = { top: 14, right: compact ? 12 : 112, bottom: 26, left: compact ? 44 : 56 };
  const innerW = Math.max(10, width - m.left - m.right);
  const innerH = height - m.top - m.bottom;

  const holdoutStart = rows.findIndex((r) => r.segment === "holdout");
  const values = useMemo(
    () => Object.fromEntries(series.map((s) => [s.key, rows.map((r) => r.values[s.key] ?? NaN)])),
    [rows, series],
  );
  const dds = useMemo(
    () => Object.fromEntries(series.map((s) => [s.key, drawdown(values[s.key] ?? [])])),
    [values, series],
  );

  const all = shown.flatMap((s) => (values[s.key] ?? []).filter(Number.isFinite));
  const lo = all.length ? Math.min(...all) : 0;
  const hi = all.length ? Math.max(...all) : 1;
  const pad = (hi - lo) * 0.06 || 1;
  const yMin = lo - pad;
  const yMax = hi + pad;
  const x = (i: number) => m.left + (rows.length > 1 ? (i / (rows.length - 1)) * innerW : 0);
  const y = (v: number) => m.top + (1 - (v - yMin) / (yMax - yMin)) * innerH;
  const ddMin = Math.min(-0.05, ...shown.flatMap((s) => dds[s.key] ?? [0]));
  const ddTop = height + 22;
  const ddInner = ddHeight - 30;
  const yd = (v: number) => ddTop + (v / ddMin) * ddInner;

  const yTicks = niceTicks(yMin, yMax, compact ? 3 : 4);
  const xTickCount = compact ? 3 : 6;
  const xTicks = rows.length
    ? Array.from({ length: xTickCount }, (_, k) => Math.round((k / (xTickCount - 1)) * (rows.length - 1)))
    : [];

  // Draw newly shown series in; the first render draws everything once.
  useEffect(() => {
    if (!width) return;
    for (const s of shown) {
      if (!previous.current.has(s.key)) drawStroke(pathRefs.current.get(s.key) ?? null, 700, 80);
    }
    previous.current = new Set(shown.map((s) => s.key));
  }, [width, shown.map((s) => s.key).join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const ddRef = useRef<SVGGElement>(null);
  useEffect(() => {
    animate(ddRef.current, [{ transform: "scaleY(0)" }, { transform: "scaleY(1)" }], { duration: 280 });
  }, [showDrawdown]);

  // End labels with simple collision avoidance.
  const labels = shown
    .map((s) => {
      const vals = values[s.key] ?? [];
      const last = vals[vals.length - 1] ?? NaN;
      return { s, y: y(last), last };
    })
    .filter((l) => Number.isFinite(l.last))
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++) {
    const prev = labels[i - 1]!;
    if (labels[i]!.y - prev.y < 14) labels[i]!.y = prev.y + 14;
  }

  const setFromPointer = (e: PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const frac = (e.clientX - box.left) / box.width;
    setCursor(Math.max(0, Math.min(rows.length - 1, Math.round(frac * (rows.length - 1)))));
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 21 : 1;
    const cur = cursor ?? rows.length - 1;
    const next =
      e.key === "ArrowLeft" ? cur - step : e.key === "ArrowRight" ? cur + step : e.key === "Home" ? 0 : e.key === "End" ? rows.length - 1 : e.key === "Escape" ? null : undefined;
    if (next === undefined) return;
    e.preventDefault();
    setCursor(next === null ? null : Math.max(0, Math.min(rows.length - 1, next)));
  };

  const at = cursor ?? null;
  const summary = shown
    .map((s) => {
      const vals = values[s.key] ?? [];
      const last = vals[vals.length - 1];
      return `${s.label} ends at ${money(last ?? NaN)}`;
    })
    .join("; ");
  const sample = rows.filter((_, i) => i % 21 === 0 || i === rows.length - 1);

  return (
    <figure className="qf-chart" style={{ display: "grid", gap: 10 }}>
      <div className="qf-readout" aria-live="polite">
        {at === null ? (
          <span>Move across the chart, or focus it and use the arrow keys, to read exact values.</span>
        ) : (
          <>
            <strong>{day(rows[at]!.date)}</strong>
            <span>{rows[at]!.segment === "holdout" ? "Holdout" : "Out of sample"}</span>
            {shown.map((s) => (
              <span key={s.key}>
                {s.label} <strong className="qf-num">{money(values[s.key]?.[at] ?? NaN)}</strong>
                {showDrawdown && <> ({pct(dds[s.key]?.[at] ?? NaN)})</>}
              </span>
            ))}
          </>
        )}
      </div>
      <div
        ref={wrap}
        tabIndex={0}
        role="group"
        aria-roledescription="interactive chart"
        aria-label={`${title}. ${summary}. Holdout starts ${holdoutStart >= 0 ? day(rows[holdoutStart]!.date) : "n/a"}.`}
        onKeyDown={onKey}
        onBlur={() => setCursor(null)}
        style={{ outlineOffset: 6 }}
      >
        {width > 0 && (
          <svg className="qf-chart-svg" width={width} height={height + ddHeight} viewBox={`0 0 ${width} ${height + ddHeight}`} aria-hidden>
            <defs>
              <pattern id={hatchId} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <line className="qf-hatch-line" x1="0" y1="0" x2="0" y2="7" />
              </pattern>
            </defs>
            {holdoutStart >= 0 && (
              <g>
                <rect
                  x={x(holdoutStart)}
                  y={m.top}
                  width={x(rows.length - 1) - x(holdoutStart)}
                  height={innerH + ddHeight}
                  fill={`url(#${hatchId})`}
                />
                <line className="qf-zero" x1={x(holdoutStart)} x2={x(holdoutStart)} y1={m.top} y2={height + ddHeight - 22} />
                <text
                  className="qf-holdout-label"
                  x={compact ? x(rows.length - 1) - 4 : x(holdoutStart) + 6}
                  y={m.top + 14}
                  textAnchor={compact ? "end" : "start"}
                >
                  {compact ? "Holdout" : "Holdout, evaluated once"}
                </text>
              </g>
            )}
            <g className="qf-grid">
              {yTicks.map((t) => (
                <line key={t} x1={m.left} x2={m.left + innerW} y1={y(t)} y2={y(t)} />
              ))}
            </g>
            <g className="qf-axis">
              {yTicks.map((t) => (
                <text key={t} x={m.left - 8} y={y(t) + 4} textAnchor="end">
                  {t >= 1000 ? `${Math.round(t / 1000)}k` : t}
                </text>
              ))}
              {xTicks.map((i) => (
                <text key={i} x={x(i)} y={height - 6} textAnchor={i === 0 ? "start" : i === rows.length - 1 ? "end" : "middle"}>
                  {monthYear(rows[i]!.date)}
                </text>
              ))}
            </g>
            {shown.map((s) => (
              <path
                key={s.key}
                ref={(el) => {
                  if (el) pathRefs.current.set(s.key, el);
                  else pathRefs.current.delete(s.key);
                }}
                className="qf-series"
                d={pathFor(values[s.key] ?? [], x, y)}
                stroke={s.color}
                strokeDasharray={s.dash || undefined}
              />
            ))}
            {!compact &&
              labels.map((l) => (
                <text key={l.s.key} className="qf-series-label" x={m.left + innerW + 8} y={l.y + 4} fill={l.s.color}>
                  {l.s.label}
                </text>
              ))}
            {showDrawdown && (
              <g ref={ddRef} style={{ transformOrigin: `0 ${ddTop}px` }}>
                <text className="qf-holdout-label" x={m.left} y={ddTop - 2}>
                  Drawdown from the running peak
                </text>
                <line className="qf-zero" x1={m.left} x2={m.left + innerW} y1={ddTop + 4} y2={ddTop + 4} />
                <g className="qf-axis">
                  <text x={m.left - 8} y={ddTop + 8} textAnchor="end">0%</text>
                  <text x={m.left - 8} y={yd(ddMin) + 4} textAnchor="end">{pct(ddMin, 0)}</text>
                </g>
                {shown.map((s) => (
                  <path
                    key={s.key}
                    className="qf-series"
                    d={pathFor(dds[s.key] ?? [], x, (v) => yd(v) + 4)}
                    stroke={s.color}
                    strokeDasharray={s.dash || undefined}
                    strokeWidth={1.2}
                  />
                ))}
              </g>
            )}
            {at !== null && (
              <line className="qf-crosshair" x1={x(at)} x2={x(at)} y1={m.top} y2={height + ddHeight - 22} />
            )}
            <rect
              x={m.left}
              y={m.top}
              width={innerW}
              height={innerH + ddHeight}
              fill="transparent"
              onPointerMove={setFromPointer}
              onPointerDown={setFromPointer}
              onPointerLeave={(e) => e.pointerType === "mouse" && setCursor(null)}
            />
          </svg>
        )}
      </div>
      <figcaption className="qf-small">{title}</figcaption>
      <Disclosure summary="Show the values as a table (every 21st trading day)">
        <div className="qf-table-wrap" tabIndex={0} role="region" aria-label="Table, scrolls sideways when narrow">
          <table className="qf-table">
            <caption className="qf-sr-only">{title}</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Segment</th>
                {shown.map((s) => (
                  <th key={s.key} scope="col">{s.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sample.map((r) => (
                <tr key={r.date}>
                  <td>{day(r.date)}</td>
                  <td>{r.segment === "holdout" ? "Holdout" : "Out of sample"}</td>
                  {shown.map((s) => (
                    <td key={s.key} className="qf-num">{money(r.values[s.key] ?? NaN)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Disclosure>
    </figure>
  );
}

export function Legend({
  series,
  visible,
  onToggle,
}: {
  series: SeriesDef[];
  visible: Set<string>;
  onToggle: (key: string) => void;
}) {
  return (
    <div className="qf-legend" role="group" aria-label="Series shown on the chart">
      {series.map((s) => (
        <button key={s.key} type="button" aria-pressed={visible.has(s.key)} onClick={() => onToggle(s.key)}>
          <svg className="qf-swatch" viewBox="0 0 26 10" aria-hidden>
            <line x1="1" x2="25" y1="5" y2="5" stroke={s.color} strokeWidth="2.4" strokeDasharray={s.dash || undefined} />
          </svg>
          {s.label}
        </button>
      ))}
    </div>
  );
}
