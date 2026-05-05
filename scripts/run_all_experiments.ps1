$ErrorActionPreference = "Stop"

Set-Location "C:\Users\tariq\Downloads\TUWien\HIEMI2026\iotaEvidenceOracle"

Write-Host "Aggregating result tables..." -ForegroundColor Cyan
python .\harness\src\aggregate_results.py

Write-Host "Generating figures..." -ForegroundColor Cyan
python .\harness\src\make_figures.py

Write-Host "Done. Check harness\results and harness\figures." -ForegroundColor Green