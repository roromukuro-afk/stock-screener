# 短期急騰3000円以下AIスクリーナー

日本株・米国株・ADRを対象に、3000円以下で短期(数日〜4週間)に+20%以上の上昇余地を持つ可能性がある銘柄をスクリーニング・分析するWebアプリ。

> ⚠️ **これは投資助言ではありません。** 売買推奨ではありません。AIは「買い推奨」「今買うべき」「必ず上がる」などの断定表現を行いません。最終判断はユーザー自身が行ってください。

---

## 構成

| レイヤ | 技術 |
|---|---|
| フロントエンド | Next.js 16 + TypeScript + Tailwind CSS + Recharts |
| バックエンド | FastAPI + Python 3.12 |
| データ取得 | yfinance + 直接Yahoo Finance API (+ サンプルフォールバック) |
| データベース | SQLite (ローカル) / PostgreSQL (本番) — `DATABASE_URL` で切替 |
| デプロイ | Vercel (frontend) + Render (backend + Postgres) |

---

## ローカル起動

### 1. バックエンド (FastAPI)

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt

# .env.example をコピーして .env を作成
cp .env.example .env

# 起動
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- ヘルス: http://localhost:8000/api/health

### 2. フロントエンド (Next.js)

```bash
cd frontend
npm install

# .env.local.example をコピー
cp .env.local.example .env.local

# 起動
npm run dev
```

- UI: http://localhost:3000/screener

`/screener` 配下にすべてのページがあります（basePath = `/screener`）。
ルート `/` にアクセスすると Vercel デプロイ時は自動で `/screener` にリダイレクトされます。

---

## 主なページ

| URL | 内容 |
|---|---|
| `/screener` | ダッシュボード |
| `/screener/screening` | 全銘柄スクリーニング |
| `/screener/ranking` | 候補ランキング (採用 / 条件付き / 監視) |
| `/screener/excluded` | 除外銘柄一覧 |
| `/screener/exclusion-list` | 除外リスト管理 (CSV/Excel/PDF/TXTアップロード) |
| `/screener/stocks/{symbol}` | 銘柄詳細 (チャート・スコア内訳・AAR) |
| `/screener/aar` | AAR出力(NotebookLM用) |
| `/screener/backtest` | バックテスト追跡 |
| `/screener/settings` | 設定 (DB保存) |
| `/screener/deploy-status` | 公開環境ステータス確認 |

---

