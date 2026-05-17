import { ScreeningResult } from "@/lib/types";

export function generate_aar_text_client(r: ScreeningResult): string {
  return `【短期急騰AAR候補メモ】

銘柄：${r.name} (${r.symbol})
日付：${r.date || new Date().toISOString().slice(0, 10)}
市場：${r.market}
判定：${r.classification}
急騰予兆スコア：${r.total_score}/100
主型：${r.main_archetype || "-"}
補助型：${(r.sub_archetypes || []).join(", ") || "-"}
チャート型：${(r.chart_types || []).join(", ") || "-"}
注意型：${(r.warning_types || []).join(", ") || "-"}

【材料】
・${r.material_status || "材料不明"}

【未来急騰予兆】
・チャートサイクル: ${r.chart_cycle_state || "-"}
・出来高サイクル: ${r.volume_cycle_state || "-"}

【出来高サイクル】
・先行大商い：${r.volume_cycle_state === "先行大商い"}
・売り枯れ：${r.volume_cycle_state === "売り枯れ"}
・価格維持：${r.volume_cycle_state === "価格維持"}
・再点火：${r.volume_cycle_state === "再点火待ち" || r.volume_cycle_state === "再点火開始"}

【チャート位置】
・支持線：${r.support_line?.toFixed(2) || "-"}
・抵抗線：${r.resistance_line?.toFixed(2) || "-"}
・25MA乖離：${r.ma25_deviation?.toFixed(1) || "-"}%
・上値余地：${r.upside_to_resistance?.toFixed(1) || "-"}%
・支持線距離：${r.support_distance?.toFixed(1) || "-"}%
・トレンド状態：${r.trend_state || "-"}
・レンジ状態：${r.range_state || "-"}

【ローソク足】
・${r.candle_state || "-"}

【チャートパターン】
・${r.chart_pattern_primary || "-"}

【T-3サイン】
・（手動記入）

【T-2サイン】
・（手動記入）

【T-1サイン】
・（手動記入）

【T-1で入る余地】
条件付き

【エントリー条件】
・（手動記入）

【損切り条件】
・支持線割れ
・25MA大幅割れ

【見送り条件】
・警告フラグ: ${(r.warning_flags || []).join(", ") || "なし"}

【結果論リスク】
・（実際の結果を後から記入）

【今後検証すべき点】
・（手動記入）

※これは投資助言ではなく、短期急騰パターンの分析・学習用メモ。`;
}
