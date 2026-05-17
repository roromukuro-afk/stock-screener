# DEPLOY.md — 公開デプロイ手順

このアプリは以下の構成で外部公開できます:

| レイヤ | 推奨ホスティング | 代替 |
|---|---|---|
| フロントエンド (Next.js) | **Vercel** | Cloudflare Pages, Netlify |
| バックエンド (FastAPI) | **Render** | Railway, Fly.io |
| データベース | **Render PostgreSQL** | Supabase, Neon |

公開後は以下のURLでアクセスできるようになります:

```
https://your-frontend.vercel.app/screener
https://your-frontend.vercel.app/screener/screening
https://your-frontend.vercel.app/screener/ranking
https://your-frontend.vercel.app/screener/stocks/7203.T
...
```

スマホ・別PCからも公開URLでアクセス可能です。

---

## 全体像

```
[ ブラウザ ] ───https───> [ Vercel: Next.js (frontend) ]
                                        │
                                        │ NEXT_PUBLIC_API_BASE_URL
                                        ▼
                            [ Render: FastAPI (backend) ]
                                        │
                                        ▼
                        [ Render PostgreSQL (DB) ]
```

---

## ステップ1: GitHubへリポジトリをプッシュ

```bash
cd C:/Users/rorom/stock-screener
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<YOUR_GH>/stock-screener.git
git push -u origin main
```

`.gitignore` に `.env` や `node_modules/` が含まれていることを確認してください。

---

## ステップ2: バックエンド+DBをRenderにデプロイ

### 方法A: render.yaml で一括デプロイ (推奨)

1. https://render.com にログイン
2. **New +** → **Blueprint**
3. GitHubリポジトリを選択
4. `render.yaml` が自動検出される → そのまま **Apply**
5. PostgreSQL DB + Web Service が作成される
6. 完了後、Web Service の `ALLOWED_ORIGINS` 環境変数を後で更新

### 方法B: 手動セットアップ

#### B-1. PostgreSQL DB を作成

1. Render Dashboard → **New +** → **PostgreSQL**
2. Name: `stock-screener-db`, Plan: Free
3. 作成後、**Internal Connection String** をコピー

#### B-2. Web Service を作成

1. **New +** → **Web Service** → GitHubリポジトリ選択
2. 設定:
   - **Root Directory**: `backend`
   - **Build Command**: `pip install -r requirements.txt && pip install psycopg2-binary`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. 環境変数:
   ```
   APP_ENV=production
   DATABASE_URL=<上記のConnection String>
   ALLOWED_ORIGINS=https://your-frontend.vercel.app
   ALLOWED_ORIGIN_REGEX=https://.*\.vercel\.app
   YFINANCE_ENABLED=true
   SAMPLE_MODE=false
   DEFAULT_USDJPY=155
   PYTHONUTF8=1
   ```
4. デプロイ完了後、URLをメモ: `https://stock-screener-backend.onrender.com`

#### B-3. 動作確認

```bash
curl https://stock-screener-backend.onrender.com/api/health
```

`{"status":"ok",...}` が返ればOK。

> ⚠️ Render Free プランは15分非アクセスでスリープします。最初のリクエストで数十秒かかることがあります。

---

## ステップ3: フロントエンドをVercelにデプロイ

1. https://vercel.com にログイン
2. **Add New** → **Project** → GitHubリポジトリを選択
3. 設定:
   - **Root Directory**: `frontend`
   - **Framework**: Next.js (自動検出)
4. **Environment Variables**:
   ```
   NEXT_PUBLIC_API_BASE_URL=https://stock-screener-backend.onrender.com
   NEXT_PUBLIC_APP_ENV=production
   ```
5. **Deploy** を押す
6. 完了後、URL: `https://your-frontend.vercel.app`

### Vercelデプロイ後の確認

- `https://your-frontend.vercel.app` → `/screener` に自動リダイレクト (vercel.json設定済み)
- `https://your-frontend.vercel.app/screener` でダッシュボード表示
- `/screener/deploy-status` ページで「✅ 接続OK」を確認

---

## ステップ4: CORS設定の最終調整

Render側のバックエンドの `ALLOWED_ORIGINS` を、Vercelの本番URLに更新:

```
ALLOWED_ORIGINS=https://your-frontend.vercel.app
```

Vercel previewデプロイURL (`*.vercel.app`) を全て許可したい場合:

```
ALLOWED_ORIGIN_REGEX=https://.*\.vercel\.app
```

Renderダッシュボードで環境変数更新後、自動で再デプロイされます。

---

## Supabase / Neon / Railway を使う場合

### Supabase

1. https://supabase.com で New Project
2. Settings → Database → Connection String (URI) をコピー
3. Render側の `DATABASE_URL` に貼り付け (`postgresql://...`)

### Neon

1. https://neon.tech で New Project
2. Connection String をコピー → 同様

### Railway

1. https://railway.app で New → PostgreSQL
2. Variables の `DATABASE_URL` を Render に設定

---

## Cloud Run / Fly.io にバックエンドをデプロイする場合

`backend/Dockerfile` が同梱されているため、そのまま使えます:

```bash
# Fly.io
cd backend
fly launch  # 質問に答えて初期化
fly deploy

# Google Cloud Run
gcloud run deploy stock-screener \
  --source backend \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars APP_ENV=production,DATABASE_URL=...
```

---

## ローカルから公開URLへ切り替える方法

開発中:

```env
# frontend/.env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

公開バックエンドを叩く確認:

```env
# frontend/.env.local
NEXT_PUBLIC_API_BASE_URL=https://stock-screener-backend.onrender.com
```

→ `npm run dev` 再起動。`/screener/deploy-status` で接続状況を確認できます。

---

## docker-compose によるローカル本番相当起動

```bash
docker compose up --build
```

- backend: http://localhost:8000
- frontend: http://localhost:3000/screener
- PostgreSQL: localhost:5432 (user: screener / pw: screener)

---

## よくあるエラー

### CORSエラー (本番)

ブラウザコンソールに `CORS policy: No 'Access-Control-Allow-Origin'` と表示される。

→ バックエンドの `ALLOWED_ORIGINS` にフロント公開URLを追加 (httpsスキーム必須)。

### `/api/health` が失敗

- Render Free がスリープ中 → 数十秒待って再アクセス
- DATABASE_URL が正しいか確認
- Renderログで Python 起動エラーを確認

### Vercelで `/screener` が 404

`next.config.ts` の `basePath: '/screener'` が反映されているか確認。Vercelで再デプロイしてください。

### Postgres接続エラー `psycopg2 not found`

ビルドコマンドに `pip install psycopg2-binary` を必ず追加してください。

### サンプルモードしか動かない

- `YFINANCE_ENABLED=true` か確認
- Render Free 環境はYahoo Finance APIへの接続が一部地域でレート制限されることがあります。
- `/screener/settings` で `sample_mode=true` にすれば合成データで動作確認できます。

---

## デプロイ後のチェックリスト

- [ ] `https://公開フロント/screener` でダッシュボードが表示される
- [ ] `https://公開バック/api/health` が `status: ok` を返す
- [ ] `/screener/deploy-status` で全項目がOK
- [ ] サンプルモードでスクリーニングが完了する
- [ ] 結果が `/screener/ranking` に表示される
- [ ] CSV / Excel 出力ができる
- [ ] DB種別が `postgresql` (本番)になっている

---

## 免責

このサイトは投資助言ではありません。最終判断はユーザー自身が行ってください。
