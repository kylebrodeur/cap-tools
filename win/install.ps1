# One-time Windows setup for cap-tools beat runner
# Run from Windows PowerShell (admin not required):
#   powershell -File install.ps1

Write-Host "Installing cap-tools beat runner dependencies..."
pip install -r requirements.txt
python -m playwright install chromium
Write-Host "Done. Verify with: python beat_runner.py --check"