## API

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/health` | ヘルスチェック (環境/DB/サンプルモード) |
| GET | `/api/status` | 詳細ステータス |
| GET | `/api/dashboard` | ダッシュボード集計 |
| GET | `/api/universe` | 銘柄ユニバース情報 |
| POST | `/api/screening/run` | スクリーニング開始 (非同期) |
| GET | `/api/screening/progress` | 進捗 |
| GET | `/api/screening/results` | 結果一覧 |
| GET | `/api/screening/exclusions` | 今回の除外結果 |
| GET | `/api/stocks/{symbol}` | 銘柄サマリ |
| GET | `/api/stocks/{symbol}/chart` | 日足チャート |
| GET | `/api/stocks/{symbol}/aar` | AARテキスト |
| GET | `/api/exclusions` | 除外リスト取得 (DB) |
| POST | `/api/exclusions` | 除外追加 |
| DELETE | `/api/exclusions/{symbol}` | 除外削除 |
| POST | `/api/exclusions/upload` | ファイルから候補抽出 |
| POST | `/api/exclusions/bulk` | 候補を一括登録 |
| GET | `/api/export/csv` | スクリーニング結果CSV |
| GET | `/api/export/excel` | Excel (シート別) |
| GET | `/api/export/aar/csv` | AAR一括テキスト |
| POST | `/api/backtest/run` | バックテスト実行 |
| GET | `/api/backtest/results` | バックテスト結果 |
| GET | `/api/settings` | 設定取得 |
| POST | `/api/settings/bulk` | 設定一括保存 |
| GET | `/api/settings/deploy-status` | 公開ステータス |

---

## 全銘柄スクリーニングの使い方

1. `/screener/screening` を開く
2. 対象市場(日本株/米国株/ADR)・価格上限・最低出来高・データモードを設定
3. 「全銘柄スクリーニング実行」を押す
4. 進捗バーが表示される。完了するとテーブルに結果が並ぶ
5. CSV / Excel ボタンでエクスポート

### 価格条件

- 日本株: 1株 3000円以下
- 米国株/ADR: 直近株価 × USD/JPYレート で 3000円以下

### ハード除外条件

- 3000円超 / 価格不明 / 出来高極端に少ない
- 直近20日で2倍以上、25MA乖離率 +80%以上
- 上値余地 +20%未満、支持線割れ
- 除外リスト登録済み

### スコア (100点満点)

| 項目 | 点数 |
|---|---:|
| +20%以上の上値余地 | 15 |
| 未来急騰予兆 | 15 |
| チャート構造 | 15 |
| 出来高サイクル | 15 |
| 材料・テーマの芯 | 10 |
| 需給の軽さ | 10 |
| アーキタイプ重なり | 10 |
| リスク管理しやすさ | 10 |

| スコア | 判定 |
|---|---|
| 85+ | 採用候補 |
| 75〜84 | 条件付き候補 |
| 65〜74 | 監視候補 |
| <65 | 通常ランキング非表示 |

---

## 出来高サイクル / チャートサイクル

**出来高:** 先行大商い → 売り枯れ → 価格維持 → 再点火
**チャート:** 支持線死守 → 安値切り上げ / 底固め → 収縮 → ブレイク / 再点火

各銘柄に状態タグが付与されます。

---

## 除外リストの使い方

1. `/screener/exclusion-list` を開く
2. CSV/Excel/PDF/TXTファイルをアップロード
3. 抽出された候補を確認し、登録する銘柄を選択
4. 「除外リストに登録」を押す
5. スクリーニング実行時、`apply_exclusion_list` が ON の場合に自動適用

> ⚠️ PDF抽出は誤認識があるため、必ず確認してから登録してください。

---

## CSV / Excel 出力

- **CSV**: スクリーニング結果ページから「CSV出力」
- **Excel**: 同様に「Excel出力」(シート別: All_Results / Adopted / Conditional / Watch / Excluded / Backtest)
- **AAR一括**: AAR出力ページから「AAR一括ダウンロード」

---

## AAR出力

`/screener/aar` または銘柄詳細ページから NotebookLM 等に貼れる形式で出力。

```
【短期急騰AAR候補メモ】
銘柄：
日付：
市場：
判定：
急騰予兆スコア：
...
```

---

## バックテスト追跡

`/screener/backtest` から「バックテスト実行」。
スクリーニング結果の銘柄について、翌営業日 / 3 / 5 / 10 / 20営業日後の株価と +20%達成率を測定。

---

## 実データモード vs サンプルモード

| モード | 動作 |
|---|---|
| 実データ | Yahoo Finance API から直接取得 → yfinance フォールバック |
| サンプル | 銘柄ごとに再現可能な合成データ(チャートパターン・出来高サイクルを含む) |

本番でAPIが遅い・失敗する場合は、設定ページから `sample_mode: true` に切り替えて挙動を確認できます。

---

## 環境変数

### バックエンド (`backend/.env`)

```
APP_ENV=local
DATABASE_URL=sqlite:///./screener.db
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
YFINANCE_ENABLED=true
SAMPLE_MODE=false
DEFAULT_USDJPY=155
```

### フロントエンド (`frontend/.env.local`)

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_APP_ENV=local
```

---

## 公開デプロイ

[DEPLOY.md](./DEPLOY.md) を参照してください。

---

## 今後の拡張案

- 実材料データ取得(EDGAR / TDnet)
- 分足/VWAPによるGU判定の精緻化
- 候補銘柄のメール/Slack通知
- ユーザーごとの除外リスト・ログイン
- 過去日付スクリーニング (ヒストリカルバックテスト)
- AAR記入用の手入力テンプレート保存

---

## 免責

このサイトは投資助言・売買推奨ではありません。教育・分析・パターン学習目的のツールです。最終判断はユーザー自身が行ってください。
