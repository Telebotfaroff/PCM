# PCM — Private Content Manager
## Product Requirements Document (PRD)

**Status:** Draft v1.0  
**Primary interface:** Private Telegram bot using Python + Pyrogram  
**Initial runtime:** Google Colab notebook (bot + worker prototype)  
**Repository:** https://github.com/Telebotfaroff/PCM

## 1. Executive Summary

PCM is a private, modular download and upload manager controlled through Telegram. A user sends one or more URLs; PCM analyzes and normalizes them, resolves supported redirects, identifies the likely website or cloud provider, classifies the content, chooses a matching scraper or extractor, validates the result, and then downloads or transfers the content to configured destinations.

PCM combines URL intelligence, reusable provider plugins, download and media-processing tools, upload adapters, queue management, and worker recovery. Its architecture must let new scrapers and storage providers be added without rewriting the Telegram bot or the core job pipeline.

The initial design separates a Telegram control bot from a Google Colab worker. Colab is temporary and cannot guarantee continuous uptime, so the bot must report worker availability accurately and job state must persist outside Colab's temporary filesystem.

## 2. Vision and Goals

### Vision
One private control point for identifying URLs, retrieving media, processing files, and uploading to one or more destinations.

### Goals
- Detect supported website pages, direct media URLs, redirect/shortener links, and cloud-share links.
- Reuse existing website-specific scraper logic through adapters where practical.
- Select extractors using provider matching, declared capabilities, validation, and bounded fallbacks.
- Support Telegram, GoFile, and additional upload destinations through interchangeable adapters.
- Show download and upload progress separately, including speed and ETA where measurable.
- Prevent disk exhaustion through bounded concurrency, queue backpressure, and cleanup policies.
- Recover or safely retry jobs after worker interruption.
- Keep credentials, session data, and signed URLs out of source control and ordinary logs.
- Make providers independently testable and configurable.

### Non-goals for the first release
- Guaranteed 24/7 operation on Google Colab.
- Guaranteed extraction from every website or unsupported/protected URL.
- A public multi-tenant SaaS service.
- A full web dashboard before the Telegram workflow is stable.
- Bypassing authentication or access controls; providers should use supported access and APIs.

## 3. Users and Core Use Cases

The initial user is the project owner using PCM privately through Telegram.

Core use cases:
1. Send a URL and automatically identify the provider and content type.
2. Submit multiple URLs as a batch.
3. View metadata and select quality/format when options are available.
4. Choose Telegram, GoFile, or both as upload destinations.
5. Monitor separate download and upload progress.
6. Retry an upload without downloading the same file again when the file remains available.
7. View, cancel, retry, and inspect jobs.
8. Add a new scraper or cloud provider without changing the core pipeline.
9. Recover job state after a Colab runtime restart.

## 4. Product Principles

- **Resolver first:** URL analysis is a separate, testable module.
- **Provider plugins:** Site-specific behavior stays out of Telegram command handlers.
- **Validated results:** A provider match is a hypothesis; extracted sources must be checked.
- **Separate stages:** Resolution, download, processing, and upload have distinct states.
- **Bounded work:** Network requests, queues, retries, and fallbacks have explicit limits.
- **Honest status:** Never report success before the relevant operation confirms success.
- **Recoverable state:** Persist job metadata outside temporary worker storage.
- **Secure by default:** Validate URLs and redirects, protect secrets, and constrain resource use.

## 5. Functional Requirements

### 5.1 Telegram Bot and Access Control

- **FR-001 Private access:** First release supports owner-only access via configured Telegram user ID. Unauthorized users cannot submit jobs or use admin commands.
- **FR-002 URL input:** Accept URLs in ordinary messages and extract multiple URLs from one message.
- **FR-003 Commands:** `/start`, `/download URL`, `/queue`, `/status [job_id]`, `/cancel job_id`, `/retry job_id`, `/settings`, `/providers`, and `/help`.
- **FR-004 Interactive choices:** Use inline keyboards for available qualities and destinations. Allow configured defaults for automatic mode.
- **FR-005 Progress:** Report download and upload progress separately, including percentage when measurable, speed, bytes, ETA when calculable, and current stage. Throttle message edits.
- **FR-006 Results:** Return destination links and summarize successes, failures, and skipped destinations.

### 5.2 URL Intelligence and Resolver

