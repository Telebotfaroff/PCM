from pathlib import Path

from pcm.providers.watchhentai import parse_file, parse_html


def test_parse_saved_watchhentai_page() -> None:
    fixture = Path(__file__).parents[1] / "providerhtml" / "watchhentai.net-04da56a1.html"
    page = parse_file(fixture)

    assert page.title == "The Lonely Snow Widow and the Cursed Ring – Episode 3 Uncensored"
    assert page.canonical_url == (
        "https://watchhentai.net/videos/"
        "the-lonely-snow-widow-and-the-cursed-ring-episode-3-uncensored-id-01/"
    )
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
      <nav><div class="item item-prev"><a href="/videos/previous/">Previous</a></div></nav>
      <div class="item item-all"><a href="/series/sample/">All Episodes</a></div>
      <a href="/genre/action/" title="Action Hentai">Action</a>
    </body></html>
    """
    page = parse_html(html, "https://watchhentai.net/videos/sample/")

    assert page.title == "Sample Episode"
    assert page.description == "A sample page"
    assert page.canonical_url == "https://watchhentai.net/videos/sample/"
    assert page.primary_player_url == "https://watchhentai.net/player/123/1/mp4/"
    assert page.alternate_player_url == "https://watchhentai.net/player-alt/123/1/mp4/"
    assert page.previous_episode_url == "https://watchhentai.net/videos/previous/"
    assert page.series_url == "https://watchhentai.net/series/sample/"
    assert page.genres == []
