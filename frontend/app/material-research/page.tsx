"use client";
import { useState } from "react";
import { fetchAPI } from "@/lib/api";

export default function MaterialResearchPage() {
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState("JP");
  const [userText, setUserText] = useState("");
  const [urls, setUrls] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const research = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const urlList = urls.split("\n").map((u) => u.trim()).filter((u) => u);
      const r = await fetchAPI("/api/materials/research", {
        method: "POST",
        body: JSON.stringify({
          symbol, market, user_text: userText || null, urls: urlList.length ? urlList : null, save: true,
        }),
      });
      setResult(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const Info = ({ label, value }: { label: string; value: any }) => (
    <div className="flex justify-between py-1 border-b border-gray-50 text-xs">
      <span className="text-gray-500">{label}</span>
      <span className="font-mono">{value ?? "-"}</span>
    </div>
  );

  return (
    <div className="space-y-5 max-w-4xl">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #422006 0%, #78350f 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">📰 AI材料調査</h1>
        <p className="text-amber-200 text-sm">公式IR・TDnet・EDGAR・ニュースURLを投入し、材料カテゴリ・強さ・リスクを判定します。</p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ 投資助言ではありません。材料の解釈は分析・学習目的です。
        </div>
      </div>

      <div className="card p-5">
        <h2 className="font-bold text-gray-800 mb-3">調査リクエスト</h2>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="text-xs text-gray-500">銘柄コード</label>
            <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="例: 7203.T or AAPL"
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-500">市場</label>
            <select value={market} onChange={(e) => setMarket(e.target.value)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm">
              <option>JP</option><option>US</option>
            </select>
          </div>
        </div>
        <div className="mb-3">
          <label className="text-xs text-gray-500">材料テキスト・メモ (任意)</label>
          <textarea value={userText} onChange={(e) => setUserText(e.target.value)} rows={4}
            placeholder="例: 業績上方修正。営業利益+30%。AI需要が大きく寄与..."
            className="w-full border border-gray-200 rounded px-3 py-2 text-sm font-mono" />
        </div>
        <div className="mb-3">
          <label className="text-xs text-gray-500">公式IR・ニュースURL (1行1URL、任意)</label>
          <textarea value={urls} onChange={(e) => setUrls(e.target.value)} rows={3}
            placeholder="https://www.release.tdnet.info/..."
            className="w-full border border-gray-200 rounded px-3 py-2 text-sm font-mono" />
        </div>
        <button onClick={research} disabled={loading || !symbol}
          className="px-6 py-2.5 bg-amber-600 text-white rounded font-bold text-sm hover:bg-amber-700 disabled:opacity-50">
          {loading ? "調査中..." : "🔍 AI材料調査を実行"}
        </button>
        {error && <p className="mt-2 text-red-600 text-sm">{error}</p>}
      </div>

      {result && (
        <div className="card p-5">
          <div className="flex justify-between items-start mb-3">
            <div>
              <p className="text-gray-500 text-xs">材料カテゴリ</p>
              <p className="text-2xl font-bold text-amber-700">{result.catalyst_category}</p>
              <p className="text-xs text-gray-500 mt-1">出典: {result.material_source_type} ({result.material_source_rank})</p>
            </div>
            <div>
              <p className="text-gray-500 text-xs">材料品質</p>
              <p className="text-2xl font-bold text-blue-600">{result.catalyst_quality_score?.toFixed(0)}/100</p>
              <p className="text-xs">{result.material_confirmed ? "✅ 確認済" : "⚠️ 未確認"}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            <div>
              <h3 className="font-bold text-sm text-gray-700 mb-2">📊 材料スコア内訳</h3>
              <Info label="catalyst_quality_score" value={result.catalyst_quality_score?.toFixed(0)} />
              <Info label="catalyst_continuity_score" value={result.catalyst_continuity_score?.toFixed(0)} />
              <Info label="catalyst_freshness_score" value={result.catalyst_freshness_score?.toFixed(0)} />
              <Info label="catalyst_surprise_score" value={result.catalyst_surprise_score?.toFixed(0)} />
              <Info label="theme_tailwind_score" value={result.theme_tailwind_score?.toFixed(0)} />
              <Info label="material_exhaustion_risk_score" value={result.material_exhaustion_risk_score?.toFixed(0)} />
            </div>
            <div>
              <h3 className="font-bold text-sm text-gray-700 mb-2">⚠️ リスクフラグ</h3>
              <Info label="bad_news_unresolved" value={result.bad_news_unresolved_flag ? "🚨 yes" : "—"} />
              <Info label="dilution_risk" value={result.dilution_risk_flag ? "🚨 yes" : "—"} />
              <Info label="going_concern_risk" value={result.going_concern_risk_flag ? "🚨 yes" : "—"} />
              <Info label="delisting_risk" value={result.delisting_risk_flag ? "🚨 yes" : "—"} />
              <Info label="weak_material_flag" value={result.weak_material_flag ? "⚠️ 弱い" : "—"} />
              <Info label="matched_keywords" value={(result.matched_keywords || []).join(", ") || "-"} />
            </div>
          </div>

          {result.summary && (
            <div className="mt-4">
              <h3 className="font-bold text-sm text-gray-700 mb-2">要約</h3>
              <pre className="bg-gray-50 p-3 rounded text-xs whitespace-pre-wrap max-h-40 overflow-y-auto">{result.summary}</pre>
            </div>
          )}
          {result.ai_analysis && (
            <div className="mt-3 text-xs text-gray-500">AI: {result.ai_analysis}</div>
          )}
        </div>
      )}

      <div className="card p-3 text-xs text-gray-500">
        <p><strong>使い方:</strong> 銘柄を入力し、TDnet・EDGAR・公式IR等のURLを貼ると、AIがソースランクと材料カテゴリを判定します。</p>
        <p className="text-orange-600 mt-1">⚠️ 投資助言ではありません。最終判断はユーザー自身が行ってください。</p>
      </div>
    </div>
  );
}
