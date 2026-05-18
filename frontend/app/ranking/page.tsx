"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, fetchAPI } from "@/lib/api";

interface PredictionResult {
  symbol: string;
  name?: string;
  market?: string;
  jpy_price?: number;
  price?: number;
  total_score?: number;
  classification?: string;
  // 予測フィールド
  prediction_label?: string;
  entry_timing_type?: string;
  final_prediction_score?: number;
  t1_entry_possible_estimate?: string;
  catalyst_quality_score?: number;
  catalyst_continuity_score?: number;
  pre_night_signal_score?: number;
  pattern_similarity_score?: number;
  positive_case_similarity?: number;
  negative_case_similarity?: number;
  overextension_risk_score?: number;
  bad_news_vacuum_score?: number;
  matched_past_cases?: Array<{ symbol: string; move_date: string; setup_type?: string; similarity: number; hit_20_percent?: boolean }>;
  reason_summary?: string;
  avoid_condition?: string;
  // 既存
  volume_cycle_state?: string;
  chart_cycle_state?: string;
  main_archetype?: string;
  upside_to_resistance?: number;
  ma25_deviation?: number;
  freshness_status?: string;
  warning_flags?: string[];
}

const LABELS = [
  { key: "急騰前夜候補", color: "bg-green-50 border-green-300 text-green-700", icon: "🌅" },
  { key: "条件付き候補", color: "bg-blue-50 border-blue-300 text-blue-700", icon: "🔵" },
  { key: "イベント監視", color: "bg-purple-50 border-purple-300 text-purple-700", icon: "📅" },
  { key: "二段目監視", color: "bg-amber-50 border-amber-300 text-amber-700", icon: "🎯" },
  { key: "悪材料出尽くし監視", color: "bg-pink-50 border-pink-300 text-pink-700", icon: "💊" },
  { key: "需給監視", color: "bg-gray-50 border-gray-300 text-gray-700", icon: "📊" },
  { key: "テーマ監視", color: "bg-cyan-50 border-cyan-300 text-cyan-700", icon: "🌐" },
  { key: "上がり切り警戒", color: "bg-orange-50 border-orange-300 text-orange-700", icon: "⚠️" },
  { key: "T0後追い警戒", color: "bg-red-50 border-red-300 text-red-700", icon: "🚫" },
  { key: "除外", color: "bg-gray-100 border-gray-200 text-gray-500", icon: "⊘" },
];

function PredictionCard({ r }: { r: PredictionResult }) {
  const score = r.final_prediction_score ?? r.total_score ?? 0;
  const overext = r.overextension_risk_score ?? 0;
  const pos = r.positive_case_similarity ?? 0;
  const neg = r.negative_case_similarity ?? 0;
  return (
    <div className="card p-4 hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start mb-2">
        <div>
          <Link href={`/stocks/${encodeURIComponent(r.symbol)}`} className="text-blue-600 font-mono font-bold hover:underline">
            {r.symbol}
          </Link>
          <p className="text-sm font-medium text-gray-800 truncate max-w-44">{r.name}</p>
          <p className="text-xs text-gray-400">{r.market}</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold text-gray-900">{score.toFixed(0)}</p>
          <p className="text-xs text-gray-400">final_score</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-2 text-xs">
        <div><span className="text-gray-400">円換算:</span> <span className="font-bold">¥{r.jpy_price?.toLocaleString()}</span></div>
        <div><span className="text-gray-400">上値余地:</span> <span className={`font-bold ${(r.upside_to_resistance ?? 0) >= 20 ? "text-green-600" : "text-gray-500"}`}>{r.upside_to_resistance?.toFixed(1)}%</span></div>
        <div><span className="text-gray-400">25MA乖離:</span> <span className={`font-bold ${(r.ma25_deviation ?? 0) > 50 ? "text-red-500" : "text-gray-700"}`}>{r.ma25_deviation?.toFixed(1)}%</span></div>
        <div><span className="text-gray-400">過熱:</span> <span className={`font-bold ${overext >= 60 ? "text-red-500" : "text-gray-700"}`}>{overext.toFixed(0)}</span></div>
      </div>

      <div className="grid grid-cols-2 gap-1 mb-2 text-xs bg-gray-50 p-2 rounded">
        <div className="text-gray-500">類似ポジ:</div>
        <div className="text-right font-bold text-green-600">{pos.toFixed(2)}</div>
        <div className="text-gray-500">類似ネガ:</div>
        <div className="text-right font-bold text-red-500">{neg.toFixed(2)}</div>
        <div className="text-gray-500">前夜兆候:</div>
        <div className="text-right font-bold">{(r.pre_night_signal_score ?? 0).toFixed(0)}</div>
      </div>

      {r.reason_summary && (
        <p className="text-xs text-gray-600 mb-1"><span className="font-medium">理由:</span> {r.reason_summary}</p>
      )}
      {r.entry_timing_type && (
        <p className="text-xs text-gray-600 mb-1"><span className="font-medium">タイミング:</span> {r.entry_timing_type}</p>
      )}
      {r.avoid_condition && r.avoid_condition !== "明確な見送り条件なし" && (
        <p className="text-xs text-orange-600 mb-2"><span className="font-medium">⚠️ 見送り条件:</span> {r.avoid_condition}</p>
      )}

      {r.matched_past_cases && r.matched_past_cases.length > 0 && (
        <div className="text-xs text-gray-500 mb-2">
          <span className="font-medium">類似過去:</span>{" "}
          {r.matched_past_cases.slice(0, 3).map((c, i) => (
            <span key={i} className="inline-block ml-1 bg-gray-100 px-1.5 py-0.5 rounded font-mono">
              {c.symbol}({c.move_date}, sim={c.similarity?.toFixed(2)})
            </span>
          ))}
        </div>
      )}

      <div className="flex gap-1 mt-2">
        <Link href={`/stocks/${encodeURIComponent(r.symbol)}`}
          className="flex-1 text-center text-xs py-1.5 bg-blue-50 text-blue-600 rounded hover:bg-blue-100">
          詳細 →
        </Link>
        <button onClick={async () => {
          try {
            const ep = await api.entryPlan(r as object);
            const res = await api.savePredictionLog(r as object, ep);
            alert(`予測として保存しました (log_id=${res.log_id})`);
          } catch (e: any) {
            alert("保存失敗: " + e.message);
          }
        }} className="flex-1 text-xs py-1.5 bg-emerald-100 text-emerald-700 rounded hover:bg-emerald-200">
          💾 予測保存
        </button>
      </div>
    </div>
  );
}

