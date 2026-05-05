$ErrorActionPreference = "Stop"

$Root = "C:\Users\tariq\Downloads\TUWien\HIEMI2026\iotaEvidenceOracle"
Set-Location $Root

Write-Host "Running baseline experiments..." -ForegroundColor Cyan
python .\harness\src\run_baseline.py --env testnet --windows 50 --sensor-counts 2 4 8 16 32

Write-Host "Running Design B finalization experiments..." -ForegroundColor Cyan
python .\harness\src\run_finalization.py --env testnet --windows 50 --sensor-counts 2 4 8 16 32

Write-Host "Running fault injection experiments..." -ForegroundColor Cyan
python .\harness\src\run_fault_injection.py --env testnet --windows 10 --sensor-counts 2 4 8 16 32

Write-Host "Aggregating tables..." -ForegroundColor Cyan
python .\harness\src\aggregate_results.py

Write-Host "Generating figures..." -ForegroundColor Cyan
python .\harness\src\make_figures.py

Write-Host "Done. Check harness/results/ and harness/figures/." -ForegroundColor Green