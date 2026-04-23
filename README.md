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
source .venv/bin/activate  # Linux/macOS

# Install
pip install -e .

# HLTV scraping browser
python -m playwright install chromium

# Configure
cp .env.example .env
# Fill in API keys in .env

# Run
overpass
```

HLTV scraping uses Playwright and requires a local Chromium install. Run `python -m playwright install chromium` after installing Python dependencies, or the HLTV collectors will fail when they try to launch the browser.

## Configuration

Edit `config.yaml` for watchlist teams, data sources, and scheduling options.
All secrets are loaded from environment variables (see `.env.example`).

## Project Status

**Phase 1 (MVP)** – Collector skeleton in place. Pipeline under construction.
