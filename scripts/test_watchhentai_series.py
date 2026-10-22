"""Export episode URLs and metadata from a WatchHentai series page."""
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
    if parsed.hostname.lower() not in {"watchhentai.net", "www.watchhentai.net"} or classify_url(parsed.normalized) != "series":
        raise ValueError("Provide a WatchHentai series URL under /series/...")
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=False, trust_env=False) as client:
        html = await _get_text(client, parsed.normalized)
    page = parse_html(html, parsed.normalized)
    discovered = await discover_episodes(parsed.normalized)
    episodes = [{
        "title": e.title, "url": e.url, "audio_type": e.audio_type,
        "episode_number": e.episode_number, "thumbnail_url": e.thumbnail_url,
        "release_date": e.release_date,
    } for e in page.episodes]
    if not episodes:
        episodes = [{"title": e["title"], "url": e["url"], "audio_type": e.get("audio_type"),
                     "episode_number": None, "thumbnail_url": None, "release_date": None}
                    for e in discovered]
    return {"input_url": parsed.normalized, "page_type": page.page_type,
            "series_url": page.series_url or page.canonical_url, "title": page.title,
            "description": page.description, "thumbnail_url": page.thumbnail_url,
            "episode_count": len(episodes), "episodes": episodes}

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--output", default="watchhentai-series-result.json")
    args = p.parse_args()
    result = asyncio.run(run(args.url))
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Extracted {result['episode_count']} episode entries; wrote {args.output}")

if __name__ == "__main__":
    main()
