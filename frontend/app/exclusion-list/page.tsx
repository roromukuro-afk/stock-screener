"use client";
import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";

interface ExclusionEntry {
  symbol: string;
  name?: string;
  market?: string;
  reason?: string;
}

interface UploadCandidate {
  symbol: string;
  name?: string;
  market?: string;
  reason?: string;
}

export default function ExclusionsPage() {
  const [exclusions, setExclusions] = useState<ExclusionEntry[]>([]);
  const [candidates, setCandidates] = useState<UploadCandidate[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string>("");
  const [newSymbol, setNewSymbol] = useState("");
  const [newReason, setNewReason] = useState("");
  const [addMsg, setAddMsg] = useState<string>("");
  const fileRef = useRef<HTMLInputElement>(null);

  const loadExclusions = async () => {
    try {
      const r = await api.exclusions();
      setExclusions(r.exclusions || []);
    } catch (e) {}
  };

  useEffect(() => { loadExclusions(); }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMsg("");
    try {
      const r = await api.uploadExclusions(file);
      setCandidates(r.candidates || []);
      setSelected(new Set((r.candidates || []).map((c: UploadCandidate) => c.symbol)));
      setUploadMsg(r.message || "");
    } catch (err: any) {
      setUploadMsg("アップロードエラー: " + err.message);
    } finally {
      setUploading(false);
    }
  };

  const registerSelected = async () => {
    const items = candidates
      .filter((c) => selected.has(c.symbol))
      .map((c) => ({ symbol: c.symbol, name: c.name || "", market: c.market || "", reason: c.reason || "ファイルアップロード" }));
    if (items.length === 0) { setUploadMsg("選択された銘柄がありません"); return; }
    try {
      const r = await api.bulkExclusions(items);
      setUploadMsg(`${r.added.length}件を除外リストに登録しました（スキップ: ${r.skipped.length}件）`);
      setCandidates([]);
      setSelected(new Set());
      loadExclusions();
    } catch (e: any) {
      setUploadMsg("登録エラー: " + e.message);
    }
  };

  const addSingle = async () => {
    if (!newSymbol.trim()) return;
    try {
      await api.addExclusion({ symbol: newSymbol.trim().toUpperCase(), reason: newReason || "手動登録" });
      setAddMsg(`${newSymbol} を除外リストに追加しました`);
      setNewSymbol("");
      setNewReason("");
      loadExclusions();
    } catch (e: any) {
      setAddMsg("エラー: " + e.message);
    }
  };

  const remove = async (symbol: string) => {
    if (!confirm(`${symbol} を除外リストから削除しますか？`)) return;
    try {
      await api.deleteExclusion(symbol);
      loadExclusions();
    } catch (e: any) {
      alert("削除エラー: " + e.message);
    }
  };

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-gray-800">⚙️ 除外リスト管理</h1>

      {/* File upload */}
      <div className="card p-5">
        <h2 className="font-bold text-gray-700 mb-3">ファイルからインポート</h2>
        <p className="text-xs text-gray-500 mb-3">CSV, TXT, Excel (.xlsx) ファイルから銘柄コードを抽出します。<br />
          <strong>重要:</strong> 抽出結果を確認し、登録する銘柄にチェックを入れてから「除外リストに登録」してください。</p>
        <div className="flex gap-3 items-center">
          <input ref={fileRef} type="file" accept=".csv,.txt,.xlsx,.xls" onChange={handleFileUpload}
            className="hidden" />
          <button onClick={() => fileRef.current?.click()} disabled={uploading}
            className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
            {uploading ? "処理中..." : "📂 ファイル選択"}
          </button>
          {uploadMsg && <p className="text-sm text-gray-600">{uploadMsg}</p>}
        </div>

        {candidates.length > 0 && (
          <div className="mt-4">
            <div className="flex justify-between items-center mb-2">
              <p className="text-sm font-medium text-gray-700">{candidates.length}件の候補を抽出 — 登録する銘柄を選択してください</p>
              <div className="flex gap-2">
                <button onClick={() => setSelected(new Set(candidates.map(c => c.symbol)))}
                  className="text-xs text-blue-600 hover:underline">全選択</button>
                <button onClick={() => setSelected(new Set())}
                  className="text-xs text-gray-500 hover:underline">全解除</button>
              </div>
            </div>
            <div className="max-h-48 overflow-y-auto border border-gray-200 rounded">
              {candidates.map((c) => (
                <label key={c.symbol} className="flex items-center gap-3 px-3 py-1.5 hover:bg-gray-50 cursor-pointer border-b border-gray-50 text-sm">
                  <input type="checkbox" checked={selected.has(c.symbol)}
                    onChange={(e) => {
                      const s = new Set(selected);
                      e.target.checked ? s.add(c.symbol) : s.delete(c.symbol);
                      setSelected(s);
                    }} className="rounded" />
                  <span className="font-mono font-bold text-gray-700">{c.symbol}</span>
                  <span className="text-gray-500">{c.market}</span>
                  <span className="text-gray-400">{c.reason}</span>
                </label>
              ))}
            </div>
            <button onClick={registerSelected}
              className="mt-3 px-4 py-2 bg-red-600 text-white rounded text-sm hover:bg-red-700">
              選択した {selected.size}件 を除外リストに登録
            </button>
          </div>
        )}
      </div>

      {/* Manual add */}
      <div className="card p-5">
        <h2 className="font-bold text-gray-700 mb-3">手動追加</h2>
        <div className="flex gap-3 items-end flex-wrap">
          <div>
            <label className="block text-xs text-gray-500 mb-1">銘柄コード</label>
            <input value={newSymbol} onChange={(e) => setNewSymbol(e.target.value)} placeholder="例: 7203.T または AAPL"
              className="border border-gray-200 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none w-48" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">除外理由</label>
            <input value={newReason} onChange={(e) => setNewReason(e.target.value)} placeholder="例: 長期保有中"
              className="border border-gray-200 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none w-48" />
          </div>
          <button onClick={addSingle}
            className="px-4 py-2 bg-orange-600 text-white rounded text-sm hover:bg-orange-700">
            追加
          </button>
          {addMsg && <p className="text-sm text-gray-600">{addMsg}</p>}
        </div>
      </div>

      {/* Exclusion list */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex justify-between items-center">
          <h2 className="font-bold text-gray-700">除外リスト ({exclusions.length}件)</h2>
        </div>
        {exclusions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 border-b text-gray-500">
                  <th className="px-3 py-2 text-left">コード</th>
                  <th className="px-3 py-2 text-left">銘柄名</th>
                  <th className="px-3 py-2 text-left">市場</th>
                  <th className="px-3 py-2 text-left">除外理由</th>
                  <th className="px-3 py-2 text-left">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {exclusions.map((e) => (
                  <tr key={e.symbol} className="hover:bg-gray-50">
                    <td className="px-3 py-2 font-mono font-bold text-gray-700">{e.symbol}</td>
                    <td className="px-3 py-2 text-gray-600">{e.name || "-"}</td>
                    <td className="px-3 py-2 text-gray-500">{e.market || "-"}</td>
                    <td className="px-3 py-2 text-gray-500">{e.reason || "-"}</td>
                    <td className="px-3 py-2">
                      <button onClick={() => remove(e.symbol)}
                        className="text-red-500 hover:text-red-700 text-xs hover:underline">
                        削除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-center text-gray-400 py-8 text-sm">除外リストは空です</p>
        )}
      </div>
    </div>
  );
}
