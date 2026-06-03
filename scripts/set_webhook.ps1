# Реєструє Telegram-вебхук на вказаний URL із secret_token із .env.
# Використання:
#   powershell -File scripts/set_webhook.ps1 -Url https://<щось>.trycloudflare.com
#   powershell -File scripts/set_webhook.ps1 -Url https://bot.example.com -Info   # лише показати стан
param(
    [Parameter(Mandatory = $false)][string]$Url,
    [switch]$Info,    # тільки getWebhookInfo
    [switch]$Delete   # видалити вебхук
)

$ErrorActionPreference = 'Stop'
$envPath = Join-Path (Split-Path $PSScriptRoot -Parent) '.env'
if (-not (Test-Path $envPath)) { throw ".env не знайдено: $envPath" }

# Читаємо TOKEN і SECRET з .env
$token = $null; $secret = ''
foreach ($line in Get-Content $envPath) {
    if ($line -match '^\s*TELEGRAM_BOT_TOKEN\s*=\s*(.+?)\s*$')      { $token  = $Matches[1] }
    if ($line -match '^\s*TELEGRAM_WEBHOOK_SECRET\s*=\s*(.*?)\s*$') { $secret = $Matches[1] }
}
if ([string]::IsNullOrWhiteSpace($token)) { throw "TELEGRAM_BOT_TOKEN порожній у .env" }
$base = "https://api.telegram.org/bot$token"

if ($Info) {
    (Invoke-RestMethod "$base/getWebhookInfo").result | Format-List url, has_custom_certificate, pending_update_count, last_error_message, last_error_date
    return
}
if ($Delete) {
    $r = Invoke-RestMethod "$base/deleteWebhook?drop_pending_updates=false"
    Write-Output "deleteWebhook: ok=$($r.ok)"
    return
}
if ([string]::IsNullOrWhiteSpace($Url)) { throw "Вкажи -Url https://...  (або -Info / -Delete)" }

$body = @{ url = "$($Url.TrimEnd('/'))/webhook"; allowed_updates = @('message','edited_message') }
if (-not [string]::IsNullOrWhiteSpace($secret)) { $body.secret_token = $secret }

$r = Invoke-RestMethod "$base/setWebhook" -Method Post -Body ($body | ConvertTo-Json) -ContentType 'application/json'
$secretState = if ($body.ContainsKey('secret_token')) { 'set' } else { 'NONE' }
Write-Output "setWebhook: ok=$($r.ok)  description=$($r.description)"
Write-Output "  url=$($body.url)"
Write-Output "  secret=$secretState"
