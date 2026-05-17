"use client";
import { useEffect, useState, useCallback } from "react";
import { fetchAPI, API_BASE_URL } from "@/lib/api";

interface Summary {
  universe: {
    total: number;
    by_market: Record<string, number>;
    by_source: Record<string, number>;
    by_instrument_type: Record<string, number>;
    eligible_count: number;
    common_stock_count: number;
    adr_count: number;
    etf_count: number;
    warrant_count: number;
    unit_count: number;
    right_count: number;
    preferred_count: number;
    test_issue_count: number;
    fund_count: number;
  };
  freshness: {
    total: number;
    fresh_count: number;
    stale_count: number;
    by_freshness_status: Record<string, number>;
  };
  latest_jobs: any[];
}

function StatCard({ label, value, color = "text-gray-900", sub }: { label: string; value: number | string; color?: string; sub?: string }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{typeof value === "number" ? value.toLocaleString() : value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

export default function UniversePage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [progress, setProgress] = useState<any>(null);
  const [refreshProgress, setRefreshProgress] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, p, rp] = await Promise.all([
        fetchAPI("/api/universe/summary"),
        fetchAPI("/api/universe/update/progress").catch(() => null),
        fetchAPI("/api/universe/refresh-progress").catch(() => null),
      ]);
      setSummary(s);
      setProgress(p);
      setRefreshProgress(rp);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const update = async (path: string, label: string) => {
    setBusy(true);
    try {
      await fetchAPI(path, { method: "POST", body: "{}" });
      await load();
    } catch (e: any) {
      alert(`${label}失敗: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const refreshPrices = async (markets: string[] | null, maxSymbols: number) => {
    setBusy(true);
    try {
      await fetchAPI("/api/universe/refresh-prices", {
        method: "POST",
        body: JSON.stringify({ markets, include_adr: true, max_symbols: maxSymbols }),
      });
      await load();
    } catch (e: any) {
      alert(`価格鮮度チェック失敗: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <div className="card p-6 max-w-2xl mx-auto mt-10">
        <p className="text-red-600 font-bold">エラー: {error}</p>
        <p className="text-sm text-gray-500 mt-2">API: {API_BASE_URL}</p>
      </div>
    );
  }

  if (!summary) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;

  const u = summary.universe;
  const f = summary.freshness;
  const isRunning = progress?.running || refreshProgress?.running;

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">🌍 ユニバース管理</h1>
        <p className="text-blue-200 text-sm">JPX (日本株) / NASDAQ listed / Other listed (NYSE等) のデータソースを管理</p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ 投資助言ではありません。分析・学習目的のツールです。
        </div>
      </div>

      {/* 統計 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard label="Raw Universe" value={u.total} sub="全データソース合計" />
        <StatCard label="Eligible (普通株+ADR)" value={u.eligible_count} color="text-green-600" sub="スクリーニング対象" />
        <StatCard label="Common Stock" value={u.common_stock_count} color="text-blue-600" />
        <StatCard label="ADR" value={u.adr_count} color="text-purple-600" />
        <StatCard label="ETF" value={u.etf_count} color="text-gray-500" sub="除外" />
        <StatCard label="Test Issue" value={u.test_issue_count} color="text-red-400" sub="除外" />
        <StatCard label="Warrant" value={u.warrant_count} color="text-orange-500" sub="除外" />
        <StatCard label="Unit" value={u.unit_count} color="text-orange-500" sub="除外" />
        <StatCard label="Right" value={u.right_count} color="text-orange-500" sub="除外" />
        <StatCard label="Preferred" value={u.preferred_count} color="text-orange-500" sub="除外" />
        <StatCard label="Fund" value={u.fund_count} color="text-gray-500" sub="除外" />
        <StatCard label="Fresh Prices" value={f.fresh_count} color="text-green-600" sub={`/ ${f.total}件中`} />
      </div>

      {/* アクション */}
      <div className="card p-5">
        <h2 className="font-bold text-gray-800 mb-3">📥 データソース更新</h2>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => update("/api/universe/update", "全更新")} disabled={busy || isRunning}
            className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
            🌐 全ソース更新 (JPX + NASDAQ + Other)
          </button>
          <button onClick={() => update("/api/universe/update/jpx", "JPX")} disabled={busy || isRunning}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200 disabled:opacity-50">
            🇯🇵 JPXのみ
          </button>
          <button onClick={() => update("/api/universe/update/nasdaq", "NASDAQ")} disabled={busy || isRunning}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200 disabled:opacity-50">
            🇺🇸 NASDAQ listed
          </button>
          <button onClick={() => update("/api/universe/update/other-listed", "Other listed")} disabled={busy || isRunning}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200 disabled:opacity-50">
            🏛 Other listed (NYSE/AMEX/Arca)
          </button>
        </div>
        {progress?.running && (
          <p className="mt-3 text-sm text-blue-600">⚡ 実行中: {progress.message}</p>
        )}
        {progress?.status === "completed" && !progress?.running && (
          <p className="mt-3 text-sm text-green-600">✅ {progress.message}</p>
        )}
        {progress?.status === "failed" && (
          <p className="mt-3 text-sm text-red-600">❌ {progress.message}</p>
        )}
      </div>

      <div className="card p-5">
        <h2 className="font-bold text-gray-800 mb-3">⏱ 価格鮮度チェック</h2>
        <p className="text-xs text-gray-500 mb-3">
          eligible銘柄の最新価格と取引日を取得し、データが古い銘柄(stale)を判定します。Render Freeでは時間がかかるため少量から実行してください。
        </p>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => refreshPrices(["JP"], 100)} disabled={busy || isRunning}
            className="px-4 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700 disabled:opacity-50">
            🇯🇵 JP 100銘柄
          </button>
          <button onClick={() => refreshPrices(["US"], 100)} disabled={busy || isRunning}
            className="px-4 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700 disabled:opacity-50">
            🇺🇸 US 100銘柄
          </button>
          <button onClick={() => refreshPrices(null, 200)} disabled={busy || isRunning}
            className="px-4 py-2 bg-emerald-700 text-white rounded text-sm hover:bg-emerald-800 disabled:opacity-50">
            🌐 全市場 200銘柄
          </button>
        </div>
        {refreshProgress && refreshProgress.total > 0 && (
          <div className="mt-3">
            <div className="flex justify-between text-xs mb-1">
              <span>{refreshProgress.running ? "実行中" : "完了"}: {refreshProgress.processed}/{refreshProgress.total}</span>
              <span>Fresh: {refreshProgress.fresh} / Stale: {refreshProgress.stale} / Failed: {refreshProgress.failed}</span>
            </div>
            <div className="bg-gray-100 rounded-full h-2">
              <div className="h-2 rounded-full bg-emerald-500"
                style={{ width: `${refreshProgress.total > 0 ? (refreshProgress.processed / refreshProgress.total * 100) : 0}%` }} />
            </div>
          </div>
        )}
      </div>

      {/* ソース別 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="card p-4">
          <h3 className="font-bold text-gray-700 mb-3 text-sm">市場別</h3>
          {Object.entries(u.by_market).map(([k, v]) => (
            <div key={k} className="flex justify-between py-1 border-b border-gray-50 text-sm">
              <span className="text-gray-600">{k}</span>
              <span className="font-bold">{v.toLocaleString()}</span>
            </div>
          ))}
        </div>
        <div className="card p-4">
          <h3 className="font-bold text-gray-700 mb-3 text-sm">データソース別</h3>
          {Object.entries(u.by_source).map(([k, v]) => (
            <div key={k} className="flex justify-between py-1 border-b border-gray-50 text-sm">
              <span className="text-gray-600">{k}</span>
              <span className="font-bold">{v.toLocaleString()}</span>
            </div>
          ))}
        </div>
        <div className="card p-4">
          <h3 className="font-bold text-gray-700 mb-3 text-sm">Instrument Type別</h3>
          {Object.entries(u.by_instrument_type).map(([k, v]) => (
            <div key={k} className="flex justify-between py-1 border-b border-gray-50 text-sm">
              <span className="text-gray-600">{k}</span>
              <span className="font-bold">{v.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 鮮度ステータス */}
      <div className="card p-4">
        <h3 className="font-bold text-gray-700 mb-3 text-sm">📊 価格鮮度別件数</h3>
        {Object.keys(f.by_freshness_status).length === 0 ? (
          <p className="text-xs text-gray-400">「価格鮮度チェック」を実行するとここに統計が出ます</p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {Object.entries(f.by_freshness_status).map(([k, v]) => (
              <div key={k} className="bg-gray-50 px-3 py-2 rounded text-xs">
                <p className="text-gray-500">{k}</p>
                <p className="font-bold text-gray-800">{v}件</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ジョブ履歴 */}
      <div className="card p-4">
        <h3 className="font-bold text-gray-700 mb-3 text-sm">📝 更新履歴</h3>
        {(summary.latest_jobs || []).length === 0 ? (
          <p className="text-xs text-gray-400">まだ更新履歴がありません</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-gray-500 border-b border-gray-100">
                <th className="px-2 py-1 text-left">source</th>
                <th className="px-2 py-1 text-left">status</th>
                <th className="px-2 py-1 text-right">raw</th>
                <th className="px-2 py-1 text-right">eligible</th>
                <th className="px-2 py-1 text-right">excluded</th>
                <th className="px-2 py-1 text-left">started</th>
                <th className="px-2 py-1 text-left">finished</th>
              </tr></thead>
              <tbody>
                {summary.latest_jobs.map((j: any) => (
                  <tr key={j.id} className="border-b border-gray-50">
                    <td className="px-2 py-1 font-mono">{j.source}</td>
                    <td className={`px-2 py-1 font-medium ${j.status === "completed" ? "text-green-600" : j.status === "failed" ? "text-red-500" : "text-gray-500"}`}>{j.status}</td>
                    <td className="px-2 py-1 text-right">{j.total_raw_count?.toLocaleString()}</td>
                    <td className="px-2 py-1 text-right">{j.eligible_count?.toLocaleString()}</td>
                    <td className="px-2 py-1 text-right">{j.excluded_count?.toLocaleString()}</td>
                    <td className="px-2 py-1 text-gray-400">{j.started_at?.slice(0,19).replace("T"," ")}</td>
                    <td className="px-2 py-1 text-gray-400">{j.finished_at?.slice(0,19).replace("T"," ") || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <a href={`${API_BASE_URL}/api/universe/export/csv`} target="_blank"
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200">
          📄 ユニバースCSV出力
        </a>
        <a href={`${API_BASE_URL}/api/universe/export/excel`} target="_blank"
          className="px-4 py-2 bg-green-50 text-green-700 rounded text-sm hover:bg-green-100">
          📊 ユニバースExcel出力
        </a>
      </div>
    </div>
  );
}
