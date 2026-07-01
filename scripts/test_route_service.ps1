# Simulate hi then service selection (e.g. 4 = Electrical) — same as phone would do via webhook.
# Requires uvicorn on :8000. For real phone, Twilio webhook must point to your tunnel/Render URL.

param(
    [string]$ServiceNumber = "4"
)

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$EnvFile = Join-Path $ProjectRoot ".env"
$From = "whatsapp:+918639097638"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*TEST_WHATSAPP_FROM=(.+)\s*$') { $From = $matches[1].Trim() }
    }
}



$Url = "http://localhost:8000/webhook/whatsapp"
function Send([string]$Body) {
    $r = Invoke-WebRequest -Uri $Url -Method POST -Body @{ From = $From; Body = $Body }
    Write-Host "-> $Body (HTTP $($r.StatusCode))"
}

Write-Host "Step 1: hi (Nova menu)"
Send "hi"
Start-Sleep -Seconds 3
Write-Host "Step 2: service $ServiceNumber"
Send $ServiceNumber
Write-Host "Check uvicorn logs for SERVICE_SELECTED + Twilio queued. Check WhatsApp for Vivek handoff + name question."
