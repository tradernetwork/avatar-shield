# 🤝 Contributing to Avatar Shield

Thanks for helping make trading & crypto Discords a little less scammy. This is a
small, focused project — a single-file bot — so contributing is easy.

## 🧭 Scope

Avatar Shield is the **free, alert-only impersonation detector**. Contributions
that fit:

- 🐛 Bug fixes
- 🎯 Detection accuracy (false-positive / false-negative reduction, threshold tuning)
- 📦 Deploy ergonomics (hosts, Docker, docs)
- 📚 Docs & member-education improvements
- 🌍 Translations of `docs/MEMBER_SAFETY.md`

Out of scope (these live in the hosted paid tier, not here): protected-member
ban-capping, dashboards, multi-server billing, auto-tuning. PRs adding those will
be redirected, not merged.

## 🛠️ Dev setup

```bash
git clone https://github.com/tradernetwork/avatar-shield
cd avatar-shield
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in a test bot token + a test channel ID
python bot.py
```

Test against a **throwaway server** you own — never against a live community.
Give a second account an admin's avatar and confirm the alert fires.

## ✅ Before you open a PR

- [ ] `python -m py_compile bot.py make_invite.py` passes (CI runs this too).
- [ ] No secrets committed — double-check you didn't stage `.env`.
- [ ] Keep it a single file where reasonable; this bot's value is that it's tiny
      and auditable. Don't pull in a framework or a database.
- [ ] Match the existing style: type hints, `log.*` (not `print`), and the
      "never crash a hot path" `try/except` discipline already in `bot.py`.

## 📤 PR process

1. Fork → branch (`fix/…`, `feat/…`, `docs/…`).
2. Small, focused commits with clear messages.
3. Open the PR against `master`; fill in the template.
4. Describe **how you tested it** — impersonation logic is easy to break subtly.

## 💬 Questions / ideas

Open a [Discussion](https://github.com/tradernetwork/avatar-shield/discussions) or
a [feature request issue](https://github.com/tradernetwork/avatar-shield/issues/new/choose).
Found a security issue? **Don't** open a public issue — see
[`SECURITY.md`](SECURITY.md).
