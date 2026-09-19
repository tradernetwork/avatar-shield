<div align="center">

<img src="docs/logo.png" alt="Avatar Shield" width="120" />

# 🛡️ Avatar Shield

**Catches scammers who copy your admins' _profile pictures_ to impersonate them.**

Name filters change the name. Scammers don't — they change the _face_.
Avatar Shield fingerprints every admin's avatar and flags anyone wearing a copy.

![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.5%2B-5865F2?logo=discord&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Alert-only by default](https://img.shields.io/badge/default-alert--only-brightgreen)
![Self-serve setup](https://img.shields.io/badge/setup-slash%20commands-5865F2)
<br/>
[![CI](https://github.com/tradernetwork/avatar-shield/actions/workflows/ci.yml/badge.svg)](https://github.com/tradernetwork/avatar-shield/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/tradernetwork/avatar-shield?color=blue)](https://github.com/tradernetwork/avatar-shield/releases/latest)

<br/><br/>

### [➕ Add to Discord (alert-only)](https://discord.com/api/oauth2/authorize?client_id=1529272730334265415&permissions=84992&scope=bot+applications.commands)

<sub>Never bans anyone. Then run **`/shield setup`** in your server. That's it — no env vars, no redeploy, no dashboard.</sub>

<sub>Want it to auto-ban later? [Add with Ban Members instead](https://discord.com/api/oauth2/authorize?client_id=1529272730334265415&permissions=84996&scope=bot+applications.commands) — it still won't ban anyone until you run `/shield mode mode:ban`.</sub>

</div>

---

<div align="center">
<img src="docs/alert-card.png" alt="Avatar Shield alert card" width="640" />
<br/><em>What your mods see the moment an impersonator shows up.</em>
</div>

---

## 🎯 The problem

Impersonation is the **#1 scam vector** in trading & crypto Discords. The play is
always the same:

1. A scammer copies an admin's **profile picture** (and often a look-alike name).
2. They DM your members pretending to be that admin — "claim your allocation
   here," "verify your wallet," "I'm running a private group."
3. Members trust the face. Money leaves.

**MEE6, Dyno, and Wick filter _names_ — not faces.** So the scammer just tweaks
the name (`RealAdmin` → `ReaIAdmin` with a capital i, or a totally different
name) and keeps the picture. Your name filter waves them right through.

Avatar Shield closes that gap. 👇

## ⚙️ How it works

- 🧬 **Perceptual hashing.** Every server admin's avatar is fingerprinted with a
  64-bit [pHash](https://en.wikipedia.org/wiki/Perceptual_hashing). Unlike a
  file checksum, pHash still matches after the scammer **re-encodes, resizes, or
  lightly crops** the image.
- 👀 **Watches the right events.** On every member **join**, **avatar change**,
  and **global avatar swap**, the newcomer's avatar is hashed and compared to the
  admin set. Close match → alert. **Per-server profile pictures count too** —
  that's the sneaky one, since a scammer can wear an admin's face in *your*
  server only and look totally clean everywhere else.
- 📏 **Two tiers.** A very close match (Hamming distance ≤ `6`) is **ban-tier**;
  a looser resemblance (≤ `10`) is **alert-tier** (posted for a human to review,
  never actioned).
- 🔁 **Zero-maintenance protected set.** Derived automatically from anyone
  with the **Administrator** permission — built at startup, refreshed hourly,
  and rebuilt the moment one of them changes their own picture. Need to
  protect someone who *isn't* staff in that server? `/shield protect`.
- 🖐️ **Proof of life.** On boot it posts `Watching N admin avatars` to each
  server's mod-log, so a quiet week reads as *"nobody tried it"* rather than
  *"is this thing even on?"*. Set `STARTUP_NOTICE=false` to silence it.
- 🎛️ **Self-serve, per-server config.** Every server that adds the bot
  configures itself with `/shield` slash commands — no env var, no redeploy,
  no help from us. Settings are stored per-server, so one deployment can run
  hundreds of independently-configured communities.

> **Alert-only by default.** Out of the box it **never bans, mutes, or touches
> anyone** — it just tells your mods. Run `/shield mode mode:ban` when you're
> ready to let it auto-ban.

---

## 🚀 Setup — the whole thing, in Discord (~2 min)

No env vars. No redeploy. No help from us. This is the same shared bot for
every server — you're just adding it to yours.

1. **[➕ Add to Discord](https://discord.com/api/oauth2/authorize?client_id=1529272730334265415&permissions=84992&scope=bot+applications.commands)**
   and authorize it for your server. You need **Manage Server** there.
2. In your server, run **`/shield setup channel:#your-alert-channel`**.
   The bot checks it can actually post there and tells you right away if it can't.
3. *(optional)* **`/shield protect user:@someone`** to protect a face that
   isn't an Administrator — a community owner hanging out in their own server,
   a public figure, a support account. Administrators are protected automatically.
4. *(optional)* **`/shield mode mode:ban`** once you trust it, to auto-ban
   ban-tier matches instead of just alerting. This needs the bot to have
   **Ban Members** and a role above whoever it would ban — if you invited with
   the alert-only link, re-invite with the
   [Ban Members link](https://discord.com/api/oauth2/authorize?client_id=1529272730334265415&permissions=84996&scope=bot+applications.commands)
   first, then run the command. It'll tell you if something's missing.

That's the whole setup. `/shield status` shows your current config any time.

> 🧩 **Heads-up on private channels:** if your alert channel lives in a locked
> category where `@everyone` is denied, add the **Avatar Shield** role to that
> channel and set **View Channel + Send Messages + Embed Links** to explicit
> green ✅ (a gray "neutral" toggle inherits the `@everyone` deny).

### 📖 Slash command reference

All `/shield` subcommands require **Manage Server** and only work inside a
server (not in DMs).

| Command | What it does |
|---|---|
| `/shield setup channel:<#channel>` | Set where alerts post. Verifies the bot can actually post there first. |
| `/shield protect user:<@member>` | Protect an extra face beyond Administrators. |
| `/shield unprotect user:<@member>` | Stop protecting that extra face (Administrators are still protected). |
| `/shield mode mode:<alert\|ban>` | Alert-only (default), or auto-ban ban-tier matches. Checks Ban Members + role position first. |
| `/shield status` | Alert channel, mode, protected-face count, thresholds, whether Members Intent is working. |
| `/shield test` | Posts a sample alert card to your configured channel, so you can see what mods will see. |
| `/shield scan` | Re-checks current members against protected faces right now (bounded, rate-limited — doesn't wait for the hourly refresh). |

---

## 🏗️ Self-hosting your own instance (advanced)

Prefer to run your own deployment instead of using the shared bot above?
Everything is MIT-licensed — clone it and host it yourself.

### 1️⃣ Create the Discord app

1. Go to the [Developer Portal](https://discord.com/developers/applications) →
   **New Application**. Name it. Create.
2. **Bot** tab → **Reset Token** → **copy it** (this is a secret — never commit
   or share it).
3. ⚠️ **Same page → Privileged Gateway Intents → turn ON `SERVER MEMBERS
   INTENT`.** *Everyone forgets this. Without it the bot is deaf to joins and
   avatar changes.*
4. **General Information** → copy the **Application ID** (for your own invite link).
5. **Bot → Installation** (or **OAuth2 → URL Generator**) → make sure your
   app is public and has the `bot` + `applications.commands` scopes, so slash
   commands work once it's in a server.

### 2️⃣ Invite it

Generate your own invite URL:

```bash
python make_invite.py <APPLICATION_ID>
```

That prints an invite with **View Channels, Send Messages, Embed Links, Read
Message History, Ban Members, and `applications.commands`** (needed for
`/shield` to work at all). Want a zero-ban invite to start? Add `--alert`.

Handing the link to someone else? Pin it to their server so it can't land in the
wrong one:

```bash
python make_invite.py <APPLICATION_ID> --guild <SERVER_ID>
```

### 3️⃣ Deploy it (always-on host)

The bot holds a live gateway connection — it can't run serverless/cron. Pick one:

<details open>
<summary>🚂 <b>Railway — one click (easiest, ~$5/mo)</b></summary>

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template?template=https%3A%2F%2Fgithub.com%2Ftradernetwork%2Favatar-shield&envs=DISCORD_BOT_TOKEN%2CMOD_LOG_CHANNEL_ID%2CENFORCE_BAN&DISCORD_BOT_TOKENDesc=Bot+token+from+the+Discord+Developer+Portal&MOD_LOG_CHANNEL_IDDesc=Channel+ID+where+alerts+post&ENFORCE_BANDesc=Leave+false+to+start+in+alert-only+mode&ENFORCE_BANDefault=false)

The button clones this repo, prompts for your **token + mod-log channel**
(`ENFORCE_BAN` pre-filled to `false`), and boots it — Railway reads
`railway.json` + the `Dockerfile`. Watch the deploy logs for
`Avatar Shield online ...`.

⚠️ **Add a volume mounted at `/data`** (Railway project → your service →
**Volumes** → New Volume → mount path `/data`) so `/shield` settings survive
restarts and redeploys. Without it the bot still runs — it just falls back to
an ephemeral local file and logs a warning that settings won't persist.

Prefer to wire it by hand? [railway.app](https://railway.app) → **New Project**
→ **Deploy from GitHub repo** → pick this repo → add the variables under
**Variables** → attach a volume at `/data`.
</details>

<details>
<summary>🪂 <b>Fly.io</b></summary>

```bash
fly launch --no-deploy
fly volumes create avatar_shield_data --size 1
fly secrets set DISCORD_BOT_TOKEN=... MOD_LOG_CHANNEL_ID=... ENFORCE_BAN=false
fly deploy
```
Mount the volume at `/data` in `fly.toml` and set `min_machines_running = 1`
so it never scales to zero.
</details>

<details>
<summary>🐳 <b>Any Docker host / VPS</b></summary>

```bash
cp .env.example .env      # fill in the values
docker build -t avatar-shield .
docker run -d --restart=unless-stopped --env-file .env \
  -v avatar_shield_data:/data --name avatar-shield avatar-shield
```
The `-v avatar_shield_data:/data` volume mount is what makes `/shield`
settings survive a container restart.
</details>

---

## 🔧 Config reference (self-hosting)

These env vars are **defaults/fallbacks only**. Any server can override every
one of them for itself with `/shield` commands — see the command reference
above. A server that never touches `/shield` behaves exactly as these vars say.

| Env var | Required | Default | Meaning |
|---|:---:|:---:|---|
| `DISCORD_BOT_TOKEN` | ✅ | — | Bot token from the Developer Portal |
| `AVATAR_SHIELD_DB` | | `/data/avatar-shield.db` | SQLite path for per-server `/shield` settings. **Mount a persistent volume at this path's directory** or settings are lost on every restart. |
| `MOD_LOG_CHANNEL_ID` | ✳️ | — | Default channel ID where alerts / ban cards post, for servers that haven't run `/shield setup`. |
| `MOD_LOG_CHANNELS` | ✳️ | — | Per-server routing for servers that haven't self-configured: `guildID:channelID,guildID:channelID`. |
| `PROTECTED_USER_IDS` | | — | Extra user IDs to protect beyond Administrators, in **every** server, comma-separated. Per-server equivalent: `/shield protect`. |
| `ENFORCE_BAN` | | `false` | Default mode for servers that haven't run `/shield mode`. `true` = auto-ban ban-tier matches. |
| `STARTUP_NOTICE` | | `true` | Post an "online, watching N admin avatars" card to each mod-log at boot |
| `THRESHOLD_BAN` | | `6` | Default pHash distance ≤ this ⇒ **ban** tier |
| `THRESHOLD_ALERT` | | `10` | Default pHash distance ≤ this ⇒ **alert** tier (review) |

✳️ With neither `MOD_LOG_CHANNEL_ID` nor `MOD_LOG_CHANNELS` set, and no
`/shield setup` for a given server, the bot falls back to auto-discovery
(below) and logs a warning.

Thresholds are out of 64 bits — **lower = stricter.** Getting false positives?
Lower `THRESHOLD_ALERT`. Missing near-copies? Raise it, carefully.

## 🌐 Resolution order (how one deployment serves many servers)

Every setting below resolves the same way, per server:

1. **That server's `/shield` setting**, stored in SQLite — always wins once set.
2. **The env var fallback** — `MOD_LOG_CHANNELS`/`MOD_LOG_CHANNEL_ID` for the
   alert channel, `ENFORCE_BAN` for mode, `THRESHOLD_BAN`/`THRESHOLD_ALERT`
   for thresholds, `PROTECTED_USER_IDS` for extra protected faces (this one
   always applies everywhere, on top of whatever a server adds itself).
3. **Auto-discovery** (alert channel only) — the first channel the bot can
   post in named `avatar-shield`, `mod-log`, `mod-logs`, `modlog`,
   `admin-log`, `staff-log`, `security`, or `alerts`.
4. Nothing → a loud startup warning naming the server, and alerts there are
   dropped rather than misrouted.

This is exactly how the original single-server deployment keeps working
unchanged after this upgrade: it never ran `/shield setup`, so every lookup
falls straight through to its env vars, same as before.

---

## 🔨 Turning on auto-ban

Run it alert-only for a few days and watch the mod-log. When you trust it:

1. Confirm the bot has **Ban Members** and its role sits **above** the roles
   it would ban (Server Settings → Roles).
2. Run **`/shield mode mode:ban`**. It checks both of those and tells you
   what's missing if it can't switch yet.

Ban-tier matches now get banned automatically (with a 24-hour message purge);
alert-tier matches still just post for review.

---

## 👤 Protecting someone who isn't an admin here

The Administrator permission is a good default for *"who gets impersonated"*,
but it's the wrong set whenever the face being copied doesn't belong to staff of
the watching server — a community owner hanging out in a friend's server, a
public figure, a support account.

```
/shield protect user:@someone
```

That user is fingerprinted and protected in **that server**, whether or not
they hold any permission there, and never flagged themselves. (Self-hosters
can also set `PROTECTED_USER_IDS` in the env to protect someone in **every**
server the bot is in — see the config reference above.)

**This does not reach outside your servers.** It protects the listed face
*within* servers the bot watches — see the loophole below for what no bot can do.

---

## 🕳️ Know the loophole → [read `docs/MEMBER_SAFETY.md`](docs/MEMBER_SAFETY.md)

Avatar Shield stops impersonators who **join your server**. The smart ones don't
join at all — they scrape your member list from a throwaway account and DM your
members from **outside**, so no bot ever sees them. **No Discord bot can read or
block those DMs — that's a hard platform privacy limit, not a gap in this tool.**

The one thing that actually beats it is **your members knowing the tells.** We
wrote a drop-in, copy-paste safety notice for you to pin — the headline rule:

> ✅ **A real admin shares _this server_ with you. Check "Mutual Servers" on
> anyone who DMs you claiming to be staff. No mutual = impersonator. Block.**

👉 **[Grab the pinned-message copy in `docs/MEMBER_SAFETY.md`.](docs/MEMBER_SAFETY.md)**

---

## 🩺 Troubleshooting

Every boot logs one line per server:
`guild <id> (<name>): mod-log=#alerts, protected=4, mode=alert`. Run
`/shield status` in the server itself for the same picture without touching logs.

| Symptom | Fix |
|---|---|
| `/shield` doesn't show up at all | Slash commands sync **globally** on boot and can take up to an hour to appear the first time. Also confirm the bot was invited with the `applications.commands` scope (re-invite with the README link if unsure). |
| Online but never reacts | Server Members Intent is **off**, or the impersonator has Administrator (admins are the *protected* set, never flagged) |
| `/shield status` shows 0 protected faces | Nobody in that server has the Administrator permission *and* a custom avatar, and nobody's been added with `/shield protect` — there is nothing to protect yet |
| "not set — run `/shield setup`" | Run `/shield setup channel:#your-channel`. Self-hosters can also set `MOD_LOG_CHANNELS`/`MOD_LOG_CHANNEL_ID` as a fallback. |
| Alerts land in one server but not another | Each server's alert channel is independent — check [Resolution order](#-resolution-order-how-one-deployment-serves-many-servers) |
| `I can't post in #x` | Grant the bot's role explicit green ✅ View Channel + Send Messages + Embed Links there (gray "neutral" inherits an `@everyone` deny) |
| `/shield mode mode:ban` refuses | It told you why — missing **Ban Members** permission, or the bot's role sits below other roles. Fix that, then rerun it. |
| Settings vanish after a redeploy (self-hosted) | `AVATAR_SHIELD_DB`'s directory isn't a mounted persistent volume — see [Config reference](#-config-reference-self-hosting) |
| Nothing at all | Wrong token, or the app didn't actually join (Server Settings → Integrations) |

---

## 🧪 Developing

```bash
pip install -r requirements-dev.txt
pytest -q
```

The tests cover the pure logic — pHash matching (including the re-encode /
resize claim), the tier thresholds, per-server channel parsing, the
server-avatar rule, the SQLite settings store (persistence, resolution order),
and the `/shield mode` permission checks — with no Discord connection and no
token. CI runs them on Python 3.11 / 3.12 / 3.13.

---

## 📜 License

MIT. Free to self-host and hand to other server owners.

<sub>Built by [Trader Network](https://github.com/tradernetwork). The hosted paid
tier adds protected-member ban-capping (so a mis-fire can't nuke a real
admin/subscriber), auto-tuning, and a dashboard.</sub>