- **FR-010 Parsing:** Extract, validate, and normalize URLs while preserving query parameters needed by signed links and share pages.
- **FR-011 Redirects:** Follow redirects with configurable hop/time limits; detect loops, invalid destinations, and unsupported schemes. Redact secrets in diagnostic logs.
- **FR-012 Provider matching:** Match hostname and path against a provider registry. Prefer exact site-specific matches over generic extractors where appropriate.
- **FR-013 Classification:** Support `video_page`, `direct_media`, `direct_file`, `hls_stream`, `dash_stream`, `cloud_share`, `image`, `playlist`, `webpage`, and `unknown`. Include confidence/evidence when uncertain.
- **FR-014 Metadata:** Extract title, thumbnail, duration, file size, MIME type, quality options, and provider name when available. Missing optional metadata must not automatically fail a usable source.
- **FR-015 Strategy planner:** Rank compatible strategies by provider match, capabilities, reliability, authentication requirements, and validation evidence.
- **FR-016 Fallbacks:** Record typed failures and try the next compatible strategy within configured attempt, time, and resource limits. Do not blindly run every extractor.
- **FR-017 Validation:** Check source schemes and plausible media/file characteristics before scheduling transfer. Mark expiring sources as ephemeral.
- **FR-018 Unknown URLs:** Return detected domain, attempted strategies, failure category, and a useful next action.
- **FR-019 Safe requests:** Block loopback, private, link-local, and other prohibited IP ranges; revalidate DNS results and each redirect destination to reduce SSRF risk.

### 5.3 Provider Plugin System

- **FR-020 Contract:** Every provider declares an ID, version, matching rules, supported content types, capabilities, and extraction behavior.
- **FR-021 Categories:** Website scrapers, generic extractors, cloud-share adapters, and upload destination adapters.
- **FR-022 Isolation:** Provider errors must not crash the bot or scheduler. Apply per-provider timeouts and bounded retries.
- **FR-023 Registry:** Providers can be enabled/disabled through configuration; expose status and diagnostics to the owner.
- **FR-024 Existing scrapers:** Wrap existing project code after inspecting its interface, dependencies, and reliability; do not assume it can be imported unchanged.
- **FR-025 Expiring sources:** Do not store signed, IP-bound, cookie-bound, or short-lived media URLs as permanent metadata. Store durable page/share references and reacquire ephemeral URLs when needed.

### 5.4 Download and Media Processing

- **FR-030 Engines:** Provide adapters for `yt-dlp`, `aria2c`, and native HTTP streaming where appropriate.
- **FR-031 Quality:** Offer only qualities actually reported by the extractor; support best-available as a configurable default.
- **FR-032 Streams:** Detect supported HLS/DASH sources and use compatible tools where technically supported.
- **FR-033 FFmpeg:** Support optional merging/remuxing and configured processing; avoid unnecessary transcoding.
- **FR-034 Resume:** Resume downloads when supported; otherwise restart safely and report the limitation.
- **FR-035 Validation:** Check file existence, nonzero size, and expected media/container properties where practical.
- **FR-036 Large files:** Support configurable splitting when a destination requires it and track parts/results independently.

### 5.5 Upload Destinations

- **FR-040 Adapter interface:** Each uploader supports capability checks, upload execution, progress events, result links, and typed errors.
- **FR-041 Initial providers:** Prioritize Telegram and GoFile. Add Streamtape and Doodstream after verifying current APIs, credentials, and limits.
- **FR-042 Modes:** Support `telegram_only`, `gofile_only`, and `both`.
- **FR-043 Partial success:** Track each destination independently; one failed upload must not erase another destination's success.
- **FR-044 Retry:** Retry a failed destination without repeating a successful download when the file remains available.
- **FR-045 Direct transfer:** Prefer remote-to-remote transfer only when supported and verifiable; otherwise download locally then upload.
- **FR-046 Telegram:** Support configured target chats/channels and the selected Telegram library. Keep bot-token and user-session modes explicit.
- **FR-047 Link verification:** Save a result link only after the provider confirms completion and returns a usable result.

### 5.6 Queue, Concurrency, and Storage

