# 📓 Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.0]: https://github.com/tradernetwork/avatar-shield/releases/tag/v1.0.0
