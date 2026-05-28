<#
ローカル surge-20 教師データ構築ヘルパー (本番DB直結)

使い方 (backend ディレクトリから):
  .\scripts\local_training.ps1 status
  .\scripts\local_training.ps1 candidates JP 20
  .\scripts\local_training.ps1 auto-save JP
  .\scripts\local_training.ps1 review
  .\scripts\local_training.ps1 save-training
  .\scripts\local_training.ps1 test          # DB接続テストのみ

秘密情報 (DATABASE_URL / password / CRON_SECRET) は表示しません。
#>
param(
    [Parameter(Mandatory = $true)][string]$Command,
    [string]$Market = "JP",
    [int]$MaxSymbols = 20
)

$ErrorActionPreference = "Stop"
$py = ".\venv\Scripts\python.exe"

# venv確認
if (-not (Test-Path $py)) {
    Write-Host "[ERROR] venv が見つかりません。先に venv\Scripts\activate を実行してください。" -ForegroundColor Red
    exit 1
}

# .env確認
if (-not (Test-Path ".env")) {
    Write-Host "[ERROR] backend/.env が見つかりません。" -ForegroundColor Red
    exit 1
}
$envHasDb = Select-String -Path ".env" -Pattern "^DATABASE_URL=" -Quiet
if (-not $envHasDb) {
    Write-Host "[ERROR] .env に DATABASE_URL がありません。" -ForegroundColor Red
    exit 1
}

# まずDB接続テスト
Write-Host "=== DB接続テスト ===" -ForegroundColor Cyan
& $py scripts/test_db_connection.py --driver psycopg2
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] DB接続に失敗しました。Render DBがresume済みか確認し、1-2分待って再試行してください。" -ForegroundColor Red
    Write-Host "（API経由で実行する場合: python scripts/run_local_training.py $Command --mode api）" -ForegroundColor Yellow
    exit 1
}

if ($Command -eq "test") {
    Write-Host "[OK] DB接続テスト成功" -ForegroundColor Green
    exit 0
}

Write-Host "=== $Command 実行 ===" -ForegroundColor Cyan
switch ($Command) {
    "status"        { & $py scripts/run_local_training.py status --no-init }
    "candidates"    { & $py scripts/run_local_training.py candidates --market $Market --max-symbols $MaxSymbols --no-init }
    "auto-save"     { & $py scripts/run_local_training.py auto-save --market $Market --no-init }
    "review"        { & $py scripts/run_local_training.py review --no-init }
    "save-training" { & $py scripts/run_local_training.py save-training --no-init }
    "full"          { & $py scripts/run_local_training.py full --market $Market --max-symbols $MaxSymbols --no-init }
    default         { Write-Host "[ERROR] 未知のコマンド: $Command (status/candidates/auto-save/review/save-training/full/test)" -ForegroundColor Red; exit 1 }
}
