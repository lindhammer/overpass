# Contributing to Overpass

Overpass is a personal hobby project. Contributions are genuinely welcome — bug fixes, resilience improvements, new data sources — but response times may vary, and I can't commit to a review SLA.

---

## Reporting issues

Open a GitHub issue. Please include:

- Your OS and Python version
- The relevant section of your `config.yaml` (redact any secrets — API keys, email addresses, bot tokens)
- The full traceback if there is one

---

## Suggesting features

Open an issue before writing code, especially for anything that touches:

- The HLTV scraper (it's deliberately minimal and already fragile)
- The LLM editorial layer (prompt structure and provider abstraction are in flux)

A quick issue first avoids the situation where you put in work and I've already decided to go a different direction.

---

## Submitting a pull request

1. Fork the repo and create a feature branch off `main`
2. Keep PRs small and focused — one thing per PR
3. Write a clear PR description: what does it do, and why is it the right approach?
4. If your PR fixes an open issue, link it

No need for a formal test suite for every change, but if the thing you changed has existing tests, please make sure they still pass (`pytest`).

---

## Code style

- Python 3.12+
- Follow the patterns already in the file you're editing
- No new dependencies without a discussion first — runtime dependencies especially

Ruff is used for linting and formatting. Run `ruff check .` and `ruff format .` before submitting.

---

## A note on the HLTV scraper

The HLTV collector (`overpass/hltv/`) uses Playwright and breaks regularly. Anti-scrape measures, layout changes, rate limiting — it's all fair game. PRs that make it more resilient (better error handling, smarter retry logic, improved selector hygiene) are especially welcome and will get prioritised.

---

## License

By submitting a pull request, you agree that your contribution will be licensed under [AGPL-3.0-or-later](LICENSE).
