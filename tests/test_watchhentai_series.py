import pytest

import pcm.providers.watchhentai_series as series_module


@pytest.mark.asyncio
async def test_discover_episodes_includes_current_and_series_links(monkeypatch):
    episode_url = "https://watchhentai.net/videos/show-episode-3/"
    series_url = "https://watchhentai.net/series/show/"
    episode_html = """
    <html><head><title>Show Episode 3</title></head><body>
      <a href="/series/show/">Show series</a>
      <a class="tv-ep-card-link" href="/videos/show-episode-2/" title="Episode 2">Episode 2</a>
      <a class="tv-ep-card-link" href="/videos/show-episode-3/" title="Episode 3">Episode 3</a>
    </body></html>
    """
    series_html = """
    <html><body>
      <a class="tv-ep-card-link" href="/videos/show-episode-1/" title="Episode 1">Episode 1</a>
      <a class="tv-ep-card-link" href="/videos/show-episode-2/" title="Episode 2">Episode 2</a>
      <a class="tv-ep-card-link" href="/videos/show-episode-3/" title="Episode 3">Episode 3</a>
    </body></html>
    """

    async def fake_get_text(client, url, referer=None):
        if url == episode_url:
            return episode_html
        if url == series_url:
            return series_html
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(series_module, "_get_text", fake_get_text)
    episodes = await series_module.discover_episodes(episode_url)

    assert [item["url"] for item in episodes] == [
        episode_url,
        "https://watchhentai.net/videos/show-episode-2/",
        "https://watchhentai.net/videos/show-episode-1/",
    ]


@pytest.mark.asyncio
async def test_discover_episodes_rejects_other_hosts():
    with pytest.raises(Exception, match="Only WatchHentai"):
        await series_module.discover_episodes("https://example.com/videos/show-episode-1/")
