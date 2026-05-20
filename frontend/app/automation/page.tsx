"use client";
import { useEffect, useState, useCallback } from "react";
import { fetchAPI, API_BASE_URL } from "@/lib/api";


function SetupWizard({ cronSecretConfigured }: { cronSecretConfigured: boolean }) {
  const [testSecret, setTestSecret] = useState("");
  const [testResult, setTestResult] = useState<string>("");
  const [copied, setCopied] = useState<string>("");
  const [generated, setGenerated] = useState("");

  const generateSecret = () => {
    const arr = new Uint8Array(32);
    crypto.getRandomValues(arr);
    const hex = Array.from(arr).map(b => b.toString(16).padStart(2, "0")).join("");
    setGenerated(hex);
  };

  const copy = async (text: string, key: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(""), 2000);
  };

  const testConnection = async () => {
    setTestResult("テスト中...");
    try {
      const r = await fetch(`${API_BASE_URL}/api/automation/test-cron-secret`, {
        method: "POST",
        headers: {
          "X-Cron-Secret": testSecret,
          "Content-Type": "application/json",
        },
        body: "{}",
      });
      if (r.status === 200) {
        setTestResult("✅ CRON_SECRET が一致 — 接続OK");
      } else if (r.status === 403) {
        setTestResult("❌ CRON_SECRET が不一致 — Renderの環境変数と同じ値を入力してください");
      } else if (r.status === 503) {
        setTestResult("⚠️ Render側のCRON_SECRETが未設定 — Render Dashboard → Environment で設定が必要");
      } else {
        const t = await r.text();
        setTestResult(`HTTP ${r.status}: ${t.slice(0, 100)}`);
      }
    } catch (e: any) {
      setTestResult(`接続エラー: ${e.message}`);
    }
  };

  return (
    <div className="card p-5 bg-blue-50 border-blue-200">
      <div className="flex justify-between items-center mb-3">
        <h2 className="font-bold text-blue-900">🧙 セットアップウィザード</h2>
        <span className={`text-xs px-2 py-1 rounded ${cronSecretConfigured ? "bg-green-100 text-green-700" : "bg-orange-100 text-orange-700"}`}>
          {cronSecretConfigured ? "✅ CRON_SECRET 設定済み" : "⚠️ CRON_SECRET 未設定"}
        </span>
      </div>

      {!cronSecretConfigured && (
        <div className="bg-orange-50 border border-orange-200 rounded p-3 mb-3 text-sm">
          <p className="font-bold text-orange-700">⚠️ GitHub Actions自動実行はまだ動いていません</p>
          <p className="text-orange-600 text-xs mt-1">以下のステップでセットアップを完了してください。</p>
        </div>
      )}

      <ol className="space-y-3 text-sm">
        <li className="bg-white rounded p-3 border border-gray-200">
          <p className="font-bold text-gray-800 mb-2">STEP 1: CRON_SECRET を生成</p>
          <div className="flex gap-2">
            <button onClick={generateSecret}
              className="px-3 py-1.5 bg-purple-600 text-white rounded text-xs hover:bg-purple-700">
              🎲 ランダム生成 (64文字)
            </button>
            {generated && (
              <>
                <input value={generated} readOnly
                  className="flex-1 border border-gray-200 rounded px-2 py-1.5 text-xs font-mono bg-gray-50" />
                <button onClick={() => copy(generated, "secret")}
                  className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">
                  {copied === "secret" ? "✅" : "📋"}
                </button>
              </>
            )}
          </div>
        </li>

        <li className="bg-white rounded p-3 border border-gray-200">
          <p className="font-bold text-gray-800 mb-2">STEP 2: GitHub Secrets に登録</p>
          <p className="text-xs text-gray-600 mb-2">
            <a href="https://github.com/roromukuro-afk/stock-screener/settings/secrets/actions" target="_blank" className="text-blue-600 hover:underline">
              → GitHub Settings → Secrets and variables → Actions
            </a>
          </p>
          <div className="space-y-1 text-xs">
            <div className="flex gap-2 items-center">
              <code className="bg-gray-100 px-2 py-0.5 rounded font-bold">BACKEND_URL</code>
              <code className="bg-gray-50 px-2 py-0.5 rounded flex-1">{API_BASE_URL}</code>
              <button onClick={() => copy(API_BASE_URL, "url")}
                className="px-2 py-0.5 bg-gray-100 rounded">{copied === "url" ? "✅" : "📋"}</button>
            </div>
            <div className="flex gap-2 items-center">
              <code className="bg-gray-100 px-2 py-0.5 rounded font-bold">CRON_SECRET</code>
              <code className="bg-gray-50 px-2 py-0.5 rounded flex-1">{generated || "(STEP 1で生成した値)"}</code>
            </div>
          </div>
        </li>

        <li className="bg-white rounded p-3 border border-gray-200">
          <p className="font-bold text-gray-800 mb-2">STEP 3: Render Environment に同じ CRON_SECRET を設定</p>
          <p className="text-xs text-gray-600 mb-2">
            <a href="https://dashboard.render.com/" target="_blank" className="text-blue-600 hover:underline">
              → Render Dashboard → stock-screener-backend → Environment
            </a>
          </p>
          <p className="text-xs text-gray-500">
            Key: <code className="bg-gray-100 px-1">CRON_SECRET</code> Value: STEP 1 と同じ値<br />
            設定後、自動再デプロイ完了まで2-3分待機。
          </p>
        </li>

        <li className="bg-white rounded p-3 border border-gray-200">
          <p className="font-bold text-gray-800 mb-2">STEP 4: 接続テスト</p>
          <div className="flex gap-2">
            <input value={testSecret} onChange={(e) => setTestSecret(e.target.value)}
              placeholder="生成したCRON_SECRETをペースト"
              className="flex-1 border border-gray-200 rounded px-2 py-1.5 text-xs font-mono" />
            <button onClick={testConnection} disabled={!testSecret}
              className="px-3 py-1.5 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 disabled:opacity-50">
              🔌 接続テスト
            </button>
          </div>
          {testResult && <p className="text-xs mt-2">{testResult}</p>}
        </li>

        <li className="bg-white rounded p-3 border border-gray-200">
          <p className="font-bold text-gray-800 mb-2">STEP 5: GitHub Actions で手動実行</p>
          <p className="text-xs text-gray-600">
            <a href="https://github.com/roromukuro-afk/stock-screener/actions" target="_blank" className="text-blue-600 hover:underline">
              → GitHub Actions タブ
            </a> → "stock-screener automation" → "Run workflow" → status を選択 → Run
          </p>
          <p className="text-xs text-gray-500 mt-1">
            成功すれば自動ジョブ履歴に "trigger=manual" の行が追加されます。
          </p>
        </li>
      </ol>
    </div>
  );
}

