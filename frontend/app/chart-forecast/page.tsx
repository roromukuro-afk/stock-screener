"use client";
import { useState } from "react";
import { fetchAPI } from "@/lib/api";

export default function ChartForecastPage() {
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState("JP");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      // Stock summary -> entry plan + forecast
      const stock = await fetchAPI(`/api/stocks/${encodeURIComponent(symbol)}`);
      const r = await fetchAPI("/api/chart-forecast/generate", {
        method: "POST",
        body: JSON.stringify({ result: stock }),
      });
      setResult({ ...r, stock });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const ScenarioCard = ({ s, color }: { s: any; color: string }) => (
    <div className={`card p-4 border-l-4 ${color}`}>
      <h3 className="font-bold text-gray-800 mb-2">{s.scenario}</h3>
      <p className="text-sm text-gray-700 mb-3"><strong>条件:</strong> {s.condition}</p>
      <div className="space-y-1 text-xs">
        {s.trigger_price !== null && s.trigger_price !== undefined && <p><strong>トリガー:</strong> {s.trigger_price.toFixed(2)}</p>}
        <p><strong>支持線:</strong> {s.support_price?.toFixed(2)} / <strong>抵抗線:</strong> {s.resistance_price?.toFixed(2)}</p>
        {s.pullback_low && <p><strong>押し目:</strong> {s.pullback_low.toFixed(2)} 〜 {s.pullback_high?.toFixed(2)}</p>}
        {s.stop_loss && <p className="text-red-600"><strong>損切り目安:</strong> {s.stop_loss.toFixed(2)}</p>}
        {s.take_profit_1 && <p className="text-green-600"><strong>利確目安1:</strong> {s.take_profit_1.toFixed(2)}</p>}
        {s.take_profit_2 && <p className="text-green-600"><strong>利確目安2:</strong> {s.take_profit_2.toFixed(2)}</p>}
        <p className="text-orange-600"><strong>無効化:</strong> {s.invalidation}</p>
        <p><strong>想定期間:</strong> {s.expected_duration} / <strong>信頼度:</strong> {s.confidence}</p>
        {s.risk_reward !== null && s.risk_reward !== undefined && <p><strong>R/R:</strong> {s.risk_reward.toFixed(2)}</p>}
      </div>
      <p className="text-xs text-gray-400 italic mt-2">{s.note}</p>
    </div>
  );

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">📐 チャート予測・エントリー設計</h1>
        <p className="text-blue-200 text-sm">支持線・抵抗線・ATR・25MA等から、強気/基本/弱気の3シナリオとエントリー価格を機械的に算出。</p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ これは投資助言ではなく、過去価格データに基づく機械的な分析条件です。
        </div>
      </div>

      <div className="card p-5">
        <div className="flex gap-3 items-end flex-wrap">
          <div>
            <label className="text-xs text-gray-500">銘柄コード</label>
            <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="例: 7203.T"
              className="border border-gray-200 rounded px-3 py-2 text-sm w-48" />
          </div>
          <div>
            <label className="text-xs text-gray-500">市場</label>
            <select value={market} onChange={(e) => setMarket(e.target.value)}
              className="border border-gray-200 rounded px-3 py-2 text-sm">
              <option>JP</option><option>US</option>
            </select>
          </div>
          <button onClick={run} disabled={loading || !symbol}
            className="px-5 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
            {loading ? "予測中..." : "📐 予測実行"}
          </button>
          {error && <p className="text-red-600 text-sm">{error}</p>}
        </div>
      </div>

      {result && (
        <>
          {/* Entry plan サマリ */}
          <div className="card p-5">
            <h2 className="font-bold text-gray-800 mb-3">🎯 エントリー設計</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div><p className="text-xs text-gray-500">entry_type</p><p className="font-bold">{result.entry_plan.entry_type}</p></div>
              <div><p className="text-xs text-gray-500">押し目ゾーン</p><p className="font-mono">{result.entry_plan.entry_zone_a_low?.toFixed(2)}〜{result.entry_plan.entry_zone_a_high?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">ブレイクトリガー</p><p className="font-mono text-blue-700">{result.entry_plan.breakout_trigger_price?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">Reclaim line</p><p className="font-mono">{result.entry_plan.reclaim_line?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">損切り目安</p><p className="font-mono text-red-600">{result.entry_plan.stop_loss_price?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">利確1</p><p className="font-mono text-green-600">{result.entry_plan.take_profit_1?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">利確2</p><p className="font-mono text-green-600">{result.entry_plan.take_profit_2?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">R/R</p><p className="font-bold">{result.entry_plan.risk_reward_1?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">追いかけ最大価格</p><p className="font-mono">{result.entry_plan.max_chase_price?.toFixed(2)}</p></div>
              <div><p className="text-xs text-gray-500">追いかけ禁止</p><p className={`font-bold ${result.entry_plan.chase_prohibited ? "text-red-600" : "text-green-600"}`}>{result.entry_plan.chase_prohibited ? "🚫 yes" : "—"}</p></div>
              <div><p className="text-xs text-gray-500">GU過大警告</p><p>{result.entry_plan.gap_up_warning ? "⚠️ yes" : "—"}</p></div>
              <div><p className="text-xs text-gray-500">ポジション</p><p className="text-sm">{result.entry_plan.position_size_hint}</p></div>
            </div>
            <p className="text-xs text-orange-600 mt-3">⚠️ {result.entry_plan.entry_comment}</p>
          </div>

          {/* 3 シナリオ */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <ScenarioCard s={result.forecast.bull} color="border-green-500" />
            <ScenarioCard s={result.forecast.base} color="border-blue-500" />
            <ScenarioCard s={result.forecast.bear} color="border-red-500" />
          </div>
        </>
      )}

      <div className="card p-3 text-xs text-gray-500">
        <p>⚠️ 「買え」「必ず上がる」「ここで買うべき」等の表現ではなく、過去データに基づく機械的な分析条件として表示しています。最終判断はユーザー自身が行ってください。</p>
      </div>
    </div>
  );
}
