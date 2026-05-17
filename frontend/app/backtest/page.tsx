"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface BacktestResult {
  symbol: string;
  name?: string;
  screen_date?: string;
  screen_price?: number;
  classification?: string;
  total_score?: number;
  result_after_1d?: number;
  result_after_3d?: number;
  result_after_5d?: number;
  result_after_10d?: number;
  result_after_20d?: number;
  max_gain?: number;
  max_drawdown?: number;
  hit_20_percent?: boolean;
}

function pct(v?: number) {
  if (v == null) return "-";
  return <span className={v >= 0 ? "text-green-600" : "text-red-500"}>{v.toFixed(2)}%</span>;
}

export default function BacktestPage() {
  const [results, setResults] = useState<BacktestResult[]>([]);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState<string>("");
  const [loaded, setLoaded] = useState(false);

  const load = async () => {
    try {
      const r = await api.backtestResults();
      setResults(r.results || []);
      setLoaded(true);
    } catch (e) {}
  };

  useEffect(() => { load(); }, []);

  const run = async () => {
    setRunning(true);
    setMsg("");
    try {
      const r = await api.runBacktest();
      setMsg(r.message || "完了");
      load();
    } catch (e: any) {
      setMsg("エラー: " + e.message);
    } finally {
      setRunning(false);
    }
  };

  const hitRate = results.filter((r) => r.hit_20_percent).length;
  const hitPct = results.length > 0 ? ((hitRate / results.length) * 100).toFixed(1) : "-";

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <h1 className="text-xl font-bold text-gray-800">📊 バックテスト・追跡</h1>
        <div className="flex gap-2">
          <button onClick={run} disabled={running}
            className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
            {running ? "実行中..." : "バックテスト実行"}
          </button>
          <button onClick={() => api.exportExcel()}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200">
            Excel出力
          </button>
        </div>
      </div>

      {msg && <div className="card p-3 text-sm text-gray-600">{msg}</div>}

      <div className="card p-3 text-xs text-gray-500">
        <p>候補抽出後の株価推移を追跡します。<strong>スクリーニング実行後に「バックテスト実行」を押してください。</strong></p>
        <p className="text-orange-500 mt-1">⚠️ 過去データに基づく参考情報です。将来の投資パフォーマンスを保証するものではありません。</p>
      </div>

      {results.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <div className="card p-4 text-center">
            <p className="text-2xl font-bold text-gray-800">{results.length}</p>
            <p className="text-xs text-gray-500">バックテスト対象</p>
          </div>
          <div className="card p-4 text-center">
            <p className="text-2xl font-bold text-green-600">{hitRate}</p>
            <p className="text-xs text-gray-500">+20%達成件数</p>
          </div>
          <div className="card p-4 text-center">
            <p className="text-2xl font-bold text-blue-600">{hitPct}%</p>
            <p className="text-xs text-gray-500">+20%達成率</p>
          </div>
        </div>
      )}

      {results.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 border-b text-gray-500">
                  <th className="px-3 py-2 text-left">コード</th>
                  <th className="px-3 py-2 text-left">銘柄名</th>
                  <th className="px-3 py-2 text-left">分類</th>
                  <th className="px-3 py-2 text-right">スコア</th>
                  <th className="px-3 py-2 text-right">翌日</th>
                  <th className="px-3 py-2 text-right">3日後</th>
                  <th className="px-3 py-2 text-right">5日後</th>
                  <th className="px-3 py-2 text-right">10日後</th>
                  <th className="px-3 py-2 text-right">20日後</th>
                  <th className="px-3 py-2 text-right">最大上昇</th>
                  <th className="px-3 py-2 text-right">最大下落</th>
                  <th className="px-3 py-2 text-center">+20%達成</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {results.map((r) => (
                  <tr key={r.symbol} className="hover:bg-blue-50">
                    <td className="px-3 py-1.5 font-mono font-bold text-gray-700">{r.symbol}</td>
                    <td className="px-3 py-1.5 text-gray-600 max-w-28 truncate">{r.name}</td>
                    <td className="px-3 py-1.5 text-gray-500">{r.classification}</td>
                    <td className="px-3 py-1.5 text-right font-bold text-blue-600">{r.total_score}</td>
                    <td className="px-3 py-1.5 text-right">{pct(r.result_after_1d)}</td>
                    <td className="px-3 py-1.5 text-right">{pct(r.result_after_3d)}</td>
                    <td className="px-3 py-1.5 text-right">{pct(r.result_after_5d)}</td>
                    <td className="px-3 py-1.5 text-right">{pct(r.result_after_10d)}</td>
                    <td className="px-3 py-1.5 text-right">{pct(r.result_after_20d)}</td>
                    <td className="px-3 py-1.5 text-right font-bold">{pct(r.max_gain)}</td>
                    <td className="px-3 py-1.5 text-right">{pct(r.max_drawdown)}</td>
                    <td className="px-3 py-1.5 text-center">
                      {r.hit_20_percent ? (
                        <span className="text-green-600 font-bold">✅</span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card p-10 text-center text-gray-400">
          <p>バックテスト結果がありません</p>
          <p className="text-sm mt-2">スクリーニング実行後に「バックテスト実行」を押してください</p>
        </div>
      )}
    </div>
  );
}
