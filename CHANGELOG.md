# 📓 Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — self-serve, multi-server release

Any community owner can now add the bot and configure it entirely themselves
in Discord, with zero env-var edits, redeploys, or help from us. The original
single-server deployment keeps running unchanged.

### Added
- 🎛️ **`/shield` slash commands** (`app_commands.CommandTree`, synced
  globally): `setup`, `protect`, `unprotect`, `mode`, `status`, `test`, and
  `scan`. All require **Manage Server** and are guild-only. `setup` verifies
  the bot can actually post in the chosen channel before saving it; `mode
  mode:ban` verifies **Ban Members** and role position first and explains
  what's missing if it can't switch yet.
- 🗄️ **Per-server settings in SQLite** (`settings_store.py`, stdlib
  `sqlite3` only — no new dependency). Path from `AVATAR_SHIELD_DB` (default
  `/data/avatar-shield.db`), with an automatic fallback to `./avatar-shield.db`
  plus a clear warning log if that directory isn't writable (e.g. no volume
  mounted). Per guild: alert channel, mode (alert/ban), extra protected user
  IDs, optional threshold overrides.
- 👋 **Onboarding on join** (`on_guild_join`): a welcome card posted to the
  system channel (or the first channel the bot can post in) explaining what
  the bot does, that it's alert-only by default, and the two-step setup.
- 🔗 **`applications.commands` OAuth2 scope** added to `make_invite.py`'s
  generated URLs, required for slash commands to work at all.
- 📎 Ready-to-click **"Add to Discord"** links in the README for application
  `1529272730334265415` — alert-only by default, plus a Ban Members variant —
  with the primary setup path now "click the link → `/shield setup`".
- 🧪 21 new tests: SQLite settings persistence and resolution order
  (`test_settings_store.py`), and the `/shield mode` permission/validation
  and mode/threshold resolution logic (`test_bot.py`).

### Changed
- **Resolution order, every setting:** per-guild `/shield` DB setting →
  existing env var (`MOD_LOG_CHANNEL_ID`/`MOD_LOG_CHANNELS`/`ENFORCE_BAN`/
  `THRESHOLD_BAN`/`THRESHOLD_ALERT`) → existing channel-name auto-discovery
  (alert channel only). `PROTECTED_USER_IDS` (env) remains global and additive
  to any per-guild `/shield protect` entries — unchanged for backward
  compatibility.
- `bot.py` now subclasses `discord.Client` (`AvatarShieldClient`) to add
  `setup_hook`, which syncs slash commands on boot. All existing `@bot.event`
  handlers are unchanged.
- `Dockerfile` now also copies `settings_store.py` and declares a `/data`
  volume.

### Deploy notes
- **New env var:** `AVATAR_SHIELD_DB` (optional, default `/data/avatar-shield.db`).
- **Mount a persistent volume** at that path's directory (`/data` by default)
  on Railway/Fly/Docker, or `/shield` settings are lost on every restart —
  the bot still runs, but logs a clear warning and falls back to a
  non-persistent local file.
- The existing single-server deployment needs **no configuration changes** —
  it has no `/shield` settings saved, so every lookup falls straight through
  to its current env vars, identical to before this release.

## [1.1.0] — 2026-09-03

Multi-server release. One deployment can now shield several servers, and a
quiet server finally proves it's working.

### Added
- 🌐 **`MOD_LOG_CHANNELS`** — per-server alert routing
  (`guildID:channelID,guildID:channelID`). Servers not listed fall back to
  `MOD_LOG_CHANNEL_ID` (only where that channel really lives) and then to
  auto-discovery of a channel named `avatar-shield` / `mod-log` / `alerts` / etc.
- 🖐️ **Startup warm-up + proof-of-life.** Admin avatars are now fingerprinted at
  boot instead of lazily on the first join, one summary line is logged per
  server (`mod-log=#x, admins=N, enforce_ban=…`), and an "online, watching N
  admin avatars" card posts to each mod-log. Disable with `STARTUP_NOTICE=false`.
