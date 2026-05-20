"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";

export default function LearningCenterPage() {
  const [summary, setSummary] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [quality, setQuality] = useState<any>(null);
  const [reviewSummary, setReviewSummary] = useState<any>(null);
  const [automationStatus, setAutomationStatus] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, st, q, rs, as_] = await Promise.all([
        fetchAPI("/api/training-builder/summary").catch(() => null),
        fetchAPI("/api/training-builder/feature-stats").catch(() => null),
        fetchAPI("/api/training-builder/quality-report").catch(() => null),
        fetchAPI("/api/prediction-review/summary").catch(() => null),
        fetchAPI("/api/automation/status").catch(() => null),
      ]);
      setSummary(s); setStats(st); setQuality(q); setReviewSummary(rs); setAutomationStatus(as_);
    } catch (e: any) { setError(e.message); }
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);

  if (error) return <div className="card p-6"><p className="text-red-600">エラー: {error}</p></div>;
  if (!summary) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;

  const StatCard = ({ label, value, color = "text-gray-900", desc }: any) => (
    <div className="card p-3">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {desc && <p className="text-xs text-gray-400 mt-1">{desc}</p>}
    </div>
  );

  // 重要特徴量の差分計算
  const featureDiffs: Array<{ key: string; pos: number; neg: number; diff: number }> = [];
  if (stats?.positive_avg && stats?.negative_avg) {
    Object.keys(stats.positive_avg).forEach((k) => {
      const p = stats.positive_avg[k] ?? 0;
      const n = stats.negative_avg[k] ?? 0;
      featureDiffs.push({ key: k, pos: p, neg: n, diff: p - n });
    });
  }
  featureDiffs.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #1e1b4b 0%, #312e81 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">🧠 AI学習センター</h1>
        <p className="text-indigo-200 text-sm">このAIが何を学習し、どの特徴が成功/失敗に効いているかを可視化します</p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ 投資助言ではありません。分析・学習・検証目的のツールです。
        </div>
      </div>

      {/* A. 学習パイプライン図 */}
      <div className="card p-4">
        <h2 className="font-bold text-gray-800 mb-3">📐 学習パイプライン</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 lg:grid-cols-11 gap-2 text-xs">
          {[
            { num: 1, label: "価格収集", color: "bg-blue-50" },
            { num: 2, label: "材料収集", color: "bg-emerald-50" },
            { num: 3, label: "急騰検出", color: "bg-purple-50" },
            { num: 4, label: "T-1特徴量", color: "bg-pink-50" },
            { num: 5, label: "教師化", color: "bg-rose-50" },
            { num: 6, label: "類似度計算", color: "bg-cyan-50" },
            { num: 7, label: "ランキング", color: "bg-amber-50" },
            { num: 8, label: "予測保存", color: "bg-green-50" },
            { num: 9, label: "結果検証", color: "bg-orange-50" },
            { num: 10, label: "成功/失敗AAR", color: "bg-red-50" },
            { num: 11, label: "次回改善", color: "bg-fuchsia-50" },
          ].map((step) => (
            <div key={step.num} className={`${step.color} p-2 rounded border border-gray-200 text-center`}>
              <p className="text-xs text-gray-400">STEP {step.num}</p>
              <p className="font-bold text-gray-700">{step.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* B. 教師データ構成 */}
      <div className="card p-4">
        <h2 className="font-bold text-gray-800 mb-3">⚖️ 教師データ構成</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 lg:grid-cols-8 gap-3 text-xs">
          {Object.entries(summary.by_case_type || {}).map(([k, v]: [string, any]) => {
            const isPos = k.startsWith("positive");
            const isFailed = k.startsWith("failed");
            const isNeg = k.startsWith("negative");
            return (
              <div key={k} className={`p-2 rounded border ${
                isPos ? "bg-green-50 border-green-200 text-green-700" :
                isFailed ? "bg-red-50 border-red-200 text-red-700" :
                isNeg ? "bg-gray-50 border-gray-200 text-gray-700" :
                "bg-blue-50 border-blue-200 text-blue-700"
              }`}>
                <p className="text-xs">{k}</p>
                <p className="font-bold text-lg">{v}</p>
              </div>
            );
          })}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
          <StatCard label="positive (合計)" value={summary.positive_cases} color="text-green-600" />
          <StatCard label="negative (合計)" value={summary.negative_cases} color="text-red-500" />
          <StatCard label="N/P 比率" value={summary.positive_negative_ratio} color={summary.positive_negative_ratio >= 1 ? "text-green-600" : "text-orange-500"} desc="推奨 >= 2" />
          <StatCard label="quality_score" value={quality?.quality_score ?? "-"} color="text-blue-600" desc="T0リーク・重複・極端値チェック" />
        </div>
      </div>

      {/* C. 成功 vs 失敗 特徴量差分 */}
      {featureDiffs.length > 0 && (
        <div className="card p-4">
          <h2 className="font-bold text-gray-800 mb-3">🔬 成功 vs 失敗 — 効いている特徴TOP15</h2>
          <p className="text-xs text-gray-500 mb-3">
            positive (n={stats?.n_positive ?? 0}) と negative (n={stats?.n_negative ?? 0}) の平均値の差分が大きい特徴量
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="border-b border-gray-100 text-gray-500">
                <th className="px-2 py-1 text-left">特徴量</th>
                <th className="px-2 py-1 text-right">positive avg</th>
                <th className="px-2 py-1 text-right">negative avg</th>
                <th className="px-2 py-1 text-right">差分 (pos-neg)</th>
                <th className="px-2 py-1 text-left">解釈</th>
              </tr></thead>
              <tbody>
                {featureDiffs.slice(0, 15).map((f) => (
                  <tr key={f.key} className="border-b border-gray-50">
                    <td className="px-2 py-1 font-mono">{f.key}</td>
                    <td className="px-2 py-1 text-right text-green-600">{f.pos?.toFixed(2)}</td>
                    <td className="px-2 py-1 text-right text-red-500">{f.neg?.toFixed(2)}</td>
                    <td className={`px-2 py-1 text-right font-bold ${f.diff > 0 ? "text-green-700" : "text-red-700"}`}>
                      {f.diff >= 0 ? "+" : ""}{f.diff.toFixed(2)}
                    </td>
                    <td className="px-2 py-1 text-gray-600 text-xs">
                      {f.diff > 0 ? `成功ケースで ${f.key} が高い` : `失敗ケースで ${f.key} が高い`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* D. ケース別平均 */}
      {stats?.overextended_failed_avg && stats.n_overext_failed > 0 && (
        <div className="card p-4">
          <h2 className="font-bold text-gray-800 mb-3">🚨 失敗パターン別の特徴量プロファイル</h2>
          <p className="text-xs text-gray-500 mb-3">
            上がり切り失敗(n={stats.n_overext_failed}) / 材料弱失敗(n={stats.n_weak_material_failed}) / 材料出尽くし(n={stats.n_material_exhaustion_failed})
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="border-b text-gray-500">
                <th className="px-2 py-1 text-left">特徴量</th>
                <th className="px-2 py-1 text-right">overextended</th>
                <th className="px-2 py-1 text-right">weak_material</th>
                <th className="px-2 py-1 text-right">material_exhaustion</th>
              </tr></thead>
              <tbody>
                {["ma25_deviation", "price_change_5d", "price_change_20d", "overextension_score", "volume_ratio_20d", "resistance_upside", "support_distance"].map((k) => (
                  <tr key={k} className="border-b border-gray-50">
                    <td className="px-2 py-1 font-mono">{k}</td>
                    <td className="px-2 py-1 text-right text-orange-600">{stats.overextended_failed_avg?.[k] ?? "-"}</td>
                    <td className="px-2 py-1 text-right text-yellow-600">{stats.weak_material_failed_avg?.[k] ?? "-"}</td>
                    <td className="px-2 py-1 text-right text-rose-600">{stats.material_exhaustion_failed_avg?.[k] ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* E. 今日学習したこと */}
      <div className="card p-4">
        <h2 className="font-bold text-gray-800 mb-3">📅 今日学習したこと</h2>
        {automationStatus?.today ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 text-sm">
            <StatCard label="急騰検出" value={automationStatus.today.surge_detected_today || 0} color="text-green-600" />
            <StatCard label="AAR追加" value={automationStatus.today.aar_cases_today || 0} color="text-purple-600" />
            <StatCard label="positive" value={automationStatus.today.positive_cases_today || 0} color="text-green-700" />
            <StatCard label="negative" value={automationStatus.today.negative_cases_today || 0} color="text-red-500" />
            <StatCard label="予測保存" value={automationStatus.today.predictions_saved_today || 0} color="text-emerald-600" />
            <StatCard label="outcomes更新" value={automationStatus.today.outcomes_updated_today || 0} color="text-blue-600" />
            <StatCard label="教師化" value={automationStatus.today.training_cases_today || 0} color="text-fuchsia-600" />
          </div>
        ) : (
          <p className="text-gray-400 text-sm">automation_status を取得できませんでした</p>
        )}
      </div>

      {/* F. 精度メトリクス */}
      {reviewSummary && (
        <div className="card p-4">
          <h2 className="font-bold text-gray-800 mb-3">🎯 予測精度メトリクス</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
            <StatCard label="保存済み予測" value={reviewSummary.total_logs} />
            <StatCard label="検証済み" value={reviewSummary.reviewed_count} color="text-blue-600" />
            <StatCard label="成功" value={reviewSummary.by_success_label?.["成功"] || 0} color="text-green-600" />
            <StatCard label="失敗" value={reviewSummary.by_success_label?.["失敗"] || 0} color="text-red-500" />
            <StatCard label="+20%達成" value={reviewSummary.hit_20_count} color="text-green-700" />
            <StatCard label="平均最大上昇率" value={`${reviewSummary.avg_max_gain?.toFixed(1)}%`} color="text-green-600" />
          </div>

          {Object.keys(reviewSummary.by_prediction_label || {}).length > 0 && (
            <div className="mt-4">
              <h3 className="font-bold text-gray-700 text-sm mb-2">prediction_label別勝率</h3>
              <table className="w-full text-xs">
                <thead><tr className="border-b text-gray-500">
                  <th className="px-2 py-1 text-left">ラベル</th>
                  <th className="px-2 py-1 text-right">件数</th>
                  <th className="px-2 py-1 text-right">成功</th>
                  <th className="px-2 py-1 text-right">失敗</th>
                  <th className="px-2 py-1 text-right">勝率</th>
                  <th className="px-2 py-1 text-right">avg_gain</th>
                </tr></thead>
                <tbody>
                  {Object.entries(reviewSummary.by_prediction_label).map(([k, v]: [string, any]) => (
                    <tr key={k} className="border-b border-gray-50">
                      <td className="px-2 py-1 font-medium">{k}</td>
                      <td className="px-2 py-1 text-right">{v.count}</td>
                      <td className="px-2 py-1 text-right text-green-600">{v.success}</td>
                      <td className="px-2 py-1 text-right text-red-500">{v.failed}</td>
                      <td className="px-2 py-1 text-right font-bold">{v.win_rate}%</td>
                      <td className="px-2 py-1 text-right">{v.avg_gain}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* スコア重み */}
      <div className="card p-4">
        <h2 className="font-bold text-gray-800 mb-3">⚙️ 現在のスコア重み</h2>
        <table className="w-full text-xs">
          <thead><tr className="border-b text-gray-500">
            <th className="px-2 py-1 text-left">スコア要素</th>
            <th className="px-2 py-1 text-right">重み</th>
            <th className="px-2 py-1 text-left">説明</th>
          </tr></thead>
          <tbody>
            <tr className="border-b border-gray-50"><td className="px-2 py-1 font-mono">upside_score</td><td className="text-right">15</td><td>抵抗線までの上値余地</td></tr>
            <tr className="border-b border-gray-50"><td className="px-2 py-1 font-mono">future_catalyst_score</td><td className="text-right">15</td><td>未来急騰予兆 (出来高サイクル+チャートサイクル)</td></tr>
            <tr className="border-b border-gray-50"><td className="px-2 py-1 font-mono">chart_score</td><td className="text-right">15</td><td>チャート構造 (パターン+MA配置)</td></tr>
            <tr className="border-b border-gray-50"><td className="px-2 py-1 font-mono">volume_cycle_score</td><td className="text-right">15</td><td>出来高サイクル状態</td></tr>
            <tr className="border-b border-gray-50"><td className="px-2 py-1 font-mono">material_theme_score</td><td className="text-right">10</td><td>材料・テーマの芯</td></tr>
            <tr className="border-b border-gray-50"><td className="px-2 py-1 font-mono">supply_score</td><td className="text-right">10</td><td>需給の軽さ (低位株ほど高い)</td></tr>
            <tr className="border-b border-gray-50"><td className="px-2 py-1 font-mono">archetype_score</td><td className="text-right">10</td><td>アーキタイプの重なり</td></tr>
            <tr className="border-b border-gray-50"><td className="px-2 py-1 font-mono">risk_management_score</td><td className="text-right">10</td><td>リスク管理のしやすさ</td></tr>
            <tr className="border-b border-gray-50 bg-fuchsia-50"><td className="px-2 py-1 font-mono">training_based_score_adjustment</td><td className="text-right text-fuchsia-700">±30</td><td>過去5年教師データとの類似度補正</td></tr>
          </tbody>
        </table>
      </div>

      <div className="card p-3 text-xs text-gray-500">
        ⚠️ これは投資助言ではありません。「買え」「必ず上がる」等の表現は行いません。最終判断はユーザー自身が行ってください。
        <br />
        🔗 関連: <Link href="/training-builder" className="text-blue-600 hover:underline">教師データ構築</Link> /{" "}
        <Link href="/prediction-review" className="text-blue-600 hover:underline">予測検証</Link> /{" "}
        <Link href="/automation" className="text-blue-600 hover:underline">自動化</Link> /{" "}
        <Link href="/ai-analyst" className="text-blue-600 hover:underline">AI総合分析</Link>
      </div>
    </div>
  );
}
