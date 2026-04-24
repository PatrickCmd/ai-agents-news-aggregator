from news_config.loader import load_sources, load_user_profile_yaml


def test_load_sources_returns_expected_shape():
    cfg = load_sources()
    assert cfg.default_hours == 24
    assert cfg.youtube_enabled is True
    assert len(cfg.youtube_channels) > 0
    # Known entry
    assert any(c["name"] == "Anthropic" for c in cfg.raw["youtube"]["channels"])


def test_load_user_profile_yaml_returns_validated_profile():
    profile, identity = load_user_profile_yaml()
    assert identity["email_name"] == "PatrickCmd"
    assert profile.interests.primary[0].startswith("Large Language Models")
