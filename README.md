# PCM — Private Content Manager

PCM is a private Telegram-controlled download and upload manager. The initial stack is Python, Pyrogram, Google Colab, and InsForge PostgreSQL.

## Current status

The repository includes an owner-only provider-routed download workflow. A supported episode URL resolves only that episode; a supported series URL lists discovered episodes and offers single-episode selection or sequential **Download series**. Single mode lets you choose an episode and quality; series mode selects the highest-labelled quality available for each episode and sends each video to the owner's private Telegram chat. Provider-specific matching, classification, discovery, and resolution are isolated behind adapters in `pcm/providers/`, with URL routing handled by `pcm/providers/registry.py`. WatchHentai is the first registered provider. The resolver parses and decodes `whJwSources`; downloads use redirect/DNS checks, streaming, size limits, and progress updates. The owner-only `/ytdlp URL` command also invokes yt-dlp for supported video sites, reports download progress, and sends the resulting video to the owner's private chat (limited to about 1.9 GiB). Phase 1 adds a PostgreSQL-backed job repository (`pcm/jobs/repository.py`) with atomic job claims, attempt tracking, worker leases, restart recovery, pause/cancel/resume/retry state transitions, and per-job destination metadata (`telegram` and/or `gofile`). The SQL migration is in `sql/pcm_jobs.sql`. Phase 2 connects directly sent supported episode URLs to the persistent queue, starts a polling worker with lease renewal and expired-job recovery, and adds `/jobs`, `/pause ID`, `/resume ID`, `/cancel ID`, and `/retry ID`. These commands currently control queued episode jobs; existing inline quality selections, series batches, and `/ytdlp` still use their original direct execution paths. Pause currently applies to queued jobs, while running cancellation is cooperative and checked by the worker heartbeat. GoFile transfer execution is not yet implemented. Live website resolution and actual media downloads have not yet been verified against the live site.

## Requirements

- Python 3.11+
- A Telegram bot token from BotFather
- Telegram API ID and API hash from Telegram's developer portal
- An InsForge project with PostgreSQL access enabled
- Google Colab for the initial worker runtime

## Local setup

1. Clone this repository.
2. Create a virtual environment and activate it.
3. Install dependencies and development tools:

   `pip install -r requirements.txt`

   `pip install -e ".[dev]"`

4. Copy `.env.example` to `.env` and fill in secrets locally.
5. Run tests with `pytest`.
6. Start the owner-only starter bot with `python -m pcm` after all required settings are configured.

Never commit `.env`, Pyrogram session files, API keys, cookies, or downloaded media. In Colab, use Colab Secrets instead of putting credentials in notebook cells.

## Design rules

- Keep modules focused and small.
- Validate every URL and redirect before fetching it.
- Keep Telegram handlers separate from resolver, job, and storage logic.
- Store durable job state in InsForge; Colab's local filesystem is temporary.
- Use atomic PostgreSQL operations for job leases and state transitions.
- Report worker availability honestly; Colab is not guaranteed to stay online.

## Planned milestones

1. Python foundation and tests.
2. Safe URL resolver and provider registry (WatchHentai adapter implemented; additional adapters can be registered).
3. InsForge schema and durable job lifecycle.
4. Owner-only Pyrogram bot, episode discovery, single/all selection, and sequential batch downloads.
5. Telegram and GoFile transfer adapters.
6. Colab bootstrap, resource backpressure, and recovery.


## Adding another provider

1. Create a provider-specific adapter in `pcm/providers/` (for example, `example_adapter.py`). Give it a unique `name` and readable `display_name`, and implement `supports_url(url)`, `classify_url(url)`, `discover_episodes(url)`, and `resolve(episode_url)`.
2. Return `"episode"`, `"series"`, or `"unknown"` from classification. Episode URLs must resolve only the requested episode; series URLs should return a list of `{"url": "...", "title": "..."}` episode records.
3. Keep the resolver result shape compatible with the bot: `{"page": {"title": "..."}, "sources": [{"label": "720p", "url": "https://..."}]}`. Preserve URL validation and validate every redirect before fetching.
4. Register the adapter in `_load_providers()` in `pcm/providers/registry.py`.
5. Add parser/resolver tests and registry-routing tests before using the provider live.

The Telegram UI, quality selection, progress updates, sequential series queue, Telegram upload, and temporary-file cleanup are shared. Site-specific HTML parsing and source resolution belong in the adapter and its provider modules.
