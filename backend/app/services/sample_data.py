"""yfinance失敗時のフォールバック合成株価データ生成"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import hashlib


def _seed_from_symbol(symbol: str) -> int:
    h = hashlib.md5(symbol.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % (2**31 - 1)


def generate_sample_price_data(symbol: str, days: int = 90, market: str = None) -> pd.DataFrame:
    """銘柄ごとに再現可能な合成株価データを生成。
    実価格に近い値域、ローソク足、移動平均線、出来高サイクルを意識する。"""
    seed = _seed_from_symbol(symbol)
    rng = np.random.default_rng(seed)

    # 市場判定
    if market is None:
        market = "JP" if ".T" in symbol else "US"

    # 基準価格 (3000円以下に収まりやすいよう調整)
    if market == "JP":
        base_price = rng.uniform(200, 2800)
    else:
        # 米国株: USDで~$2〜$22 (150円換算で300〜3300円)
        base_price = rng.uniform(2, 22)

    # 出来高ベース
    if market == "JP":
        base_volume = rng.uniform(80_000, 3_000_000)
    else:
        base_volume = rng.uniform(200_000, 10_000_000)

    # トレンドパターン選択 (急騰候補が見つかるよう、有望パターンに少し偏らせる)
    pattern_type = int(rng.choice([0, 1, 2, 3, 4, 5, 6, 7], p=[0.05, 0.05, 0.10, 0.10, 0.15, 0.15, 0.20, 0.20]))
    # 0=横ばい 1=上昇 2=下降 3=反転 4=ダブルボトム 5=ボックス→ブレイク
    # 6=ラリー→押し目→収縮(上値余地大) 7=売り枯れ→底固め(上値余地特大)

    dates = []
    today = datetime.now().date()
    for i in range(days, 0, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:  # 土日スキップ
            continue
        dates.append(d.strftime("%Y-%m-%d"))

    n = len(dates)
    if n < 30:
        n = 80
        dates = [(today - timedelta(days=days - i)).strftime("%Y-%m-%d") for i in range(n)]

    # 価格生成
    trend = np.zeros(n)
    if pattern_type == 0:  # 横ばい
        trend = np.sin(np.linspace(0, 4 * np.pi, n)) * 0.03
    elif pattern_type == 1:  # 上昇
        trend = np.linspace(0, 0.15, n) + np.sin(np.linspace(0, 4 * np.pi, n)) * 0.02
    elif pattern_type == 2:  # 下降
        trend = -np.linspace(0, 0.25, n) + np.sin(np.linspace(0, 4 * np.pi, n)) * 0.02
    elif pattern_type == 3:  # 反転(下げ→底打ち→上昇)
        half = n // 2
        trend[:half] = -np.linspace(0, 0.18, half)
        trend[half:] = -0.18 + np.linspace(0, 0.30, n - half)
    elif pattern_type == 4:  # ダブルボトム
        x = np.linspace(0, 1, n)
        trend = -0.10 * np.exp(-((x - 0.3) ** 2) / 0.02) - 0.10 * np.exp(-((x - 0.7) ** 2) / 0.02) + 0.05 * x
    elif pattern_type == 5:  # ボックス→ブレイク直前(まだブレイクしてない=上値余地あり)
        rally_end = int(n * 0.4)
        trend[:rally_end] = np.linspace(0, 0.30, rally_end)  # 上昇
        trend[rally_end:] = 0.30 + np.sin(np.linspace(0, 4 * np.pi, n - rally_end)) * 0.03 - 0.10 * np.linspace(0, 1, n - rally_end) * 0.5
    elif pattern_type == 6:  # ラリー→押し目→収縮(理想的な再点火待ち)
        rally_end = int(n * 0.35)
        pullback_end = int(n * 0.6)
        trend[:rally_end] = np.linspace(0, 0.35, rally_end)  # +35%上昇
        trend[rally_end:pullback_end] = np.linspace(0.35, 0.10, pullback_end - rally_end)  # 25%押し
        trend[pullback_end:] = 0.10 + np.sin(np.linspace(0, 3 * np.pi, n - pullback_end)) * 0.02  # 横ばい収縮
    elif pattern_type == 7:  # 売り枯れ→底固め(下落後の安定 = 上値余地特大)
        decline_end = int(n * 0.5)
        trend[:decline_end] = np.linspace(0, -0.25, decline_end)  # 下落
        trend[decline_end:] = -0.25 + np.sin(np.linspace(0, 4 * np.pi, n - decline_end)) * 0.02  # 横ばい

    noise = rng.normal(0, 0.012, n)
    log_returns = np.diff(np.concatenate([[0], trend + noise]))

    closes = base_price * np.exp(np.cumsum(log_returns))

    # OHLCV生成
    opens = np.zeros(n)
    highs = np.zeros(n)
    lows = np.zeros(n)
    volumes = np.zeros(n)

    for i in range(n):
        c = closes[i]
        o_prev = closes[i - 1] if i > 0 else c
        opens[i] = o_prev * (1 + rng.normal(0, 0.005))
        body = abs(c - opens[i])
        upper = body * rng.uniform(0.3, 1.5)
        lower = body * rng.uniform(0.3, 1.5)
        highs[i] = max(c, opens[i]) + upper
        lows[i] = min(c, opens[i]) - lower

        # 出来高: トレンド変化点で増加
        vol_mult = 1.0
        ratio_pos = i / n
        if i > 0 and abs(log_returns[i]) > 0.02:
            vol_mult = rng.uniform(1.5, 3.5)
        elif pattern_type == 4 and 0.25 < ratio_pos < 0.35:
            vol_mult = rng.uniform(0.3, 0.6)  # ダブルボトムでの売り枯れ
        elif pattern_type == 6 and ratio_pos < 0.4:
            vol_mult = rng.uniform(1.8, 3.0)  # 先行大商い
        elif pattern_type == 6 and ratio_pos > 0.7:
            vol_mult = rng.uniform(0.3, 0.6)  # 売り枯れ→再点火待ち
        elif pattern_type == 7 and ratio_pos > 0.6:
            vol_mult = rng.uniform(0.2, 0.5)  # 売り枯れ
        elif pattern_type == 5 and ratio_pos > 0.5:
            vol_mult = rng.uniform(0.4, 0.8)  # ブレイク前の収縮
        volumes[i] = base_volume * vol_mult * rng.uniform(0.7, 1.3)

    df = pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })
    return df


def generate_sample_info(symbol: str, name: str = None, market: str = None) -> dict:
    if market is None:
        market = "JP" if ".T" in symbol else "US"
    return {
        "name": name or symbol,
        "sector": "Sample",
        "industry": "Sample",
        "market_cap": 0,
        "currency": "JPY" if market == "JP" else "USD",
        "country": "Japan" if market == "JP" else "United States",
    }
