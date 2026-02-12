param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$FrontendUrl = "http://localhost:8501",
    [string]$DocsUrl = "http://localhost:8000/api/v1/documents",
    [string]$CasesUrl = "http://localhost:8000/api/v1/cases"
)

$ErrorActionPreference = "Stop"

Write-Host "Smoke test Evidence Crusher" -ForegroundColor Cyan

function Assert-Ok($resp, $name) {
    if ($resp.StatusCode -lt 200 -or $resp.StatusCode -ge 300) {
        throw "$name failed with status $($resp.StatusCode)"
    }
}

Write-Host "1) Ping API..."
$ping = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/ping"
Assert-Ok $ping "Ping"

Write-Host "2) Create case..."
$casePayload = @{ title = "SmokeTest"; description = "Smoke" } | ConvertTo-Json
$caseResp = Invoke-WebRequest -UseBasicParsing -Uri $CasesUrl -Method Post -ContentType "application/json" -Body $casePayload
Assert-Ok $caseResp "Create case"
$caseId = (ConvertFrom-Json $caseResp.Content).id

Write-Host "3) Upload document..."
$filePath = Join-Path $PSScriptRoot "sample.pdf"
if (-not (Test-Path $filePath)) {
    throw "Missing sample.pdf at $filePath"
}
$form = @{
    case_id = $caseId
    doc_type = "DETECTANDO..."
    file = Get-Item $filePath
}
$docResp = Invoke-WebRequest -UseBasicParsing -Uri "$DocsUrl/" -Method Post -Form $form
Assert-Ok $docResp "Upload document"
$docId = (ConvertFrom-Json $docResp.Content).document_id

Write-Host "4) Enqueue process..."
$proc = Invoke-WebRequest -UseBasicParsing -Uri "$DocsUrl/$docId/process" -Method Post
Assert-Ok $proc "Process enqueue"

Write-Host "5) Enqueue embed..."
$emb = Invoke-WebRequest -UseBasicParsing -Uri "$DocsUrl/$docId/embed" -Method Post
Assert-Ok $emb "Embed enqueue"

Write-Host "6) Fetch file..."
$fileResp = Invoke-WebRequest -UseBasicParsing -Uri "$DocsUrl/$docId/file" -Method Get
Assert-Ok $fileResp "Fetch file"

Write-Host "7) Frontend check..."
$front = Invoke-WebRequest -UseBasicParsing -Uri $FrontendUrl
Assert-Ok $front "Frontend"

Write-Host "Smoke test OK" -ForegroundColor Green
