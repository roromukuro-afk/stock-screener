"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";

interface Candidate {
  symbol: string;
  name?: string;
  market?: string;
  current_price?: number;
  avg_similarity_top5?: number;
  resistance_upside?: number;
  ma25_deviation?: number;
  overextension_score?: number;
  support_distance?: number;
  matched_relative_days?: string[];
  matched_past_symbols?: string[];
}

export default function Surge20CandidatesPage() {
  const [market, setMarket] = useState("JP");
  const [maxSymbols, setMaxSymbols] = useState(100);
  const [data, setData] = useState<any>(null);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await fetchAPI("/api/surge-20/summary");
      setSummary(s);
    } catch (e: any) { setError(e.message); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const buildCandidates = async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetchAPI("/api/surge-20/build-candidates", {
        method: "POST",
        body: JSON.stringify({ market, max_symbols: maxSymbols }),
      });
      setData(r);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const cards = (data?.candidates_top50 || []) as Candidate[];

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #064e3b 0%, #047857 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">🌅 20%急騰到達候補</h1>
        <p className="text-emerald-200 text-sm">
          5〜20営業日 / 1か月以内に <strong>+20%以上に到達した過去ケースの T-3/T-5/T-1</strong> に類似する銘柄を、現在の universe から類似度マッチで抽出します。
        </p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs space-y-1">
          <p>⚠️ これは「明日上がる」予測ではなく「5〜20営業日で20%到達を狙う分析」です。</p>
          <p>⚠️ 1日で+20%以上急騰する銘柄は別ラベル (1日急騰イベント) で検出・保存します。</p>
          <p>⚠️ すでに大きく上昇している銘柄は別途「上がり切り警戒/二段目監視」に分類されます。</p>
          <p>⚠️ 投資助言ではありません。最終判断はユーザー自身が行ってください。</p>
        </div>
      </div>

      {summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 text-sm">
            <div className="card p-3"><p className="text-xs text-gray-500">surge_20_events</p><p className="text-2xl font-bold text-emerald-700">{summary.surge_20_events}</p><p className="text-xs text-gray-400">{summary.unique_symbols_with_events || 0} unique</p></div>
            <div className="card p-3"><p className="text-xs text-gray-500">pre_features</p><p className="text-2xl font-bold text-blue-600">{summary.pre_features}</p><p className="text-xs text-gray-400">{summary.unique_symbols_with_features || 0} unique</p></div>
            <div className="card p-3"><p className="text-xs text-gray-500">negative_cases</p><p className="text-2xl font-bold text-red-500">{summary.negative_cases}</p></div>
            <div className="card p-3"><p className="text-xs text-gray-500">P/N ratio (neg/events)</p><p className="text-2xl font-bold text-orange-600">{summary.positive_negative_ratio ?? "-"}</p></div>
            <div className="card p-3"><p className="text-xs text-gray-500">ranking_snapshots</p><p className="text-2xl font-bold text-purple-600">{summary.ranking_snapshots}</p></div>
            <div className="card p-3"><p className="text-xs text-gray-500">ranking_items</p><p className="text-2xl font-bold text-gray-700">{summary.ranking_items}</p></div>
            <div className="card p-3"><p className="text-xs text-gray-500">recent snapshots</p><p className="text-2xl font-bold text-cyan-600">{(summary.recent_snapshots || []).length}</p></div>
          </div>
          {summary.events_by_type && Object.keys(summary.events_by_type).length > 0 && (
            <div className="card p-3">
              <p className="text-xs font-bold text-gray-700 mb-2">event_type別件数</p>
              <div className="flex flex-wrap gap-2 text-xs">
                {Object.entries(summary.events_by_type).map(([k, v]: [string, any]) => (
                  <span key={k} className="px-2 py-1 rounded bg-emerald-50 border border-emerald-200 text-emerald-700">
                    {k}: <strong>{v}</strong>
                  </span>
                ))}
              </div>
            </div>
          )}
          {summary.negative_cases_by_reason && Object.keys(summary.negative_cases_by_reason).length > 0 && (
            <div className="card p-3">
              <p className="text-xs font-bold text-gray-700 mb-2">negative_cases by failure_reason</p>
              <div className="flex flex-wrap gap-2 text-xs">
                {Object.entries(summary.negative_cases_by_reason).map(([k, v]: [string, any]) => (
                  <span key={k} className="px-2 py-1 rounded bg-red-50 border border-red-200 text-red-700">
                    {k}: <strong>{v}</strong>
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <div className="card p-5">
        <h2 className="font-bold text-gray-800 mb-3">候補生成</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="text-xs text-gray-500">市場</label>
            <select value={market} onChange={(e) => setMarket(e.target.value)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm">
              <option>JP</option><option>US</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500">最大走査銘柄数</label>
            <input type="number" value={maxSymbols} onChange={(e) => setMaxSymbols(parseInt(e.target.value) || 100)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm w-32" />
          </div>
          <button onClick={buildCandidates} disabled={loading}
            className="px-5 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700 disabled:opacity-50">
            {loading ? "計算中..." : "🌅 20%到達候補を生成"}
          </button>
        </div>
        {error && <p className="text-red-600 mt-2 text-sm">{error}</p>}
        {data?.status === "no_library" && (
          <p className="text-orange-600 mt-2 text-sm">
            ⚠️ pre_features がまだ作成されていません。先に <Link href="/training-builder" className="text-blue-600 hover:underline">/training-builder</Link> または{" "}
            <code className="bg-gray-100 px-1">/api/surge-20/detect-events</code> + <code className="bg-gray-100 px-1">/api/surge-20/extract-pre-features</code> を実行してください。
          </p>
        )}
      </div>

      {data?.status === "ok" && (
        <div className="card p-4">
          <h2 className="font-bold text-gray-800 mb-3">
            候補: {data.candidates_count} 件 (走査 {data.universe_scanned} 銘柄中)
          </h2>
          <p className="text-xs text-gray-500 mb-3">
            類似度上位TOP5の平均similarityでソート (高いほど過去の+20%到達直前パターンに類似)
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {cards.map((c) => {
              const sim = c.avg_similarity_top5 || 0;
              const overext = c.overextension_score || 0;
              const isOverextended = overext >= 60;
              const upside = c.resistance_upside || 0;
              return (
                <div key={c.symbol} className={`card p-3 ${isOverextended ? "bg-orange-50 border-orange-200" : ""}`}>
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <Link href={`/stocks/${encodeURIComponent(c.symbol)}`} className="text-blue-600 font-mono font-bold hover:underline">{c.symbol}</Link>
                      <p className="text-sm font-medium text-gray-800 truncate max-w-36">{c.name}</p>
                      <p className="text-xs text-gray-400">{c.market}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xl font-bold text-emerald-700">{(sim * 100).toFixed(0)}%</p>
                      <p className="text-xs text-gray-400">類似度</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>現在値: <strong>{c.current_price?.toFixed(2)}</strong></div>
                    <div>上値余地: <strong className={upside >= 20 ? "text-green-600" : "text-gray-500"}>{upside?.toFixed(1)}%</strong></div>
                    <div>25MA乖離: <strong className={(c.ma25_deviation || 0) > 50 ? "text-red-500" : ""}>{c.ma25_deviation?.toFixed(1)}%</strong></div>
                    <div>過熱: <strong className={isOverextended ? "text-orange-600" : ""}>{overext?.toFixed(0)}</strong></div>
                  </div>
                  {c.matched_relative_days && (
                    <p className="text-xs text-gray-600 mt-2">
                      <strong>類似時点:</strong> {c.matched_relative_days.slice(0, 3).join(", ")}
                    </p>
                  )}
                  {c.matched_past_symbols && (
                    <p className="text-xs text-gray-500 mt-1 truncate">
                      <strong>類似過去:</strong> {c.matched_past_symbols.slice(0, 3).join(", ")}
                    </p>
                  )}
                  {isOverextended && (
                    <p className="text-xs text-orange-700 mt-2">⚠️ 過熱気味 — 「上がり切り警戒/二段目監視」に該当する可能性</p>
                  )}
                  <Link href={`/stocks/${encodeURIComponent(c.symbol)}`}
                    className="mt-2 block text-center text-xs py-1.5 bg-emerald-50 text-emerald-700 rounded hover:bg-emerald-100">
                    詳細 →
                  </Link>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="card p-3 text-xs text-gray-500">
        🔗 関連: <Link href="/surge-ranking-import" className="text-blue-600">ランキング自動生成・取込</Link> /{" "}
        <Link href="/training-builder" className="text-blue-600">教師データ構築</Link> /{" "}
        <Link href="/ai-analyst" className="text-blue-600">AI総合分析</Link>
      </div>
    </div>
  );
}
