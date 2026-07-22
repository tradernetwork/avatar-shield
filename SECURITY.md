# 🔒 Security Policy

Avatar Shield is a **defensive** tool that runs with real moderation powers
(reading member data, and — when `ENFORCE_BAN=true` — banning). We take reports
seriously.

## 📣 Reporting a vulnerability

**Please do _not_ open a public issue for security problems.**

Report privately via GitHub's **[Private Vulnerability
Reporting](https://github.com/tradernetwork/avatar-shield/security/advisories/new)**
(Security tab → *Report a vulnerability*). That keeps the details out of public
view until a fix ships.

Include, if you can:

- What the issue is and where (file / function).
- Steps to reproduce or a proof of concept.
- The impact you see (e.g. false-ban vector, token exposure, DoS).

We'll acknowledge your report and work with you on a fix and coordinated
disclosure.

## 🎯 What we especially care about

- **False-ban / abuse vectors** — anything that lets a bad actor trick the bot
  into banning a legitimate member (e.g. a crafted avatar that collides with an
  admin's pHash to weaponize the auto-ban).
- **Secret exposure** — token or config leaking into logs or errors.
- **Resource exhaustion** — a join/avatar-swap pattern that pins CPU or hits
  rate limits hard enough to knock the bot offline.

## 🛡️ Operator hardening (self-host checklist)

- Never commit your `.env` or bot token. Rotate the token immediately if it's
  ever pasted into a chat, screenshot, or log.
- Start with `ENFORCE_BAN=false`; only enable auto-ban after watching alerts.
- Give the bot the **least privilege** that works: View Channel + Send Messages +
  Embed Links on the mod-log channel, and Ban Members **only** if enforcing.
- Keep the `Avatar Shield` role no higher than it needs to be to ban impersonators.
