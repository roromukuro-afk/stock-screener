"""CSV / Excel出力サービス"""
import io
import pandas as pd
from typing import List, Dict
from datetime import datetime


def results_to_df(results: List[Dict]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


def export_csv(results: List[Dict]) -> bytes:
    df = results_to_df(results)
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    return buf.getvalue().encode("utf-8-sig")


def export_excel(results: List[Dict], exclusions: List[Dict] = None) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_all = results_to_df(results)
        if not df_all.empty:
            df_all.to_excel(writer, sheet_name="All_Results", index=False)

            for cls, sheet in [("採用候補", "Adopted"), ("条件付き候補", "Conditional"), ("監視候補", "Watch")]:
                df_sub = df_all[df_all["classification"] == cls] if "classification" in df_all.columns else pd.DataFrame()
                df_sub.to_excel(writer, sheet_name=sheet, index=False)

        if exclusions:
            df_ex = pd.DataFrame(exclusions)
            df_ex.to_excel(writer, sheet_name="Excluded", index=False)

        pd.DataFrame([{"note": "バックテスト結果はバックテストページから出力してください"}]).to_excel(
            writer, sheet_name="Backtest", index=False
        )

    buf.seek(0)
    return buf.read()


def generate_aar_text(result: Dict) -> str:
    name = result.get("name", result.get("symbol", ""))
    symbol = result.get("symbol", "")
    market = result.get("market", "")
    date = result.get("date", datetime.now().strftime("%Y-%m-%d"))
    classification = result.get("classification", "")
    score = result.get("total_score", 0)
    main_arch = result.get("main_archetype", "")
    sub_arch = ", ".join(result.get("sub_archetypes", []))
    chart_type = ", ".join(result.get("chart_types", []))
    warning_type = ", ".join(result.get("warning_types", []))
    material = result.get("material_status", "材料不明")
    vol_cycle = result.get("volume_cycle_state", "")
    chart_cycle = result.get("chart_cycle_state", "")
    support = result.get("support_line", "")
    resistance = result.get("resistance_line", "")
    ma25_dev = result.get("ma25_deviation", "")
    upside = result.get("upside_to_resistance", "")
    support_dist = result.get("support_distance", "")
    trend = result.get("trend_state", "")
    range_state = result.get("range_state", "")
    candle = result.get("candle_state", "")
    pattern = result.get("chart_pattern_primary", "")
    flags = ", ".join(result.get("warning_flags", []))

    text = f"""【短期急騰AAR候補メモ】

銘柄：{name} ({symbol})
日付：{date}
市場：{market}
判定：{classification}
急騰予兆スコア：{score}/100
主型：{main_arch}
補助型：{sub_arch}
チャート型：{chart_type}
注意型：{warning_type}

【材料】
・{material}

【未来急騰予兆】
・チャートサイクル: {chart_cycle}
・出来高サイクル: {vol_cycle}

【出来高サイクル】
・先行大商い：{vol_cycle == '先行大商い'}
・売り枯れ：{vol_cycle == '売り枯れ'}
・価格維持：{vol_cycle == '価格維持'}
・再点火：{vol_cycle in ['再点火待ち', '再点火開始']}

【チャート位置】
・支持線：{support}
・抵抗線：{resistance}
・25MA乖離：{ma25_dev}%
・上値余地：{upside}%
・支持線距離：{support_dist}%
・トレンド状態：{trend}
・レンジ状態：{range_state}

【ローソク足】
・{candle}

【チャートパターン】
・{pattern}

【T-3サイン】
・（手動記入）

【T-2サイン】
・（手動記入）

【T-1サイン】
・（手動記入）

【T-1で入る余地】
条件付き

【エントリー条件】
・抵抗線ブレイク確認後
・出来高増加を確認してから
・損切りラインを事前に設定すること

【損切り条件】
・支持線割れ
・25MA大幅割れ
・大商い大陰線

【見送り条件】
・警告フラグ: {flags if flags else 'なし'}
・上値余地20%未満の場合
・流動性不足の場合

【結果論リスク】
・（実際の結果を後から記入）

【今後検証すべき点】
・このパターンが{classification}として機能したか
・{vol_cycle}状態からの推移

※これは投資助言ではなく、短期急騰パターンの分析・学習用メモ。
最終的な売買判断はユーザー自身が行ってください。
"""
    return text
