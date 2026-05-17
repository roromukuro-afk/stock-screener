"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface ExclusionItem {
  symbol: string;
  name?: string;
  market?: string;
  exclude_reason: string;
  price?: number;
  volume?: number;
  date?: string;
}

const reasonColorMap: Record<string, string> = {
  "価格条件外": "text-orange-600 bg-orange-50",
  "価格不明": "text-gray-500 bg-gray-50",
  "データ取得失敗": "text-red-500 bg-red-50",
  "出来高不足": "text-blue-600 bg-blue-50",
  "上値余地不足": "text-yellow-600 bg-yellow-50",
  "25MA乖離過大": "text-red-600 bg-red-50",
  "短期急騰済み": "text-red-700 bg-red-50",
  "天井大商い": "text-red-700 bg-red-50",
  "除外リスト登録済み": "text-purple-600 bg-purple-50",
  "指標計算失敗": "text-gray-500 bg-gray-50",
};

export default function ExcludedPage() {
  const [items, setItems] = useState<ExclusionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState({ reason: "", search: "" });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.screeningExclusions(1000).then((r) => {
      setItems(r.exclusions || []);
      setTotal(r.total || 0);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const reasonCounts: Record<string, number> = {};
  for (const i of items) {
    reasonCounts[i.exclude_reason] = (reasonCounts[i.exclude_reason] || 0) + 1;
  }

  const filtered = items.filter((i) => {
    if (filter.reason && i.exclude_reason !== filter.reason) return false;
    if (filter.search) {
      const s = filter.search.toLowerCase();
      if (!i.symbol.toLowerCase().includes(s) && !(i.name || "").toLowerCase().includes(s)) return false;
    }
    return true;
  });

  if (loading) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <h1 className="text-xl font-bold text-gray-800">📋 除外銘柄一覧</h1>
        <button onClick={() => api.exportCsv()} className="px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200">
          📄 CSV出力
        </button>
      </div>

      {/* Summary */}
      <div className="card p-4">
        <p className="text-sm text-gray-600 mb-3">除外理由別内訳 (合計: {total}件)</p>
        <div className="flex flex-wrap gap-2">
          {Object.entries(reasonCounts).sort((a, b) => b[1] - a[1]).map(([reason, count]) => (
            <button key={reason} onClick={() => setFilter((f) => ({ ...f, reason: f.reason === reason ? "" : reason }))}
              className={`text-xs px-2 py-1 rounded-full border transition-colors ${filter.reason === reason ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"}`}>
              {reason}: {count}件
            </button>
          ))}
        </div>
      </div>

      {/* Filters */}
      <div className="card p-4 flex gap-3">
        <input placeholder="コード・名称検索" value={filter.search}
          onChange={(e) => setFilter((f) => ({ ...f, search: e.target.value }))}
          className="border border-gray-200 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none w-48" />
        <select value={filter.reason} onChange={(e) => setFilter((f) => ({ ...f, reason: e.target.value }))}
          className="border border-gray-200 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
          <option value="">全除外理由</option>
          {Object.keys(reasonCounts).map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <span className="text-sm text-gray-500 self-center">{filtered.length}件表示</span>
      </div>

      {filtered.length > 0 ? (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100 text-gray-500 text-left">
                  <th className="px-3 py-2">コード</th>
                  <th className="px-3 py-2">銘柄名</th>
                  <th className="px-3 py-2">市場</th>
                  <th className="px-3 py-2">除外理由</th>
                  <th className="px-3 py-2 text-right">価格</th>
                  <th className="px-3 py-2 text-right">出来高</th>
                  <th className="px-3 py-2">取得日</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.slice(0, 500).map((i, idx) => (
                  <tr key={`${i.symbol}-${idx}`} className="hover:bg-gray-50">
                    <td className="px-3 py-1.5 font-mono font-bold text-gray-700">{i.symbol}</td>
                    <td className="px-3 py-1.5 text-gray-600 max-w-32 truncate">{i.name || "-"}</td>
                    <td className="px-3 py-1.5 text-gray-500">{i.market || "-"}</td>
                    <td className="px-3 py-1.5">
                      <span className={`px-2 py-0.5 rounded text-xs ${reasonColorMap[i.exclude_reason] || "text-gray-600 bg-gray-50"}`}>
                        {i.exclude_reason}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-right text-gray-600">
                      {i.price != null ? i.price.toLocaleString() : "-"}
                    </td>
                    <td className="px-3 py-1.5 text-right text-gray-600">
                      {i.volume != null ? i.volume.toLocaleString() : "-"}
                    </td>
                    <td className="px-3 py-1.5 text-gray-400">{i.date || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length > 500 && (
            <p className="text-center text-xs text-gray-400 py-2">最初の500件表示 / 全{filtered.length}件</p>
          )}
        </div>
      ) : (
        <div className="card p-10 text-center text-gray-400">
          {items.length === 0 ? "スクリーニングを実行してください" : "該当する除外銘柄がありません"}
        </div>
      )}
    </div>
  );
}
