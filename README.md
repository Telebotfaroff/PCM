# PCM — Private Content Manager

PCM is a private Telegram-controlled download and upload manager. The initial stack is Python, Pyrogram, Google Colab, and InsForge PostgreSQL.

## Current status

The repository is in the foundation phase. Implemented so far: project configuration, owner-only Pyrogram starter commands, basic URL parsing/classification, job state transitions, InsForge PostgreSQL connection-pool scaffold, initial SQL schema, a saved-HTML parser for the WatchHentai provider, and starter tests. URL submission currently validates only; it does not download or upload content yet. Durable job repository methods and the full transfer pipeline remain to be implemented.

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
2. Safe URL resolver and provider registry.
3. InsForge schema and durable job lifecycle.
4. Owner-only Pyrogram bot and batch queue.
5. Telegram and GoFile transfer adapters.
6. Colab bootstrap, resource backpressure, and recovery.
