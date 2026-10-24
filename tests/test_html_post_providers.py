from pcm.providers.html_post import parse_post_html
from pcm.providers.registry import get_provider, get_provider_by_name, registered_providers


URLS = {
    "hanime_red": "https://hanime.red/mahou-touki-lilustear-episode-4",
    "porn4days": "https://porn4days.pw/video/example-post",
    "movie4days": "https://movie4days.com/video/example-post",
    "tube321": "https://321tube.com/video/example-post",
    "bestporn4free": "https://bestporn4free.com/evil-angel-luna-bunny/",
    "netfapx": "https://netfapx.com/2020/06/share/",
    "analbabes": "https://analbabes.porn/video/example-post/",
}


def test_each_new_host_routes_to_its_own_provider():
    for name, url in URLS.items():
        provider = get_provider(url)
        assert provider is not None
        assert provider.name == name
        assert provider.classify_url(url) == "episode"
        assert get_provider_by_name(name) is provider


def test_cloudflare_affected_hanime1_is_not_registered():
    assert get_provider("https://hanime1.me/watch?v=408297") is None


def test_unregistered_hosts_are_not_claimed():
    assert get_provider("https://example.com/video/post") is None


def test_new_providers_are_additive_and_keep_watchhentai():
    names = registered_providers()
    assert "watchhentai" in names
    assert all(name in names for name in URLS)
    assert len(names) == 8


def test_parse_post_html_extracts_metadata_direct_media_and_embeds():
    html = """
    <!doctype html>
    <html>
      <head>
        <title>Generic site title</title>
        <meta property="og:title" content="Specific post title">
        <meta property="og:description" content="Post description">
        <meta property="og:url" content="https://example.test/post/42">
        <meta property="og:image" content="/images/post.webp">
        <meta property="video:duration" content="2147">
      </head>
      <body>
        <h1>Fallback title</h1>
        <iframe src="https://player.example.test/embed/42"></iframe>
        <video><source src="/media/42.mp4" type="video/mp4"></video>
      </body>
    </html>
    """
    page = parse_post_html(html, "https://example.test/post/42")
    assert page.title == "Specific post title"
    assert page.description == "Post description"
    assert page.canonical_url == "https://example.test/post/42"
    assert page.thumbnail_url == "https://example.test/images/post.webp"
    assert page.duration_seconds == 2147
    assert page.embed_urls == ["https://player.example.test/embed/42"]
    assert page.media_urls == [{
        "url": "https://example.test/media/42.mp4",
        "label": "video/mp4",
        "type": "video/mp4",
    }]
