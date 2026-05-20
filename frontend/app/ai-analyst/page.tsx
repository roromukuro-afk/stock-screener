"use client";
import { useState } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";

export default function AiAnalystPage() {
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState("JP");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedLogId, setSavedLogId] = useState<number | null>(null);

  const analyze = async () => {
    setLoading(true); setError(null); setData(null); setSavedLogId(null);
    try {
      const [stock, materials] = await Promise.all([
        fetchAPI(`/api/stocks/${encodeURIComponent(symbol)}`),
        fetchAPI(`/api/materials/${encodeURIComponent(symbol)}`).catch(() => ({ items: [] })),
      ]);
      const forecast = await fetchAPI("/api/chart-forecast/generate", {
        method: "POST",
        body: JSON.stringify({ result: stock }),
      });
      setData({ stock, materials: materials.items || [], forecast });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const saveAsPrediction = async () => {
    if (!data) return;
    try {
      const res = await fetchAPI("/api/prediction-log/save", {
        method: "POST",
        body: JSON.stringify({ result: data.stock, entry_plan: data.forecast.entry_plan }),
      });
      setSavedLogId(res.log_id);
      alert(`✅ 予測ログとして保存しました (log_id=${res.log_id})`);
    } catch (e: any) {
      alert("保存失敗: " + e.message);
    }
  };

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #1f2937 0%, #374151 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">🤖 AI総合分析</h1>
        <p className="text-gray-300 text-sm">材料・チャート・出来高・過去類似・失敗リスク・エントリー設計を統合した分析レポート</p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ これは投資助言ではありません。分析・学習・検証目的の自動分析です。「買え」「必ず上がる」等の表現は行いません。
        </div>
      </div>

      <div className="card p-5">
        <div className="flex gap-3 items-end flex-wrap">
          <div>
            <label className="text-xs text-gray-500">銘柄コード</label>
            <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="例: 7203.T or AAPL"
              className="border border-gray-200 rounded px-3 py-2 text-sm w-48" />
          </div>
          <div>
            <label className="text-xs text-gray-500">市場</label>
            <select value={market} onChange={(e) => setMarket(e.target.value)}
              className="border border-gray-200 rounded px-3 py-2 text-sm">
              <option>JP</option><option>US</option>
            </select>
          </div>
          <button onClick={analyze} disabled={loading || !symbol}
            className="px-5 py-2 bg-gray-700 text-white rounded text-sm hover:bg-gray-800 disabled:opacity-50">
            {loading ? "AI分析中..." : "🤖 AI総合分析を実行"}
          </button>
          {error && <p className="text-red-600 text-sm">{error}</p>}
        </div>
      </div>

      {data && (
        <>
          {/* 1. 4行結論 */}
          <div className="card p-5">
            <h2 className="font-bold text-gray-800 mb-3">📌 4行結論</h2>
            <div className="space-y-2 text-sm">
              <p><span className="font-medium text-gray-500">勝因候補の核:</span> {data.stock.main_archetype || "未判定"}</p>
              <p><span className="font-medium text-gray-500">初動前夜サイン:</span> {data.stock.volume_cycle_state} / {data.stock.chart_cycle_state} / {data.stock.candle_state}</p>
              <p><span className="font-medium text-gray-500">今の判定:</span>{" "}
                <span className="font-bold text-blue-700">{data.stock.prediction_label || data.stock.classification || "未分類"}</span>
                (score={data.stock.final_prediction_score?.toFixed(0) ?? data.stock.total_score?.toFixed(0)})
              </p>
              <p><span className="font-medium text-gray-500">追いかけ可否:</span>{" "}
                {data.forecast.entry_plan.chase_prohibited ? (
                  <span className="text-red-600 font-bold">🚫 追いかけ禁止 — 押し目待ち推奨</span>
                ) : (
                  <span className="text-green-700">条件下で押し目買いを検討する分析条件</span>
                )}
              </p>
            </div>
          </div>

          {/* 2. 材料分析 */}
          <div className="card p-5">
            <h2 className="font-bold text-gray-800 mb-3">📰 材料分析</h2>
            {data.materials.length === 0 ? (
              <div className="p-3 bg-gray-50 rounded text-sm">
                <p className="text-gray-600">この銘柄の material_events はまだ収集されていません。</p>
                <p className="text-xs text-gray-400 mt-1">→ <Link href="/material-research" className="text-blue-600">/material-research</Link> でURL入力 or 自動収集を実行</p>
              </div>
            ) : (
              <div className="space-y-2">
                {data.materials.slice(0, 5).map((m: any) => (
                  <div key={m.id} className="border border-gray-100 rounded p-2 text-sm">
                    <div className="flex justify-between items-start">
                      <div>
                        <p className="font-medium">{m.title}</p>
                        <p className="text-xs text-gray-500">{m.source_type} ({m.source_rank}) · {m.detected_at?.slice(0,16)?.replace("T"," ")}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs">品質: <span className="font-bold">{m.catalyst_quality_score?.toFixed(0)}</span></p>
                        <p className="text-xs">{m.material_confirmed ? "✅確認" : "⚠️未確認"}</p>
                      </div>
                    </div>
                    <p className="text-xs text-gray-600 mt-1">カテゴリ: {m.catalyst_category}</p>
                    {m.source_url && (
                      <a href={m.source_url} target="_blank" rel="noopener" className="text-xs text-blue-600 hover:underline">→ ソース</a>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 3. チャート分析 */}
          <div className="card p-5">
            <h2 className="font-bold text-gray-800 mb-3">📊 チャート分析</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div><p className="text-xs text-gray-500">現在値</p><p className="font-bold">¥{data.stock.jpy_price?.toLocaleString()}</p></div>
              <div><p className="text-xs text-gray-500">支持線</p><p className="font-mono">{data.stock.support_line?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">抵抗線</p><p className="font-mono">{data.stock.resistance_line?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">上値余地</p><p className={`font-bold ${(data.stock.upside_to_resistance ?? 0) >= 20 ? "text-green-600" : "text-gray-500"}`}>{data.stock.upside_to_resistance?.toFixed(1)}%</p></div>
              <div><p className="text-xs text-gray-500">支持線距離</p><p>{data.stock.support_distance?.toFixed(1)}%</p></div>
              <div><p className="text-xs text-gray-500">25MA乖離</p><p className={(data.stock.ma25_deviation ?? 0) > 50 ? "text-red-500 font-bold" : ""}>{data.stock.ma25_deviation?.toFixed(1)}%</p></div>
              <div><p className="text-xs text-gray-500">出来高サイクル</p><p>{data.stock.volume_cycle_state}</p></div>
              <div><p className="text-xs text-gray-500">チャートサイクル</p><p>{data.stock.chart_cycle_state}</p></div>
            </div>
          </div>

          {/* 4. エントリー設計 */}
          <div className="card p-5">
            <h2 className="font-bold text-gray-800 mb-3">🎯 エントリー設計 (分析条件として)</h2>
            <p className="text-xs text-orange-600 mb-3">⚠️ これは売買指示ではなく、過去の支持線/抵抗線/ATRに基づく機械的な分析条件です。</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div><p className="text-xs text-gray-500">entry_type</p><p className="font-bold">{data.forecast.entry_plan.entry_type}</p></div>
              <div><p className="text-xs text-gray-500">押し目ゾーン</p><p className="font-mono">{data.forecast.entry_plan.entry_zone_a_low?.toFixed(2)}〜{data.forecast.entry_plan.entry_zone_a_high?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">ブレイクトリガー</p><p className="font-mono text-blue-700">{data.forecast.entry_plan.breakout_trigger_price?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">Reclaim line</p><p className="font-mono">{data.forecast.entry_plan.reclaim_line?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">損切り目安</p><p className="font-mono text-red-600">{data.forecast.entry_plan.stop_loss_price?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">利確1</p><p className="font-mono text-green-600">{data.forecast.entry_plan.take_profit_1?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">利確2</p><p className="font-mono text-green-600">{data.forecast.entry_plan.take_profit_2?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">R/R</p><p className="font-bold">{data.forecast.entry_plan.risk_reward_1?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">追いかけ禁止</p><p className={`font-bold ${data.forecast.entry_plan.chase_prohibited ? "text-red-600" : "text-green-600"}`}>{data.forecast.entry_plan.chase_prohibited ? "🚫 yes" : "—"}</p></div>
              <div><p className="text-xs text-gray-500">GU過大警告</p><p>{data.forecast.entry_plan.gap_up_warning ? "⚠️" : "—"}</p></div>
              <div><p className="text-xs text-gray-500">ポジション</p><p>{data.forecast.entry_plan.position_size_hint}</p></div>
              <div><p className="text-xs text-gray-500">無効化</p><p className="text-xs">{data.forecast.entry_plan.invalidation_price?.toFixed(2)}</p></div>
            </div>
          </div>

          {/* 5. 過去類似ケース */}
          {(data.stock.matched_past_cases?.length || data.stock.similar_historical_cases?.length) ? (
            <div className="card p-5">
              <h2 className="font-bold text-gray-800 mb-3">🔍 類似した過去ケース</h2>
              {data.stock.matched_past_cases && data.stock.matched_past_cases.length > 0 && (
                <div className="mb-4">
                  <h3 className="text-sm font-medium text-gray-700 mb-2">AAR教師データから (TOP5)</h3>
                  <div className="space-y-1">
                    {data.stock.matched_past_cases.slice(0, 5).map((c: any, i: number) => (
                      <div key={i} className="flex justify-between items-center text-xs border-b border-gray-50 py-1">
                        <div>
                          <span className="font-mono font-bold">{c.symbol}</span>
                          <span className="text-gray-500 ml-2">{c.move_date}</span>
                          <span className="text-gray-600 ml-2">{c.setup_type}</span>
                        </div>
                        <div>
                          <span className="text-blue-600 font-bold">sim={c.similarity?.toFixed(3)}</span>
                          {c.hit_20_percent && <span className="ml-2 text-green-600">✅+20%</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {data.stock.similar_historical_cases && data.stock.similar_historical_cases.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-700 mb-2">過去5年training_feature_vectorから (TOP5)</h3>
                  <div className="space-y-1">
                    {data.stock.similar_historical_cases.slice(0, 5).map((c: any, i: number) => (
                      <div key={i} className={`flex justify-between items-center text-xs border-b py-1 px-2 rounded ${
                        c.case_type?.startsWith("positive") ? "bg-green-50" :
                        c.case_type?.startsWith("failed") ? "bg-red-50" : "bg-gray-50"
                      }`}>
                        <div>
                          <span className="font-mono font-bold">{c.symbol}</span>
                          <span className="text-gray-600 ml-2">{c.case_type}</span>
                        </div>
                        <div>
                          <span className="text-blue-600 font-bold">sim={(c.similarity * 100).toFixed(0)}%</span>
                          {c.label_hit_20_percent && <span className="ml-2 text-green-600">✅+20%</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : null}

          {/* 6. 反証・見送り条件 */}
          <div className="card p-5">
            <h2 className="font-bold text-gray-800 mb-3">⚠️ 反証・見送り条件</h2>
            <div className="space-y-1 text-sm">
              <p>• 価格データが古い場合: <span className={data.stock.freshness_status?.startsWith("fresh") ? "text-green-600" : "text-red-500"}>{data.stock.freshness_status || "不明"}</span></p>
              <p>• 25MA乖離が +50% 以上で過熱: 現在 <strong>{data.stock.ma25_deviation?.toFixed(1)}%</strong></p>
              <p>• 直近20日で +80% 以上: 現在 <strong>{data.stock.price_change_20d?.toFixed(1)}%</strong></p>
              <p>• 上値余地 20% 未満: 現在 <strong>{data.stock.upside_to_resistance?.toFixed(1)}%</strong></p>
              <p>• 支持線割れ: 現在 <strong>{(data.stock.support_distance ?? 0) > 0 ? "維持" : "割れ"}</strong></p>
              <p>• 上ヒゲ・大商い大陰線: <strong>{data.stock.candle_state}</strong></p>
              {data.stock.avoid_condition && (
                <p className="text-orange-600 mt-2"><strong>追いかけ禁止条件:</strong> {data.stock.avoid_condition}</p>
              )}
            </div>
          </div>

          {/* 7. 予測検証への登録 */}
          <div className="card p-5 bg-emerald-50 border-emerald-200">
            <h2 className="font-bold text-gray-800 mb-3">💾 予測検証への登録</h2>
            <p className="text-sm text-gray-700 mb-3">この分析をprediction_logsにスナップショット保存し、翌営業日からの株価で自動検証→成功/失敗を教師データへ反映できます。</p>
            <button onClick={saveAsPrediction} disabled={!!savedLogId}
              className="px-5 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700 disabled:opacity-50">
              {savedLogId ? `✅ 保存済み (log_id=${savedLogId})` : "💾 予測ログに保存"}
            </button>
            {savedLogId && (
              <Link href="/prediction-review" className="ml-3 text-sm text-blue-600 hover:underline">→ 予測検証ページで進捗確認</Link>
            )}
          </div>
        </>
      )}

      <div className="card p-3 text-xs text-gray-500">
        ⚠️ これは投資助言ではありません。最終判断はユーザー自身が行ってください。<br />
        🔗 関連: <Link href="/learning-center" className="text-blue-600">AI学習センター</Link> /{" "}
        <Link href="/ranking" className="text-blue-600">ランキング</Link> /{" "}
        <Link href="/prediction-review" className="text-blue-600">予測検証</Link>
      </div>
    </div>
  );
}