interface Status {
  automation_enabled: boolean;
  cron_secret_configured: boolean;
  latest_job_id: number | null;
  latest_job_type: string | null;
  latest_run_at: string | null;
  latest_success_at: string | null;
  latest_failure_at: string | null;
  running_jobs: number;
  today: {
    jobs_today: number;
    surge_detected_today: number;
    aar_cases_today: number;
    positive_cases_today: number;
    negative_cases_today: number;
    predictions_saved_today: number;
    outcomes_updated_today: number;
    training_cases_today: number;
  };
  training_data_balance: { total: number; positive: number; negative: number; ratio: number };
}

export default function AutomationPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [errors, setErrors] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, j, e] = await Promise.all([
        fetchAPI("/api/automation/status"),
        fetchAPI("/api/automation/jobs?limit=30"),
        fetchAPI("/api/automation/errors?limit=20"),
      ]);
      setStatus(s); setJobs(j.items || []); setErrors(e.items || []);
      setError(null);
    } catch (err: any) { setError(err.message); }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  if (error) return <div className="card p-6 max-w-2xl mx-auto"><p className="text-red-600">エラー: {error}</p></div>;
  if (!status) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;

  const StatusBadge = ({ label, ok, txt }: { label: string; ok: boolean; txt?: string }) => (
    <div className="flex justify-between py-1 border-b border-gray-50">
      <span className="text-sm text-gray-600">{label}</span>
      <span className={`text-sm font-bold ${ok ? "text-green-600" : "text-red-500"}`}>
        {ok ? "✅" : "❌"} {txt || (ok ? "ON" : "OFF")}
      </span>
    </div>
  );

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #0c4a6e 0%, #075985 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">⚙️ 自動化パイプライン管理</h1>
        <p className="text-sky-200 text-sm">GitHub Actions Cron が毎日自動でJP/USの急騰検出 → 材料収集 → AAR分析 → 予測 → 検証 → 教師化 を回します</p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ これは投資助言ではありません。分析・学習・検証目的の自動化です。
        </div>
      </div>

      {/* 状態 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-4">
          <h2 className="font-bold text-gray-800 mb-3">🔧 自動化設定</h2>
          <StatusBadge label="自動化 (DB設定)" ok={status.automation_enabled} />
          <StatusBadge label="CRON_SECRET 設定済み" ok={status.cron_secret_configured} txt={status.cron_secret_configured ? "configured" : "未設定"} />
          <StatusBadge label="GitHub Actions" ok={true} txt=".github/workflows/stock-screener-automation.yml" />
          <div className="flex justify-between py-1 border-b border-gray-50">
            <span className="text-sm text-gray-600">最終ジョブ</span>
            <span className="text-sm font-mono">{status.latest_job_type || "-"} (id={status.latest_job_id || "-"})</span>
          </div>
          <div className="flex justify-between py-1 border-b border-gray-50">
            <span className="text-sm text-gray-600">最終実行</span>
            <span className="text-sm">{status.latest_run_at?.slice(0, 19).replace("T", " ") || "-"}</span>
          </div>
          <div className="flex justify-between py-1 border-b border-gray-50">
            <span className="text-sm text-gray-600">最終成功</span>
            <span className="text-sm text-green-600">{status.latest_success_at?.slice(0, 19).replace("T", " ") || "-"}</span>
          </div>
          <div className="flex justify-between py-1 border-b border-gray-50">
            <span className="text-sm text-gray-600">最終失敗</span>
            <span className="text-sm text-red-500">{status.latest_failure_at?.slice(0, 19).replace("T", " ") || "-"}</span>
          </div>
          <div className="flex justify-between py-1 border-b border-gray-50">
            <span className="text-sm text-gray-600">現在実行中ジョブ</span>
            <span className={`text-sm font-bold ${status.running_jobs > 0 ? "text-blue-600" : "text-gray-500"}`}>{status.running_jobs}</span>
          </div>
        </div>

        <div className="card p-4">
          <h2 className="font-bold text-gray-800 mb-3">📅 次回 cron 予定 (UTC→JST変換)</h2>
          <ul className="text-xs space-y-1 text-gray-700">
            <li>🌅 JST 16:40 (UTC 07:40) 平日 — JP daily 急騰検出 + AAR分析</li>
            <li>📊 JST 17:10 (UTC 08:10) 平日 — JP screening + 予測自動保存</li>
            <li>🌅 JST 07:40 (UTC 22:40) 平日 — US daily 急騰検出 + AAR分析</li>
            <li>📊 JST 08:10 (UTC 23:10) 平日 — US screening + 予測自動保存</li>
            <li>🔁 JST 09:00 (UTC 00:00) 平日 — 予測検証 + 教師化</li>
            <li>🏗 JST 23:00 (UTC 14:00) 土日 — training builder (known seed + smallcap)</li>
          </ul>
          <p className="text-xs text-gray-500 mt-3">📝 GitHub Secrets に <code className="bg-gray-100 px-1">BACKEND_URL</code> と <code className="bg-gray-100 px-1">CRON_SECRET</code> を設定してください</p>
        </div>
      </div>

      {/* 今日の集計 */}
      <div>
        <h2 className="font-bold text-gray-800 mb-3">📊 本日の自動化結果</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          <div className="card p-3"><p className="text-xs text-gray-500">ジョブ数</p><p className="text-2xl font-bold">{status.today.jobs_today}</p></div>
          <div className="card p-3"><p className="text-xs text-gray-500">急騰検出</p><p className="text-2xl font-bold text-green-600">{status.today.surge_detected_today}</p></div>
          <div className="card p-3"><p className="text-xs text-gray-500">AAR追加</p><p className="text-2xl font-bold text-purple-600">{status.today.aar_cases_today}</p></div>
          <div className="card p-3"><p className="text-xs text-gray-500">positive追加</p><p className="text-2xl font-bold text-green-700">{status.today.positive_cases_today}</p></div>
          <div className="card p-3"><p className="text-xs text-gray-500">negative追加</p><p className="text-2xl font-bold text-red-500">{status.today.negative_cases_today}</p></div>
          <div className="card p-3"><p className="text-xs text-gray-500">予測保存</p><p className="text-2xl font-bold text-emerald-600">{status.today.predictions_saved_today}</p></div>
          <div className="card p-3"><p className="text-xs text-gray-500">outcomes更新</p><p className="text-2xl font-bold text-blue-600">{status.today.outcomes_updated_today}</p></div>
          <div className="card p-3"><p className="text-xs text-gray-500">教師化</p><p className="text-2xl font-bold text-fuchsia-600">{status.today.training_cases_today}</p></div>
        </div>
      </div>

      {/* 教師データバランス */}
      <div className="card p-4">
        <h2 className="font-bold text-gray-800 mb-3">⚖️ 教師データバランス (training_feature_vectors)</h2>
        <div className="grid grid-cols-4 gap-3 text-sm">
          <div><p className="text-xs text-gray-500">total</p><p className="text-2xl font-bold">{status.training_data_balance.total}</p></div>
          <div><p className="text-xs text-gray-500">positive</p><p className="text-2xl font-bold text-green-600">{status.training_data_balance.positive}</p></div>
          <div><p className="text-xs text-gray-500">negative</p><p className="text-2xl font-bold text-red-500">{status.training_data_balance.negative}</p></div>
          <div><p className="text-xs text-gray-500">N/P ratio</p><p className={`text-2xl font-bold ${status.training_data_balance.ratio >= 1 ? "text-green-600" : "text-orange-500"}`}>{status.training_data_balance.ratio}</p></div>
        </div>
      </div>

      {/* ジョブ履歴 */}
      <div className="card p-4">
        <h2 className="font-bold text-gray-800 mb-3">📝 自動ジョブ履歴 ({jobs.length}件)</h2>
        {jobs.length === 0 ? (
          <p className="text-gray-400 text-sm">まだジョブがありません。GitHub Actionsを設定すると自動で記録されます。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-gray-500 border-b border-gray-100">
                <th className="px-2 py-1 text-left">id</th>
                <th className="px-2 py-1 text-left">job_type</th>
                <th className="px-2 py-1 text-left">market</th>
                <th className="px-2 py-1 text-left">trigger</th>
                <th className="px-2 py-1 text-left">status</th>
                <th className="px-2 py-1 text-right">処理</th>
                <th className="px-2 py-1 text-right">急騰</th>
                <th className="px-2 py-1 text-right">pos</th>
                <th className="px-2 py-1 text-right">neg</th>
                <th className="px-2 py-1 text-right">予測</th>
                <th className="px-2 py-1 text-right">outcomes</th>
                <th className="px-2 py-1 text-right">教師</th>
                <th className="px-2 py-1 text-right">秒</th>
                <th className="px-2 py-1 text-left">started</th>
              </tr></thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id} className="border-b border-gray-50 hover:bg-blue-50">
                    <td className="px-2 py-1 font-mono">{j.id}</td>
                    <td className="px-2 py-1 text-gray-700">{j.job_type}</td>
                    <td className="px-2 py-1">{j.market}</td>
                    <td className="px-2 py-1 text-gray-500">{j.trigger_type}</td>
                    <td className={`px-2 py-1 font-medium ${j.status === "completed" ? "text-green-600" : j.status === "failed" ? "text-red-500" : "text-blue-500"}`}>{j.status}</td>
                    <td className="px-2 py-1 text-right">{j.processed_symbols || "-"}</td>
                    <td className="px-2 py-1 text-right text-green-600">{j.detected_surge_count || "-"}</td>
                    <td className="px-2 py-1 text-right text-green-700">{j.positive_cases_created || "-"}</td>
                    <td className="px-2 py-1 text-right text-red-500">{j.negative_cases_created || "-"}</td>
                    <td className="px-2 py-1 text-right text-emerald-600">{j.predictions_saved || "-"}</td>
                    <td className="px-2 py-1 text-right text-blue-600">{j.outcomes_updated || "-"}</td>
                    <td className="px-2 py-1 text-right text-fuchsia-600">{j.training_cases_created || "-"}</td>
                    <td className="px-2 py-1 text-right text-gray-400">{j.duration_seconds?.toFixed(0) || "-"}</td>
                    <td className="px-2 py-1 text-gray-400">{j.started_at?.slice(0, 19).replace("T", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* エラー */}
      {errors.length > 0 && (
        <div className="card p-4">
          <h2 className="font-bold text-red-700 mb-3">⚠️ 自動化エラー ({errors.length}件)</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-gray-500 border-b border-gray-100">
                <th className="px-2 py-1 text-left">id</th>
                <th className="px-2 py-1 text-left">job_id</th>
                <th className="px-2 py-1 text-left">symbol</th>
                <th className="px-2 py-1 text-left">step</th>
                <th className="px-2 py-1 text-left">error</th>
                <th className="px-2 py-1 text-left">at</th>
              </tr></thead>
              <tbody>
                {errors.map((e) => (
                  <tr key={e.id} className="border-b border-gray-50">
                    <td className="px-2 py-1 font-mono">{e.id}</td>
                    <td className="px-2 py-1">{e.job_id}</td>
                    <td className="px-2 py-1 font-mono">{e.symbol}</td>
                    <td className="px-2 py-1">{e.step}</td>
                    <td className="px-2 py-1 text-red-600 max-w-md truncate" title={e.error_message}>{e.error_type}: {e.error_message?.slice(0, 80)}</td>
                    <td className="px-2 py-1 text-gray-400">{e.created_at?.slice(0, 19).replace("T", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* セットアップウィザード */}
      <SetupWizard cronSecretConfigured={status.cron_secret_configured} />

      {/* 関連リンク */}
      <div className="card p-3 text-xs text-gray-500">
        🔗 関連: <a href="/screener/learning-center" className="text-blue-600 hover:underline">AI学習センター</a> /{" "}
        <a href="/screener/ai-analyst" className="text-blue-600 hover:underline">AI総合分析</a> /{" "}
        <a href="/screener/training-builder" className="text-blue-600 hover:underline">教師データ構築</a> /{" "}
        <a href="/screener/prediction-review" className="text-blue-600 hover:underline">予測検証</a> /{" "}
        <a href="/screener/material-research" className="text-blue-600 hover:underline">材料調査</a>
      </div>

      <div className="card p-3 text-xs text-gray-500">
        ⚠️ これは投資助言ではありません。「買え」「必ず上がる」等の表現は行いません。最終判断はユーザー自身が行ってください。
      </div>
    </div>
  );
}