- **FR-050 Queue states:** Track pending, active, completed, failed, cancelled, and recovery-needed jobs.
- **FR-051 Concurrency:** Configure download and upload concurrency independently. Initial suggested defaults: two downloads and two uploads, subject to worker capacity.
- **FR-052 Backpressure:** Stop scheduling downloads when the upload queue or temporary storage reaches configured limits.
- **FR-053 Disk limits:** Monitor free space and file size; defer or reject jobs that exceed safety limits.
- **FR-054 Cleanup:** Delete temporary files only after required uploads succeed or after a configured retention period and failure policy. Never remove files used by active uploads.
- **FR-055 Duplicates:** Detect duplicates using normalized source identity and, where available, file hashes. Signed URLs for the same page should not automatically count as separate content.
- **FR-056 Cancellation:** Stop work cooperatively, terminate child processes safely, and preserve completed destination results.

### 5.7 Persistence and Colab Worker

- **FR-060 Persistence:** Store job state, stage, attempt count, destination results, timestamps, and error summaries outside Colab's temporary disk.
- **FR-061 Heartbeat:** Worker periodically reports health, capacity, active jobs, and version. Bot distinguishes offline, idle, busy, and unhealthy states.
- **FR-062 Job claiming:** Use atomic claims or leases to prevent duplicate processing across workers.
- **FR-063 Recovery:** Reconcile interrupted jobs at startup. Resume supported operations, retry safe operations, and flag ambiguous operations rather than blindly duplicating uploads.
- **FR-064 Offline behavior:** The bot remains responsive when Colab is offline and labels jobs as waiting, not running.
- **FR-065 Communication:** Use an authenticated job API or explicit protocol. Avoid unsynchronized writes to a shared JSON file.

## 6. Non-Functional Requirements

- Reliability: one provider failure must not crash unrelated jobs.
- Observability: structured logs include job ID, provider, stage, duration, and error category.
- Security: secrets are stored in environment variables or a secret manager, never committed.
- Privacy: restrict access and minimize retention of sensitive URLs, cookies, tokens, and media.
- Performance: use streaming I/O where practical; do not load large files fully into memory.
- Resource control: enforce timeouts, queue limits, concurrency caps, and disk thresholds.
- Maintainability: typed interfaces, modular adapters, and provider-specific tests.
- Portability: worker runs in Colab initially and can later move to a VPS or persistent worker.
- Transparency: distinguish unsupported content from temporary failures and show accurate progress.

## 7. Proposed Architecture — Python First

### Initial MVP runtime
- Python 3.11+ (verify compatibility of pinned dependencies during implementation).
- Pyrogram for Telegram bot updates, commands, callbacks, message handling, and Telegram media operations.
- A Google Colab notebook runs the initial private bot and worker in one prototype runtime to minimize deployment complexity.
- Async-first design using `asyncio`; use bounded subprocess wrappers for tools such as `yt-dlp`, `aria2c`, and FFmpeg.
- Keep bot handlers thin: they validate input and create jobs; provider resolution and transfers run in separate modules/tasks.
- Use environment variables or Colab Secrets for credentials. Never commit bot tokens, API hashes, session strings, cookies, or provider keys.

### Future deployment boundary
The first prototype may run both bot and worker in Colab. Colab runtimes can disconnect or be reclaimed, so this is not a 24/7 guarantee. Keep the control logic, worker loop, and persistence interfaces separable so a later always-on host can run the bot/API while Colab or a persistent worker handles heavy transfers. Do not claim jobs are actively processing when the Colab runtime is offline.

### Python processing plane
- `yt-dlp` for supported media extraction and downloads.
- `aria2c` for supported HTTP downloads where segmented downloading is appropriate.
- FFmpeg for optional merge/remux and media validation.
- `httpx` or `aiohttp` for HTTP requests and streaming, selected consistently.
- Pyrogram upload adapter for configured Telegram chats/channels.
- GoFile adapter as the initial external cloud destination; other destinations are added after API and limit verification.
- Bounded queues, independent download/upload concurrency, disk backpressure, retry policies, and cleanup.

### Core modules
- URL parser/normalizer and safe redirect resolver.
- Content classifier and strategy planner.
- Provider registry with typed capabilities/errors.
- Download engine and upload destination adapters.
- Job scheduler, progress events, persistence interface, recovery, and health status.
- Pyrogram handlers and inline keyboards.

