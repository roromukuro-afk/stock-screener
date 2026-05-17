"use client";
import { useEffect, useState } from "react";
import { api, API_BASE_URL } from "@/lib/api";

export default function DeployStatusPage() {
  const [status, setStatus] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [pinging, setPinging] = useState(false);

  const ping = async () => {
    setPinging(true);
    setError(null);
    try {
      const [h, d] = await Promise.all([api.health(), api.deployStatus()]);
      setHealth(h);
      setStatus(d);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setPinging(false);
    }
  };

  useEffect(() => { ping(); }, []);

  const Item = ({ label, value, ok }: { label: string; value: React.ReactNode; ok?: boolean }) => (
    <div className="flex items-start justify-between py-2 border-b border-gray-100">
      <span className="text-sm text-gray-600">{label}</span>
      <span className={`text-sm font-mono text-right ${ok === true ? "text-green-600" : ok === false ? "text-red-500" : "text-gray-800"}`}>
        {value}
      </span>
    </div>
  );

  return (
    <div className="space-y-5 max-w-3xl">
      <div className="flex justify-between items-center">
        <h1 className="text-xl font-bold text-gray-800">🌐 公開環境ステータス</h1>
        <button onClick={ping} disabled={pinging}
          className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
          {pinging ? "確認中..." : "🔄 再確認"}
        </button>
      </div>

      {error && (
        <div className="card p-4 border-l-4 border-red-500">
          <p className="text-red-600 font-bold">❌ バックエンドに接続できません</p>
          <p className="text-xs text-gray-500 mt-1">{error}</p>
          <p className="text-xs text-gray-500 mt-2">API接続先: <code className="font-mono">{API_BASE_URL}</code></p>
          <p className="text-xs text-gray-500 mt-1">フロントエンドの NEXT_PUBLIC_API_BASE_URL とバックエンドの ALLOWED_ORIGINS を確認してください。</p>
        </div>
      )}

      <div className="card p-4">
        <h2 className="font-bold text-gray-700 mb-3">フロントエンド</h2>
        <Item label="API接続先 URL" value={API_BASE_URL} />
        <Item label="現在のページURL" value={typeof window !== "undefined" ? window.location.origin : "-"} />
        <Item label="アプリ環境 (NEXT_PUBLIC_APP_ENV)" value={process.env.NEXT_PUBLIC_APP_ENV || "未設定"} />
      </div>

      <div className="card p-4">
        <h2 className="font-bold text-gray-700 mb-3">バックエンド</h2>
        <Item label="ヘルスチェック" value={health ? "✅ 接続OK" : "❌ 失敗"} ok={!!health} />
        <Item label="status" value={health?.status || "-"} />
        <Item label="アプリ環境 (APP_ENV)" value={health?.environment || "-"} />
        <Item label="DB接続" value={health?.database || "-"} ok={health?.database === "connected"} />
        <Item label="DB種別" value={health?.database_type || "-"} />
        <Item label="サンプルモード" value={health?.sample_mode ? "🟢 ON" : "⚪ OFF"} />
      </div>

      {status && (
        <div className="card p-4">
          <h2 className="font-bold text-gray-700 mb-3">CORS / 環境変数</h2>
          <Item label="許可Origin" value={(status.allowed_origins || []).join(", ")} />
          <Item label="サンプルモード(実行時)" value={status.sample_mode_active ? "🟢" : "⚪"} />
          <Item label="yfinance有効" value={status.yfinance_enabled ? "🟢" : "⚪"} />
          <Item label="DEFAULT_USDJPY" value={`¥${status.default_usdjpy}`} />
          <Item label="DB url_scheme" value={status.database?.url_scheme} />
          <Item label="is_postgresql" value={String(status.database?.is_postgresql)} />
        </div>
      )}

      <div className="card p-3 text-xs text-gray-500">
        <p><strong>公開デプロイ後のチェック:</strong></p>
        <ul className="list-disc ml-5 mt-1 space-y-0.5">
          <li>このページで「ヘルスチェック ✅ 接続OK」になれば公開構成は正常です</li>
          <li>失敗する場合は ALLOWED_ORIGINS にフロントURLを追加してください</li>
          <li>NEXT_PUBLIC_API_BASE_URL が公開バックエンドURLになっているか確認してください</li>
          <li>DB種別が postgresql になっていれば本番DB接続済みです</li>
        </ul>
      </div>
    </div>
  );
}
