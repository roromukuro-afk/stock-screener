export interface ScreeningResult {
  symbol: string;
  name: string;
  market: string;
  exchange?: string;
  is_adr?: boolean;
  date: string;
  price: number;
  currency: string;
  jpy_price: number;
  fx_rate?: number;
  fx_rate_timestamp?: string;
  price_timestamp?: string;
  volume?: number;
  volume_avg20?: number;
  volume_ratio?: number;
  turnover?: number;
  ma5?: number;
  ma25?: number;
  ma75?: number;
  ma200?: number;
  ma25_deviation?: number;
  recent_high_20?: number;
  recent_low_20?: number;
  support_line?: number;
  resistance_line?: number;
  upside_to_resistance?: number;
  support_distance?: number;
  price_change_1d?: number;
  price_change_5d?: number;
  price_change_20d?: number;
  rsi?: number;
  atr?: number;
  trend_state?: string;
  range_state?: string;
  candle_state?: string;
  chart_pattern_primary?: string;
  chart_pattern_secondary?: string;
  chart_pattern_warning?: string;
  pattern_confidence?: number;
  volume_cycle_state?: string;
  chart_cycle_state?: string;
  material_status?: string;
  upside_score?: number;
  future_catalyst_score?: number;
  chart_score?: number;
  volume_cycle_score?: number;
  material_theme_score?: number;
  supply_score?: number;
  archetype_score?: number;
  risk_management_score?: number;
  total_score: number;
  classification: string;
  main_archetype?: string;
  sub_archetypes?: string[];
  chart_types?: string[];
  warning_types?: string[];
  warning_flags?: string[];
  exclude_flag?: boolean;
  exclude_reason?: string;
  ai_comment?: string;
}

export interface DashboardData {
  screening_status: string;
  screening_running: boolean;
  started_at?: string;
  finished_at?: string;
  total_universe: number;
  total_results: number;
  total_exclusions: number;
  price_pass: number;
  adopted_count: number;
  conditional_count: number;
  watch_count: number;
  low_score_count: number;
  classification_counts: Record<string, number>;
  vol_cycle_counts: Record<string, number>;
  chart_cycle_counts: Record<string, number>;
  warning_flag_counts: Record<string, number>;
  top_candidates: ScreeningResult[];
  usd_jpy: number;
}

export interface ScreeningProgress {
  running: boolean;
  status: string;
  total: number;
  processed: number;
  failed: number;
  result_count: number;
  exclusion_count: number;
  started_at?: string;
  finished_at?: string;
  error?: string;
}

export interface ChartDataPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma5?: number;
  ma25?: number;
  ma75?: number;
  ma200?: number;
}

export const CLASSIFICATION_COLORS: Record<string, string> = {
  "採用候補": "text-green-600 bg-green-50 border-green-200",
  "条件付き候補": "text-blue-600 bg-blue-50 border-blue-200",
  "監視候補": "text-yellow-600 bg-yellow-50 border-yellow-200",
  "低スコア": "text-gray-500 bg-gray-50 border-gray-200",
  "除外対象": "text-red-500 bg-red-50 border-red-200",
};

export const MARKET_LABELS: Record<string, string> = {
  JP: "日本株",
  US: "米国株",
};
