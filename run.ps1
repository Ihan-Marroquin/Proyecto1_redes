$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "A .env file was created. Add your ANTHROPIC_API_KEY and run this script again."
    exit 1
}

python -m src.chatbot

