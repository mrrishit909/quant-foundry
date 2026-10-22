export interface Metrics {
  total_return: number;
  cagr: number;
  volatility: number;
  sharpe: number;
  max_drawdown: number;
  trades: number;
  round_trips?: number;
  days?: number;
  turnover: number;
  fees_paid: number;
  slippage_paid: number;
  exposure: number;
}

export type Params = Record<string, number>;

export interface StrategyResult {
  id: string;
  name: string;
  verdict: "accepted" | "rejected";
  reasons: string[];
  oos_metrics: Metrics;
  holdout_metrics: Metrics;
  frozen_params: Params;
  stability: number;
  chosen_rank: number;
}

export interface Results {
  generated_by: string;
  strategies: StrategyResult[];
  benchmarks: Record<"buyhold" | "cash", { oos: Metrics; holdout: Metrics }>;
  summary: { accepted: number; rejected: number; headline: string };
}

export interface Snapshot {
  project: string;
  mode: "state-snapshot" | "fixture";
  generated_at: string;
  source_commit: string;
  state_commit: string;
  latest_run_id: string | null;
  runs_included: string[];
  stale_after_hours: number;
  state_branch_url: string;
  files?: { release: boolean; memory: boolean };
}

export interface IndexEntry {
  run_id: string;
  request_id: string;
  status: "queued" | "running" | "completed" | "failed" | "blocked" | "cancelled";
  attempt: number;
  created_at: string;
  completed_at: string | null;
  source: string;
  issue: number | null;
  headline: string | null;
}

export interface RunRecord {
  run_id: string;
  request_id: string;
  workflow_run_id: number | null;
  source_commit: string;
  input_manifest_hash: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  status: IndexEntry["status"];
  attempt: number;
  parent_run_id: string | null;
  result_paths: string[];
  evidence_paths: string[];
  error_summary: string | null;
  resource_usage_summary: { wall_seconds: number | null; output_bytes: number | null };
  request_source: { type: string; issue_number: number | null; actor: string | null };
}

export interface RequestParams {
  dataset: { kind: string; seed: number; symbols: number; days: number; regime_mix: string };
  strategies: string[];
  costs: { fee_bps: number; slippage_bps: number };
  walk_forward: { train_days: number; test_days: number };
  holdout_fraction: number;
  allow_short: boolean;
}

export interface Manifest {
  params: RequestParams;
  dataset: Record<string, unknown> & { sha256: string; rows: number; start: string; end: string };
  input_manifest_hash: string;
  package_version: string;
}

export interface WalkWindow {
  index: number;
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
}

export interface WalkForward {
  windows: WalkWindow[];
  strategies: Record<string, { window: number; chosen_params: Params; in_sample: Metrics; out_of_sample: Metrics }[]>;
}

export interface Sensitivity {
  strategies: Record<
    string,
    {
      best_oos_sharpe: number;
      chosen_rank: number;
      combos: { params: Params; metrics: Metrics }[];
      frozen_params: Params;
      grid_size: number;
      stability: number;
      tolerance: number;
      within_tolerance: number;
    }
  >;
}

export interface Holdout {
  span: [string, string];
  sealed: boolean;
  selection_frozen_before_holdout: boolean;
  evaluations: { strategy: string; frozen_params: Params; metrics: Metrics }[];
}

export interface HoldoutAudit {
  dataset_sha256: string;
  strategies: { strategy: string; prior_evaluations: number; contaminated: boolean; prior_runs: string[] }[];
}

export interface QualityCheck {
  name: string;
  status: "pass" | "warn" | "fail";
  detail: unknown;
}

export interface DataQuality {
  status: "pass" | "warn" | "fail";
  rows: number;
  symbols: string[];
  checks: QualityCheck[];
}

export type Assumptions = Record<string, { text: string } & Record<string, unknown>>;

export interface StrategySpec {
  id: string;
  name: string;
  description: string;
  params_grid: Params[];
  signal_timing: string;
  warmup_rule: string;
  long_only: boolean;
}

export interface Checks {
  accounting: { backtests_checked: number; max_abs_error: number; passed: boolean; tolerance: number };
  lookahead_probe: { cutoff_date: string; passed: boolean };
  holdout: { evaluated_once: boolean; selection_frozen_before_holdout: boolean };
  determinism: { note: string };
  missing_data_events: unknown[];
}

export interface EquityRow {
  date: string;
  segment: "out_of_sample" | "holdout";
  values: Record<string, number>;
}

export interface Trade {
  date: string;
  strategy: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  ref_open: number;
  fill_price: number;
  fee: number;
  slippage_cost: number;
  segment: string;
  window: string;
}

export interface Release {
  release_id: string;
  status: "released" | "blocked";
  source_commit: string;
  created_at: string;
  findings: { id: string; title: string; status: "pass" | "fail"; detail: string }[];
  subjective: { status: string; reason?: string; scores: { criterion: string; score: number }[] };
}

/** Everything loaded for one run. Optional parts may be missing in older runs. */
export interface RunBundle {
  record: RunRecord;
  manifest: Manifest;
  results: Results;
  walkforward: WalkForward;
  sensitivity: Sensitivity;
  holdout: Holdout;
  audit: HoldoutAudit | null;
  quality: DataQuality;
  assumptions: Assumptions;
  strategies: StrategySpec[];
  checks: Checks;
  equity: EquityRow[];
  trades: Trade[];
  reportUrl: string;
}
