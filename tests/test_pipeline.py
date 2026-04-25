from datetime import date

import pytest

from overpass.delivery.html import briefing_path_for_date
from overpass.pipeline import run_daily_briefing


def test_briefing_path_for_date_uses_static_output_directory():
    path = briefing_path_for_date(date(2026, 4, 26))

    assert path.parts[-3:] == ("output", "briefings", "2026-04-26.html")


@pytest.mark.asyncio
async def test_run_daily_briefing_skips_existing_file_when_not_forced(monkeypatch, tmp_path):
    target_date = date(2026, 4, 26)
    existing_path = tmp_path / "output" / "briefings" / "2026-04-26.html"
    existing_path.parent.mkdir(parents=True)
    existing_path.write_text("existing", encoding="utf-8")

    async def fail_run_collectors():
        raise AssertionError("collectors should not run when existing output is not forced")

    class FakeConfig:
        web_base_url = "https://briefs.example.com"

    monkeypatch.setattr("overpass.pipeline.briefing_path_for_date", lambda _date: existing_path)
    monkeypatch.setattr("overpass.pipeline.load_config", lambda: FakeConfig())
    monkeypatch.setattr("overpass.pipeline.run_collectors", fail_run_collectors)

    result = await run_daily_briefing(target_date, force=False)

    assert result.path == existing_path
    assert result.skipped is True
    assert result.briefing_url == "https://briefs.example.com/briefings/2026-04-26.html"


@pytest.mark.asyncio
async def test_run_daily_briefing_forced_rerun_ignores_existing_file(monkeypatch, tmp_path):
    target_date = date(2026, 4, 26)
    existing_path = tmp_path / "output" / "briefings" / "2026-04-26.html"
    existing_path.parent.mkdir(parents=True)
    existing_path.write_text("existing", encoding="utf-8")
    calls = {"collectors": 0, "telegram": 0}

    class FakeConfig:
        web_base_url = "https://briefs.example.com"

        class llm:
            default_provider = "gemini"
            providers = {"gemini": type("Provider", (), {"model": "fake", "api_key_env": "fake-key"})()}

    class FakeDigest:
        summary_line = "Forced briefing"

    async def fake_run_collectors():
        calls["collectors"] += 1
        return []

    async def fake_generate_digest(items, provider):
        assert items == []
        return FakeDigest()

    async def fake_send_digest_notification(summary_line, briefing_url):
        calls["telegram"] += 1
        assert summary_line == "Forced briefing"
        assert briefing_url == "https://briefs.example.com/briefings/2026-04-26.html"

    monkeypatch.setattr("overpass.pipeline.briefing_path_for_date", lambda _date: existing_path)
    monkeypatch.setattr("overpass.pipeline.load_config", lambda: FakeConfig())
    monkeypatch.setattr("overpass.pipeline.run_collectors", fake_run_collectors)
    monkeypatch.setattr("overpass.pipeline.GeminiProvider", lambda model, api_key: object())
    monkeypatch.setattr("overpass.pipeline.generate_digest", fake_generate_digest)
    monkeypatch.setattr("overpass.pipeline.get_primary_for", lambda _date: None)
    monkeypatch.setattr("overpass.pipeline.render_briefing", lambda *args, **kwargs: "<html>new</html>")
    monkeypatch.setattr("overpass.pipeline.save_briefing", lambda html, _date: existing_path)
    monkeypatch.setattr("overpass.pipeline.send_digest_notification", fake_send_digest_notification)

    result = await run_daily_briefing(target_date, force=True)

    assert result.path == existing_path
    assert result.skipped is False
    assert result.briefing_url == "https://briefs.example.com/briefings/2026-04-26.html"
    assert calls == {"collectors": 1, "telegram": 1}