### Persistence decision
Do not use GitHub JSON as a concurrent live queue shared by independent processes. It may hold provider manifests, configuration snapshots, or backups. The first prototype may use SQLite for local development/testing, but Colab's local disk is ephemeral; production-like job state must live in durable remote storage before recovery can be trusted. Choose a remote transactional store before implementing cross-runtime job claims and leases. Avoid introducing MongoDB or Redis unless explicitly chosen; the storage decision remains open.

## 8. Proposed Python Repository Structure

```text
PCM/
├── pcm/
│   ├── bot/                 # Pyrogram handlers, callbacks, keyboards
│   ├── core/                # Config, schemas, typed errors, logging
│   ├── resolver/            # URL parsing, redirects, classification
│   ├── providers/           # Provider contracts and registry
│   ├── downloads/            # yt-dlp, aria2c, HTTP adapters
│   ├── uploads/              # Telegram, GoFile and future adapters
│   ├── jobs/                 # Queue, lifecycle, retries, recovery
│   └── storage/              # Persistence interface and implementations
├── providers/
│   ├── websites/
│   ├── generic_extractors/
│   ├── cloud_links/
│   └── destinations/
├── colab/
│   └── PCM_Worker.ipynb     # Initial run/setup notebook
├── tests/
│   ├── resolver/
│   ├── providers/
│   ├── jobs/
│   └── integration/
├── config/
├── docs/
├── .env.example
├── requirements.txt
├── pyproject.toml
├── README.md
└── PRD.md
```

This is a proposed target structure; files should be added incrementally as each phase is implemented. The Colab notebook should bootstrap from the repository rather than become the only source of truth for application code.

## 9. Telegram UX and Job Lifecycle

### Example flow
1. User sends one or more URLs.
2. PCM validates URLs and creates resolution jobs.
3. Resolver identifies provider candidates and classifies content.
4. PCM presents metadata, quality choices, and destinations when needed.
5. User confirms or configured defaults apply.
6. PCM queues download or direct transfer.
7. Worker reports download progress.
8. PCM validates the file and begins uploads.
9. Each destination reports independent progress and completion.
10. PCM returns result links and cleans up according to policy.

### Job states
Primary flow: `received → resolving → awaiting_selection → queued → downloading → validating → uploading → completed`.

Other states: `failed`, `cancelled`, `waiting_for_worker`, `retry_wait`, `recovery_needed`, and `partial_success`.

Each destination has its own upload state. Overall success is derived from configured required destinations, not one global boolean.

## 10. Proposed Environment Variables

```dotenv
# Telegram bot identity and API access
TELEGRAM_BOT_TOKEN=
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_OWNER_ID=
TELEGRAM_TARGET_CHAT_ID=

# Optional user-session mode only if explicitly required for a feature.
# Treat the session string/file as a high-sensitivity credential.
TELEGRAM_SESSION_STRING=

# Persistence/coordination (final remote store to be selected)
PCM_DATABASE_URL=
PCM_WORKER_SHARED_SECRET=

MAX_CONCURRENT_DOWNLOADS=2
MAX_CONCURRENT_UPLOADS=2
MAX_QUEUE_SIZE=50
MIN_FREE_DISK_MB=2048
MAX_REDIRECT_HOPS=8
PROVIDER_TIMEOUT_SECONDS=60
MAX_FALLBACK_ATTEMPTS=3

DEFAULT_QUALITY=best
DEFAULT_DESTINATION=telegram
TEMP_DIR=/content/pcm
LOG_LEVEL=INFO

# Optional provider credentials, only when needed
GOFILE_TOKEN=
STREAMTAPE_LOGIN=
STREAMTAPE_KEY=
DOODSTREAM_API_KEY=
```

These names are proposals and should be validated during implementation. In Colab, prefer Colab Secrets for credentials rather than notebook literals. Keep `.env` and Pyrogram session files out of Git. A bot token and a user session are different access modes; default to bot-token mode unless a specific feature requires user authorization. Never log session strings, bot tokens, API hashes, cookies, or signed URLs.

## 11. Testing and Acceptance Criteria

### Resolver
- Recognizes direct media URLs, known provider pages, supported cloud shares, redirects, and unknown domains.
- Preserves required query parameters.
- Detects redirect loops and enforces hop/time limits.
- Blocks prohibited private-network requests and validates redirect destinations.
- Prefers exact provider matches when appropriate.
- Returns typed errors and useful diagnostics when no strategy succeeds.

