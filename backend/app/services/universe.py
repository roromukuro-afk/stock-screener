"""銘柄ユニバース取得サービス"""
import os
import io
import requests
import pandas as pd
from typing import List, Dict

SAMPLE_JP = [
    {"symbol": "7203.T", "name": "トヨタ自動車", "market": "JP", "exchange": "TSE"},
    {"symbol": "9432.T", "name": "日本電信電話", "market": "JP", "exchange": "TSE"},
    {"symbol": "6758.T", "name": "ソニーグループ", "market": "JP", "exchange": "TSE"},
    {"symbol": "8306.T", "name": "三菱UFJフィナンシャルG", "market": "JP", "exchange": "TSE"},
    {"symbol": "6861.T", "name": "キーエンス", "market": "JP", "exchange": "TSE"},
    {"symbol": "9984.T", "name": "ソフトバンクグループ", "market": "JP", "exchange": "TSE"},
    {"symbol": "4519.T", "name": "中外製薬", "market": "JP", "exchange": "TSE"},
    {"symbol": "6367.T", "name": "ダイキン工業", "market": "JP", "exchange": "TSE"},
    {"symbol": "4063.T", "name": "信越化学工業", "market": "JP", "exchange": "TSE"},
    {"symbol": "8035.T", "name": "東京エレクトロン", "market": "JP", "exchange": "TSE"},
    {"symbol": "2413.T", "name": "エムスリー", "market": "JP", "exchange": "TSE"},
    {"symbol": "4543.T", "name": "テルモ", "market": "JP", "exchange": "TSE"},
    {"symbol": "9983.T", "name": "ファーストリテイリング", "market": "JP", "exchange": "TSE"},
    {"symbol": "6098.T", "name": "リクルートHD", "market": "JP", "exchange": "TSE"},
    {"symbol": "7974.T", "name": "任天堂", "market": "JP", "exchange": "TSE"},
    {"symbol": "4661.T", "name": "オリエンタルランド", "market": "JP", "exchange": "TSE"},
    {"symbol": "2802.T", "name": "味の素", "market": "JP", "exchange": "TSE"},
    {"symbol": "8801.T", "name": "三井不動産", "market": "JP", "exchange": "TSE"},
    {"symbol": "5108.T", "name": "ブリヂストン", "market": "JP", "exchange": "TSE"},
    {"symbol": "4503.T", "name": "アステラス製薬", "market": "JP", "exchange": "TSE"},
    {"symbol": "3382.T", "name": "セブン&アイHD", "market": "JP", "exchange": "TSE"},
    {"symbol": "9022.T", "name": "東海旅客鉄道", "market": "JP", "exchange": "TSE"},
    {"symbol": "6902.T", "name": "デンソー", "market": "JP", "exchange": "TSE"},
    {"symbol": "4901.T", "name": "富士フイルムHD", "market": "JP", "exchange": "TSE"},
    {"symbol": "8316.T", "name": "三井住友フィナンシャルG", "market": "JP", "exchange": "TSE"},
    {"symbol": "6954.T", "name": "ファナック", "market": "JP", "exchange": "TSE"},
    {"symbol": "4568.T", "name": "第一三共", "market": "JP", "exchange": "TSE"},
    {"symbol": "6501.T", "name": "日立製作所", "market": "JP", "exchange": "TSE"},
    {"symbol": "5401.T", "name": "日本製鉄", "market": "JP", "exchange": "TSE"},
    {"symbol": "2914.T", "name": "日本たばこ産業", "market": "JP", "exchange": "TSE"},
    {"symbol": "4911.T", "name": "資生堂", "market": "JP", "exchange": "TSE"},
    {"symbol": "9613.T", "name": "NTTデータグループ", "market": "JP", "exchange": "TSE"},
    {"symbol": "6723.T", "name": "ルネサスエレクトロニクス", "market": "JP", "exchange": "TSE"},
    {"symbol": "4704.T", "name": "トレンドマイクロ", "market": "JP", "exchange": "TSE"},
    {"symbol": "3659.T", "name": "ネクソン", "market": "JP", "exchange": "TSE"},
    {"symbol": "7267.T", "name": "本田技研工業", "market": "JP", "exchange": "TSE"},
    {"symbol": "7751.T", "name": "キヤノン", "market": "JP", "exchange": "TSE"},
    {"symbol": "8411.T", "name": "みずほフィナンシャルG", "market": "JP", "exchange": "TSE"},
    {"symbol": "4452.T", "name": "花王", "market": "JP", "exchange": "TSE"},
    {"symbol": "9001.T", "name": "東武鉄道", "market": "JP", "exchange": "TSE"},
    {"symbol": "3861.T", "name": "王子HD", "market": "JP", "exchange": "TSE"},
    {"symbol": "5020.T", "name": "ENEOSホールディングス", "market": "JP", "exchange": "TSE"},
    {"symbol": "6752.T", "name": "パナソニックHD", "market": "JP", "exchange": "TSE"},
    {"symbol": "7270.T", "name": "SUBARU", "market": "JP", "exchange": "TSE"},
    {"symbol": "4578.T", "name": "大塚HD", "market": "JP", "exchange": "TSE"},
    {"symbol": "6594.T", "name": "日本電産(ニデック)", "market": "JP", "exchange": "TSE"},
    {"symbol": "6503.T", "name": "三菱電機", "market": "JP", "exchange": "TSE"},
    {"symbol": "6301.T", "name": "小松製作所", "market": "JP", "exchange": "TSE"},
    {"symbol": "9531.T", "name": "東京ガス", "market": "JP", "exchange": "TSE"},
    {"symbol": "8002.T", "name": "丸紅", "market": "JP", "exchange": "TSE"},
    {"symbol": "8031.T", "name": "三井物産", "market": "JP", "exchange": "TSE"},
    {"symbol": "8058.T", "name": "三菱商事", "market": "JP", "exchange": "TSE"},
    {"symbol": "7011.T", "name": "三菱重工業", "market": "JP", "exchange": "TSE"},
    {"symbol": "6702.T", "name": "富士通", "market": "JP", "exchange": "TSE"},
    {"symbol": "6479.T", "name": "ミネベアミツミ", "market": "JP", "exchange": "TSE"},
    {"symbol": "4151.T", "name": "協和キリン", "market": "JP", "exchange": "TSE"},
    {"symbol": "2269.T", "name": "明治HD", "market": "JP", "exchange": "TSE"},
    {"symbol": "9433.T", "name": "KDDI", "market": "JP", "exchange": "TSE"},
    {"symbol": "9101.T", "name": "日本郵船", "market": "JP", "exchange": "TSE"},
    {"symbol": "9104.T", "name": "商船三井", "market": "JP", "exchange": "TSE"},
    {"symbol": "9107.T", "name": "川崎汽船", "market": "JP", "exchange": "TSE"},
    {"symbol": "4755.T", "name": "楽天グループ", "market": "JP", "exchange": "TSE"},
    {"symbol": "3092.T", "name": "ZOZO", "market": "JP", "exchange": "TSE"},
    {"symbol": "4689.T", "name": "LINEヤフー", "market": "JP", "exchange": "TSE"},
    {"symbol": "4385.T", "name": "メルカリ", "market": "JP", "exchange": "TSE"},
    {"symbol": "3697.T", "name": "SHIFT", "market": "JP", "exchange": "TSE"},
    {"symbol": "4480.T", "name": "メドレー", "market": "JP", "exchange": "TSE"},
    {"symbol": "4194.T", "name": "ビジョナル", "market": "JP", "exchange": "TSE"},
    {"symbol": "4051.T", "name": "GMOフィナンシャルG", "market": "JP", "exchange": "TSE"},
    {"symbol": "3496.T", "name": "アズームホールディングス", "market": "JP", "exchange": "TSE"},
    {"symbol": "2160.T", "name": "ジーエヌアイグループ", "market": "JP", "exchange": "TSE"},
    {"symbol": "6625.T", "name": "JALCO HD", "market": "JP", "exchange": "TSE"},
    {"symbol": "7379.T", "name": "サーキュレーション", "market": "JP", "exchange": "TSE"},
    {"symbol": "4430.T", "name": "東海ソフト", "market": "JP", "exchange": "TSE"},
    {"symbol": "3498.T", "name": "霞ヶ関キャピタル", "market": "JP", "exchange": "TSE"},
    {"symbol": "2641.T", "name": "グロービス", "market": "JP", "exchange": "TSE"},
]

