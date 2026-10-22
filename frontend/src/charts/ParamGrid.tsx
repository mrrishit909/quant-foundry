import { useMemo } from "react";
import type { Metrics, Params } from "../data/types";
import { fixed } from "../lib/format";

/**
 * Parameter explorer: out-of-sample Sharpe for every grid combination, laid out as a
 * two-parameter grid. Cells are buttons (keyboard and touch), values are always printed, and
 * the frozen choice and best cell carry text badges, so colour is never the only signal.
 */
export function ParamGrid({
  combos,
  frozen,
  selected,
  onSelect,
}: {
  combos: { params: Params; metrics: Metrics }[];
  frozen: Params;
  selected: Params | null;
  onSelect: (p: Params) => void;
}) {
  const keys = Object.keys(combos[0]?.params ?? {});
  const [rowKey = "", colKey = ""] = keys;
  const rowsV = useMemo(() => [...new Set(combos.map((c) => c.params[rowKey]!))].sort((a, b) => a - b), [combos, rowKey]);
  const colsV = useMemo(() => [...new Set(combos.map((c) => c.params[colKey]!))].sort((a, b) => a - b), [combos, colKey]);
  const best = combos.reduce((b, c) => (c.metrics.sharpe > b.metrics.sharpe ? c : b), combos[0]!);
  const maxAbs = Math.max(0.5, ...combos.map((c) => Math.abs(c.metrics.sharpe)));
  const same = (a: Params, b: Params | null) => !!b && keys.every((k) => a[k] === b[k]);

  const fill = (s: number) => {
    const t = Math.min(1, Math.abs(s) / maxAbs);
    const tone = s >= 0 ? "var(--qf-heat-pos)" : "var(--qf-heat-neg)";
    return `color-mix(in srgb, ${tone} ${Math.round(12 + t * 48)}%, var(--qf-raised))`;
  };

  return (
    <div className="qf-heat" role="group" aria-label={`Out-of-sample Sharpe by ${rowKey} and ${colKey}`}>
      <div className="qf-heat-row" style={{ gridTemplateColumns: `72px repeat(${colsV.length}, minmax(0, 1fr))` }}>
        <span className="qf-heat-axis">{rowKey} / {colKey}</span>
        {colsV.map((c) => (
          <span key={c} className="qf-heat-axis" style={{ justifyContent: "center" }}>
            {colKey} {c}
          </span>
        ))}
      </div>
      {rowsV.map((r) => (
        <div key={r} className="qf-heat-row" style={{ gridTemplateColumns: `72px repeat(${colsV.length}, minmax(0, 1fr))` }}>
          <span className="qf-heat-axis">{rowKey} {r}</span>
          {colsV.map((c) => {
            const combo = combos.find((x) => x.params[rowKey] === r && x.params[colKey] === c);
            if (!combo) return <span key={c} className="qf-small" style={{ placeSelf: "center" }}>not in grid</span>;
            const isFrozen = same(combo.params, frozen);
            const isBest = same(combo.params, best.params);
            const label = `${rowKey} ${r}, ${colKey} ${c}: out-of-sample Sharpe ${fixed(combo.metrics.sharpe)}${isFrozen ? ", frozen choice" : ""}${isBest ? ", best in grid" : ""}`;
            return (
              <button
                key={c}
                type="button"
                className="qf-heat-cell qf-num"
                style={{ background: fill(combo.metrics.sharpe) }}
                aria-pressed={same(combo.params, selected)}
                aria-label={label}
                onClick={() => onSelect(combo.params)}
              >
                {fixed(combo.metrics.sharpe)}
                {(isFrozen || isBest) && <span className="qf-badge" aria-hidden>{isFrozen ? "chosen" : "best"}</span>}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
