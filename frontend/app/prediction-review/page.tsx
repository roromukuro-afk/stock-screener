"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { fetchAPI, API_BASE_URL } from "@/lib/api";

interface Summary {
  total_logs: number;
  reviewed_count: number;
  open_count: number;
  by_success_label: Record<string, number>;
  by_failed_reason: Record<string, number>;
  hit_20_count: number;
  stop_loss_hit_count: number;
  saved_as_training_count: number;
  avg_max_gain: number;
  avg_max_drawdown: number;
  by_prediction_label: Record<string, any>;
}

const LABEL_COLOR: Record<string, string> = {
  "成功": "text-green-700 bg-green-50 border-green-200",
  "条件付き成功": "text-blue-700 bg-blue-50 border-blue-200",
  "失敗": "text-red-700 bg-red-50 border-red-200",
  "見送り正解": "text-emerald-700 bg-emerald-50 border-emerald-200",
  "追いかけ禁止正解": "text-emerald-700 bg-emerald-50 border-emerald-200",
  "未判定": "text-gray-500 bg-gray-50 border-gray-200",
};

export default function PredictionReviewPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [items, setItems] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string>("");

  const [surge20Perf, setSurge20Perf] = useState<any>(null);
  const load = useCallback(async () => {
    try {
      const [s, r, sp] = await Promise.all([
        fetchAPI("/api/prediction-review/summary"),
        fetchAPI("/api/prediction-review/results?limit=300"),
        fetchAPI("/api/surge-20/prediction-performance").catch(() => null),
      ]);
      setSummary(s);
      setItems(r.items || []);
      setSurge20Perf(sp);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  const triggerSurge20Review = async () => {
    try {
      await fetchAPI("/api/surge-20/review-predictions?limit=300", { method: "POST", body: "{}" });
      setTimeout(load, 5000);
    } catch (e: any) {
      alert(e.message);
    }
  };
  const saveSurge20Training = async () => {
    try {
      const r = await fetchAPI("/api/surge-20/save-reviewed-predictions-as-training", { method: "POST", body: "{}" });
      alert(`保存: positive=${r.positive_saved} negative=${r.negative_saved}`);
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  useEffect(() => { load(); }, [load]);

  const action = async (path: string, label: string) => {
    setBusy(label);
    try {
      await fetchAPI(path, { method: "POST", body: "{}" });
      await load();
    } catch (e: any) {
      alert(`${label} 失敗: ${e.message}`);
    } finally {
      setBusy("");
    }
  };

  const reviewOne = async (id: number) => {
    setBusy(`review-${id}`);
    try {
      await fetchAPI(`/api/prediction-review/review/${id}`, { method: "POST", body: "{}" });
      await load();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setBusy("");
    }
  };

  const saveAsTraining = async (id: number) => {
    setBusy(`save-${id}`);
    try {
      const r = await fetchAPI(`/api/prediction-review/save-as-training/${id}`, { method: "POST", body: "{}" });
      alert(`保存しました: case_id=${r.case_id} pos=${r.is_positive} neg=${r.is_negative}`);
      await load();
    } catch (e: any) {
      alert(e.message);
    } finally {
      setBusy("");
    }
  };

  if (error) return <div className="card p-6 max-w-2xl mx-auto"><p className="text-red-600">エラー: {error}</p></div>;
  if (!summary) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #134e4a 0%, #115e59 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">🔁 予測検証・反省ログ</h1>
        <p className="text-teal-200 text-sm">予測を保存→自動追跡→成功/失敗判定→教師データ化のループ。</p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ これは投資助言ではありません。分析・学習・検証目的のツールです。
        </div>
      </div>

      {/* surge_20専用パネル */}
      {surge20Perf && (
        <div className="card p-4 border-l-4 border-emerald-400">
          <h2 className="font-bold text-emerald-800 mb-3">🌅 surge_20_prediction 専用成績</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mb-3">
            <div><p className="text-xs text-gray-500">total</p><p className="text-2xl font-bold">{surge20Perf.total_surge_20_predictions}</p></div>
            <div><p className="text-xs text-gray-500">saved as training</p><p className="text-2xl font-bold text-fuchsia-600">{surge20Perf.saved_as_training}</p></div>
          </div>
          {surge20Perf.by_result_label && Object.keys(surge20Perf.by_result_label).length > 0 && (
            <div className="flex flex-wrap gap-2 text-xs mb-3">
              {Object.entries(surge20Perf.by_result_label).map(([k, v]: [string, any]) => {
                const isSuccess = k.includes("success");
                const isFailed = k.includes("failed") || k.includes("stopped");
                const isOpen = k === "still_open" || k === "insufficient_days";
                return (
                  <span key={k} className={`px-2 py-1 rounded border ${
                    isSuccess ? "bg-green-50 border-green-300 text-green-700" :
                    isFailed ? "bg-red-50 border-red-300 text-red-700" :
                    isOpen ? "bg-gray-50 border-gray-300 text-gray-600" :
                    "bg-yellow-50 border-yellow-200 text-yellow-700"
                  }`}>{k}: <strong>{v}</strong></span>
                );
              })}
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={triggerSurge20Review}
              className="px-4 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700">
              🔁 surge_20 予測を検証
            </button>
            <button onClick={saveSurge20Training}
              className="px-4 py-2 bg-fuchsia-600 text-white rounded text-sm hover:bg-fuchsia-700">
              🎓 検証結果を教師データへ
            </button>
          </div>
        </div>
      )}

      {/* 操作ボタン */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => action("/api/prediction-review/update-outcomes", "outcomes更新")} disabled={!!busy}
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
          📈 予測結果を更新 (全件)
        </button>
        <button onClick={() => action("/api/prediction-review/review-all", "review-all")} disabled={!!busy}
          className="px-4 py-2 bg-purple-600 text-white rounded text-sm hover:bg-purple-700 disabled:opacity-50">
          🧪 全件を再検証
        </button>
        <button onClick={() => action("/api/prediction-review/save-all-reviewed-as-training", "save-all-training")} disabled={!!busy}
          className="px-4 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700 disabled:opacity-50">
          🎓 全件を教師データへ保存
        </button>
        <a href={`${API_BASE_URL}/api/prediction-review/export/csv`} target="_blank"
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200">
          📄 CSV出力
        </a>
        <Link href="/ranking" className="px-4 py-2 bg-yellow-100 text-yellow-700 rounded text-sm hover:bg-yellow-200">
          🏆 ランキング に戻る
        </Link>
      </div>

      {/* サマリ */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
        <div className="card p-3"><p className="text-xs text-gray-500">保存済み予測</p><p className="text-2xl font-bold">{summary.total_logs}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">検証済み</p><p className="text-2xl font-bold text-blue-600">{summary.reviewed_count}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">検証待ち</p><p className="text-2xl font-bold text-orange-500">{summary.open_count}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">成功</p><p className="text-2xl font-bold text-green-600">{summary.by_success_label?.["成功"] || 0}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">失敗</p><p className="text-2xl font-bold text-red-500">{summary.by_success_label?.["失敗"] || 0}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">+20%達成</p><p className="text-2xl font-bold text-green-700">{summary.hit_20_count}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">損切り到達</p><p className="text-2xl font-bold text-red-700">{summary.stop_loss_hit_count}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">平均最大上昇率</p><p className="text-2xl font-bold text-green-600">{summary.avg_max_gain?.toFixed(1)}%</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">平均最大下落率</p><p className="text-2xl font-bold text-red-500">{summary.avg_max_drawdown?.toFixed(1)}%</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">教師データ追加済</p><p className="text-2xl font-bold text-purple-600">{summary.saved_as_training_count}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">条件付き成功</p><p className="text-2xl font-bold text-blue-600">{summary.by_success_label?.["条件付き成功"] || 0}</p></div>
        <div className="card p-3"><p className="text-xs text-gray-500">見送り正解</p><p className="text-2xl font-bold text-emerald-600">{summary.by_success_label?.["見送り正解"] || 0}</p></div>
      </div>

      {/* prediction_label別成績 */}
      {Object.keys(summary.by_prediction_label || {}).length > 0 && (
        <div className="card p-4">
          <h3 className="font-bold text-gray-800 mb-3">📊 prediction_label別成績</h3>
          <table className="w-full text-xs">
            <thead><tr className="text-gray-500 border-b border-gray-100">
              <th className="px-2 py-1 text-left">ラベル</th>
              <th className="px-2 py-1 text-right">件数</th>
              <th className="px-2 py-1 text-right">成功</th>
              <th className="px-2 py-1 text-right">失敗</th>
              <th className="px-2 py-1 text-right">勝率</th>
              <th className="px-2 py-1 text-right">avg_gain</th>
            </tr></thead>
            <tbody>
              {Object.entries(summary.by_prediction_label).map(([k, v]: [string, any]) => (
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

      {/* 失敗理由 */}
      {Object.keys(summary.by_failed_reason || {}).length > 0 && (
        <div className="card p-4">
          <h3 className="font-bold text-gray-800 mb-2">❌ 失敗理由別件数</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(summary.by_failed_reason).map(([k, v]) => (
              <span key={k} className="text-xs px-2 py-1 bg-red-50 text-red-700 rounded">
                {k}: {v}件
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 予測一覧 */}
      <div className="card p-4">
        <h3 className="font-bold text-gray-800 mb-3">予測ログ一覧 ({items.length}件)</h3>
        {items.length === 0 ? (
          <p className="text-center text-gray-400 py-6">
            予測ログがありません。<Link href="/ranking" className="text-blue-600 hover:underline">ランキング</Link>から「予測として保存」を押してください。
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 border-b border-gray-100 text-gray-500">
                <tr>
                  <th className="px-2 py-1 text-left">id</th>
                  <th className="px-2 py-1 text-left">symbol</th>
                  <th className="px-2 py-1 text-left">予測日</th>
                  <th className="px-2 py-1 text-left">予測ラベル</th>
                  <th className="px-2 py-1 text-right">score</th>
                  <th className="px-2 py-1 text-right">entry</th>
                  <th className="px-2 py-1 text-right">SL</th>
                  <th className="px-2 py-1 text-right">TP1</th>
                  <th className="px-2 py-1 text-right">max_gain</th>
                  <th className="px-2 py-1 text-right">max_dd</th>
                  <th className="px-2 py-1 text-center">+20%</th>
                  <th className="px-2 py-1 text-center">SL hit</th>
                  <th className="px-2 py-1 text-left">結果</th>
                  <th className="px-2 py-1 text-left">失敗理由</th>
                  <th className="px-2 py-1 text-center">教師化</th>
                  <th className="px-2 py-1 text-left">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => {
                  const rev = it.review;
                  return (
                    <tr key={it.id} className="border-b border-gray-50 hover:bg-blue-50">
                      <td className="px-2 py-1 text-gray-400">{it.id}</td>
                      <td className="px-2 py-1">
                        <Link href={`/stocks/${encodeURIComponent(it.symbol)}`} className="text-blue-600 font-mono font-bold hover:underline">{it.symbol}</Link>
                      </td>
                      <td className="px-2 py-1 text-gray-600">{it.prediction_date}</td>
                      <td className="px-2 py-1 text-gray-700 text-xs">{it.prediction_label}</td>
                      <td className="px-2 py-1 text-right font-bold">{it.final_prediction_score?.toFixed(0)}</td>
                      <td className="px-2 py-1 text-right">{it.current_price_at_prediction?.toFixed(2)}</td>
                      <td className="px-2 py-1 text-right text-red-500">{it.stop_loss_price?.toFixed(2)}</td>
                      <td className="px-2 py-1 text-right text-green-600">{it.take_profit_1?.toFixed(2)}</td>
                      <td className={`px-2 py-1 text-right font-bold ${rev && (rev.max_gain || 0) >= 10 ? "text-green-600" : "text-gray-500"}`}>
                        {rev ? `${rev.max_gain?.toFixed(1)}%` : "-"}
                      </td>
                      <td className={`px-2 py-1 text-right ${rev && (rev.max_drawdown || 0) <= -10 ? "text-red-500" : "text-gray-500"}`}>
                        {rev ? `${rev.max_drawdown?.toFixed(1)}%` : "-"}
                      </td>
                      <td className="px-2 py-1 text-center">{rev?.hit_20_percent ? "✅" : "—"}</td>
                      <td className="px-2 py-1 text-center">{rev?.stop_loss_hit ? "❌" : "—"}</td>
                      <td className="px-2 py-1">
                        {rev?.success_label ? (
                          <span className={`text-xs px-2 py-0.5 rounded border ${LABEL_COLOR[rev.success_label] || "text-gray-700 bg-gray-50"}`}>
                            {rev.success_label}
                          </span>
                        ) : <span className="text-gray-400 text-xs">未検証</span>}
                      </td>
                      <td className="px-2 py-1 text-red-600 max-w-32 truncate" title={rev?.failed_reason_detail}>
                        {rev?.failed_reason_category || "-"}
                      </td>
                      <td className="px-2 py-1 text-center">
                        {rev?.saved_as_training ? <span className="text-purple-600 text-xs">✓case_{rev.saved_aar_case_id}</span> : "—"}
                      </td>
                      <td className="px-2 py-1">
                        <div className="flex gap-1">
                          <button onClick={() => reviewOne(it.id)} disabled={busy === `review-${it.id}`}
                            className="text-xs text-blue-600 hover:underline">検証</button>
                          {rev && !rev.saved_as_training && (rev.should_save_as_positive_training || rev.should_save_as_negative_training) && (
                            <button onClick={() => saveAsTraining(it.id)} disabled={busy === `save-${it.id}`}
                              className="text-xs text-purple-600 hover:underline">教師化</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