SAMPLE_US = [
    {"symbol": "AAPL", "name": "Apple Inc.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "MSFT", "name": "Microsoft Corp.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "NVDA", "name": "NVIDIA Corp.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "META", "name": "Meta Platforms Inc.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "INTC", "name": "Intel Corp.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "SMCI", "name": "Super Micro Computer", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "MARA", "name": "MARA Holdings", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "RIOT", "name": "Riot Platforms", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "CLSK", "name": "CleanSpark Inc.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "CLOV", "name": "Clover Health", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "SOUN", "name": "SoundHound AI", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "BBAI", "name": "BigBear.ai", "market": "US", "exchange": "NYSE"},
    {"symbol": "IONQ", "name": "IonQ Inc.", "market": "US", "exchange": "NYSE"},
    {"symbol": "JOBY", "name": "Joby Aviation", "market": "US", "exchange": "NYSE"},
    {"symbol": "ACHR", "name": "Archer Aviation", "market": "US", "exchange": "NYSE"},
    {"symbol": "LUNR", "name": "Intuitive Machines", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "RKLB", "name": "Rocket Lab USA", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "SPCE", "name": "Virgin Galactic", "market": "US", "exchange": "NYSE"},
    {"symbol": "MNKD", "name": "MannKind Corp.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "BNGO", "name": "Bionano Genomics", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "SENS", "name": "Sensata Technologies", "market": "US", "exchange": "NYSE"},
    {"symbol": "OPEN", "name": "Opendoor Technologies", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "GRAB", "name": "Grab Holdings", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "SE", "name": "Sea Limited", "market": "US", "exchange": "NYSE"},
    {"symbol": "SOFI", "name": "SoFi Technologies", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "HOOD", "name": "Robinhood Markets", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "COUR", "name": "Coursera Inc.", "market": "US", "exchange": "NYSE"},
    {"symbol": "AFRM", "name": "Affirm Holdings", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "UPST", "name": "Upstart Holdings", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "AI", "name": "C3.ai Inc.", "market": "US", "exchange": "NYSE"},
    {"symbol": "PLTR", "name": "Palantir Technologies", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "RIVN", "name": "Rivian Automotive", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "LCID", "name": "Lucid Group", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "FSR", "name": "Fisker Inc.", "market": "US", "exchange": "NYSE"},
    {"symbol": "NKLA", "name": "Nikola Corp.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "GOEV", "name": "Canoo Inc.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "BLNK", "name": "Blink Charging", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "CHPT", "name": "ChargePoint Holdings", "market": "US", "exchange": "NYSE"},
    {"symbol": "STEM", "name": "Stem Inc.", "market": "US", "exchange": "NYSE"},
    {"symbol": "PLUG", "name": "Plug Power Inc.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "BE", "name": "Bloom Energy", "market": "US", "exchange": "NYSE"},
    {"symbol": "FCEL", "name": "FuelCell Energy", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "RUN", "name": "Sunrun Inc.", "market": "US", "exchange": "NASDAQ"},
    {"symbol": "NOVA", "name": "Sunnova Energy", "market": "US", "exchange": "NYSE"},
    {"symbol": "HIMS", "name": "Hims & Hers Health", "market": "US", "exchange": "NYSE"},
    {"symbol": "RXRX", "name": "Recursion Pharmaceuticals", "market": "US", "exchange": "NASDAQ"},
]

SAMPLE_ADR = [
    {"symbol": "BABA", "name": "Alibaba Group (ADR)", "market": "US", "exchange": "NYSE", "is_adr": True},
    {"symbol": "JD", "name": "JD.com (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "PDD", "name": "PDD Holdings (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "BIDU", "name": "Baidu Inc. (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "NIO", "name": "NIO Inc. (ADR)", "market": "US", "exchange": "NYSE", "is_adr": True},
    {"symbol": "XPEV", "name": "XPeng Inc. (ADR)", "market": "US", "exchange": "NYSE", "is_adr": True},
    {"symbol": "LI", "name": "Li Auto Inc. (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "TCOM", "name": "Trip.com Group (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "TME", "name": "Tencent Music (ADR)", "market": "US", "exchange": "NYSE", "is_adr": True},
    {"symbol": "FUTU", "name": "Futu Holdings (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "TIGR", "name": "UP Fintech (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "MOMO", "name": "Hello Group (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "VNET", "name": "VNET Group (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "DOYU", "name": "DouYu International (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "HUYA", "name": "HUYA Inc. (ADR)", "market": "US", "exchange": "NYSE", "is_adr": True},
    {"symbol": "NOAH", "name": "Noah Holdings (ADR)", "market": "US", "exchange": "NYSE", "is_adr": True},
    {"symbol": "BZUN", "name": "Baozun Inc. (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "KC", "name": "Kingsoft Cloud (ADR)", "market": "US", "exchange": "NASDAQ", "is_adr": True},
    {"symbol": "LSPD", "name": "Lightspeed Commerce (ADR)", "market": "US", "exchange": "NYSE", "is_adr": True},
    {"symbol": "SHOP", "name": "Shopify Inc. (ADR)", "market": "US", "exchange": "NYSE", "is_adr": True},
]


def get_jp_universe(use_real: bool = True) -> List[Dict]:
    if use_real:
        try:
            url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                df = pd.read_excel(io.BytesIO(resp.content), dtype=str)
                df.columns = df.columns.str.strip()
                col_code = next((c for c in df.columns if "コード" in c or "code" in c.lower()), None)
                col_name = next((c for c in df.columns if "銘柄名" in c or "name" in c.lower()), None)
                col_market = next((c for c in df.columns if "市場" in c or "market" in c.lower()), None)
                if col_code and col_name:
                    result = []
                    for _, row in df.iterrows():
                        code = str(row[col_code]).strip().zfill(4)
                        name = str(row[col_name]).strip() if col_name else ""
                        market_name = str(row[col_market]).strip() if col_market else "TSE"
                        symbol = f"{code}.T"
                        result.append({"symbol": symbol, "name": name, "market": "JP", "exchange": market_name})
                    if result:
                        return result
        except Exception as e:
            print(f"JPX real data failed: {e}")
    return SAMPLE_JP


def get_us_universe(use_real: bool = True) -> List[Dict]:
    if use_real:
        try:
            url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=5000&exchange=nasdaq&download=true"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                rows = data.get("data", {}).get("rows", [])
                result = []
                for row in rows:
                    symbol = row.get("symbol", "").strip()
                    name = row.get("name", "").strip()
                    if symbol:
                        result.append({"symbol": symbol, "name": name, "market": "US", "exchange": "NASDAQ"})
                if result:
                    return result
        except Exception as e:
            print(f"NASDAQ real data failed: {e}")
    return SAMPLE_US


def get_adr_universe() -> List[Dict]:
    return SAMPLE_ADR


def get_universe(markets: List[str], include_adr: bool = False, use_real: bool = True) -> List[Dict]:
    universe = []
    seen = set()

    if "JP" in markets:
        for s in get_jp_universe(use_real):
            if s["symbol"] not in seen:
                seen.add(s["symbol"])
                universe.append(s)

    if "US" in markets:
        for s in get_us_universe(use_real):
            if s["symbol"] not in seen:
                seen.add(s["symbol"])
                s.setdefault("is_adr", False)
                universe.append(s)

    if include_adr:
        for s in get_adr_universe():
            if s["symbol"] not in seen:
                seen.add(s["symbol"])
                universe.append(s)

    return universe
