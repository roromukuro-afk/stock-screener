"use client";
import { useEffect, useState } from "react";
import { use } from "react";
import { api } from "@/lib/api";
import { ScreeningResult, ChartDataPoint } from "@/lib/types";
import ClassificationBadge from "@/components/ClassificationBadge";
import ScoreBar from "@/components/ScoreBar";
import VolCycleBadge from "@/components/VolCycleBadge";
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend
} from "recharts";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <h3 className="font-bold text-gray-800 text-sm mb-3 border-b border-gray-100 pb-2">{title}</h3>
      <div className="text-sm text-gray-700 space-y-1">{children}</div>
    </div>
  );
}

function InfoRow({ label, value, highlight }: { label: string; value: string | number | undefined | null; highlight?: boolean }) {
  return (
    <div className="flex justify-between py-0.5 border-b border-gray-50">
      <span className="text-gray-500 text-xs">{label}</span>
      <span className={`text-xs font-medium ${highlight ? "text-green-600" : "text-gray-800"}`}>{value ?? "-"}</span>
    </div>
  );
}

function ScoreBreakdown({ data }: { data: ScreeningResult }) {
  const items = [
    { label: "上値余地", score: data.upside_score, max: 15 },
    { label: "未来急騰予兆", score: data.future_catalyst_score, max: 15 },
    { label: "チャート構造", score: data.chart_score, max: 15 },
    { label: "出来高サイクル", score: data.volume_cycle_score, max: 15 },
    { label: "材料・テーマ", score: data.material_theme_score, max: 10 },
    { label: "需給の軽さ", score: data.supply_score, max: 10 },
    { label: "アーキタイプ", score: data.archetype_score, max: 10 },
    { label: "リスク管理", score: data.risk_management_score, max: 10 },
  ];
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-2">
          <span className="text-xs text-gray-500 w-28">{item.label}</span>
          <div className="flex-1 bg-gray-100 rounded-full h-1.5">
            <div className="h-1.5 rounded-full bg-blue-500"
              style={{ width: `${((item.score ?? 0) / item.max) * 100}%` }} />
          </div>
          <span className="text-xs font-bold text-gray-700 w-12 text-right">{item.score ?? 0}/{item.max}</span>
        </div>
      ))}
      <div className="flex justify-between pt-2 border-t border-gray-100">
        <span className="text-sm font-bold text-gray-700">合計</span>
        <span className="text-sm font-bold text-blue-700">{data.total_score}/100</span>
      </div>
    </div>
  );
}

