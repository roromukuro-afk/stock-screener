"use client";
import { useState, useRef, useEffect } from "react";
import { fetchAPI, API_BASE_URL } from "@/lib/api";

interface AnalysisResult {
  status?: string;
  error?: string;
  case_id?: number;
  symbol?: string;
  name?: string;
  market?: string;
  move_date?: string;
  move_percent?: number;
  t1_judgement?: string;
  t1_entry_type?: string;
  setup_type?: string;
  volume_type?: string;
  chart_type?: string;
  catalyst_category?: string;
  catalyst_summary?: string;
  catalyst?: string;
  material_confirmed?: boolean;
  weak_material_flag?: boolean;
  t1_close?: number;
  t1_volume_ratio_20d?: number;
  t1_ma25_deviation?: number;
  t1_resistance_upside?: number;
  t1_support_distance?: number;
  t1_overextension_score?: number;
  t1_range_break_flag?: boolean;
  t1_high_close_flag?: boolean;
  t0_result_move_percent?: number;
  hit_20_percent?: boolean;
  is_positive_case?: boolean;
  is_negative_case?: boolean;
  snapshots?: Array<{ relative_day: string; date: string; open: number; high: number; low: number; close: number; volume: number }>;
  nlm_data?: string;
}

export default function AARAnalyzerPage() {
  // 個別入力フォーム
  const [symbol, setSymbol] = useState("7203");
  const [market, setMarket] = useState("JP");
  const [moveDate, setMoveDate] = useState("");
  const [movePercent, setMovePercent] = useState<string>("");
  const [name, setName] = useState("");
  const [memo, setMemo] = useState("");
  const [catalystText, setCatalystText] = useState("");
  const [newsSource, setNewsSource] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // CSV
  const fileRef = useRef<HTMLInputElement>(null);
  const [csvMsg, setCsvMsg] = useState<string>("");
  const [csvProgress, setCsvProgress] = useState<any>(null);
  const [maxRows, setMaxRows] = useState(30);

  // CSV progress polling
  useEffect(() => {
    const t = setInterval(async () => {
      try {
        const p = await fetchAPI("/api/aar/csv-progress");
        setCsvProgress(p);
      } catch {}
    }, 2000);
    return () => clearInterval(t);
  }, []);

  const analyze = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const r = await fetchAPI("/api/aar/analyze", {
        method: "POST",
        body: JSON.stringify({
          symbol, market, move_date: moveDate,
          move_percent: movePercent ? parseFloat(movePercent) : null,
          name: name || null, user_memo: memo || null,
          catalyst_text: catalystText || null, news_source: newsSource || null,
          save: true,
        }),
      });
      if (r.status === "failed") setError(r.error || "分析失敗");
      else setResult(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const uploadCsv = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setCsvMsg("CSVファイルを選択してください");
      return;
    }
    setCsvMsg("送信中...");
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(`${API_BASE_URL}/api/aar/upload-csv?max_rows=${maxRows}`, {
        method: "POST",
        body: form,
      });
      const data = await r.json();
      if (!r.ok) {
        setCsvMsg(`エラー: ${data.detail || r.status}`);
        return;
      }
      setCsvMsg(`開始: total_rows=${data.total_rows_in_file}, 処理=${data.max_rows_to_process}件`);
    } catch (e: any) {
      setCsvMsg(`エラー: ${e.message}`);
    }
  };

  const Info = ({ label, value, highlight }: { label: string; value: any; highlight?: string }) => (
    <div className="flex justify-between py-1 border-b border-gray-50 text-xs">
      <span className="text-gray-500">{label}</span>
      <span className={`font-mono ${highlight || "text-gray-800"}`}>{value ?? "-"}</span>
    </div>
  );

  const judgementColor = (j?: string) => {
    if (!j) return "text-gray-500";
    if (j.includes("入る余地あり")) return "text-green-600 font-bold";
    if (j.includes("条件付き")) return "text-blue-600 font-bold";
    if (j.includes("見送り") || j.includes("T0初動のみ")) return "text-red-500 font-bold";
    return "text-orange-500 font-bold";
  };

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #4c1d95 0%, #6d28d9 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">🔬 急騰銘柄AAR自動分析</h1>
        <p className="text-purple-200 text-sm">
          ユーザーが急騰銘柄を投げると、Webアプリが T-3〜T-1 のOHLCVを取得して
          「T-1時点で観測できた情報」だけで自動AARを生成し、教師データとしてDBに保存します。
        </p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ T0以降のデータは「結果ラベル」としてだけ使用し、予測特徴量には混ぜません。投資助言ではありません。
        </div>
      </div>

      {/* 個別入力 */}
      <div className="card p-5">
        <h2 className="font-bold text-gray-800 mb-3">📝 個別入力</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">銘柄コード / Ticker</label>
            <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="例: 7203 または AAPL"
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500 outline-none" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">市場</label>
            <select value={market} onChange={(e) => setMarket(e.target.value)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500 outline-none">
              <option>JP</option>
              <option>US</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">急騰日 (YYYY-MM-DD)</label>
            <input type="date" value={moveDate} onChange={(e) => setMoveDate(e.target.value)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500 outline-none" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">前日比% (任意)</label>
            <input type="number" step="0.01" value={movePercent} onChange={(e) => setMovePercent(e.target.value)} placeholder="例: 25.3"
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500 outline-none" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">銘柄名 (任意)</label>
            <input value={name} onChange={(e) => setName(e.target.value)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500 outline-none" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">材料テキスト (任意)</label>
            <input value={catalystText} onChange={(e) => setCatalystText(e.target.value)} placeholder="例: 業績上方修正"
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500 outline-none" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">ニュース出典 (任意)</label>
            <input value={newsSource} onChange={(e) => setNewsSource(e.target.value)} placeholder="例: TDnet, SEC"
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500 outline-none" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">材料URL (任意)</label>
            <input value={memo} onChange={(e) => setMemo(e.target.value)} placeholder="https://..."
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500 outline-none" />
          </div>
        </div>
        <button onClick={analyze} disabled={running || !symbol || !moveDate}
          className="mt-3 px-6 py-2.5 bg-purple-600 text-white rounded font-bold text-sm hover:bg-purple-700 disabled:opacity-50">
          {running ? "分析中..." : "🔬 自動AAR分析を実行"}
        </button>
        {error && <p className="mt-2 text-red-600 text-sm">{error}</p>}
      </div>

      {/* CSV一括 */}
      <div className="card p-5">
        <h2 className="font-bold text-gray-800 mb-3">📂 CSV一括投入</h2>
        <p className="text-xs text-gray-500 mb-3">
          CSV列: 日付, 市場, 銘柄コード, yf_シンボル, 銘柄名, 前日比(%), 急騰理由, ニュース出典 / または英語 (move_date, market, symbol, yf_symbol, move_percent, catalyst, news_source)
        </p>
        <div className="flex flex-wrap gap-2 items-end">
          <input ref={fileRef} type="file" accept=".csv" className="text-sm" />
          <div>
            <label className="block text-xs text-gray-500 mb-1">最大処理件数</label>
            <input type="number" value={maxRows} onChange={(e) => setMaxRows(parseInt(e.target.value) || 0)}
              className="w-24 border border-gray-200 rounded px-2 py-1 text-sm" />
          </div>
          <button onClick={uploadCsv} className="px-4 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700">
            📤 アップロード
          </button>
          {csvMsg && <span className="text-sm text-gray-600">{csvMsg}</span>}
        </div>
        {csvProgress && csvProgress.total > 0 && (
          <div className="mt-3">
            <div className="flex justify-between text-xs mb-1">
              <span>{csvProgress.running ? "処理中" : "完了"}: {csvProgress.processed}/{csvProgress.total}</span>
              <span>保存: {csvProgress.saved} / 失敗: {csvProgress.failed}</span>
            </div>
            <div className="bg-gray-100 rounded-full h-2">
              <div className="h-2 rounded-full bg-emerald-500"
                style={{ width: `${(csvProgress.processed / csvProgress.total * 100)}%` }} />
            </div>
          </div>
        )}
      </div>

      {/* 結果表示 */}
      {result && (
        <div className="card p-5">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h2 className="font-bold text-lg text-gray-800">
                {result.name || result.symbol} <span className="text-gray-400 text-sm">({result.symbol})</span>
              </h2>
              <p className="text-sm text-gray-500">市場: {result.market} / 急騰日: {result.move_date} / 前日比(計算値): {result.move_percent?.toFixed(2)}%</p>
            </div>
            <div className="text-right">
              <p className={`text-2xl ${judgementColor(result.t1_judgement)}`}>{result.t1_judgement}</p>
              <p className="text-sm text-gray-500">{result.t1_entry_type}</p>
              {result.case_id && <p className="text-xs text-gray-400 mt-1">case_id: {result.case_id} (DB保存済)</p>}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div>
              <h3 className="font-bold text-sm text-gray-700 mb-2">📊 セットアップ分類</h3>
              <Info label="setup_type" value={result.setup_type} highlight="text-purple-700" />
              <Info label="volume_type" value={result.volume_type} highlight="text-blue-700" />
              <Info label="chart_type" value={result.chart_type} highlight="text-emerald-700" />
              <Info label="catalyst_category" value={result.catalyst_category} highlight={result.weak_material_flag ? "text-orange-500" : "text-green-600"} />
              <Info label="material_confirmed" value={result.material_confirmed ? "✅" : "⚠️ 未確認"} />
              <Info label="is_positive_case" value={result.is_positive_case ? "✅" : "❌"} />
              <Info label="is_negative_case" value={result.is_negative_case ? "❌" : "—"} />
            </div>

            <div>
              <h3 className="font-bold text-sm text-gray-700 mb-2">🎯 T-1特徴量(T0前)</h3>
              <Info label="t1_close" value={result.t1_close?.toFixed(2)} />
              <Info label="出来高倍率 T-1" value={result.t1_volume_ratio_20d?.toFixed(2) + "x"} />
              <Info label="25MA乖離率" value={result.t1_ma25_deviation?.toFixed(2) + "%"} />
              <Info label="上値余地(抵抗線)" value={result.t1_resistance_upside?.toFixed(2) + "%"} />
              <Info label="支持線距離" value={result.t1_support_distance?.toFixed(2) + "%"} />
              <Info label="上がり切りリスク" value={result.t1_overextension_score?.toFixed(1)}
                highlight={(result.t1_overextension_score ?? 0) >= 60 ? "text-red-500 font-bold" : ""} />
              <Info label="レンジブレイク" value={result.t1_range_break_flag ? "✅" : "—"} />
              <Info label="高値引け" value={result.t1_high_close_flag ? "✅" : "—"} />
            </div>

            <div>
              <h3 className="font-bold text-sm text-gray-700 mb-2">📈 T0以降ラベル(検証用)</h3>
              <Info label="T0 前日比(計算)" value={result.t0_result_move_percent?.toFixed(2) + "%"} highlight="text-blue-600" />
              <Info label="+20%達成" value={result.hit_20_percent ? "✅ Hit" : "—"} highlight={result.hit_20_percent ? "text-green-600 font-bold" : "text-gray-400"} />
              <p className="text-xs text-gray-400 mt-2 italic">※ T0以降は教師ラベルとして保存。予測特徴量には混入させていません。</p>
            </div>
          </div>

          {/* スナップショット表 */}
          {result.snapshots && result.snapshots.length > 0 && (
            <div className="mt-4">
              <h3 className="font-bold text-sm text-gray-700 mb-2">📅 OHLCVスナップショット</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 border-b border-gray-100 text-gray-500">
                    <tr>
                      <th className="px-2 py-1 text-left">rel</th>
                      <th className="px-2 py-1 text-left">date</th>
                      <th className="px-2 py-1 text-right">open</th>
                      <th className="px-2 py-1 text-right">high</th>
                      <th className="px-2 py-1 text-right">low</th>
                      <th className="px-2 py-1 text-right">close</th>
                      <th className="px-2 py-1 text-right">volume</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.snapshots.map((s, i) => (
                      <tr key={i} className={`border-b border-gray-50 ${s.relative_day === "T-1" ? "bg-blue-50 font-bold" : s.relative_day === "T0" ? "bg-yellow-50" : ""}`}>
                        <td className="px-2 py-1 font-mono">{s.relative_day}</td>
                        <td className="px-2 py-1">{s.date}</td>
                        <td className="px-2 py-1 text-right">{s.open?.toFixed(2)}</td>
                        <td className="px-2 py-1 text-right">{s.high?.toFixed(2)}</td>
                        <td className="px-2 py-1 text-right">{s.low?.toFixed(2)}</td>
                        <td className="px-2 py-1 text-right font-bold">{s.close?.toFixed(2)}</td>
                        <td className="px-2 py-1 text-right">{s.volume?.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* NLM_DATA */}
          {result.nlm_data && (
            <div className="mt-4">
              <div className="flex justify-between items-center mb-2">
                <h3 className="font-bold text-sm text-gray-700">📋 NLM_DATA (NotebookLM用)</h3>
                <button onClick={() => result.nlm_data && navigator.clipboard.writeText(result.nlm_data)}
                  className="text-xs text-blue-600 hover:underline">コピー</button>
              </div>
              <pre className="bg-gray-50 p-3 rounded text-xs font-mono overflow-x-auto break-all whitespace-pre-wrap">{result.nlm_data}</pre>
            </div>
          )}
        </div>
      )}

      <div className="card p-3 text-xs text-gray-500">
        <p><strong>使い方:</strong> 個別入力で1件ずつ分析するか、過去の急騰銘柄一覧CSVを一括投入してください。T-1時点のOHLCVから自動でセットアップ・出来高・チャート型を分類し、T-1判定 + NLM_DATAを生成します。</p>
        <p className="text-orange-600 mt-1">⚠️ これは投資助言ではなく、急騰前夜パターン分析・学習目的のツールです。</p>
      </div>
    </div>
  );
}