### Plugins
- Each provider tests matching, success, malformed responses, timeouts, expired sources, and authentication failures.
- Provider failure does not crash the worker.
- Providers can be enabled/disabled through configuration.

### Pipeline
- Download and upload progress are independently visible.
- Failed upload can be retried without repeating a successful download when the file remains available.
- Multi-destination jobs preserve partial success.
- Backpressure prevents uncontrolled disk growth.
- Cleanup never deletes files required by active jobs.

### Worker and Telegram
- Bot reports worker offline after missed heartbeats.
- Jobs remain waiting while the worker is offline.
- Recovery avoids blindly duplicating completed uploads.
- Multiple workers cannot claim the same job without an expired/released lease.
- Only authorized users control the private bot.
- Commands handle invalid job IDs and report accurate state.
- Progress updates are throttled; sensitive signed URLs and secrets are not logged.

## 12. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Colab stops unexpectedly | Persistent state, heartbeat, restart reconciliation |
| Website changes break extraction | Provider isolation, fixture tests, diagnostics |
| Signed URL expires | Keep it ephemeral and reacquire before transfer |
| Disk fills during parallel work | Disk thresholds, backpressure, cleanup |
| Upload acknowledgement is lost | Idempotency where available; reconcile before retry |
| SSRF through URLs/redirects | Scheme/host checks, DNS/IP validation, redirect revalidation |
| Provider API changes | Separate adapters and capability checks |
| Shared-state races | Transactional storage or atomic leases |

## 13. Delivery Phases

1. **Python foundation:** Create `pyproject.toml`, pinned `requirements.txt`, config loading, structured logging, typed models/errors, URL parsing/normalization, redirect policy, and resolver unit tests.
2. **Pyrogram bot skeleton:** Implement owner-only access, `/start`, `/help`, URL intake, `/queue`, `/status`, `/cancel`, `/retry`, and `/settings`; add callback handling and test authorization.
3. **Resolver MVP:** Implement direct-media/direct-file detection, generic HTTP inspection, yt-dlp integration, provider registry, classification, safe fallback planning, and clear unsupported-URL diagnostics.
4. **Transfer pipeline:** Add bounded download/upload queues, separate progress events, speed/ETA reporting, disk backpressure, retries, validation, cleanup, and Telegram + GoFile adapters. Preserve per-destination partial success.
5. **Colab notebook:** Provide one-click setup/run instructions, secret loading, dependency checks, FFmpeg/aria2c availability checks, runtime heartbeat, resumable configuration, and safe shutdown/restart reconciliation. Notebook code should import modules from the repository.
6. **Durable persistence and recovery:** Select a remote transactional store before cross-runtime processing. Implement atomic job claims/leases, idempotency/reconciliation, worker heartbeats, and recovery tests.
7. **Provider expansion and hardening:** Wrap the first existing scraper after inspection, add cloud-share providers incrementally, verify third-party upload APIs, and expand integration/security tests.
8. **Deployment portability:** Document the Colab limitations and a path to run the Pyrogram control bot on an always-on host while processing runs on a worker.

## 14. Open Decisions

1. Which existing provider/repository should be wrapped first? Candidate: `Telebotfaroff/whbot`; inspect its current code before reusing anything.
2. Which durable remote store should hold jobs and coordinate recovery?
3. For the first prototype, bot and worker run together in Colab; when should they be split onto separate runtimes?
4. Are Telegram and GoFile the only required first-release destinations?
5. Confirm owner-only access for the MVP (recommended).
6. Which existing scraper integrations are stable enough to reuse?
7. Should Telegram uploads use bot-token mode only, or is a user session required for a clearly identified use case? Default recommendation: bot-token mode.

## 15. MVP Definition of Done

An authorized Telegram user can submit a supported URL; PCM identifies it, resolves or downloads content through a registered provider, uploads it to Telegram or GoFile, reports separate progress, returns a verified result link, and allows job inspection/retry. A worker disconnect does not cause queued work to be falsely reported as active. Resolver and provider tests cover successful, unsupported, and failure paths.

---

## 16. Implementation Plan and Milestones

The implementation should proceed in small, testable commits. Do not attempt to build every scraper or destination before the core job lifecycle works.