function PriceChart({ chartData, support, resistance }: {
  chartData: ChartDataPoint[];
  support?: number;
  resistance?: number;
}) {
  if (!chartData || chartData.length === 0) return <p className="text-gray-400 text-sm">チャートデータなし</p>;

  return (
    <div className="space-y-4">
      <div style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
            <YAxis tick={{ fontSize: 10 }} width={60} />
            <Tooltip
              labelStyle={{ fontSize: 11 }}
              contentStyle={{ fontSize: 11 }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {support && <ReferenceLine y={support} stroke="#22c55e" strokeDasharray="4 4" label={{ value: "支持線", fontSize: 10 }} />}
            {resistance && <ReferenceLine y={resistance} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "抵抗線", fontSize: 10 }} />}
            <Line type="monotone" dataKey="close" stroke="#3b82f6" dot={false} strokeWidth={2} name="終値" />
            <Line type="monotone" dataKey="ma5" stroke="#f59e0b" dot={false} strokeWidth={1} name="MA5" />
            <Line type="monotone" dataKey="ma25" stroke="#8b5cf6" dot={false} strokeWidth={1.5} name="MA25" />
            <Line type="monotone" dataKey="ma75" stroke="#06b6d4" dot={false} strokeWidth={1} name="MA75" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div style={{ height: 100 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
            <YAxis tick={{ fontSize: 10 }} width={60} />
            <Tooltip contentStyle={{ fontSize: 11 }} />
            <Bar dataKey="volume" fill="#93c5fd" name="出来高" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function StockDetailPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params);
  const decodedSymbol = decodeURIComponent(symbol);

  const [data, setData] = useState<ScreeningResult | null>(null);
  const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
  const [aarText, setAarText] = useState<string>("");
  const [aarCopied, setAarCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState("3mo");

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.stock(decodedSymbol),
      api.stockChart(decodedSymbol, period),
    ]).then(([stockData, cd]) => {
      setData(stockData);
      setChartData(cd.data || []);
      setLoading(false);
    }).catch((e) => {
      setError(e.message);
      setLoading(false);
    });
  }, [decodedSymbol, period]);

  const loadAAR = async () => {
    try {
      const r = await api.stockAAR(decodedSymbol);
      setAarText(r.aar_text || "");
    } catch (e: any) {
      setAarText("AARの生成にはスクリーニング実行が必要です。");
    }
  };

  if (loading) return <div className="text-center py-20 text-gray-400">読み込み中...</div>;
  if (error) return (
    <div className="card p-6 max-w-xl mx-auto">
      <p className="text-red-600 font-bold">エラー: {error}</p>
    </div>
  );
  if (!data) return <div className="text-center py-20 text-gray-400">データなし</div>;

  const change = data.price_change_1d ?? 0;
  const upside = data.upside_to_resistance ?? 0;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="card p-5">
        <div className="flex flex-wrap justify-between items-start gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-2xl font-bold text-gray-900">{data.name}</h1>
              <ClassificationBadge cls={data.classification} />
            </div>
            <p className="text-gray-500 text-sm">
              {decodedSymbol} | {data.market}{data.is_adr ? " (ADR)" : ""} | {data.exchange || ""}
            </p>
          </div>
          <div className="text-right">
            <p className="text-3xl font-bold text-gray-900">¥{data.jpy_price?.toLocaleString()}</p>
            <p className="text-sm text-gray-500">{data.currency}: {data.price?.toLocaleString()}</p>
            <p className={`text-lg font-bold ${change >= 0 ? "text-green-600" : "text-red-500"}`}>
              {change >= 0 ? "+" : ""}{change.toFixed(2)}%
            </p>
          </div>
        </div>

        <div className="mt-4">
          <p className="text-xs text-gray-500 mb-1">急騰予兆スコア</p>
          <div className="flex items-center gap-3">
            <div className="flex-1"><ScoreBar score={data.total_score} /></div>
            <span className="text-2xl font-bold text-blue-700">{data.total_score}/100</span>
          </div>
        </div>

        {data.warning_flags && data.warning_flags.length > 0 && (
          <div className="mt-3 p-2 bg-orange-50 rounded border border-orange-200">
            <p className="text-orange-600 text-xs font-bold">⚠️ 警告フラグ: {data.warning_flags.join(", ")}</p>
          </div>
        )}
        <div className="mt-3 p-2 bg-yellow-50 rounded text-yellow-700 text-xs">
          ※ これは投資助言ではありません。最終判断はユーザー自身が行ってください。
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left column */}
        <div className="lg:col-span-2 space-y-5">
          {/* Chart */}
          <div className="card p-4">
            <div className="flex justify-between items-center mb-4">
              <h2 className="font-bold text-gray-800">📊 チャート</h2>
              <div className="flex gap-1">
                {["1mo", "3mo", "6mo", "1y"].map((p) => (
                  <button key={p} onClick={() => setPeriod(p)}
                    className={`px-3 py-1 rounded text-xs ${period === p ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600"}`}>
                    {p}
                  </button>
                ))}
              </div>
            </div>
            <PriceChart chartData={chartData} support={data.support_line} resistance={data.resistance_line} />
          </div>

          {/* Score Breakdown */}
          <Section title="📈 スコア内訳">
            <ScoreBreakdown data={data} />
          </Section>

          {/* AI Comment */}
          {data.ai_comment && (
            <Section title="🤖 AI分析コメント">
              <pre className="whitespace-pre-wrap text-xs text-gray-700 font-sans leading-relaxed">
                {data.ai_comment}
              </pre>
            </Section>
          )}

          {/* AAR */}
          <div className="card p-4">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-bold text-gray-800 text-sm">📝 AARメモ</h3>
              <div className="flex gap-2">
                <button onClick={loadAAR} className="px-3 py-1.5 bg-purple-600 text-white rounded text-xs hover:bg-purple-700">
                  AAR生成
                </button>
                {aarText && (
                  <button onClick={() => {
                    navigator.clipboard.writeText(aarText);
                    setAarCopied(true);
                    setTimeout(() => setAarCopied(false), 2000);
                  }} className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-xs hover:bg-gray-200">
                    {aarCopied ? "✅ コピー済み" : "コピー"}
                  </button>
                )}
              </div>
            </div>
            {aarText ? (
              <pre className="whitespace-pre-wrap text-xs text-gray-700 font-mono bg-gray-50 p-3 rounded border border-gray-200 max-h-80 overflow-y-auto leading-relaxed">
                {aarText}
              </pre>
            ) : (
              <p className="text-xs text-gray-400">「AAR生成」ボタンを押してください</p>
            )}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          <Section title="基本情報">
            <InfoRow label="現在値" value={`${data.price?.toLocaleString()} ${data.currency}`} />
            <InfoRow label="円換算価格" value={`¥${data.jpy_price?.toLocaleString()}`} />
            <InfoRow label="為替レート" value={`${data.fx_rate?.toFixed(2)} JPY`} />
            <InfoRow label="出来高" value={data.volume?.toLocaleString()} />
            <InfoRow label="20日平均出来高" value={data.volume_avg20?.toLocaleString()} />
            <InfoRow label="出来高倍率" value={`${data.volume_ratio?.toFixed(2)}x`} />
          </Section>

          <Section title="移動平均線">
            <InfoRow label="5日MA" value={data.ma5?.toFixed(2)} />
            <InfoRow label="25日MA" value={data.ma25?.toFixed(2)} />
            <InfoRow label="75日MA" value={data.ma75?.toFixed(2)} />
            <InfoRow label="200日MA" value={data.ma200?.toFixed(2)} />
            <InfoRow label="25MA乖離率" value={`${data.ma25_deviation?.toFixed(2)}%`}
              highlight={(data.ma25_deviation ?? 0) < 30} />
          </Section>

          <Section title="支持線・抵抗線">
            <InfoRow label="支持線" value={data.support_line?.toFixed(2)} />
            <InfoRow label="抵抗線" value={data.resistance_line?.toFixed(2)} />
            <InfoRow label="上値余地" value={`${upside.toFixed(2)}%`} highlight={upside >= 20} />
            <InfoRow label="支持線までの距離" value={`${data.support_distance?.toFixed(2)}%`} />
            <InfoRow label="20日高値" value={data.recent_high_20?.toFixed(2)} />
            <InfoRow label="20日安値" value={data.recent_low_20?.toFixed(2)} />
          </Section>

          <Section title="テクニカル指標">
            <InfoRow label="RSI" value={data.rsi?.toFixed(1)} />
            <InfoRow label="ATR" value={data.atr?.toFixed(4)} />
            <InfoRow label="前日比" value={`${change.toFixed(2)}%`} />
            <InfoRow label="5日騰落率" value={`${data.price_change_5d?.toFixed(2)}%`} />
            <InfoRow label="20日騰落率" value={`${data.price_change_20d?.toFixed(2)}%`} />
          </Section>

          <Section title="チャート判定">
            <InfoRow label="トレンド" value={data.trend_state} />
            <InfoRow label="レンジ状態" value={data.range_state} />
            <InfoRow label="ローソク足" value={data.candle_state} />
            <InfoRow label="チャートパターン" value={data.chart_pattern_primary} />
            <InfoRow label="パターン信頼度" value={`${((data.pattern_confidence ?? 0) * 100).toFixed(0)}%`} />
          </Section>

          <Section title="サイクル判定">
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs text-gray-500">出来高サイクル</span>
                <VolCycleBadge state={data.volume_cycle_state} />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-gray-500">チャートサイクル</span>
                <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">{data.chart_cycle_state}</span>
              </div>
              <InfoRow label="材料状況" value={data.material_status} />
            </div>
          </Section>

          <Section title="アーキタイプ分類">
            <InfoRow label="主型" value={data.main_archetype} />
            <InfoRow label="補助型" value={(data.sub_archetypes || []).join(", ") || "-"} />
            <InfoRow label="チャート型" value={(data.chart_types || []).join(", ") || "-"} />
            <InfoRow label="注意型" value={(data.warning_types || []).join(", ") || "-"} />
          </Section>
        </div>
      </div>
    </div>
  );
}
