"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";

interface Summary {
  total_cases: number;
  positive_case_count: number;
  negative_case_count: number;
  t0_only_count: number;
  already_ran_count: number;
  weak_material_count: number;
  by_judgement: Record<string, number>;
  by_catalyst_category: Record<string, number>;
  by_setup_type: Record<string, number>;
  by_volume_type: Record<string, number>;
  by_chart_type: Record<string, number>;
}

interface Case {
  id: number;
  symbol: string;
  yahoo_symbol?: string;
  name?: string;
  market?: string;
  move_date: string;
  move_percent?: number;
  catalyst_category?: string;
  t1_judgement?: string;
  setup_type?: string;
  volume_type?: string;
  chart_type?: string;
  overextension_risk_score?: number;
  weak_material_flag?: boolean;
  t0_only_flag?: boolean;
  already_ran_flag?: boolean;
  is_positive_case?: boolean;
  is_negative_case?: boolean;
  created_at?: string;
}

function StatCard({ label, value, color = "text-gray-900", sub }: { label: string; value: number | string; color?: string; sub?: string }) {
  return (
    <div className="card p-3">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-xl font-bold ${color}`}>{typeof value === "number" ? value.toLocaleString() : value}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

function MiniBar({ data, title }: { data: Record<string, number>; title: string }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  return (
    <div className="card p-4">
      <h3 className="font-bold text-gray-700 text-sm mb-3">{title}</h3>
      <div className="space-y-1">
        {entries.map(([k, v]) => (
          <div key={k} className="flex justify-between text-xs py-0.5 border-b border-gray-50">
            <span className="text-gray-600">{k}</span>
            <span className="font-bold text-gray-800">{v.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AARLearningPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([
        fetchAPI("/api/aar/summary"),
        fetchAPI(`/api/aar/cases?limit=300${filter ? "&judgement=" + encodeURIComponent(filter) : ""}`),
      ]);
      setSummary(s);
      setCases(c.items || []);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, [filter]);

  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  const deleteCase = async (id: number) => {
    if (!confirm(`case_id=${id} を削除しますか?`)) return;
    try {
      await fetchAPI(`/api/aar/cases/${id}`, { method: "DELETE" });
      load();
    } catch (e: any) {
      alert(e.message);
    }
  };

  if (error) return <div className="card p-6 mt-10 mx-auto max-w-2xl"><p className="text-red-600">エラー: {error}</p></div>;
  if (!summary) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;

  return (
    <div className="space-y-5">
      <div className="card p-5" style={{ background: "linear-gradient(135deg, #312e81 0%, #1e3a8a 100%)" }}>
        <h1 className="text-white text-xl font-bold mb-1">🎓 AAR学習データ管理</h1>
        <p className="text-blue-200 text-sm">急騰AARを構造化教師データとして管理。現在銘柄の急騰前夜予測に活用されます。</p>
        <div className="mt-3">
          <Link href="/aar-analyzer" className="inline-block px-4 py-2 bg-purple-600 text-white rounded text-sm hover:bg-purple-700">
            🔬 新しい急騰銘柄を分析する →
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard label="取り込んだ急騰ケース" value={summary.total_cases} sub="教師データ総数" />
        <StatCard label="Positive Case" value={summary.positive_case_count} color="text-green-600" sub="+20%達成 & 上がり切りでない" />
        <StatCard label="Negative Case" value={summary.negative_case_count} color="text-red-500" sub="+20%未達 or 後DD大" />
        <StatCard label="T0初動のみ" value={summary.t0_only_count} color="text-orange-500" sub="T-1兆候なし" />
        <StatCard label="上がり切りケース" value={summary.already_ran_count} color="text-red-400" sub="ranking上位から除外" />
        <StatCard label="材料弱いケース" value={summary.weak_material_count} color="text-gray-500" sub="材料未確認" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
        <MiniBar data={summary.by_judgement} title="T-1判定別" />
        <MiniBar data={summary.by_catalyst_category} title="材料カテゴリ別" />
        <MiniBar data={summary.by_setup_type} title="セットアップ型別" />
        <MiniBar data={summary.by_volume_type} title="出来高型別" />
        <MiniBar data={summary.by_chart_type} title="チャート型別" />
      </div>

      <div className="card p-4">
        <div className="flex justify-between items-center mb-3">
          <h2 className="font-bold text-gray-800">学習ケース一覧</h2>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}
            className="border border-gray-200 rounded px-2 py-1 text-xs">
            <option value="">全件</option>
            <option value="入る余地あり">入る余地あり</option>
            <option value="条件付き">条件付き</option>
            <option value="見送り">見送り</option>
            <option value="T0初動のみ">T0初動のみ</option>
            <option value="イベント確認後のみ">イベント確認後のみ</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 border-b border-gray-100 text-gray-500">
              <tr>
                <th className="px-2 py-1 text-left">id</th>
                <th className="px-2 py-1 text-left">symbol</th>
                <th className="px-2 py-1 text-left">name</th>
                <th className="px-2 py-1 text-left">market</th>
                <th className="px-2 py-1 text-left">move_date</th>
                <th className="px-2 py-1 text-right">move %</th>
                <th className="px-2 py-1 text-left">catalyst</th>
                <th className="px-2 py-1 text-left">t1判定</th>
                <th className="px-2 py-1 text-left">setup</th>
                <th className="px-2 py-1 text-left">volume</th>
                <th className="px-2 py-1 text-left">chart</th>
                <th className="px-2 py-1 text-right">過熱</th>
                <th className="px-2 py-1 text-center">P/N</th>
                <th className="px-2 py-1 text-center">flags</th>
                <th className="px-2 py-1 text-left">操作</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id} className="border-b border-gray-50 hover:bg-blue-50">
                  <td className="px-2 py-1 text-gray-400">{c.id}</td>
                  <td className="px-2 py-1 font-mono font-bold">{c.symbol}</td>
                  <td className="px-2 py-1 text-gray-700 max-w-24 truncate">{c.name}</td>
                  <td className="px-2 py-1 text-gray-500">{c.market}</td>
                  <td className="px-2 py-1 text-gray-600">{c.move_date}</td>
                  <td className="px-2 py-1 text-right font-bold text-green-600">{c.move_percent?.toFixed(1)}%</td>
                  <td className="px-2 py-1 text-gray-600">{c.catalyst_category}</td>
                  <td className={`px-2 py-1 font-medium ${c.t1_judgement === "入る余地あり" ? "text-green-600" : c.t1_judgement === "条件付き" ? "text-blue-600" : "text-red-500"}`}>
                    {c.t1_judgement}
                  </td>
                  <td className="px-2 py-1 text-gray-600">{c.setup_type}</td>
                  <td className="px-2 py-1 text-gray-600">{c.volume_type}</td>
                  <td className="px-2 py-1 text-gray-600">{c.chart_type}</td>
                  <td className={`px-2 py-1 text-right ${(c.overextension_risk_score ?? 0) >= 60 ? "text-red-500" : "text-gray-600"}`}>
                    {c.overextension_risk_score?.toFixed(0)}
                  </td>
                  <td className="px-2 py-1 text-center">
                    {c.is_positive_case && <span className="text-green-600">✓P</span>}
                    {c.is_negative_case && <span className="text-red-500 ml-1">✗N</span>}
                  </td>
                  <td className="px-2 py-1 text-center text-xs">
                    {c.weak_material_flag && <span title="材料弱い" className="text-orange-500">材</span>}
                    {c.already_ran_flag && <span title="上がり切り" className="text-red-500 ml-0.5">過</span>}
                    {c.t0_only_flag && <span title="T0のみ" className="text-purple-500 ml-0.5">T0</span>}
                  </td>
                  <td className="px-2 py-1">
                    <button onClick={() => deleteCase(c.id)} className="text-red-400 text-xs hover:underline">削除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {cases.length === 0 && (
          <p className="text-center text-gray-400 py-8 text-sm">
            学習データがありません。<Link href="/aar-analyzer" className="text-blue-600 hover:underline">AAR分析ページ</Link>から急騰銘柄を投入してください。
          </p>
        )}
      </div>

      <div className="card p-3 text-xs text-gray-500">
        <p><strong>P/N(positive/negative):</strong> P=T0以降+20%達成かつ上がり切り型でない / N=+20%未達もしくは大幅DD</p>
        <p><strong>flags:</strong> 材=材料弱い 過=上がり切り T0=T-1兆候なくT0で初めて出来高急増</p>
        <p className="text-orange-600 mt-1">⚠️ これは投資助言ではなく、急騰前夜パターンの分析・学習目的のツールです。</p>
      </div>
    </div>
  );
}
