"use client";
import { useEffect, useState, useCallback } from "react";
import { fetchAPI, API_BASE_URL } from "@/lib/api";

export default function TrainingBuilderPage() {
  const [summary, setSummary] = useState<any>(null);
  const [quality, setQuality] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [progress, setProgress] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const [markets, setMarkets] = useState<string[]>(["JP"]);
  const [includeAdr, setIncludeAdr] = useState(true);
  const [maxSymbols, setMaxSymbols] = useState(30);
  const [chunkSize, setChunkSize] = useState(15);
  const [surgeThreshold, setSurgeThreshold] = useState(20);
  const [semiThreshold, setSemiThreshold] = useState(15);
  const [negRatio, setNegRatio] = useState(3);

  const load = useCallback(async () => {
    try {
      const [s, q, p, st] = await Promise.all([
        fetchAPI("/api/training-builder/summary"),
        fetchAPI("/api/training-builder/quality-report"),
        fetchAPI("/api/training-builder/progress"),
        fetchAPI("/api/training-builder/feature-stats"),
      ]);
      setSummary(s); setQuality(q); setProgress(p); setStats(st);
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

  const buildAll = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await fetchAPI("/api/training-builder/build-all", {
        method: "POST",
        body: JSON.stringify({
          markets, include_adr: includeAdr,
          max_symbols: maxSymbols, chunk_size: chunkSize,
          surge_threshold_percent: surgeThreshold,
          semi_surge_threshold_percent: semiThreshold,
          negative_sample_ratio: negRatio,
        }),
      });
      setMsg(r.message);
    } catch (e: any) {
      setMsg(`エラー: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const toggleMarket = (m: string) => {
    setMarkets((cur) => cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m]);
  };

  if (error) return <div className="card p-6 max-w-2xl mx-auto"><p className="text-red-600">エラー: {error}</p></div>;
  if (!summary) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;

  const StatCard = ({ label, value, color = "text-gray-900", sub }: any) => (
    <div className="card p-3">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-xl font-bold ${color}`}>{typeof value === "number" ? value.toLocaleString() : value}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  );

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #4a044e 0%, #701a75 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">🏗 過去5年教師データ構築</h1>
        <p className="text-pink-200 text-sm">急騰銘柄だけでなく、急騰前夜似で不発・上がり切り失敗・材料弱い失敗・材料出尽くしを negative case として収集します。</p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ 投資助言ではありません。サバイバーシップバイアスを避けた分析・学習目的のデータベースです。
        </div>
      </div>

      {/* パラメータ */}
      <div className="card p-5">
        <h2 className="font-bold text-gray-800 mb-3">パラメータ</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <div>
            <label className="text-xs text-gray-500">対象市場</label>
            <div className="flex gap-2 mt-1">
              {["JP", "US"].map((m) => (
                <label key={m} className="flex items-center gap-1 text-sm">
                  <input type="checkbox" checked={markets.includes(m)} onChange={() => toggleMarket(m)} /> {m}
                </label>
              ))}
              <label className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={includeAdr} onChange={(e) => setIncludeAdr(e.target.checked)} /> ADR
              </label>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-500">最大銘柄数 (Render Free対策)</label>
            <input type="number" value={maxSymbols} onChange={(e) => setMaxSymbols(parseInt(e.target.value) || 0)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-500">chunk size</label>
            <input type="number" value={chunkSize} onChange={(e) => setChunkSize(parseInt(e.target.value) || 0)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-500">急騰閾値 / 準閾値 (%)</label>
            <div className="flex gap-2">
              <input type="number" value={surgeThreshold} onChange={(e) => setSurgeThreshold(parseFloat(e.target.value) || 0)}
                className="w-full border border-gray-200 rounded px-3 py-2 text-sm" />
              <input type="number" value={semiThreshold} onChange={(e) => setSemiThreshold(parseFloat(e.target.value) || 0)}
                className="w-full border border-gray-200 rounded px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-500">negative_sample_ratio (1positiveに対し)</label>
            <input type="number" step="0.5" value={negRatio} onChange={(e) => setNegRatio(parseFloat(e.target.value) || 0)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm" />
          </div>
        </div>

        <button onClick={buildAll} disabled={busy || progress?.running}
          className="px-6 py-2.5 bg-fuchsia-600 text-white rounded font-bold text-sm hover:bg-fuchsia-700 disabled:opacity-50">
          {busy ? "起動中..." : "🏗 過去5年データ構築を実行 (fetch → 急騰検出 → negative生成 → 特徴量)"}
        </button>
        {msg && <p className="mt-2 text-sm text-gray-600">{msg}</p>}
        <a href={`${API_BASE_URL}/api/training-builder/export/csv`} target="_blank"
          className="inline-block mt-2 ml-2 px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200">
          📄 特徴量CSV出力
        </a>
      </div>

      {/* 進捗 */}
      {progress && progress.total_symbols > 0 && (
        <div className="card p-4">
          <div className="flex justify-between text-sm mb-2">
            <span>{progress.running ? `⚡ ${progress.phase || "running"}` : "完了"}: {progress.processed_symbols}/{progress.total_symbols}</span>
            <span className="text-xs text-gray-500">current: {progress.current_symbol || "-"}</span>
          </div>
          <div className="bg-gray-100 rounded-full h-2 mb-2">
            <div className="h-2 rounded-full bg-fuchsia-500"
              style={{ width: `${(progress.processed_symbols / Math.max(1, progress.total_symbols) * 100)}%` }} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <div>fetched_rows: <strong>{progress.fetched_rows}</strong></div>
            <div>surge_events: <strong className="text-green-600">{progress.surge_events_found}</strong></div>
            <div>negative_cases: <strong className="text-red-600">{progress.negative_cases_found}</strong></div>
            <div>feature_vectors: <strong className="text-blue-600">{progress.feature_vectors_created}</strong></div>
          </div>
        </div>
      )}

      {/* サマリ */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard label="historical OHLCV行" value={summary.ohlcv_rows} sub={`${summary.ohlcv_symbols}銘柄`} />
        <StatCard label="surge_events" value={summary.surge_events_count} color="text-purple-600" />
        <StatCard label="positive_surge" value={summary.positive_surge_count} color="text-green-600" sub="+20%以上" />
        <StatCard label="semi_surge" value={summary.semi_surge_count} color="text-blue-600" sub="+15-20%" />
        <StatCard label="training_feature_vectors" value={summary.training_feature_vectors} color="text-fuchsia-600" />
        <StatCard label="P/N比率" value={summary.positive_negative_ratio} color={summary.positive_negative_ratio >= 1 ? "text-green-600" : "text-orange-500"} sub="negative/positive" />
      </div>

      {/* ケースタイプ別 */}
      <div className="card p-4">
        <h3 className="font-bold text-gray-800 mb-3">ケースタイプ別件数</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          {Object.entries(summary.by_case_type || {}).map(([k, v]: [string, any]) => (
            <div key={k} className={`px-3 py-2 rounded border ${
              k.startsWith("positive") ? "bg-green-50 border-green-200 text-green-700" :
              k.startsWith("failed_overextended") ? "bg-orange-50 border-orange-200 text-orange-700" :
              k.startsWith("failed_weak") ? "bg-yellow-50 border-yellow-200 text-yellow-700" :
              k.startsWith("failed_material_exhaustion") ? "bg-rose-50 border-rose-200 text-rose-700" :
              k.startsWith("failed") ? "bg-red-50 border-red-200 text-red-700" :
              k.startsWith("negative") ? "bg-gray-50 border-gray-200 text-gray-700" :
              "bg-blue-50 border-blue-200 text-blue-700"
            }`}>
              <p className="text-xs">{k}</p>
              <p className="font-bold text-lg">{v}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 品質チェック */}
      {quality && quality.total_feature_vectors > 0 && (
        <div className="card p-4">
          <h3 className="font-bold text-gray-800 mb-3">📊 データ品質レポート</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
            <div>
              <p className="text-xs text-gray-500">品質スコア</p>
              <p className={`text-2xl font-bold ${quality.quality_score >= 80 ? "text-green-600" : quality.quality_score >= 60 ? "text-yellow-600" : "text-red-500"}`}>
                {quality.quality_score}/100
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">T0リーク</p>
              <p className="font-bold">{quality.leakage_check_pass ? "✅ pass" : "❌ fail"}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">重複</p>
              <p className={`font-bold ${quality.duplicate_case_count > 0 ? "text-orange-500" : "text-green-600"}`}>{quality.duplicate_case_count}件</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">極端値</p>
              <p className={`font-bold ${quality.extreme_outlier_count > 0 ? "text-orange-500" : "text-green-600"}`}>{quality.extreme_outlier_count}件</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">価格欠損</p>
              <p className={`font-bold ${quality.missing_price_count > 0 ? "text-orange-500" : "text-green-600"}`}>{quality.missing_price_count}件</p>
            </div>
          </div>
          {quality.warnings && quality.warnings.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded p-2 text-xs">
              <p className="font-bold text-yellow-800 mb-1">警告:</p>
              <ul className="list-disc ml-5 text-yellow-700">
                {quality.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* 特徴量分析 */}
      {stats && stats.n_positive >= 0 && (
        <div className="card p-4">
          <h3 className="font-bold text-gray-800 mb-3">🔬 ケース別 特徴量平均</h3>
          <p className="text-xs text-gray-500 mb-2">
            positive ({stats.n_positive}) vs negative ({stats.n_negative}) vs overext_failed ({stats.n_overext_failed}) vs weak_material_failed ({stats.n_weak_material_failed}) vs material_exhaustion_failed ({stats.n_material_exhaustion_failed})
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 text-gray-500">
                <tr>
                  <th className="px-2 py-1 text-left">特徴量</th>
                  <th className="px-2 py-1 text-right">positive</th>
                  <th className="px-2 py-1 text-right">negative</th>
                  <th className="px-2 py-1 text-right">overext失敗</th>
                  <th className="px-2 py-1 text-right">材料弱失敗</th>
                  <th className="px-2 py-1 text-right">材料出尽くし</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(stats.positive_avg || {}).map((k) => (
                  <tr key={k} className="border-b border-gray-50">
                    <td className="px-2 py-1 font-mono text-xs">{k}</td>
                    <td className="px-2 py-1 text-right text-green-600 font-medium">{stats.positive_avg[k] ?? "-"}</td>
                    <td className="px-2 py-1 text-right text-gray-600">{stats.negative_avg?.[k] ?? "-"}</td>
                    <td className="px-2 py-1 text-right text-orange-600">{stats.overextended_failed_avg?.[k] ?? "-"}</td>
                    <td className="px-2 py-1 text-right text-yellow-600">{stats.weak_material_failed_avg?.[k] ?? "-"}</td>
                    <td className="px-2 py-1 text-right text-rose-600">{stats.material_exhaustion_failed_avg?.[k] ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ジョブ履歴 */}
      <div className="card p-4">
        <h3 className="font-bold text-gray-800 mb-3">📝 ジョブ履歴</h3>
        {(summary.recent_jobs || []).length === 0 ? (
          <p className="text-gray-400 text-sm">まだジョブがありません</p>
        ) : (
          <table className="w-full text-xs">
            <thead><tr className="text-gray-500 border-b border-gray-100">
              <th className="px-2 py-1 text-left">id</th>
              <th className="px-2 py-1 text-left">status</th>
              <th className="px-2 py-1 text-left">scope</th>
              <th className="px-2 py-1 text-right">processed</th>
              <th className="px-2 py-1 text-right">rows</th>
              <th className="px-2 py-1 text-right">surges</th>
              <th className="px-2 py-1 text-right">negative</th>
              <th className="px-2 py-1 text-right">features</th>
              <th className="px-2 py-1 text-right">err</th>
              <th className="px-2 py-1 text-left">started</th>
            </tr></thead>
            <tbody>
              {summary.recent_jobs.map((j: any) => (
                <tr key={j.id} className="border-b border-gray-50">
                  <td className="px-2 py-1 font-mono">{j.id}</td>
                  <td className={`px-2 py-1 ${j.status === "completed" ? "text-green-600" : j.status === "failed" ? "text-red-500" : "text-blue-500"}`}>{j.status}</td>
                  <td className="px-2 py-1">{j.market_scope}</td>
                  <td className="px-2 py-1 text-right">{j.processed_symbols}/{j.total_symbols}</td>
                  <td className="px-2 py-1 text-right">{j.fetched_rows}</td>
                  <td className="px-2 py-1 text-right text-green-600">{j.surge_events_found}</td>
                  <td className="px-2 py-1 text-right text-red-600">{j.negative_cases_found}</td>
                  <td className="px-2 py-1 text-right text-fuchsia-600">{j.feature_vectors_created}</td>
                  <td className="px-2 py-1 text-right text-orange-500">{j.error_count}</td>
                  <td className="px-2 py-1 text-gray-400">{j.started_at?.slice(0, 19).replace("T", " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card p-3 text-xs text-gray-500">
        <p>⚠️ サバイバーシップバイアス対策: 急騰銘柄だけでなく、急騰前夜似だが不発 / 上がり切り後反落 / 材料弱い不発 / 材料出尽くし失敗 を negative case として保存します。これらは ranking の `historical_negative_similarity` として現在銘柄スコアに反映されます。</p>
        <p className="text-orange-600 mt-1">⚠️ これは投資助言ではありません。最終判断はユーザー自身が行ってください。</p>
      </div>
    </div>
  );
}
