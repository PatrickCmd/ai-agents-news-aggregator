from __future__ import annotations

from news_config.loader import load_sources


def test_load_sources_reads_rss_block() -> None:
    cfg = load_sources()
    assert cfg.rss is not None
    assert cfg.rss.enabled is True
    assert cfg.rss.max_concurrent_feeds == 5
    names = [f.name for f in cfg.rss.feeds]
    assert "openai_news" in names
    assert "anthropic_engineering" in names


def test_load_sources_reads_web_search_block() -> None:
    cfg = load_sources()
    assert cfg.web_search is not None
    assert cfg.web_search.enabled is True
    assert cfg.web_search.max_concurrent_sites == 2
    site_names = [s.name for s in cfg.web_search.sites]
    assert "replit_blog" in site_names
    for s in cfg.web_search.sites:
        assert str(s.url).startswith("http")


def test_load_sources_backward_compat_fields_still_present() -> None:
    cfg = load_sources()
    assert cfg.youtube_enabled is True
    assert cfg.openai_enabled is True
    assert cfg.anthropic_enabled is True
