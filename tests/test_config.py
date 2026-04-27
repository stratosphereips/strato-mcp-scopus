"""Tests for configuration loading."""
import pytest
from scopus_mcp.config import Config, ConfigurationError, load_config


def test_config_defaults():
    """Test default configuration values."""
    config = Config(api_key="test_key")

    assert config.api_key == "test_key"
    assert config.api_base_url == "https://api.elsevier.com"
    assert config.content_key is None
    assert config.default_limit == 25


def test_config_custom_values():
    """Test custom configuration values."""
    config = Config(
        api_key="test_key",
        api_base_url="https://custom.api.com",
        content_key="content_key",
        default_limit=50,
    )

    assert config.api_base_url == "https://custom.api.com"
    assert config.content_key == "content_key"
    assert config.default_limit == 50


def test_config_invalid_limit():
    """Test that invalid limit raises error."""
    with pytest.raises(ConfigurationError):
        Config(api_key="test_key", default_limit=0)

    with pytest.raises(ConfigurationError):
        Config(api_key="test_key", default_limit=-1)


def test_api_base_url_trailing_slash_stripped():
    """Test that trailing slashes are stripped from base URL."""
    config = Config(api_key="test_key", api_base_url="https://api.elsevier.com/")

    assert config.api_base_url == "https://api.elsevier.com"
