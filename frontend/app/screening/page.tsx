"use client";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { ScreeningResult, ScreeningProgress } from "@/lib/types";
import ClassificationBadge from "@/components/ClassificationBadge";
import ScoreBar from "@/components/ScoreBar";
import VolCycleBadge from "@/components/VolCycleBadge";

const defaultParams = {
  markets: ["JP", "US"] as string[],
  include_adr: false,
  use_real_data: true,
  price_limit: 3000,
  min_vol_jp: 30000,
  min_vol_us: 100000,
  min_score: 0,
};

export default function ScreeningPage() {
  const [params, setParams] = useState(defaultParams);
  const [progress, setProgress] = useState<ScreeningProgress | null>(null);
  const [results, setResults] = useState<ScreeningResult[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState({ classification: "", market: "", search: "" });
  const [sortKey, setSortKey] = useState("total_score");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollProgress = useCallback(async () => {
    try {
      const p = await api.screeningProgress();
      setProgress(p);
      if (!p.running && p.status === "completed") {
        loadResults();
      }
    } catch (e) {}
  }, []);

  useEffect(() => {
    pollProgress();
    const t = setInterval(pollProgress, 2000);
    return () => clearInterval(t);
  }, [pollProgress]);

  const loadResults = async () => {
    try {
      const r = await api.screeningResults({ limit: 500 });
      setResults(r.results || []);
      setTotal(r.total || 0);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleRun = async () => {
    if (progress?.running) return;
    setLoading(true);
    setError(null);
    try {
      await api.runScreening(params);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleMarket = (m: string) => {
    setParams((p) => ({
      ...p,
      markets: p.markets.includes(m) ? p.markets.filter((x) => x !== m) : [...p.markets, m],
    }));
  };

  const filtered = results
    .filter((r) => {
      if (filter.classification && r.classification !== filter.classification) return false;
      if (filter.market && r.market !== filter.market) return false;
      if (filter.search) {
        const s = filter.search.toLowerCase();
        if (!r.symbol.toLowerCase().includes(s) && !r.name?.toLowerCase().includes(s)) return false;
      }
      return true;
    })
    .sort((a, b) => {
      const aVal = (a as any)[sortKey] ?? 0;
      const bVal = (b as any)[sortKey] ?? 0;
      return sortDir === "desc" ? bVal - aVal : aVal - bVal;
    });

  const pct = progress ? (progress.total > 0 ? Math.round((progress.processed / progress.total) * 100) : 0) : 0;

  return (
    <div className="space-y-5">
      <div className="card p-5">
        <h1 className="text-xl font-bold text-gray-800 mb-4">⚡ 全銘柄スクリーニング</h1>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
          {/* 対象市場 */}
          <div>
            <label className="block text-xs text-gray-500 mb-2 font-medium">対象市場</label>
            <div className="flex gap-2 flex-wrap">
              {["JP", "US"].map((m) => (
                <label key={m} className="flex items-center gap-1 cursor-pointer">
                  <input type="checkbox" checked={params.markets.includes(m)} onChange={() => toggleMarket(m)}
                    className="rounded" />
                  <span className="text-sm">{m === "JP" ? "日本株" : "米国株"}</span>
                </label>
              ))}
              <label className="flex items-center gap-1 cursor-pointer">
                <input type="checkbox" checked={params.include_adr}
                  onChange={(e) => setParams((p) => ({ ...p, include_adr: e.target.checked }))} className="rounded" />
                <span className="text-sm">ADR含む</span>
              </label>
            </div>
          </div>

          {/* 価格上限 */}
          <div>
            <label className="block text-xs text-gray-500 mb-2 font-medium">価格上限 (円換算)</label>
            <div className="flex items-center gap-2">
              <input type="number" value={params.price_limit} step={100}
                onChange={(e) => setParams((p) => ({ ...p, price_limit: Number(e.target.value) }))}
                className="border border-gray-200 rounded px-3 py-1.5 text-sm w-28 focus:ring-2 focus:ring-blue-500 outline-none" />
              <span className="text-sm text-gray-500">円</span>
            </div>
          </div>

          {/* 最低出来高 */}
          <div>
            <label className="block text-xs text-gray-500 mb-2 font-medium">最低出来高</label>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-xs w-12 text-gray-500">日本株</span>
                <input type="number" value={params.min_vol_jp}
                  onChange={(e) => setParams((p) => ({ ...p, min_vol_jp: Number(e.target.value) }))}
                  className="border border-gray-200 rounded px-2 py-1 text-xs w-28 focus:ring-2 focus:ring-blue-500 outline-none" />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs w-12 text-gray-500">米国株</span>
                <input type="number" value={params.min_vol_us}
                  onChange={(e) => setParams((p) => ({ ...p, min_vol_us: Number(e.target.value) }))}
                  className="border border-gray-200 rounded px-2 py-1 text-xs w-28 focus:ring-2 focus:ring-blue-500 outline-none" />
              </div>
            </div>
          </div>

          {/* データモード */}
          <div>
            <label className="block text-xs text-gray-500 mb-2 font-medium">データモード</label>
            <div className="flex gap-3">
              {[true, false].map((v) => (
                <label key={String(v)} className="flex items-center gap-1 cursor-pointer">
                  <input type="radio" checked={params.use_real_data === v}
                    onChange={() => setParams((p) => ({ ...p, use_real_data: v }))} />
                  <span className="text-sm">{v ? "実データ" : "サンプル"}</span>
                </label>
              ))}
            </div>
            {!params.use_real_data && <p className="text-xs text-orange-500 mt-1">サンプルデータ使用中</p>}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button onClick={handleRun} disabled={progress?.running || loading || params.markets.length === 0}
            className="px-6 py-2.5 bg-green-600 text-white rounded-lg text-sm font-bold hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
            {progress?.running ? "⚡ 実行中..." : "🚀 全銘柄スクリーニング実行"}
          </button>
          <button onClick={() => { api.exportCsv(); }}
            className="px-4 py-2.5 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 transition-colors">
            📄 CSV出力
          </button>
          <button onClick={() => { api.exportExcel(); }}
            className="px-4 py-2.5 bg-green-50 text-green-700 rounded-lg text-sm hover:bg-green-100 transition-colors">
            📊 Excel出力
          </button>
        </div>

        {error && <p className="mt-3 text-red-600 text-sm bg-red-50 px-3 py-2 rounded">{error}</p>}
      </div>

      {/* Progress bar */}
      {progress && (progress.running || progress.status === "completed") && (
        <div className="card p-4">
          <div className="flex justify-between text-sm mb-2">
            <span className="font-medium">
              {progress.running ? "⚡ スクリーニング中..." : "✅ 完了"}
            </span>
            <span className="text-gray-500">
              {progress.processed} / {progress.total} ({progress.failed}件失敗)
            </span>
          </div>
          <div className="bg-gray-100 rounded-full h-3">
            <div className="h-3 rounded-full bg-green-500 transition-all" style={{ width: `${pct}%` }} />
          </div>
          <div className="flex gap-4 mt-2 text-xs text-gray-500">
            <span>結果: {progress.result_count}件</span>
            <span>除外: {progress.exclusion_count}件</span>
            {progress.error && <span className="text-red-500">エラー: {progress.error}</span>}
          </div>
        </div>
      )}

      {/* Filters */}
      {results.length > 0 && (
        <div className="card p-4 flex flex-wrap gap-3 items-center">
          <input placeholder="銘柄コード・名称検索" value={filter.search}
            onChange={(e) => setFilter((f) => ({ ...f, search: e.target.value }))}
            className="border border-gray-200 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none w-48" />
          <select value={filter.classification} onChange={(e) => setFilter((f) => ({ ...f, classification: e.target.value }))}
            className="border border-gray-200 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
            <option value="">全分類</option>
            <option value="採用候補">採用候補</option>
            <option value="条件付き候補">条件付き候補</option>
            <option value="監視候補">監視候補</option>
            <option value="低スコア">低スコア</option>
          </select>
          <select value={filter.market} onChange={(e) => setFilter((f) => ({ ...f, market: e.target.value }))}
            className="border border-gray-200 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
            <option value="">全市場</option>
            <option value="JP">日本株</option>
            <option value="US">米国株</option>
          </select>
          <span className="text-sm text-gray-500">{filtered.length}件 / {total}件</span>
        </div>
      )}

      {/* Results table */}
      {filtered.length > 0 && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  {[
                    ["symbol", "コード"], ["name", "銘柄名"], ["market", "市場"],
                    ["jpy_price", "円換算価格"], ["price_change_1d", "前日比%"],
                    ["prediction_label", "🔮予測ラベル"],
                    ["final_prediction_score", "🔮final"],
                    ["positive_case_similarity", "類似ポジ"],
                    ["negative_case_similarity", "類似ネガ"],
                    ["overextension_risk_score", "過熱"],
                    ["volume", "出来高"], ["volume_ratio", "出来高倍率"],
                    ["ma25_deviation", "25MA乖離%"], ["upside_to_resistance", "上値余地%"],
                    ["support_distance", "支持線距離%"], ["trend_state", "トレンド"],
                    ["candle_state", "ローソク足"], ["chart_pattern_primary", "パターン"],
                    ["volume_cycle_state", "出来高サイクル"], ["chart_cycle_state", "チャートサイクル"],
                    ["total_score", "旧スコア"],
                    ["reason_summary", "理由"],
                    ["avoid_condition", "見送り条件"],
                    ["warning_flags", "警告"],
                  ].map(([key, label]) => (
                    <th key={key} className="px-2 py-2 text-left text-gray-500 font-medium whitespace-nowrap cursor-pointer hover:bg-gray-100"
                      onClick={() => { setSortKey(key); setSortDir(d => d === "desc" ? "asc" : "desc"); }}>
                      {label}{sortKey === key ? (sortDir === "desc" ? " ▼" : " ▲") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.slice(0, 200).map((r) => (
                  <tr key={r.symbol} className="hover:bg-blue-50 transition-colors">
                    <td className="px-2 py-1.5">
                      <Link href={`/stocks/${encodeURIComponent(r.symbol)}`} className="text-blue-600 font-mono font-bold hover:underline">
                        {r.symbol}
                      </Link>
                    </td>
                    <td className="px-2 py-1.5 text-gray-700 max-w-24 truncate">{r.name}</td>
                    <td className="px-2 py-1.5 text-gray-500">{r.market}</td>
                    <td className="px-2 py-1.5 font-mono text-right">¥{r.jpy_price?.toLocaleString()}</td>
                    <td className={`px-2 py-1.5 text-right font-medium ${(r.price_change_1d ?? 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                      {r.price_change_1d?.toFixed(2)}%
                    </td>
                    {/* AAR予測フィールド */}
                    <td className="px-2 py-1.5 text-xs">
                      {(r as any).prediction_label ? (
                        <span className={`px-1.5 py-0.5 rounded font-medium ${
                          (r as any).prediction_label?.includes("急騰前夜") ? "bg-green-100 text-green-700" :
                          (r as any).prediction_label?.includes("条件付き") ? "bg-blue-100 text-blue-700" :
                          (r as any).prediction_label?.includes("警戒") ? "bg-orange-100 text-orange-700" :
                          (r as any).prediction_label?.includes("除外") ? "bg-gray-100 text-gray-500" :
                          "bg-gray-50 text-gray-700"
                        }`}>{(r as any).prediction_label}</span>
                      ) : "-"}
                    </td>
                    <td className="px-2 py-1.5 text-right font-bold text-blue-600">{(r as any).final_prediction_score?.toFixed(0) ?? "-"}</td>
                    <td className="px-2 py-1.5 text-right text-green-600">{(r as any).positive_case_similarity?.toFixed(2) ?? "-"}</td>
                    <td className="px-2 py-1.5 text-right text-red-500">{(r as any).negative_case_similarity?.toFixed(2) ?? "-"}</td>
                    <td className={`px-2 py-1.5 text-right ${((r as any).overextension_risk_score ?? 0) >= 60 ? "text-red-500 font-bold" : "text-gray-600"}`}>
                      {(r as any).overextension_risk_score?.toFixed(0) ?? "-"}
                    </td>
                    <td className="px-2 py-1.5 text-right text-gray-600">{r.volume?.toLocaleString()}</td>
                    <td className="px-2 py-1.5 text-right text-gray-600">{r.volume_ratio?.toFixed(2)}x</td>
                    <td className={`px-2 py-1.5 text-right font-medium ${(r.ma25_deviation ?? 0) > 50 ? "text-red-500" : (r.ma25_deviation ?? 0) > 20 ? "text-orange-500" : "text-gray-600"}`}>
                      {r.ma25_deviation?.toFixed(1)}%
                    </td>
                    <td className={`px-2 py-1.5 text-right font-medium ${(r.upside_to_resistance ?? 0) >= 20 ? "text-green-600" : "text-gray-500"}`}>
                      {r.upside_to_resistance?.toFixed(1)}%
                    </td>
                    <td className="px-2 py-1.5 text-right text-gray-600">{r.support_distance?.toFixed(1)}%</td>
                    <td className="px-2 py-1.5 text-gray-600 whitespace-nowrap">{r.trend_state}</td>
                    <td className="px-2 py-1.5 text-gray-600 whitespace-nowrap">{r.candle_state}</td>
                    <td className="px-2 py-1.5 text-gray-600 whitespace-nowrap max-w-28 truncate">{r.chart_pattern_primary}</td>
                    <td className="px-2 py-1.5"><VolCycleBadge state={r.volume_cycle_state} /></td>
                    <td className="px-2 py-1.5 whitespace-nowrap text-gray-600">{r.chart_cycle_state}</td>
                    <td className="px-2 py-1.5 w-20"><ScoreBar score={r.total_score} /></td>
                    <td className="px-2 py-1.5 text-gray-600 max-w-40 truncate" title={(r as any).reason_summary}>{(r as any).reason_summary || "-"}</td>
                    <td className="px-2 py-1.5 text-orange-600 max-w-40 truncate" title={(r as any).avoid_condition}>{(r as any).avoid_condition || "-"}</td>
                    <td className="px-2 py-1.5 text-orange-500 max-w-32 truncate">{(r.warning_flags || []).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length > 200 && (
            <p className="text-center text-xs text-gray-400 py-2">最初の200件を表示 / 全{filtered.length}件</p>
          )}
        </div>
      )}

      {results.length === 0 && progress?.status !== "running" && (
        <div className="card p-10 text-center text-gray-400">
          <p className="text-lg">スクリーニング未実行</p>
          <p className="text-sm mt-2">上の「全銘柄スクリーニング実行」ボタンを押してください</p>
        </div>
      )}
    </div>
  );
}
