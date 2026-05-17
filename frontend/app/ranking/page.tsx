"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { ScreeningResult } from "@/lib/types";
import ClassificationBadge from "@/components/ClassificationBadge";
import ScoreBar from "@/components/ScoreBar";
import VolCycleBadge from "@/components/VolCycleBadge";

type ViewMode = "card" | "table";

function StockCard({ r }: { r: ScreeningResult }) {
  const upside = r.upside_to_resistance ?? 0;
  const change = r.price_change_1d ?? 0;
  return (
    <div className="card p-4 hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start mb-3">
        <div>
          <Link href={`/stocks/${encodeURIComponent(r.symbol)}`} className="text-blue-600 font-mono font-bold hover:underline text-sm">
            {r.symbol}
          </Link>
          <p className="text-gray-700 text-sm font-medium mt-0.5 truncate max-w-40">{r.name}</p>
          <p className="text-xs text-gray-400">{r.market}{r.is_adr ? " (ADR)" : ""}</p>
        </div>
        <ClassificationBadge cls={r.classification} />
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3 text-xs">
        <div>
          <p className="text-gray-400">円換算価格</p>
          <p className="font-bold text-gray-800">¥{r.jpy_price?.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-gray-400">前日比</p>
          <p className={`font-bold ${change >= 0 ? "text-green-600" : "text-red-500"}`}>{change.toFixed(2)}%</p>
        </div>
        <div>
          <p className="text-gray-400">上値余地</p>
          <p className={`font-bold ${upside >= 20 ? "text-green-600" : "text-gray-500"}`}>{upside.toFixed(1)}%</p>
        </div>
        <div>
          <p className="text-gray-400">25MA乖離</p>
          <p className={`font-bold ${(r.ma25_deviation ?? 0) > 50 ? "text-red-500" : "text-gray-600"}`}>
            {r.ma25_deviation?.toFixed(1)}%
          </p>
        </div>
      </div>

      <div className="mb-3">
        <p className="text-xs text-gray-400 mb-1">急騰予兆スコア</p>
        <ScoreBar score={r.total_score} />
      </div>

      <div className="flex flex-wrap gap-1 mb-3">
        <VolCycleBadge state={r.volume_cycle_state} />
        {r.chart_cycle_state && (
          <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">{r.chart_cycle_state}</span>
        )}
      </div>

      {r.main_archetype && (
        <p className="text-xs text-gray-500 mb-1"><span className="font-medium">主型:</span> {r.main_archetype}</p>
      )}
      {r.chart_pattern_primary && r.chart_pattern_primary !== "特定パターンなし" && (
        <p className="text-xs text-gray-500 mb-1"><span className="font-medium">パターン:</span> {r.chart_pattern_primary}</p>
      )}
      {r.warning_flags && r.warning_flags.length > 0 && (
        <p className="text-xs text-orange-500">⚠️ {r.warning_flags.join(", ")}</p>
      )}

      <Link href={`/stocks/${encodeURIComponent(r.symbol)}`}
        className="mt-3 block text-center text-xs py-1.5 bg-blue-50 text-blue-600 rounded hover:bg-blue-100 transition-colors">
        詳細を見る →
      </Link>
    </div>
  );
}

export default function RankingPage() {
  const [all, setAll] = useState<ScreeningResult[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("card");
  const [activeTab, setActiveTab] = useState<string>("採用候補");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.screeningResults({ limit: 500 }).then((r) => {
      setAll(r.results || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const tabs = ["採用候補", "条件付き候補", "監視候補"];
  const filtered = all.filter((r) => r.classification === activeTab);

  if (loading) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;

  if (all.length === 0) {
    return (
      <div className="card p-10 text-center">
        <p className="text-gray-500 text-lg">スクリーニング結果がありません</p>
        <Link href="/screening" className="mt-4 inline-block px-4 py-2 bg-green-600 text-white rounded text-sm hover:bg-green-700">
          スクリーニングを実行する
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <h1 className="text-xl font-bold text-gray-800">🏆 候補ランキング</h1>
        <div className="flex gap-2">
          <button onClick={() => setViewMode("card")} className={`px-3 py-1.5 rounded text-sm ${viewMode === "card" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600"}`}>
            カード
          </button>
          <button onClick={() => setViewMode("table")} className={`px-3 py-1.5 rounded text-sm ${viewMode === "table" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600"}`}>
            テーブル
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-white rounded-lg border border-gray-200 p-1 w-fit">
        {tabs.map((t) => {
          const count = all.filter((r) => r.classification === t).length;
          return (
            <button key={t} onClick={() => setActiveTab(t)}
              className={`px-4 py-2 rounded text-sm font-medium transition-colors ${activeTab === t ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-50"}`}>
              {t} ({count})
            </button>
          );
        })}
      </div>

      {filtered.length === 0 ? (
        <div className="card p-8 text-center text-gray-400">この分類の候補はありません</div>
      ) : viewMode === "card" ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map((r) => <StockCard key={r.symbol} r={r} />)}
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100 text-gray-500">
                  <th className="px-3 py-2 text-left">コード</th>
                  <th className="px-3 py-2 text-left">銘柄名</th>
                  <th className="px-3 py-2 text-left">市場</th>
                  <th className="px-3 py-2 text-right">円換算価格</th>
                  <th className="px-3 py-2 text-right">前日比</th>
                  <th className="px-3 py-2 text-right">上値余地</th>
                  <th className="px-3 py-2 text-right">25MA乖離</th>
                  <th className="px-3 py-2 text-left">スコア</th>
                  <th className="px-3 py-2 text-left">判定</th>
                  <th className="px-3 py-2 text-left">出来高サイクル</th>
                  <th className="px-3 py-2 text-left">チャートサイクル</th>
                  <th className="px-3 py-2 text-left">主型</th>
                  <th className="px-3 py-2 text-left">警告</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((r) => (
                  <tr key={r.symbol} className="hover:bg-blue-50 transition-colors">
                    <td className="px-3 py-2">
                      <Link href={`/stocks/${encodeURIComponent(r.symbol)}`} className="text-blue-600 font-mono font-bold hover:underline">
                        {r.symbol}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-gray-700 max-w-32 truncate">{r.name}</td>
                    <td className="px-3 py-2 text-gray-500">{r.market}</td>
                    <td className="px-3 py-2 font-mono text-right">¥{r.jpy_price?.toLocaleString()}</td>
                    <td className={`px-3 py-2 text-right font-medium ${(r.price_change_1d ?? 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
                      {r.price_change_1d?.toFixed(2)}%
                    </td>
                    <td className={`px-3 py-2 text-right font-medium ${(r.upside_to_resistance ?? 0) >= 20 ? "text-green-600" : "text-gray-500"}`}>
                      {r.upside_to_resistance?.toFixed(1)}%
                    </td>
                    <td className={`px-3 py-2 text-right ${(r.ma25_deviation ?? 0) > 50 ? "text-red-500" : "text-gray-600"}`}>
                      {r.ma25_deviation?.toFixed(1)}%
                    </td>
                    <td className="px-3 py-2 w-28"><ScoreBar score={r.total_score} /></td>
                    <td className="px-3 py-2"><ClassificationBadge cls={r.classification} /></td>
                    <td className="px-3 py-2"><VolCycleBadge state={r.volume_cycle_state} /></td>
                    <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{r.chart_cycle_state}</td>
                    <td className="px-3 py-2 text-gray-600 max-w-32 truncate">{r.main_archetype}</td>
                    <td className="px-3 py-2 text-orange-500 max-w-32 truncate">{(r.warning_flags || []).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