### Milestone 0 — Repository and runtime baseline
- Add Python package layout, `pyproject.toml`, `requirements.txt`, `.gitignore`, `.env.example`, and README setup instructions.
- Pin/test Python and library versions in a clean runtime; record known limitations of Pyrogram and Colab.
- Add config validation that fails fast when required settings are missing.
- Ensure secrets, session files, downloaded media, and logs containing private URLs are ignored by Git.

**Acceptance:** the package imports cleanly, configuration validation has tests, and a fresh Colab runtime can install dependencies without manually editing source files.

### Milestone 1 — Safe URL resolver
- Build URL parsing, normalization, scheme/host validation, redirect limits, redirect-loop detection, DNS/IP checks, and redacted diagnostics.
- Add provider contract, registry, content classification, typed failures, and bounded strategy planning.
- Begin with fixture-based tests and a small allowlist of known test URLs; never depend exclusively on live websites in unit tests.

**Acceptance:** unit tests cover valid, malformed, redirected, unsupported, expired, and prohibited-network URLs.

### Milestone 2 — Private Pyrogram control bot
- Add owner-ID authorization before any command or callback performs work.
- Implement `/start`, `/help`, URL intake, `/queue`, `/status`, `/cancel`, `/retry`, `/settings`, and `/providers`.
- Store job IDs and stage transitions through a persistence interface, not in handler-local variables.
- Use inline keyboards for quality and destination selection when more than one option exists.

**Acceptance:** unauthorized users cannot create or control jobs; invalid job IDs and callback inputs return safe errors; basic commands work without a download provider installed.

### Milestone 3 — Download and upload vertical slice
- Integrate yt-dlp for supported pages and native HTTP streaming for validated direct media/files.
- Add file validation and a single-download/single-upload pipeline first.
- Add Telegram destination, then GoFile, with independently tracked results.
- Add separate download/upload progress, speed/ETA where available, throttled Telegram edits, cancellation, retry, and cleanup.
- Expand concurrency only after the single-job path is reliable; start conservatively in Colab and enforce disk backpressure.

**Acceptance:** a supported test URL can be resolved, downloaded, validated, uploaded to the selected destination, and reported with a verified result link. A failed destination does not erase a successful one.

### Milestone 4 — Colab operations and recovery
- Create `colab/PCM_Worker.ipynb` to clone/update the repository, load Colab Secrets, install dependencies, check required binaries, configure temporary storage, and launch PCM.
- Show runtime/worker status and a clear warning that Colab may disconnect and is not guaranteed always-on hosting.
- Checkpoint job transitions in durable storage; reconcile jobs after restart and avoid blindly repeating uploads whose outcome is ambiguous.
- Keep a lightweight SQLite implementation for local tests if useful, but do not treat Colab's local SQLite file as durable across runtime loss.

**Acceptance:** after a simulated worker restart, jobs are reconciled into waiting, retryable, completed, or recovery-needed states without claiming the runtime was continuously available.

### Milestone 5 — Provider expansion and hardening
- Inspect and wrap existing scraper code one provider at a time.
- Add cloud-share adapters and additional destinations only after their APIs, credentials, rate limits, and output-link behavior are verified.
- Add integration tests, concurrency tests, SSRF tests, retry/backoff tests, and storage pressure tests.
- Document environment variables, Colab operation, troubleshooting, and future migration to an always-on control bot plus worker.

**Acceptance:** provider failures are isolated, resource limits are enforced, secrets are not logged, and the MVP can be operated from the documented setup.

### First implementation commit scope
The first coding change should establish the Python project skeleton, configuration and logging, URL model/provider interfaces, a minimal resolver with tests, and a Colab bootstrap outline. Do not implement speculative support for every site in the first commit.

## 17. Implementation Guardrails

- Keep Pyrogram handlers thin and use asynchronous I/O for network-bound work.
- Use subprocess argument arrays (not shell-concatenated user input) when invoking external tools.
- Never fetch arbitrary URLs without SSRF protection; validate every redirect and resolved address.
- Never log bot tokens, API hashes, session strings, cookies, or complete signed URLs.
- Use finite timeouts, retry caps, queue bounds, disk thresholds, and provider-specific limits.
- Do not claim Colab is always-on; show worker offline/waiting status honestly.
- Treat upload acknowledgements carefully and reconcile ambiguous outcomes before retrying.
- Do not add unrelated databases or services without a deliberate decision.

---

**End of PRD — Draft v1.1 (Python + Pyrogram + Colab)**
