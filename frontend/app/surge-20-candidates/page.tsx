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
  positive_similarity?: number;
  negative_similarity?: number;
  similarity_diff?: number;
  candidate_label?: string;
  resistance_upside?: number;
  ma25_deviation?: number;
  overextension_score?: number;
  support_distance?: number;
  price_change_5d?: number;
  price_change_20d?: number;
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

  const [autoSaveResult, setAutoSaveResult] = useState<any>(null);

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

  const runAutoSave = async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetchAPI("/api/surge-20/auto-save-top-candidates", {
        method: "POST",
        body: JSON.stringify({ market, limit: 20, min_score: 70 }),
      });
      setAutoSaveResult(r);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const runOrchestrator = async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetchAPI("/api/surge-20/run-auto-orchestrator", {
        method: "POST",
        body: JSON.stringify({ market, phase: "all" }),
      });
      setAutoSaveResult({ orchestrator: r });
      // 90秒後にreload
      setTimeout(load, 90000);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const cards = (data?.candidates_top50 || []) as Candidate[];
  const [savedIds, setSavedIds] = useState<Record<string, number>>({});

  const saveAsPrediction = async (c: Candidate) => {
    try {
      const res = await fetchAPI("/api/surge-20/save-candidate-prediction", {
        method: "POST",
        body: JSON.stringify({
          symbol: c.symbol,
          name: c.name,
          market: c.market || market,
          candidate_label: c.candidate_label,
          final_surge_20_score: (c.positive_similarity ?? 0) * 100,
          prediction_horizon: "within_20d",
          target_return: 20.0,
          current_price: c.current_price,
          positive_similarity: c.positive_similarity,
          negative_similarity: c.negative_similarity,
          reason_summary: `pos_sim=${c.positive_similarity?.toFixed(2)} neg_sim=${c.negative_similarity?.toFixed(2)} label=${c.candidate_label}`,
          risk_summary: c.candidate_label === "上がり切り警戒" ? "上がり切り警戒" : (c.candidate_label === "後追い危険" ? "後追い危険" : ""),
        }),
      });
      if (res.log_id) {
        setSavedIds((prev) => ({ ...prev, [c.symbol]: res.log_id }));
      }
    } catch (e: any) {
      alert(`保存失敗: ${e.message}`);
    }
  };

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
            {loading ? "計算中..." : "🌅 候補生成"}
          </button>
          <button onClick={runAutoSave} disabled={loading}
            className="px-5 py-2 bg-fuchsia-600 text-white rounded text-sm hover:bg-fuchsia-700 disabled:opacity-50">
            💾 本命+watch自動保存
          </button>
          <button onClick={runOrchestrator} disabled={loading}
            className="px-5 py-2 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700 disabled:opacity-50">
            🤖 orchestrator全フェーズ
          </button>
        </div>
        {autoSaveResult && (
          <div className="mt-3 p-3 bg-fuchsia-50 border border-fuchsia-200 rounded text-xs">
            <p className="font-bold text-fuchsia-700 mb-1">📊 auto-save結果</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <div>main_saved: <strong className="text-emerald-700">{autoSaveResult.main_saved ?? "-"}</strong></div>
              <div>watch_saved: <strong className="text-blue-700">{autoSaveResult.watch_saved ?? "-"}</strong></div>
              <div>rejected_watch_saved: <strong className="text-gray-700">{autoSaveResult.rejected_watch_saved ?? "-"}</strong></div>
              <div>late_chase_watch_saved: <strong className="text-orange-700">{autoSaveResult.late_chase_watch_saved ?? "-"}</strong></div>
              <div>skipped_duplicate: {autoSaveResult.skipped_duplicate ?? "-"}</div>
              <div>skipped_data_quality: {autoSaveResult.skipped_data_quality ?? "-"}</div>
              <div>skipped_error: {autoSaveResult.skipped_error ?? "-"}</div>
              <div>total_saved: <strong>{autoSaveResult.total_saved ?? "-"}</strong></div>
            </div>
            {autoSaveResult.orchestrator && (
              <p className="mt-2 text-indigo-700">orchestrator: {autoSaveResult.orchestrator.message}</p>
            )}
          </div>
        )}
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
            候補: {data.candidates_count} 件 (走査 {data.universe_scanned} 銘柄中, valid features {data.valid_pre_features_used}, orphan {data.orphan_pre_features_excluded || 0}除外)
          </h2>
          {data.by_label && Object.keys(data.by_label).length > 0 && (
            <div className="flex flex-wrap gap-2 text-xs mb-3">
              {Object.entries(data.by_label).map(([k, v]: [string, any]) => (
                <span key={k} className={`px-2 py-1 rounded border ${
                  k.includes("候補") ? "bg-emerald-50 border-emerald-200 text-emerald-700" :
                  k === "上がり切り警戒" || k === "後追い危険" ? "bg-orange-50 border-orange-200 text-orange-700" :
                  k === "negative類似高め" ? "bg-red-50 border-red-200 text-red-700" :
                  "bg-gray-50 border-gray-200 text-gray-600"
                }`}>
                  {k}: <strong>{v}</strong>
                </span>
              ))}
            </div>
          )}
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
                  {c.candidate_label && (
                    <p className="text-xs font-bold text-emerald-700 mt-2 px-2 py-1 bg-emerald-50 rounded inline-block">
                      🌅 {c.candidate_label}
                    </p>
                  )}
                  {c.negative_similarity != null && (
                    <p className="text-xs text-gray-500 mt-1">
                      pos_sim={c.positive_similarity?.toFixed(2)} / neg_sim={c.negative_similarity?.toFixed(2)} / diff={c.similarity_diff?.toFixed(2)}
                    </p>
                  )}
                  <div className="flex gap-2 mt-2">
                    <Link href={`/stocks/${encodeURIComponent(c.symbol)}`}
                      className="flex-1 text-center text-xs py-1.5 bg-emerald-50 text-emerald-700 rounded hover:bg-emerald-100">
                      詳細 →
                    </Link>
                    {savedIds[c.symbol] ? (
                      <Link href="/prediction-review"
                        className="flex-1 text-center text-xs py-1.5 bg-blue-50 text-blue-700 rounded hover:bg-blue-100">
                        💾 保存済(#{savedIds[c.symbol]}) → 検証
                      </Link>
                    ) : (
                      <button onClick={() => saveAsPrediction(c)}
                        className="flex-1 text-center text-xs py-1.5 bg-emerald-600 text-white rounded hover:bg-emerald-700">
                        💾 20%予測として保存
                      </button>
                    )}
                  </div>
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
