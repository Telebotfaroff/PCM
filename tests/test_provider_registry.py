from pcm.providers.registry import get_provider, get_provider_by_name, registered_providers


def test_registry_routes_watchhentai_urls():
    provider = get_provider("https://watchhentai.net/videos/example-episode/")
    assert provider is not None
    assert provider.name == "watchhentai"
    assert provider.classify_url("https://watchhentai.net/videos/example-episode/") == "episode"
    assert provider.classify_url("https://watchhentai.net/series/example-series/") == "series"


def test_registry_does_not_claim_unregistered_hosts():
    assert get_provider("https://example.com/videos/example-episode/") is None


def test_provider_can_be_retrieved_by_name():
    provider = get_provider_by_name("watchhentai")
    assert provider is not None
    assert provider.name in registered_providers()