- 🧪 **Unit tests** (`pytest -q`) covering pHash matching, the re-encode/resize
  claim, tier thresholds, channel-map parsing and the avatar rules — no Discord
  connection needed. CI now runs them on Python 3.11 / 3.12 / 3.13.
- 👤 **`PROTECTED_USER_IDS`** — protect faces that don't hold Administrator in
  the watching server. The admin permission is the wrong set whenever the person
  being copied isn't staff there. Listed users are fingerprinted in every server
  the bot is in, never flagged themselves, and named in a startup warning when
  they aren't a member of a given server.
- 🔗 `make_invite.py --guild <SERVER_ID>` pins an invite to one server.

### Fixed
- 🕵️ **Server-profile avatars were invisible.** A member with only a per-server
  avatar (Edit Server Profile) has no global `.avatar`, so they were treated as
  a default-avatar user and skipped entirely — the most targeted form of the
  attack went undetected, and admins using one were never fingerprinted.
- 📮 **A second server's alerts went nowhere.** `MOD_LOG_CHANNEL_ID` is a single
  channel in a single server; every other server's `get_channel` returned None
  and the alert was dropped with only a debug-level warning.
- ⏱️ **Stale admin fingerprint window.** An admin changing their own avatar is
  skipped by the detector (admins are the protected set), so the new face stayed
  unprotected until the hourly refresh. The cache is now invalidated on the spot.
- 🔁 **Duplicate work per avatar swap.** One change fires both `on_member_update`
  and `on_user_update`; a 60-second per-member debounce keeps it to one CDN
  fetch and hash.
- 🧯 **Boot-time crashes on bad config.** Missing/garbage `MOD_LOG_CHANNEL_ID`
  and non-numeric thresholds now warn and fall back instead of raising `KeyError`
  / `ValueError` at import.

### Changed
- 🏷️ "admin" → "protected member" throughout (alert embeds, ban reasons, logs),
  now that the protected set is more than just Administrators.
- ⚠️ `member.ban(delete_message_days=…)` → `delete_message_seconds=…`
  (the former is deprecated in discord.py 2.x).
- 📌 Dependencies pinned to major ranges: `discord.py>=2.5,<3`,
  `Pillow>=11,<13`, `ImageHash>=4.3,<5`.

## [1.0.0] — 2026-07-22

First public release. 🎉

### Added
- 🛡️ **Perceptual-hash avatar impersonation detection.** Fingerprints every
  server admin's avatar (64-bit pHash) and flags members wearing a close copy —
  robust to re-encoding, resizing, and light cropping.
- 👀 **Event coverage:** member join, per-guild avatar change, and global avatar
  swap (`on_member_join` / `on_member_update` / `on_user_update`).
- 📏 **Two-tier matching:** ban tier (distance ≤ `THRESHOLD_BAN`, default 6) and
  alert tier (≤ `THRESHOLD_ALERT`, default 10).
- 🚦 **Alert-only by default** (`ENFORCE_BAN=false`) — posts a mod-log card and
  touches no one until you opt in to auto-ban.
- 🔁 **Zero-config admin set:** protected avatars derived from the Administrator
  permission, refreshed hourly, held in memory (no database).
- 📦 **Deploy scaffolding:** `Dockerfile`, `Procfile`, `railway.json`, and a
  `make_invite.py` OAuth2 invite-URL helper.
- 📚 **Docs:** full setup README and `docs/MEMBER_SAFETY.md` — a drop-in,
  copy-paste member-safety notice built around the "check Mutual Servers" rule
  that beats the outside-DM impersonation loophole.

[1.1.0]: https://github.com/tradernetwork/avatar-shield/releases/tag/v1.1.0
[1.0.0]: https://github.com/tradernetwork/avatar-shield/releases/tag/v1.0.0
