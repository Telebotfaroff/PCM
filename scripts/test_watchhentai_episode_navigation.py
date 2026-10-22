"""Export previous/next links and related episode data from an episode page."""
from __future__ import annotations
import argparse, asyncio, json
from pathlib import Path
import httpx
from pcm.providers.watchhentai import classify_url, parse_html
from pcm.providers.watchhentai_resolver import _get_text
from pcm.providers.watchhentai_series import discover_episodes
from pcm.resolver.url_model import parse_url

async def run(url: str) -> dict:
    parsed = parse_url(url)
    if parsed.hostname.lower() not in {"watchhentai.net", "www.watchhentai.net"} or classify_url(parsed.normalized) != "episode":
        raise ValueError("Provide a WatchHentai episode URL under /videos/...")
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=False, trust_env=False) as client:
        html = await _get_text(client, parsed.normalized)
    page = parse_html(html, parsed.normalized)
    related, error = [], None
    try:
        related = await discover_episodes(parsed.normalized)
    except Exception as exc:
        error = str(exc)[:500]
    return {"input_url": parsed.normalized, "page_type": page.page_type,
            "title": page.title, "canonical_url": page.canonical_url,
            "series_url": page.series_url, "previous_episode_url": page.previous_episode_url,
            "next_episode_url": page.next_episode_url, "thumbnail_url": page.thumbnail_url,
            "primary_player_url": page.primary_player_url,
            "alternate_player_url": page.alternate_player_url,
            "related_episodes": related, "discovery_error": error}

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--output", default="watchhentai-episode-navigation.json")
    args = p.parse_args()
    result = asyncio.run(run(args.url))
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Previous: {result['previous_episode_url'] or 'not found'}")
    print(f"Next: {result['next_episode_url'] or 'not found'}")
    print(f"Wrote {args.output}")

if __name__ == "__main__":
    main()
