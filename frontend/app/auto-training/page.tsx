"use client";
import { useEffect, useState, useCallback } from "react";
import { fetchAPI } from "@/lib/api";

export default function AutoTrainingPage() {
  const [markets, setMarkets] = useState<string[]>(["JP"]);
  const [includeAdr, setIncludeAdr] = useState(true);
  const [targetDate, setTargetDate] = useState("");
  const [threshold, setThreshold] = useState(20);
  const [maxSymbols, setMaxSymbols] = useState(200);
  const [progress, setProgress] = useState<any>(null);
  const [results, setResults] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const [p, j, r] = await Promise.all([
        fetchAPI("/api/auto-training/progress"),
        fetchAPI("/api/auto-training/jobs?limit=10"),
        fetchAPI("/api/auto-training/results?limit=200"),
      ]);
      setProgress(p);
      setJobs(j.items || []);
      setResults(r.items || []);
    } catch {}
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const run = async () => {
    setBusy(true);
    setMsg("");
    try {
      const r = await fetchAPI("/api/auto-training/run-daily", {
        method: "POST",
        body: JSON.stringify({
          markets, include_adr: includeAdr,
          target_date: targetDate || null,
          threshold_percent: threshold,
          max_symbols: maxSymbols,
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

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #14532d 0%, #166534 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">🤖 自動教師データ収集</h1>
        <p className="text-emerald-200 text-sm">ユニバースから前日比+N%以上の急騰銘柄を自動検出 → AAR分析 → 重複チェック → 教師データ化</p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ これは投資助言ではありません。分析・学習目的のツールです。
        </div>
      </div>

      <div className="card p-5">
        <h2 className="font-bold text-gray-800 mb-3">パラメータ</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <div>
            <label className="text-xs text-gray-500">対象市場</label>
            <div className="flex gap-2 mt-1">
              {["JP", "US"].map((m) => (
                <label key={m} className="flex items-center gap-1 text-sm">
                  <input type="checkbox" checked={markets.includes(m)} onChange={() => toggleMarket(m)} />
                  {m}
                </label>
              ))}
              <label className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={includeAdr} onChange={(e) => setIncludeAdr(e.target.checked)} />
                ADR含む
              </label>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-500">対象日 (空欄=今日)</label>
            <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-500">急騰閾値 (%)</label>
            <input type="number" value={threshold} onChange={(e) => setThreshold(parseFloat(e.target.value) || 0)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-500">最大スキャン銘柄数 (Render Free対策)</label>
            <input type="number" value={maxSymbols} onChange={(e) => setMaxSymbols(parseInt(e.target.value) || 0)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm" />
          </div>
        </div>
        <button onClick={run} disabled={busy || (progress?.running)}
          className="px-5 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700 disabled:opacity-50">
          {busy ? "起動中..." : "🤖 自動収集 実行"}
        </button>
        {msg && <p className="mt-2 text-sm text-gray-600">{msg}</p>}
      </div>

      {progress && progress.total > 0 && (
        <div className="card p-4">
          <div className="flex justify-between text-sm mb-2">
            <span>{progress.running ? "実行中" : "完了"}: {progress.processed}/{progress.total}</span>
            <span>検出: {progress.detected} / 保存: {progress.saved} / 重複: {progress.duplicate} / 失敗: {progress.failed}</span>
          </div>
          <div className="bg-gray-100 rounded-full h-2">
            <div className="h-2 rounded-full bg-emerald-500"
              style={{ width: `${progress.total > 0 ? (progress.processed / progress.total * 100) : 0}%` }} />
          </div>
        </div>
      )}

      {/* ジョブ履歴 */}
      <div className="card p-4">
        <h3 className="font-bold text-gray-800 mb-2">📝 ジョブ履歴</h3>
        {jobs.length === 0 ? (
          <p className="text-gray-400 text-sm">まだジョブがありません</p>
        ) : (
          <table className="w-full text-xs">
            <thead><tr className="text-gray-500 border-b border-gray-100">
              <th className="px-2 py-1 text-left">id</th>
              <th className="px-2 py-1 text-left">target_date</th>
              <th className="px-2 py-1 text-left">market</th>
              <th className="px-2 py-1 text-right">閾値</th>
              <th className="px-2 py-1 text-right">検出</th>
              <th className="px-2 py-1 text-right">保存</th>
              <th className="px-2 py-1 text-right">重複</th>
              <th className="px-2 py-1 text-right">失敗</th>
              <th className="px-2 py-1 text-left">started</th>
            </tr></thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="border-b border-gray-50">
                  <td className="px-2 py-1 font-mono">{j.id}</td>
                  <td className="px-2 py-1">{j.target_date}</td>
                  <td className="px-2 py-1">{j.market_scope}</td>
                  <td className="px-2 py-1 text-right">{j.threshold_percent}%</td>
                  <td className="px-2 py-1 text-right">{j.surge_detected_count}</td>
                  <td className="px-2 py-1 text-right text-green-600">{j.saved_case_count}</td>
                  <td className="px-2 py-1 text-right text-gray-500">{j.duplicate_count}</td>
                  <td className="px-2 py-1 text-right text-red-500">{j.failed_count}</td>
                  <td className="px-2 py-1 text-gray-400">{j.started_at?.slice(0, 19).replace("T", " ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 結果 */}
      <div className="card p-4">
        <h3 className="font-bold text-gray-800 mb-2">📈 検出された急騰銘柄 ({results.length}件)</h3>
        {results.length === 0 ? (
          <p className="text-gray-400 text-sm">結果がありません</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-gray-500 border-b border-gray-100">
                <th className="px-2 py-1 text-left">symbol</th>
                <th className="px-2 py-1 text-left">market</th>
                <th className="px-2 py-1 text-left">date</th>
                <th className="px-2 py-1 text-right">+%</th>
                <th className="px-2 py-1 text-center">analyzed</th>
                <th className="px-2 py-1 text-center">saved</th>
                <th className="px-2 py-1 text-center">duplicate</th>
                <th className="px-2 py-1 text-left">catalyst</th>
                <th className="px-2 py-1 text-left">t1判定</th>
              </tr></thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.id} className="border-b border-gray-50 hover:bg-blue-50">
                    <td className="px-2 py-1 font-mono font-bold">{r.symbol}</td>
                    <td className="px-2 py-1">{r.market}</td>
                    <td className="px-2 py-1">{r.target_date}</td>
                    <td className="px-2 py-1 text-right text-green-600 font-bold">{r.move_percent?.toFixed(1)}%</td>
                    <td className="px-2 py-1 text-center">{r.analyzed ? "✅" : "—"}</td>
                    <td className="px-2 py-1 text-center">{r.saved_to_training ? "✅" : "—"}</td>
                    <td className="px-2 py-1 text-center">{r.duplicate ? "↩" : "—"}</td>
                    <td className="px-2 py-1 text-gray-600">{r.catalyst_category || "-"}</td>
                    <td className="px-2 py-1 text-gray-600">{r.t1_judgement || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
