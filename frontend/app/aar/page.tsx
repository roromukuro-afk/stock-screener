"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ScreeningResult } from "@/lib/types";
import { generate_aar_text_client } from "./aarHelper";

function AARCard({ result, onCopy }: { result: ScreeningResult; onCopy: (text: string) => void }) {
  const [aar, setAar] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const generateAAR = async () => {
    setLoading(true);
    try {
      const r = await api.stockAAR(result.symbol);
      setAar(r.aar_text || "");
    } catch {
      setAar(generate_aar_text_client(result));
    } finally {
      setLoading(false);
    }
  };

  const copy = () => {
    navigator.clipboard.writeText(aar);
    setCopied(true);
    onCopy(aar);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="card p-4">
      <div className="flex justify-between items-start mb-3">
        <div>
          <p className="font-mono font-bold text-gray-800">{result.symbol}</p>
          <p className="text-sm text-gray-600">{result.name}</p>
          <p className="text-xs text-gray-400">{result.market} | 分類: {result.classification}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={generateAAR} disabled={loading}
            className="px-3 py-1.5 bg-purple-600 text-white rounded text-xs hover:bg-purple-700 disabled:opacity-50">
            {loading ? "生成中..." : "AAR生成"}
          </button>
          {aar && (
            <button onClick={copy}
              className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">
              {copied ? "✅" : "コピー"}
            </button>
          )}
        </div>
      </div>
      {aar && (
        <pre className="whitespace-pre-wrap text-xs text-gray-700 font-mono bg-gray-50 p-3 rounded border border-gray-200 max-h-64 overflow-y-auto leading-relaxed">
          {aar}
        </pre>
      )}
    </div>
  );
}

export default function AARPage() {
  const [results, setResults] = useState<ScreeningResult[]>([]);
  const [activeTab, setActiveTab] = useState("採用候補");
  const [combinedText, setCombinedText] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.screeningResults({ limit: 500 }).then((r) => {
      setResults(r.results || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const tabs = ["採用候補", "条件付き候補", "監視候補"];
  const filtered = results.filter((r) => r.classification === activeTab);

  const generateAllAAR = async () => {
    const texts: string[] = [];
    for (const r of filtered) {
      try {
        const res = await api.stockAAR(r.symbol);
        texts.push(res.aar_text || generate_aar_text_client(r));
      } catch {
        texts.push(generate_aar_text_client(r));
      }
    }
    setCombinedText(texts);
  };

  if (loading) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <h1 className="text-xl font-bold text-gray-800">📝 AAR出力</h1>
        <div className="flex gap-2">
          <button onClick={generateAllAAR}
            className="px-4 py-2 bg-purple-600 text-white rounded text-sm hover:bg-purple-700">
            全件AAR生成
          </button>
          <button onClick={() => api.exportAARCsv()}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200">
            📄 AAR一括ダウンロード
          </button>
        </div>
      </div>

      <div className="card p-3 text-xs text-gray-500">
        <p><strong>AARメモの使い方:</strong> 候補銘柄のAARを生成し、NotebookLM等に貼り付けて分析・学習にご活用ください。</p>
        <p className="text-orange-500 mt-1">⚠️ これは投資助言ではなく、パターン分析・学習目的です。最終判断はご自身でお願いします。</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-white rounded-lg border border-gray-200 p-1 w-fit">
        {tabs.map((t) => {
          const count = results.filter((r) => r.classification === t).length;
          return (
            <button key={t} onClick={() => setActiveTab(t)}
              className={`px-4 py-2 rounded text-sm font-medium transition-colors ${activeTab === t ? "bg-purple-600 text-white" : "text-gray-600 hover:bg-gray-50"}`}>
              {t} ({count})
            </button>
          );
        })}
      </div>

      {combinedText.length > 0 && (
        <div className="card p-4">
          <div className="flex justify-between items-center mb-2">
            <h3 className="font-bold text-gray-700 text-sm">全件AAR ({combinedText.length}件)</h3>
            <button onClick={() => {
              navigator.clipboard.writeText(combinedText.join("\n\n" + "=".repeat(60) + "\n\n"));
            }} className="text-xs text-blue-600 hover:underline">全コピー</button>
          </div>
          <pre className="whitespace-pre-wrap text-xs text-gray-700 font-mono bg-gray-50 p-3 rounded border max-h-80 overflow-y-auto leading-relaxed">
            {combinedText.join("\n\n" + "=".repeat(60) + "\n\n")}
          </pre>
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="card p-10 text-center text-gray-400">
          {results.length === 0 ? "スクリーニングを実行してください" : "この分類の候補はありません"}
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map((r) => (
            <AARCard key={r.symbol} result={r} onCopy={(text) => {
              setCombinedText((prev) => [...prev.filter((t) => !t.includes(r.symbol)), text]);
            }} />
          ))}
        </div>
      )}
    </div>
  );
}
