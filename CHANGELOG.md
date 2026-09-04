# 📓 Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
