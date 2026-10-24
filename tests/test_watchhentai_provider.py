from pathlib import Path

from pcm.providers.watchhentai import classify_url, parse_file, parse_html


def test_parse_saved_watchhentai_page() -> None:
    fixture = Path(__file__).parent / "fixtures" / "watchhentai-episode.html"
    page = parse_file(fixture)

    assert page.title == "The Lonely Snow Widow and the Cursed Ring – Episode 3 Uncensored"
    assert page.canonical_url == (
        "https://watchhentai.net/videos/"
        "the-lonely-snow-widow-and-the-cursed-ring-episode-3-uncensored-id-01/"
    )
    assert page.page_type == "episode"
    assert page.primary_player_url == "https://watchhentai.net/player/71422/1/mp4/"
    assert page.alternate_player_url == "https://watchhentai.net/player-alt/71422/1/mp4/"
    assert page.player_id == "71422"
    assert page.thumbnail_url is not None
    assert page.preview_images
    assert page.series_url == (
        "https://watchhentai.net/series/the-lonely-snow-widow-and-the-cursed-ring-id-01/"
    )


def test_parse_relative_urls_and_basic_metadata() -> None:
    html = """
    <html><head>
      <meta name="description" content="A sample page">
      <link rel="canonical" href="/videos/sample/">
    </head><body>
      <h1 class="module-title">Sample Episode</h1>
      <iframe data-primary-player-url="/player/123/1/mp4/"
              data-alternate-player-url="/player-alt/123/1/mp4/"></iframe>
      <nav><div class="item item-prev"><a href="/videos/previous/" aria-label="Previous episode">Previous</a></div></nav>
      <div class="item item-all"><a href="/series/sample/">All Episodes</a></div>
      <a href="/genre/action/" title="Action Hentai">Action</a>
    </body></html>
    """
    page = parse_html(html, "https://watchhentai.net/videos/sample/")

    assert page.title == "Sample Episode"
    assert page.description == "A sample page"
    assert page.canonical_url == "https://watchhentai.net/videos/sample/"
    assert page.page_type == "episode"
    assert page.primary_player_url == "https://watchhentai.net/player/123/1/mp4/"
    assert page.alternate_player_url == "https://watchhentai.net/player-alt/123/1/mp4/"
    assert page.previous_episode_url == "https://watchhentai.net/videos/previous/"
    assert page.series_url == "https://watchhentai.net/series/sample/"
    assert page.genres == []


def test_classify_watchhentai_url_examples() -> None:
    assert classify_url(
        "https://watchhentai.net/series/the-lonely-snow-widow-and-the-cursed-ring-id-01/"
    ) == "series"
    assert classify_url(
        "https://watchhentai.net/videos/the-lonely-snow-widow-and-the-cursed-ring-episode-1-uncensored-id-01/"
    ) == "episode"
    assert classify_url("https://watchhentai.net/") == "unknown"
    assert classify_url("https://example.com/series/sample/") == "unknown"
    assert classify_url("not a URL") == "unknown"


def test_series_page_extracts_deduplicated_audio_variants() -> None:
    html = """
    <html><head>
      <link rel="canonical" href="/series/sample/">
      <title>Sample Series</title>
    </head><body>
      <ul class="episodios">
        <li data-audio="subbed">
          <a class="tv-ep-card-link" href="/videos/sample-episode-1/" title="Episode 1 Watch Hentai">
            <img data-src="/uploads/1.jpg"><span class="eptitle">Episode 1</span>
            <span class="date">Oct. 03, 2026</span>
          </a>
        </li>
        <li data-audio="dubbed" hidden>
          <a class="tv-ep-card-link" href="/videos/sample-episode-1-dubbed/" title="Episode 1 (Dubbed) Watch Hentai">
            <img data-src="/uploads/1-dubbed.jpg"><span class="eptitle">Episode 1 (Dubbed)</span>
          </a>
        </li>
        <li data-audio="subbed">
          <a class="tv-ep-card-link" href="/videos/sample-episode-1/" title="Episode 1 Watch Hentai">Duplicate</a>
        </li>
      </ul>
      <section class="related"><a href="/series/unrelated/">Related series</a></section>
    </body></html>
    """
    page = parse_html(html, "https://watchhentai.net/series/sample/")

    assert page.page_type == "series"
    assert page.series_url == "https://watchhentai.net/series/sample/"
    assert len(page.episodes) == 2
    assert [episode.audio_type for episode in page.episodes] == ["subbed", "dubbed"]
    assert page.episodes[0].episode_number == 1
    assert page.episodes[0].thumbnail_url == "https://watchhentai.net/uploads/1.jpg"
    assert page.episodes[0].release_date == "Oct. 03, 2026"
