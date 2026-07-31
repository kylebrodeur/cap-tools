# One-time Windows setup for cap-tools beat runner
# Run from Windows PowerShell (admin not required):
#   powershell -File install.ps1

Write-Host "Installing cap-tools beat runner dependencies..."
pip install -r requirements.txt
python -m playwright install chromium

Write-Host "Installing capt package (editable) so beat_runner_entry.py can import capt.record.beat..."
$repoRoot = Split-Path $PSScriptRoot -Parent
pip install -e $repoRoot

Write-Host "Done. Verify with: python beat_runner_entry.py --help"