export default function RankingPage() {
  const [all, setAll] = useState<PredictionResult[]>([]);
  const [activeTab, setActiveTab] = useState<string>("急騰前夜候補");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.screeningResults({ limit: 1000 }).then((r) => {
      setAll(r.results || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;
  if (all.length === 0) {
    return (
      <div className="card p-10 text-center">
        <p className="text-gray-500 text-lg">スクリーニング結果がありません</p>
        <Link href="/screening" className="mt-4 inline-block px-4 py-2 bg-green-600 text-white rounded text-sm hover:bg-green-700">スクリーニングを実行</Link>
      </div>
    );
  }

  // 各ラベルごとに件数集計
  const counts: Record<string, number> = {};
  for (const l of LABELS) counts[l.key] = 0;
  counts["未分類"] = 0;
  for (const r of all) {
    const k = r.prediction_label || "未分類";
    counts[k] = (counts[k] || 0) + 1;
  }

  const filtered = all.filter((r) => (r.prediction_label || "未分類") === activeTab);

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">🏆 AAR予測ランキング</h1>
        <p className="text-blue-200 text-sm">
          各銘柄を過去AAR学習データと類似度マッチングし、急騰前夜パターンに該当するかを判定したランキング。
        </p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ これは投資助言ではありません。過去類似分析・学習目的のツールです。
        </div>
      </div>

      {/* タブ */}
      <div className="flex flex-wrap gap-2">
        {LABELS.map((l) => (
          <button key={l.key} onClick={() => setActiveTab(l.key)}
            className={`px-3 py-2 rounded text-xs font-medium border transition ${activeTab === l.key ? l.color + " ring-2 ring-offset-1 ring-blue-300" : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"}`}>
            <span className="mr-1">{l.icon}</span>
            {l.key} <span className="ml-1 font-bold">({counts[l.key] || 0})</span>
          </button>
        ))}
        {counts["未分類"] > 0 && (
          <button onClick={() => setActiveTab("未分類")}
            className={`px-3 py-2 rounded text-xs font-medium border ${activeTab === "未分類" ? "bg-gray-200" : "bg-white text-gray-500 border-gray-200"}`}>
            未分類 ({counts["未分類"]})
          </button>
        )}
      </div>

      {/* 内容 */}
      {filtered.length === 0 ? (
        <div className="card p-10 text-center text-gray-400">
          この分類に該当する銘柄はありません
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.slice(0, 60).map((r) => <PredictionCard key={r.symbol} r={r} />)}
        </div>
      )}
      {filtered.length > 60 && (
        <p className="text-center text-xs text-gray-400">最初の60件を表示 / 全{filtered.length}件</p>
      )}

      <div className="card p-3 text-xs text-gray-500">
        <p><strong>分類定義:</strong></p>
        <ul className="ml-4 list-disc space-y-0.5 mt-1">
          <li><strong>急騰前夜候補:</strong> T-1時点で先行兆候・上値余地・支持線・過熱なし全てクリア</li>
          <li><strong>条件付き候補:</strong> 部分的に条件クリア。小ロット限定や様子見</li>
          <li><strong>イベント監視:</strong> 決算/FDA/政策イベント待ち</li>
          <li><strong>二段目監視:</strong> 一段目急騰の押し目を待つ</li>
          <li><strong>悪材料出尽くし監視:</strong> 公式リスク後退確認後のみ</li>
          <li><strong>需給監視:</strong> 出来高は良いが会社固有材料が未確認</li>
          <li><strong>テーマ監視:</strong> テーマ波及のみで本命特定待ち</li>
          <li><strong>上がり切り警戒:</strong> 25MA乖離過大・短期急騰済み</li>
          <li><strong>T0後追い警戒:</strong> T-1兆候なくT0で初めて出来高急増した類似パターン</li>
          <li><strong>除外:</strong> 価格条件外・データ古い・上値余地なし</li>
        </ul>
      </div>
    </div>
  );
}
