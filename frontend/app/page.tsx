"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { DashboardData, ScreeningResult } from "@/lib/types";
import ClassificationBadge from "@/components/ClassificationBadge";
import ScoreBar from "@/components/ScoreBar";
import VolCycleBadge from "@/components/VolCycleBadge";

function StatCard({ label, value, sub, color }: { label: string; value: number | string; sub?: string; color?: string }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color || "text-gray-900"}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

function CandidateRow({ r }: { r: ScreeningResult }) {
  return (
    <tr className="hover:bg-blue-50 transition-colors">
      <td className="px-3 py-2 text-sm">
        <Link href={`/stocks/${encodeURIComponent(r.symbol)}`} className="text-blue-600 font-mono font-bold hover:underline">
          {r.symbol}
        </Link>
      </td>
      <td className="px-3 py-2 text-sm text-gray-700 max-w-32 truncate">{r.name}</td>
      <td className="px-3 py-2 text-xs text-gray-500">{r.market}</td>
      <td className="px-3 py-2 text-sm font-mono text-right">¥{r.jpy_price?.toLocaleString()}</td>
      <td className="px-3 py-2 text-sm"><ClassificationBadge cls={r.classification} /></td>
      <td className="px-3 py-2 w-32"><ScoreBar score={r.total_score} /></td>
      <td className="px-3 py-2"><VolCycleBadge state={r.volume_cycle_state} /></td>
      <td className="px-3 py-2 text-xs text-gray-500 max-w-28 truncate">{r.chart_pattern_primary}</td>
    </tr>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.dashboard();
      setData(d);
      setError(null);
    } catch (e: any) {
      setError("バックエンドに接続できません。FastAPIサーバーが起動しているか確認してください。");
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  if (error) {
    return (
      <div className="card p-6 max-w-xl mx-auto mt-10">
        <h2 className="text-red-600 font-bold mb-2">接続エラー</h2>
        <p className="text-gray-600 text-sm">{error}</p>
        <p className="text-gray-500 text-xs mt-3">起動コマンド: <code className="bg-gray-100 px-1 py-0.5 rounded">cd backend && uvicorn app.main:app --reload</code></p>
        <button onClick={load} className="mt-4 px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700">再試行</button>
      </div>
    );
  }

  if (!data) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;

  const statusColor = data.screening_running ? "text-green-600" : data.screening_status === "completed" ? "text-blue-600" : "text-gray-500";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%)" }}>
        <h1 className="text-white text-2xl font-bold mb-1">📈 短期急騰3000円以下AIスクリーナー</h1>
        <p className="text-blue-200 text-sm">日本株・米国株・ADRを対象とした短期急騰パターン分析・学習ツール</p>
        <div className="mt-3 flex flex-wrap gap-4 text-sm">
          <span className="text-blue-300">USD/JPY: <strong className="text-white">¥{data.usd_jpy?.toFixed(2)}</strong></span>
          <span className={`font-medium ${statusColor}`}>
            スクリーニング: {data.screening_running ? "⚡ 実行中" : data.screening_status === "completed" ? "✅ 完了" : "⏸ 待機中"}
          </span>
          {data.finished_at && <span className="text-gray-400 text-xs">{new Date(data.finished_at).toLocaleString("ja-JP")}</span>}
        </div>
        <div className="mt-3 p-2 bg-yellow-900/50 rounded text-yellow-200 text-xs">
          ⚠️ これは投資助言ではありません。分析・学習目的です。最終判断はユーザー自身が行ってください。
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
        <StatCard label="ユニバース総数" value={data.total_universe} />
        <StatCard label="価格条件通過" value={data.price_pass} color="text-blue-600" />
        <StatCard label="スクリーニング結果" value={data.total_results} />
        <StatCard label="採用候補" value={data.adopted_count} color="text-green-600" />
        <StatCard label="条件付き候補" value={data.conditional_count} color="text-blue-600" />
        <StatCard label="監視候補" value={data.watch_count} color="text-yellow-600" />
        <StatCard label="除外銘柄" value={data.total_exclusions} color="text-red-500" />
        <StatCard label="低スコア" value={data.low_score_count} color="text-gray-400" />
      </div>

      {/* Quick actions */}
      <div className="flex flex-wrap gap-3">
        <Link href="/screening" className="px-5 py-2.5 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 transition-colors">
          ⚡ 全銘柄スクリーニング実行
        </Link>
        <Link href="/ranking" className="px-5 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
          🏆 候補ランキングを見る
        </Link>
        <Link href="/excluded" className="px-5 py-2.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors">
          📋 除外銘柄
        </Link>
        <Link href="/aar" className="px-5 py-2.5 bg-purple-100 text-purple-700 rounded-lg text-sm font-medium hover:bg-purple-200 transition-colors">
          📝 AAR出力
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Top candidates */}
        <div className="lg:col-span-2 card overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 flex justify-between items-center">
            <h2 className="font-bold text-gray-800">🏆 上位候補ランキング</h2>
            <Link href="/ranking" className="text-xs text-blue-600 hover:underline">すべて見る</Link>
          </div>
          {data.top_candidates.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-gray-50 text-xs text-gray-500">
                    <th className="px-3 py-2 text-left">コード</th>
                    <th className="px-3 py-2 text-left">銘柄名</th>
                    <th className="px-3 py-2 text-left">市場</th>
                    <th className="px-3 py-2 text-right">円換算価格</th>
                    <th className="px-3 py-2 text-left">判定</th>
                    <th className="px-3 py-2 text-left w-32">スコア</th>
                    <th className="px-3 py-2 text-left">出来高サイクル</th>
                    <th className="px-3 py-2 text-left">パターン</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {data.top_candidates.map((r) => <CandidateRow key={r.symbol} r={r} />)}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-400">
              <p className="text-lg">スクリーニング未実行</p>
              <Link href="/screening" className="mt-3 inline-block px-4 py-2 bg-green-600 text-white rounded text-sm hover:bg-green-700">
                スクリーニングを実行する
              </Link>
            </div>
          )}
        </div>

        {/* Side panels */}
        <div className="space-y-4">
          <div className="card p-4">
            <h3 className="font-bold text-gray-700 mb-3 text-sm">出来高サイクル別件数</h3>
            {Object.entries(data.vol_cycle_counts).length > 0 ? (
              <div className="space-y-1">
                {Object.entries(data.vol_cycle_counts).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-xs">
                    <span className="text-gray-600">{k}</span>
                    <span className="font-bold text-gray-800">{v}件</span>
                  </div>
                ))}
              </div>
            ) : <p className="text-xs text-gray-400">データなし</p>}
          </div>

          <div className="card p-4">
            <h3 className="font-bold text-gray-700 mb-3 text-sm">チャートサイクル別件数</h3>
            {Object.entries(data.chart_cycle_counts).length > 0 ? (
              <div className="space-y-1">
                {Object.entries(data.chart_cycle_counts).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-xs">
                    <span className="text-gray-600">{k}</span>
                    <span className="font-bold text-gray-800">{v}件</span>
                  </div>
                ))}
              </div>
            ) : <p className="text-xs text-gray-400">データなし</p>}
          </div>

          <div className="card p-4">
            <h3 className="font-bold text-gray-700 mb-3 text-sm">⚠️ 警告フラグ別件数</h3>
            {Object.entries(data.warning_flag_counts).length > 0 ? (
              <div className="space-y-1">
                {Object.entries(data.warning_flag_counts).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-xs">
                    <span className="text-orange-600">{k}</span>
                    <span className="font-bold">{v}件</span>
                  </div>
                ))}
              </div>
            ) : <p className="text-xs text-gray-400">データなし</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
