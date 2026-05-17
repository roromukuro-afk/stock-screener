// API クライアント — localhost を直書きしない
// NEXT_PUBLIC_API_BASE_URL を本番ではVercel等の環境変数で設定する
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

export const API_BASE_URL = API_BASE;

export async function fetchAPI(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `API error: ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => fetchAPI("/api/health"),
  status: () => fetchAPI("/api/status"),
  dashboard: () => fetchAPI("/api/dashboard"),
  universe: () => fetchAPI("/api/universe"),
  runScreening: (params: object) =>
    fetchAPI("/api/screening/run", { method: "POST", body: JSON.stringify(params) }),
  screeningProgress: () => fetchAPI("/api/screening/progress"),
  screeningResults: (params?: { classification?: string; market?: string; min_score?: number; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.classification) qs.set("classification", params.classification);
    if (params?.market) qs.set("market", params.market);
    if (params?.min_score) qs.set("min_score", String(params.min_score));
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    return fetchAPI(`/api/screening/results?${qs}`);
  },
  screeningExclusions: (limit = 500) => fetchAPI(`/api/screening/exclusions?limit=${limit}`),
  stock: (symbol: string) => fetchAPI(`/api/stocks/${encodeURIComponent(symbol)}`),
  stockChart: (symbol: string, period = "3mo") =>
    fetchAPI(`/api/stocks/${encodeURIComponent(symbol)}/chart?period=${period}`),
  stockAAR: (symbol: string) => fetchAPI(`/api/stocks/${encodeURIComponent(symbol)}/aar`),
  exclusions: () => fetchAPI("/api/exclusions"),
  addExclusion: (item: object) =>
    fetchAPI("/api/exclusions", { method: "POST", body: JSON.stringify(item) }),
  deleteExclusion: (symbol: string) =>
    fetchAPI(`/api/exclusions/${encodeURIComponent(symbol)}`, { method: "DELETE" }),
  bulkExclusions: (items: object[]) =>
    fetchAPI("/api/exclusions/bulk", { method: "POST", body: JSON.stringify(items) }),
  uploadExclusions: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API_BASE}/api/exclusions/upload`, { method: "POST", body: form }).then((r) => r.json());
  },
  exportCsv: (classification?: string) => {
    const qs = classification ? `?classification=${encodeURIComponent(classification)}` : "";
    if (typeof window !== "undefined") window.open(`${API_BASE}/api/export/csv${qs}`, "_blank");
  },
  exportExcel: () => {
    if (typeof window !== "undefined") window.open(`${API_BASE}/api/export/excel`, "_blank");
  },
  exportAARCsv: () => {
    if (typeof window !== "undefined") window.open(`${API_BASE}/api/export/aar/csv`, "_blank");
  },
  runBacktest: (symbols?: string[]) =>
    fetchAPI("/api/backtest/run", { method: "POST", body: JSON.stringify({ symbols }) }),
  backtestResults: () => fetchAPI("/api/backtest/results"),
  // universe
  universeSummary: () => fetchAPI("/api/universe/summary"),
  universeUpdate: () => fetchAPI("/api/universe/update", { method: "POST", body: "{}" }),
  universeUpdateJpx: () => fetchAPI("/api/universe/update/jpx", { method: "POST", body: "{}" }),
  universeUpdateNasdaq: () => fetchAPI("/api/universe/update/nasdaq", { method: "POST", body: "{}" }),
  universeUpdateOther: () => fetchAPI("/api/universe/update/other-listed", { method: "POST", body: "{}" }),
  universeProgress: () => fetchAPI("/api/universe/update/progress"),
  universeList: (params?: { eligible_only?: boolean; market?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.eligible_only) qs.set("eligible_only", "true");
    if (params?.market) qs.set("market", params.market);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    return fetchAPI(`/api/universe/list?${qs}`);
  },
  universeRefreshPrices: (params: { markets?: string[]; include_adr?: boolean; max_symbols?: number }) =>
    fetchAPI("/api/universe/refresh-prices", { method: "POST", body: JSON.stringify(params) }),
  universeRefreshProgress: () => fetchAPI("/api/universe/refresh-progress"),
  universeStalePrices: (limit = 500) => fetchAPI(`/api/universe/stale-prices?limit=${limit}`),
  // settings
  settings: () => fetchAPI("/api/settings"),
  saveSetting: (key: string, value: string) =>
    fetchAPI("/api/settings", { method: "POST", body: JSON.stringify({ key, value }) }),
  saveSettingsBulk: (settings: Record<string, string>) =>
    fetchAPI("/api/settings/bulk", { method: "POST", body: JSON.stringify({ settings }) }),
  deployStatus: () => fetchAPI("/api/settings/deploy-status"),
};
