#!/usr/bin/env sh
set -eu

if [ ! -f ".env" ]; then
  cp ".env.example" ".env"
  echo "A .env file was created. Add your ANTHROPIC_API_KEY and run this script again."
  exit 1
fi

python3 -m src.chatbot

