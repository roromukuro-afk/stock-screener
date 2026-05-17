"use client";
import { useEffect, useState } from "react";
import { api, API_BASE_URL } from "@/lib/api";

interface SettingsResponse {
  settings: Record<string, string>;
  defaults: Record<string, string>;
  env: Record<string, string>;
  runtime: {
    sample_mode_active: boolean;
    usd_jpy: number;
    db: { url_scheme: string; is_sqlite: boolean; is_postgresql: boolean };
  };
}

const FIELDS: { key: string; label: string; type: "number" | "boolean" | "text"; hint?: string }[] = [
  { key: "price_limit", label: "価格上限 (円換算)", type: "number", hint: "デフォルト 3000 円" },
  { key: "min_vol_jp", label: "日本株 最低出来高", type: "number" },
  { key: "min_vol_us", label: "米国株 最低出来高", type: "number" },
  { key: "min_score", label: "最低スコア (フィルター)", type: "number", hint: "通常は0でOK" },
  { key: "include_adr", label: "ADRを含める", type: "boolean" },
  { key: "sample_mode", label: "サンプルモード", type: "boolean", hint: "yfinanceを使わず合成データで動作" },
  { key: "default_usdjpy", label: "為替仮値 USD/JPY", type: "number" },
  { key: "apply_exclusion_list", label: "除外リストを適用", type: "boolean" },
  { key: "max_symbols", label: "最大取得銘柄数 (0=全て)", type: "number", hint: "本番で長時間処理を避ける用" },
];

export default function SettingsPage() {
  const [data, setData] = useState<SettingsResponse | null>(null);
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const d = await api.settings();
      setData(d);
      setEditing(d.settings);
    } catch (e: any) {
      setMsg("読み込みエラー: " + e.message);
    }
  };

  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    setMsg("");
    try {
      await api.saveSettingsBulk(editing);
      setMsg("✅ 設定を保存しました");
      load();
    } catch (e: any) {
      setMsg("保存エラー: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    if (data) setEditing(data.defaults);
  };

  if (!data) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;

  return (
    <div className="space-y-5 max-w-3xl">
      <h1 className="text-xl font-bold text-gray-800">⚙️ 設定</h1>

      <div className="card p-4">
        <h2 className="font-bold text-gray-700 mb-3">現在の環境</h2>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="text-gray-500">アプリ環境</div>
          <div className="font-mono">{data.env.APP_ENV}</div>
          <div className="text-gray-500">API接続先</div>
          <div className="font-mono text-blue-600 break-all">{API_BASE_URL}</div>
          <div className="text-gray-500">DB種別</div>
          <div className="font-mono">{data.runtime.db.url_scheme}</div>
          <div className="text-gray-500">サンプルモード(実行時)</div>
          <div className="font-mono">{data.runtime.sample_mode_active ? "🟢 ON" : "⚪ OFF"}</div>
          <div className="text-gray-500">為替 USD/JPY (現在値)</div>
          <div className="font-mono">¥{data.runtime.usd_jpy?.toFixed(2)}</div>
          <div className="text-gray-500">許可Origin (CORS)</div>
          <div className="font-mono text-xs break-all">{data.env.ALLOWED_ORIGINS}</div>
        </div>
      </div>

      <div className="card p-4">
        <h2 className="font-bold text-gray-700 mb-3">スクリーニング設定</h2>
        <p className="text-xs text-gray-500 mb-4">DBに保存され、API経由で参照されます。スクリーニング実行画面のフォームと別に、規定値として記録されます。</p>
        <div className="space-y-3">
          {FIELDS.map((f) => (
            <div key={f.key} className="grid grid-cols-3 gap-3 items-center">
              <label className="text-sm text-gray-600">
                {f.label}
                {f.hint && <p className="text-xs text-gray-400 font-normal">{f.hint}</p>}
              </label>
              <div className="col-span-2">
                {f.type === "boolean" ? (
                  <select
                    value={editing[f.key] || "false"}
                    onChange={(e) => setEditing({ ...editing, [f.key]: e.target.value })}
                    className="border border-gray-200 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none w-32"
                  >
                    <option value="true">ON</option>
                    <option value="false">OFF</option>
                  </select>
                ) : (
                  <input
                    type={f.type === "number" ? "number" : "text"}
                    value={editing[f.key] ?? ""}
                    onChange={(e) => setEditing({ ...editing, [f.key]: e.target.value })}
                    className="border border-gray-200 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none w-48"
                  />
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="flex gap-3 mt-5">
          <button onClick={save} disabled={saving}
            className="px-5 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
            {saving ? "保存中..." : "保存"}
          </button>
          <button onClick={reset}
            className="px-5 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200">
            デフォルトに戻す
          </button>
          {msg && <span className="text-sm self-center">{msg}</span>}
        </div>
      </div>

      <div className="card p-3 text-xs text-gray-500">
        <p>⚠️ これは投資助言ではありません。最終判断はユーザー自身が行ってください。</p>
      </div>
    </div>
  );
}
