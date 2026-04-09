# Overpass

CS2 Daily Briefing & Live Alerts – a personal CS2 information aggregator that delivers a curated daily digest via Telegram.

## Setup

```bash
# Clone
git clone https://github.com/lindhammer/overpass.git
cd overpass

# Create venv
python -m venv .venv
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install
pip install -e .

# Configure
cp .env.example .env
# Fill in API keys in .env

# Run
overpass
```

## Configuration

Edit `config.yaml` for watchlist teams, data sources, and scheduling options.
All secrets are loaded from environment variables (see `.env.example`).

## Project Status

**Phase 1 (MVP)** – Collector skeleton in place. Pipeline under construction.

