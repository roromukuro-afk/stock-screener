<#
ローカル直結CLI 対話セットアップ (本番PostgreSQL接続)

Render External Database URL を手作業で .env に書く負担をなくすための対話ツール。
入力URLを正規化して backend/.env.local-training に保存し、接続テストまで実行します。

セキュリティ:
  - URL全文 / password / CRON_SECRET は絶対に表示しない
  - .env.local-training が git 管理下なら中止 (秘密漏洩防止)
  - 秘密情報を git add / push しない

使い方 (backend ディレクトリから):
  .\scripts\setup_local_training.ps1
#>
$ErrorActionPreference = "Stop"

$backendRoot = Split-Path -Parent $PSScriptRoot
$py = Join-Path $backendRoot "venv\Scripts\python.exe"
$envFileName = ".env.local-training"
$envFile = Join-Path $backendRoot $envFileName
$backendUrlDefault = "https://stock-screener-backend-2h6a.onrender.com"

Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host " ローカル直結CLI セットアップ (本番PostgreSQL)" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host @"

Render Dashboard で接続URLを取得してください:
  1. https://dashboard.render.com を開く
  2. 対象の PostgreSQL を選択
  3. [Connections] -> "External Database URL" をコピー
     (Internal ではなく External。postgres:// で始まる文字列)

貼り付けたURLは画面に表示されません (scheme/host等のみ表示)。
"@

# venv確認
if (-not (Test-Path $py)) {
    Write-Host "[ERROR] venv が見つかりません。先に venv\Scripts\activate を実行してください。" -ForegroundColor Red
    exit 1
}

# URL入力 (非表示)
$secure = Read-Host "External Database URL を貼り付けてください" -AsSecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$rawUrl = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
$rawUrl = $rawUrl.Trim()

if ([string]::IsNullOrWhiteSpace($rawUrl)) {
    Write-Host "[ERROR] 空のため中止します。" -ForegroundColor Red
    exit 1
}
if (-not ($rawUrl.StartsWith("postgres://") -or $rawUrl.StartsWith("postgresql://"))) {
    Write-Host "[ERROR] postgres:// または postgresql:// で始まる必要があります。" -ForegroundColor Red
    Write-Host "        (Internal ではなく External Database URL を貼ってください)" -ForegroundColor Yellow
    exit 1
}

# 正規化 (postgres->postgresql, sslmode=require付与) を Python に委譲。URLは引数ではなく環境変数で渡す。
$env:SETUP_RAW_URL = $rawUrl
$normalized = & $py -c @"
import os, sys
sys.path.insert(0, r'$backendRoot')
from app.db_url import normalize_database_url, safe_database_url_info
url = normalize_database_url(os.environ['SETUP_RAW_URL'])
info = safe_database_url_info(url)
sys.stderr.write(f""[DB] scheme={info.get('scheme')} host={info.get('host')} port={info.get('port')} database={info.get('database')} sslmode={info.get('sslmode')} has_password={info.get('has_password')}\n"")
sys.stdout.write(url)
"@
Remove-Item Env:\SETUP_RAW_URL -ErrorAction SilentlyContinue
$rawUrl = $null

if ([string]::IsNullOrWhiteSpace($normalized)) {
    Write-Host "[ERROR] URL正規化に失敗しました。" -ForegroundColor Red
    exit 1
}

# CRON_SECRET (任意)
$secureCron = Read-Host "CRON_SECRET (任意・未使用ならEnterでスキップ)" -AsSecureString
$bstr2 = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureCron)
$cron = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr2)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr2)
$cron = $cron.Trim()

# .gitignore 保証 (リポジトリルート = backend の親)
$repoRoot = Split-Path -Parent $backendRoot
$giPath = Join-Path $repoRoot ".gitignore"
$needed = @(".env", ".env.*", "!.env.example")
$existing = @()
if (Test-Path $giPath) { $existing = Get-Content $giPath }
$missing = $needed | Where-Object { $existing -notcontains $_ }
if ($missing.Count -gt 0) {
    Add-Content -Path $giPath -Value "`n# local training secrets"
    $missing | ForEach-Object { Add-Content -Path $giPath -Value $_ }
    Write-Host "[gitignore] 追記: $($missing -join ', ')" -ForegroundColor Yellow
} else {
    Write-Host "[gitignore] OK (.env / .env.* / !.env.example 済み)" -ForegroundColor Green
}

# .env.local-training 保存
$lines = @(
    "# ローカル直結CLI 専用設定 (git管理しない / 秘密情報)",
    "# setup_local_training.ps1 が生成。手で編集してもよい。",
    "DATABASE_URL=$normalized",
    "LOCAL_TRAINING_CLI=true",
    "BACKEND_URL=$backendUrlDefault"
)
if (-not [string]::IsNullOrWhiteSpace($cron)) { $lines += "CRON_SECRET=$cron" }
Set-Content -Path $envFile -Value $lines -Encoding UTF8
$normalized = $null
$cron = $null
Write-Host "[保存] $envFileName を書き込みました (内容は表示しません)。" -ForegroundColor Green

# git 管理下でないことを確認
Push-Location $backendRoot
git ls-files --error-unmatch $envFileName 2>$null | Out-Null
$tracked = ($LASTEXITCODE -eq 0)
Pop-Location
if ($tracked) {
    Write-Host "[CRITICAL] $envFileName が git 管理下にあります！秘密漏洩の恐れ。" -ForegroundColor Red
    Write-Host "  対処: git rm --cached backend/$envFileName してから .gitignore を確認。" -ForegroundColor Yellow
    exit 1
}
Write-Host "[git] OK ($envFileName は未追跡)" -ForegroundColor Green

# 接続テスト
$env:LOCAL_TRAINING_ENV_FILE = $envFileName
Write-Host "`n=== DB接続テスト ===" -ForegroundColor Cyan
& $py scripts/test_db_connection.py --driver psycopg2 --require-postgres
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[ERROR] DB接続テストに失敗しました。" -ForegroundColor Red
    Write-Host "  Render DBがresume済みか / External URLか / 1-2分待って再試行。" -ForegroundColor Yellow
    exit 1
}

# status
Write-Host "`n=== status ===" -ForegroundColor Cyan
& $py scripts/run_local_training.py status --no-init --require-postgres

# 次コマンド案内
Write-Host "`n$("=" * 60)" -ForegroundColor Cyan
Write-Host " セットアップ完了。以降は以下で実行できます:" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host @"

  `$env:LOCAL_TRAINING_ENV_FILE = "$envFileName"

  python scripts/run_local_training.py candidates --market JP --max-symbols 50 --require-postgres
  python scripts/run_local_training.py auto-save --market JP --require-postgres
  python scripts/run_local_training.py review --require-postgres
  python scripts/run_local_training.py save-training --require-postgres
  python scripts/run_local_training.py full --market JP --max-symbols 50 --require-postgres

これは投資助言ではありません。分析・学習・検証目的です。
"@
