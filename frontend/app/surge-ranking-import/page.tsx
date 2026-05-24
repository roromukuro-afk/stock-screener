"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";

const RANKING_TYPES = [
  { value: "one_day_gain", label: "1日 (前日比)" },
  { value: "three_day_gain", label: "3営業日" },
  { value: "five_day_gain", label: "5営業日" },
  { value: "one_week_gain", label: "1週間" },
  { value: "ten_day_gain", label: "10営業日" },
  { value: "twenty_day_gain", label: "20営業日" },
  { value: "one_month_gain", label: "1か月" },
];

export default function SurgeRankingImportPage() {
  const [market, setMarket] = useState("JP");
  const [rankingType, setRankingType] = useState("one_week_gain");
  const [topN, setTopN] = useState(50);
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [items, setItems] = useState<any[]>([]);
  const [selectedSnap, setSelectedSnap] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // 手動取込
  const [importCsv, setImportCsv] = useState("");
  const [importType, setImportType] = useState("custom_uploaded_ranking");

  const load = useCallback(async () => {
    try {
      const r = await fetchAPI("/api/surge-20/recent-snapshots");
      setSnapshots(r.items || []);
    } catch (e) {}
  }, []);

  useEffect(() => { load(); }, [load]);

  const loadItems = async (snapId: number) => {
    setSelectedSnap(snapId);
    setItems([]);
    try {
      const r = await fetchAPI(`/api/surge-20/snapshot/${snapId}/items?limit=100`);
      setItems(r.items || []);
    } catch (e: any) { setError(e.message); }
  };

  const generate = async () => {
    setLoading(true); setError(null); setMsg(null);
    try {
      const r = await fetchAPI("/api/surge-20/generate-rankings-from-ohlcv", {
        method: "POST",
        body: JSON.stringify({ market, top_n: topN, ranking_types: [rankingType] }),
      });
      const snapId = r.rankings?.[rankingType]?.snapshot_id;
      setMsg(`✅ 生成完了: snapshot_id=${snapId}`);
      await load();
      if (snapId) await loadItems(snapId);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const generateAll = async () => {
    setLoading(true); setError(null); setMsg(null);
    try {
      const r = await fetchAPI("/api/surge-20/generate-rankings-from-ohlcv", {
        method: "POST",
        body: JSON.stringify({ market, top_n: topN }),
      });
      const total = Object.values(r.rankings || {}).reduce((s: number, x: any) => s + (x.total || 0), 0);
      setMsg(`✅ 全ランキング生成完了: ${Object.keys(r.rankings || {}).length}種類 / ${total}件`);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const doImport = async () => {
    setLoading(true); setError(null); setMsg(null);
    try {
      // CSV: symbol,name,rank,gain_percent,current_price?
      const lines = importCsv.trim().split("\n");
      const items: any[] = [];
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line || line.startsWith("#") || (i === 0 && line.toLowerCase().includes("symbol"))) continue;
        const parts = line.split(/[,\t]/);
        items.push({
          symbol: parts[0]?.trim(),
          name: parts[1]?.trim() || "",
          rank: parseInt(parts[2]) || i + 1,
          gain_percent: parseFloat(parts[3]) || null,
          current_price: parseFloat(parts[4]) || null,
        });
      }
      const r = await fetchAPI("/api/surge-20/import-ranking", {
        method: "POST",
        body: JSON.stringify({
          ranking_type: importType,
          market,
          items,
        }),
      });
      setMsg(`✅ 取込完了: snapshot_id=${r.snapshot_id} (${r.items}件) — OHLCVで再検証済み`);
      await load();
      if (r.snapshot_id) await loadItems(r.snapshot_id);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">📊 急騰ランキング 自動生成・取込</h1>
        <p className="text-blue-200 text-sm">
          OHLCVから 1日/3日/5日/1週/10日/20日/1か月 の値上がりランキングを自動生成。
          手動CSV取込は補助で、必ずOHLCVで再検証されます (画像OCR非依存)。
        </p>
        <div className="mt-3 p-2 bg-yellow-900/40 rounded text-yellow-200 text-xs">
          ⚠️ ランキングは「今買う候補」ではなく「+20%到達ケースを教師データ化」するための材料です。最終判断はユーザー自身。
        </div>
      </div>

      {/* OHLCV自動生成 */}
      <div className="card p-5">
        <h2 className="font-bold text-gray-800 mb-3">A. OHLCVから自動生成</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="text-xs text-gray-500">市場</label>
            <select value={market} onChange={(e) => setMarket(e.target.value)}
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm">
              <option>JP</option><option>US</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500">ランキング種類</label>
            <select value={rankingType} onChange={(e) => setRankingType(e.target.value)}
              className="border border-gray-200 rounded px-3 py-2 text-sm">
              {RANKING_TYPES.map((rt) => <option key={rt.value} value={rt.value}>{rt.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500">Top N</label>
            <input type="number" value={topN} onChange={(e) => setTopN(parseInt(e.target.value) || 50)}
              className="border border-gray-200 rounded px-3 py-2 text-sm w-20" />
          </div>
          <button onClick={generate} disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
            {loading ? "..." : "📈 単一ランキング生成"}
          </button>
          <button onClick={generateAll} disabled={loading}
            className="px-4 py-2 bg-blue-700 text-white rounded text-sm hover:bg-blue-800 disabled:opacity-50">
            🌐 全ランキング(7種類)を生成
          </button>
        </div>
        {msg && <p className="text-emerald-700 text-sm mt-2">{msg}</p>}
        {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
      </div>

      {/* 手動取込 */}
      <div className="card p-5">
        <h2 className="font-bold text-gray-800 mb-3">B. 手動CSV取込 (補助機能)</h2>
        <p className="text-xs text-gray-500 mb-2">
          画像OCRには依存しません。CSVで貼り付け→OHLCVで自動再検証→計算値との差が±5%以上なら警告。
        </p>
        <div className="flex gap-3 mb-3">
          <select value={importType} onChange={(e) => setImportType(e.target.value)}
            className="border border-gray-200 rounded px-3 py-2 text-sm">
            <option value="custom_uploaded_ranking">custom_uploaded_ranking</option>
            {RANKING_TYPES.map((rt) => <option key={rt.value} value={rt.value}>{rt.label}</option>)}
          </select>
        </div>
        <textarea value={importCsv} onChange={(e) => setImportCsv(e.target.value)} rows={6}
          placeholder="symbol,name,rank,gain_percent,current_price&#10;7203.T,トヨタ自動車,1,5.2,2900&#10;9432.T,日本電信電話,2,4.8,180"
          className="w-full border border-gray-200 rounded px-3 py-2 text-xs font-mono" />
        <button onClick={doImport} disabled={loading || !importCsv}
          className="mt-2 px-4 py-2 bg-gray-700 text-white rounded text-sm hover:bg-gray-800 disabled:opacity-50">
          📥 CSVを取込 (OHLCV検証付き)
        </button>
      </div>

      {/* 過去スナップショット一覧 */}
      <div className="card p-4">
        <h2 className="font-bold text-gray-800 mb-3">📝 ランキング履歴 ({snapshots.length}件)</h2>
        {snapshots.length === 0 ? (
          <p className="text-gray-400 text-sm">まだランキングがありません。上の「生成」ボタンを押してください。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="border-b text-gray-500">
                <th className="px-2 py-1 text-left">id</th>
                <th className="px-2 py-1 text-left">ranking_type</th>
                <th className="px-2 py-1 text-left">market</th>
                <th className="px-2 py-1 text-left">snapshot_date</th>
                <th className="px-2 py-1 text-right">items</th>
                <th className="px-2 py-1 text-left">method</th>
                <th className="px-2 py-1 text-left">source</th>
                <th className="px-2 py-1 text-left">操作</th>
              </tr></thead>
              <tbody>
                {snapshots.map((s) => (
                  <tr key={s.id} className="border-b border-gray-50 hover:bg-blue-50">
                    <td className="px-2 py-1 font-mono">{s.id}</td>
                    <td className="px-2 py-1">{s.ranking_type}</td>
                    <td className="px-2 py-1">{s.market}</td>
                    <td className="px-2 py-1">{s.snapshot_date}</td>
                    <td className="px-2 py-1 text-right">{s.total_items}</td>
                    <td className="px-2 py-1 text-gray-500">{s.calculation_method}</td>
                    <td className="px-2 py-1">{s.auto_generated ? "🤖 OHLCV" : "📥 手動"}</td>
                    <td className="px-2 py-1">
                      <button onClick={() => loadItems(s.id)} className="text-blue-600 hover:underline text-xs">
                        items
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* スナップショット内訳 */}
      {selectedSnap && items.length > 0 && (
        <div className="card p-4">
          <h2 className="font-bold text-gray-800 mb-3">snapshot #{selectedSnap} の内訳 (Top 30)</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="border-b text-gray-500">
                <th className="px-2 py-1 text-left">rank</th>
                <th className="px-2 py-1 text-left">symbol</th>
                <th className="px-2 py-1 text-right">current_price</th>
                <th className="px-2 py-1 text-right">start_price</th>
                <th className="px-2 py-1 text-right">calc_gain%</th>
                <th className="px-2 py-1 text-right">imported%</th>
                <th className="px-2 py-1 text-right">diff%</th>
                <th className="px-2 py-1 text-left">verify</th>
              </tr></thead>
              <tbody>
                {items.slice(0, 30).map((r) => (
                  <tr key={r.id} className={`border-b border-gray-50 ${r.verification_warning ? "bg-orange-50" : ""}`}>
                    <td className="px-2 py-1">{r.rank}</td>
                    <td className="px-2 py-1 font-mono">
                      <Link href={`/stocks/${encodeURIComponent(r.symbol)}`} className="text-blue-600 hover:underline">{r.symbol}</Link>
                    </td>
                    <td className="px-2 py-1 text-right">{r.current_price?.toFixed(2)}</td>
                    <td className="px-2 py-1 text-right">{r.start_price?.toFixed(2)}</td>
                    <td className="px-2 py-1 text-right text-green-600 font-bold">{r.calculated_gain_percent?.toFixed(2)}%</td>
                    <td className="px-2 py-1 text-right">{r.imported_gain_percent != null ? `${r.imported_gain_percent}%` : "-"}</td>
                    <td className={`px-2 py-1 text-right ${r.gain_percent_diff && Math.abs(r.gain_percent_diff) > 5 ? "text-orange-600 font-bold" : ""}`}>
                      {r.gain_percent_diff != null ? `${r.gain_percent_diff}%` : "-"}
                    </td>
                    <td className="px-2 py-1">{r.verified_by_ohlcv ? "✅" : "—"} {r.verification_warning ? "⚠" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card p-3 text-xs text-gray-500">
        🔗 関連: <Link href="/surge-20-candidates" className="text-blue-600">20%到達候補</Link> /{" "}
        <Link href="/training-builder" className="text-blue-600">教師データ構築</Link>
      </div>
    </div>
  );
}
