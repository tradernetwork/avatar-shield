#!/usr/bin/env python3
"""
Avatar Shield — self-serve, multi-server admin-impersonation detector.

Scammers copy your admins' profile pictures to DM your members with fake
"support" / "airdrop" links. Name filters miss this — they change the name,
not the face. Avatar Shield fingerprints every server admin's avatar with a
perceptual hash and posts a mod-log alert when a member shows up wearing a
close copy — even a re-encoded or lightly-cropped one.

This free tier is ALERT-ONLY by default: it never bans, mutes, or touches
anyone. It just tells you. Run `/shield mode mode:ban` once you trust it and
the bot has Ban Members.

Self-serve setup (any server owner, no redeploy)
-------------------------------------------------
1. Click the "Add to Discord" invite link in the README, authorize it.
2. In your server: `/shield setup channel:#your-alert-channel`.
3. (optional) `/shield protect user:@someone` to protect a non-admin face.
4. `/shield status` any time to see the current config.

Every setting above is stored per-server in SQLite (see AVATAR_SHIELD_DB
below) and overrides the env vars for that server only. The env vars below
remain the defaults for any server that hasn't configured itself — that's
what keeps the original deployment working unchanged.

Operator setup (env vars — defaults/fallbacks only)
----------------------------------------------------
1. pip install -r requirements.txt
2. Discord Developer Portal -> your app -> Bot -> enable the
   **Server Members Intent** (privileged). Without it the bot can't see joins
   or avatar changes.
3. Copy .env.example to .env and fill in:
     DISCORD_BOT_TOKEN=...        # bot token
     AVATAR_SHIELD_DB=...         # sqlite path for per-server settings (default /data/avatar-shield.db)
     MOD_LOG_CHANNEL_ID=...       # default channel where alerts are posted
     MOD_LOG_CHANNELS=...         # optional per-guild override, guild:channel,...
     PROTECTED_USER_IDS=...       # optional extra faces to protect (non-admins), global
     ENFORCE_BAN=false            # default mode for guilds with no /shield mode setting
     THRESHOLD_BAN=6              # <= this distance = ban tier
     THRESHOLD_ALERT=10           # <= this distance = alert tier
4. python bot.py

The protected set is derived automatically from anyone with the Administrator
permission, plus anyone named in PROTECTED_USER_IDS or added per-server via
`/shield protect` — warmed at startup and refreshed hourly.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

import discord
import imagehash
from discord import app_commands
from PIL import Image, UnidentifiedImageError

import settings_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("avatar-shield")


# ---- Config (env-driven) -------------------------------------------------
def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        log.warning("%s=%r is not an integer — falling back to %d", name, raw, default)
        return default


def parse_channel_map(raw: str) -> dict[int, int]:
    """Parse ``guild_id:channel_id,guild_id:channel_id`` into a dict.

    Whitespace, newlines and semicolons are all accepted as separators so the
    value survives being pasted into a Railway/Fly variable box. Malformed
    pairs are logged and skipped rather than crashing the bot at boot.
    """
    out: dict[int, int] = {}
    if not raw:
        return out
    for chunk in raw.replace(";", ",").replace("\n", ",").split(","):
        pair = chunk.strip()
        if not pair:
            continue
        guild_s, sep, channel_s = pair.partition(":")
        if not sep:
            log.warning("MOD_LOG_CHANNELS: skipping %r (expected guild_id:channel_id)", pair)
            continue
        try:
            out[int(guild_s.strip())] = int(channel_s.strip())
        except ValueError:
            log.warning("MOD_LOG_CHANNELS: skipping %r (ids must be numeric)", pair)
    return out


MOD_LOG_CHANNEL_ID: Optional[int] = None
_default_log_raw = os.environ.get("MOD_LOG_CHANNEL_ID", "").strip()
if _default_log_raw:
    try:
        MOD_LOG_CHANNEL_ID = int(_default_log_raw)
    except ValueError:
        log.warning("MOD_LOG_CHANNEL_ID=%r is not numeric — ignoring", _default_log_raw)

MOD_LOG_CHANNELS: dict[int, int] = parse_channel_map(os.environ.get("MOD_LOG_CHANNELS", ""))


def parse_id_list(raw: str) -> set[int]:
    """Parse a comma/space/newline separated list of Discord snowflakes."""
    out: set[int] = set()
    for chunk in raw.replace(";", ",").replace("\n", ",").replace(" ", ",").split(","):
        item = chunk.strip()
        if not item:
            continue
        try:
            out.add(int(item))
        except ValueError:
            log.warning("PROTECTED_USER_IDS: skipping %r (ids must be numeric)", item)
    return out


# People whose face is protected even though they don't hold Administrator here.
# The admin permission is a good default for "who gets impersonated", but it is
# the wrong set whenever the person being copied isn't staff in the server doing
# the watching — a community owner in a friend's server, a public figure, a
# support account. Listed users are protected in every guild the bot is in,
# and are never flagged themselves.
PROTECTED_USER_IDS: set[int] = parse_id_list(os.environ.get("PROTECTED_USER_IDS", ""))
ENFORCE_BAN = _env_flag("ENFORCE_BAN", False)
STARTUP_NOTICE = _env_flag("STARTUP_NOTICE", True)
THRESHOLD_BAN = _env_int("THRESHOLD_BAN", 6)
THRESHOLD_ALERT = _env_int("THRESHOLD_ALERT", 10)

# Channel names tried, in order, when a guild has no explicit mod-log configured.
# Multi-guild installs shouldn't need a redeploy just to gain a second server.
DISCOVER_CHANNEL_NAMES: tuple[str, ...] = (
    "avatar-shield",
    "mod-log",
    "mod-logs",
    "modlog",
    "admin-log",
    "staff-log",
    "security",
    "alerts",
)

# ---- Per-server settings (SQLite) ----------------------------------------
# Every server that self-configures via /shield gets its own row here. A
# server that never touches /shield keeps behaving exactly like before —
# every lookup here falls through to the env vars above when a guild has no
# saved setting. AVATAR_SHIELD_DB should point at a mounted persistent volume
# (Railway volume, Fly volume, a host bind-mount) or settings are lost on
# every restart/redeploy.
AVATAR_SHIELD_DB = settings_store.resolve_db_path(
    os.environ.get("AVATAR_SHIELD_DB", "/data/avatar-shield.db").strip()
    or "/data/avatar-shield.db"
)
store = settings_store.SettingsStore(AVATAR_SHIELD_DB)


def resolve_mode(guild_id: int) -> str:
    """Per-guild mode: DB setting -> ENFORCE_BAN env -> "alert" default."""
    saved = store.get(guild_id).mode
    if saved is not None:
        return saved
    return "ban" if ENFORCE_BAN else "alert"


def resolve_thresholds(guild_id: int) -> tuple[int, int]:
    """Per-guild thresholds: DB setting -> THRESHOLD_* env defaults."""
    settings = store.get(guild_id)
    ban = settings.threshold_ban if settings.threshold_ban is not None else THRESHOLD_BAN
    alert = settings.threshold_alert if settings.threshold_alert is not None else THRESHOLD_ALERT
    return ban, alert


def ban_mode_check(has_ban_permission: bool, bot_role_position: int, highest_role_position: int) -> tuple[bool, str]:
    """Pure. Can this guild's bot switch to ban mode?

    Returns (allowed, message). allowed=False blocks the switch and message
    explains why. allowed=True with a non-empty message is an advisory
    warning only (the switch still goes through) — a low bot role means
    individual bans can still fail later, but that's a per-member fact we
    can't fully know ahead of time.
    """
    if not has_ban_permission:
        return False, (
            "I don't have the **Ban Members** permission in this server yet. "
            "Grant it to my role in Server Settings -> Roles, then run this again."
        )
    if bot_role_position < highest_role_position:
        return True, (
            "My role isn't at the top of your role list. Discord won't let me ban "
            "anyone whose top role sits above mine — drag **Avatar Shield** higher in "
            "Server Settings -> Roles for it to work on everyone."
        )
    return True, ""


# ---- pHash constants -----------------------------------------------------
PHASH_SIZE = 8                    # 8x8 = 64-bit fingerprint
ADMIN_HASH_TTL_S = 3600           # refresh admin fingerprints hourly
MAX_AVATAR_BYTES = 8 * 1024 * 1024
AVATAR_ASSET_SIZE = 128
AVATAR_ASSET_FORMAT = "png"
RECHECK_TTL_S = 60                # suppress duplicate checks of the same avatar
BAN_PURGE_SECONDS = 86400         # delete a banned impersonator's last day of messages


# ---- Cache types ---------------------------------------------------------
@dataclass
class _ProtectedEntry:
    user_id: int
    phash: imagehash.ImageHash
    reason: str  # 'admin' | 'listed'


@dataclass
class _GuildCache:
    protected: list[_ProtectedEntry] = field(default_factory=list)
    refreshed_at: float = 0.0


@dataclass(frozen=True)
class AvatarMatch:
    impersonated_user_id: int
    distance: int
    severity: str  # 'ban' | 'alert'


_cache: dict[int, _GuildCache] = {}
# guild_id -> resolved mod-log channel id, or None when the guild has none.
_mod_log_resolved: dict[int, Optional[int]] = {}
# (guild_id, user_id) -> (avatar key, checked_at). One avatar swap fires both
# on_member_update and on_user_update; this keeps it to a single CDN fetch.
_recent_checks: dict[tuple[int, int], tuple[str, float]] = {}


def _invalidate(guild_id: int) -> None:
    _cache.pop(guild_id, None)


def _has_custom_avatar(user: discord.abc.User) -> bool:
    """True when this user has uploaded an avatar we can meaningfully hash.

    A per-server avatar counts. Discord's "Edit Server Profile" is the natural
    way to impersonate staff in exactly one server, and a member using it can
    still have ``.avatar is None`` globally — so checking only the global
    avatar would let the most targeted form of the attack through untouched.
    Default avatars are never fingerprinted: every default collides with every
    other one.
    """
    return (
        getattr(user, "guild_avatar", None) is not None
        or getattr(user, "avatar", None) is not None
    )


def _is_admin(member: discord.Member) -> bool:
    try:
        return bool(member.guild_permissions.administrator)
    except AttributeError:
        return False


def _is_protected(member: discord.Member) -> bool:
    """Members who ARE the protected set — never flagged for their own face."""
    if member.id in PROTECTED_USER_IDS or _is_admin(member):
        return True
    return member.id in store.get(member.guild.id).protected_user_ids


# ---- pHash computation ---------------------------------------------------
async def _fetch_avatar_bytes(asset: discord.Asset) -> Optional[bytes]:
    try:
        png = asset.replace(format=AVATAR_ASSET_FORMAT, size=AVATAR_ASSET_SIZE)
        data = await png.read()
        if len(data) > MAX_AVATAR_BYTES:
            return None
        return data
    except (discord.HTTPException, discord.NotFound):
        return None
    except Exception as e:  # noqa: BLE001 — never crash a hot path
        log.debug("avatar fetch failed: %s", e)
        return None


def phash_from_bytes(data: bytes) -> Optional[imagehash.ImageHash]:
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            return imagehash.phash(im, hash_size=PHASH_SIZE)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


async def _compute_phash(member: discord.abc.User) -> Optional[imagehash.ImageHash]:
    if not _has_custom_avatar(member):
        return None
    data = await _fetch_avatar_bytes(member.display_avatar)
    if data is None:
        return None
    # imagehash/PIL are CPU-bound — keep them off the event loop.
    return await asyncio.to_thread(phash_from_bytes, data)


# ---- Admin cache ---------------------------------------------------------
async def _refresh_protected(guild: discord.Guild) -> _GuildCache:
    cache = _GuildCache(refreshed_at=time.time())
    guild_protected_ids = store.get(guild.id).protected_user_ids
    all_protected_ids = PROTECTED_USER_IDS | guild_protected_ids
    people: list[tuple[discord.Member, str]] = []
    for m in guild.members:
        if m.bot or not _has_custom_avatar(m):
            continue
        if m.id in all_protected_ids:
            people.append((m, "listed"))
        elif _is_admin(m):
            people.append((m, "admin"))

    if people:
        results = await asyncio.gather(
            *(_compute_phash(m) for m, _ in people), return_exceptions=True
        )
        for (m, reason), r in zip(people, results):
            if isinstance(r, imagehash.ImageHash):
                cache.protected.append(_ProtectedEntry(user_id=m.id, phash=r, reason=reason))

    listed = sum(1 for e in cache.protected if e.reason == "listed")
    log.info(
        "guild %s (%s): cached %d protected fingerprints (%d admin, %d listed)",
        guild.id, guild.name, len(cache.protected), len(cache.protected) - listed, listed,
    )
    missing = all_protected_ids - {m.id for m, _ in people}
    if missing:
        log.warning(
            "guild %s (%s): protected user id(s) %s are not members here (or have no "
            "avatar) — their face is NOT protected in this server",
            guild.id, guild.name, ", ".join(str(i) for i in sorted(missing)),
        )
    _cache[guild.id] = cache
    return cache


async def _get_cache(guild: discord.Guild) -> _GuildCache:
    c = _cache.get(guild.id)
    if c is not None and (time.time() - c.refreshed_at) < ADMIN_HASH_TTL_S:
        return c
    return await _refresh_protected(guild)


# ---- Match ---------------------------------------------------------------
def best_match(
    subject: imagehash.ImageHash,
    protected: Iterable[_ProtectedEntry],
    *,
    exclude_user_id: Optional[int] = None,
    threshold_ban: int = THRESHOLD_BAN,
    threshold_alert: int = THRESHOLD_ALERT,
) -> Optional[AvatarMatch]:
    """Closest protected face within the alert threshold, or None. Pure — unit-testable."""
    best: Optional[AvatarMatch] = None
    for entry in protected:
        if exclude_user_id is not None and entry.user_id == exclude_user_id:
            continue
        distance = subject - entry.phash
        if distance > threshold_alert:
            continue
        severity = "ban" if distance <= threshold_ban else "alert"
        if best is None or distance < best.distance:
            best = AvatarMatch(entry.user_id, distance, severity)
    return best


async def check_member(member: discord.Member) -> Optional[AvatarMatch]:
    if member.bot or not _has_custom_avatar(member):
        return None
    if _is_protected(member):
        return None  # they ARE the protected set

    cache = await _get_cache(member.guild)
    if not cache.protected:
        return None

    mhash = await _compute_phash(member)
    if mhash is None:
        return None

    threshold_ban, threshold_alert = resolve_thresholds(member.guild.id)
    return best_match(
        mhash, cache.protected, exclude_user_id=member.id,
        threshold_ban=threshold_ban, threshold_alert=threshold_alert,
    )


# ---- Bot -----------------------------------------------------------------
intents = discord.Intents.default()
intents.members = True  # REQUIRED — join + avatar-change events


class AvatarShieldClient(discord.Client):
    async def setup_hook(self) -> None:
        # Global sync so /shield works in every server, including ones that
        # join after this boot — no per-guild sync, no redeploy needed.
        synced = await tree.sync()
        log.info("synced %d slash command(s) globally", len(synced))


bot = AvatarShieldClient(intents=intents)
tree = app_commands.CommandTree(bot)


def _can_post(guild: discord.Guild, channel: discord.TextChannel) -> bool:
    me = guild.me
    if me is None:
        return False
    p = channel.permissions_for(me)
    return p.view_channel and p.send_messages and p.embed_links


def _text_channel(guild: discord.Guild, channel_id: int) -> Optional[discord.TextChannel]:
    ch = guild.get_channel(channel_id)
    return ch if isinstance(ch, discord.TextChannel) else None


def resolve_mod_log(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """Find this guild's mod-log channel.

    Order: this guild's own `/shield setup` setting (SQLite) -> explicit
    per-guild env mapping -> the global env default (only if it really lives
    in *this* guild) -> a conventionally-named channel the bot can post in.
    The env steps are what let the original single-server deployment keep
    working with zero config changes; DB always wins once a server has run
    `/shield setup` for itself.
    """
    cached = _mod_log_resolved.get(guild.id)
    if cached is not None:
        ch = _text_channel(guild, cached)
        if ch is not None:
            return ch
        _mod_log_resolved.pop(guild.id, None)  # deleted — re-resolve below

    guild_setting = store.get(guild.id).mod_log_channel_id
    if guild_setting is not None:
        ch = _text_channel(guild, guild_setting)
        if ch is None:
            log.warning(
                "guild %s (%s): /shield setup points at channel %s, which this bot cannot see",
                guild.id, guild.name, guild_setting,
            )
        else:
            if not _can_post(guild, ch):
                log.warning(
                    "guild %s (%s): #%s is configured but the bot lacks "
                    "View Channel / Send Messages / Embed Links there",
                    guild.id, guild.name, ch.name,
                )
            _mod_log_resolved[guild.id] = ch.id
            return ch

    explicit = MOD_LOG_CHANNELS.get(guild.id)
    if explicit is not None:
        ch = _text_channel(guild, explicit)
        if ch is None:
            log.warning(
                "guild %s (%s): MOD_LOG_CHANNELS points at %s, which this bot cannot see",
                guild.id, guild.name, explicit,
            )
        else:
            if not _can_post(guild, ch):
                log.warning(
                    "guild %s (%s): #%s is configured but the bot lacks "
                    "View Channel / Send Messages / Embed Links there",
                    guild.id, guild.name, ch.name,
                )
            _mod_log_resolved[guild.id] = ch.id
            return ch

    if MOD_LOG_CHANNEL_ID is not None:
        ch = _text_channel(guild, MOD_LOG_CHANNEL_ID)
        if ch is not None:
            _mod_log_resolved[guild.id] = ch.id
            return ch

    for name in DISCOVER_CHANNEL_NAMES:
        for ch in guild.text_channels:
            if ch.name.lower() == name and _can_post(guild, ch):
                log.info(
                    "guild %s (%s): no mod-log configured — auto-selected #%s. "
                    "Pin it with MOD_LOG_CHANNELS=%s:%s",
                    guild.id, guild.name, ch.name, guild.id, ch.id,
                )
                _mod_log_resolved[guild.id] = ch.id
                return ch

    # Deliberately not cached: if the owner creates #mod-log later, the next
    # alert should find it without a restart.
    log.warning(
        "guild %s (%s): NO mod-log channel — alerts have nowhere to go. Set "
        "MOD_LOG_CHANNELS=%s:<channel_id> or create a #mod-log the bot can post in.",
        guild.id, guild.name, guild.id,
    )
    return None


async def _post_and_maybe_ban(member: discord.Member, match: AvatarMatch, trigger: str) -> None:
    channel = resolve_mod_log(member.guild)
    if channel is None:
        log.warning(
            "guild %s: impersonation match (user=%s distance=%d) with no mod-log to report it to",
            member.guild.id, member.id, match.distance,
        )
        return

    impersonated = member.guild.get_member(match.impersonated_user_id)
    target = f"{impersonated.mention} (`{impersonated}`)" if impersonated else f"user {match.impersonated_user_id}"

    mode = resolve_mode(member.guild.id)
    banned = False
    if match.severity == "ban" and mode == "ban":
        try:
            await member.ban(
                reason=f"Avatar impersonation of protected member {match.impersonated_user_id} "
                       f"(pHash distance={match.distance}, trigger={trigger})",
                delete_message_seconds=BAN_PURGE_SECONDS,
            )
            banned = True
        except discord.Forbidden:
            log.warning("ban forbidden — check bot role position + Ban Members perm")
        except discord.HTTPException as e:
            log.warning("ban failed: %s", e)

    if banned:
        title, color, action = "🛡️ BAN — avatar_impersonation", 0xE53935, "Banned"
    elif match.severity == "ban":
        title, color, action = "🚨 Avatar impersonation (ban-tier)", 0xFB8C00, "Alert only (enforcement off)"
    else:
        title, color, action = "👁️ Avatar similarity alert", 0xFDD835, "Alert only — review"

    threshold_ban, threshold_alert = resolve_thresholds(member.guild.id)
    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="User", value=f"{member.mention} (`{member}` · `{member.id}`)", inline=False)
    embed.add_field(name="Resembles protected member", value=target, inline=False)
    embed.add_field(name="pHash distance", value=f"**{match.distance}** (ban ≤{threshold_ban}, alert ≤{threshold_alert})", inline=True)
    embed.add_field(name="Action", value=action, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"trigger: {trigger}")
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        log.warning(
            "guild %s: cannot post in #%s — grant the bot's role explicit "
            "View Channel + Send Messages + Embed Links there",
            member.guild.id, channel.name,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("mod-log post failed: %s", e)


def _should_check(member: discord.Member) -> bool:
    """Debounce repeat checks of an avatar we just hashed for this member."""
    key = (member.guild.id, member.id)
    avatar_key = str(member.display_avatar)
    seen = _recent_checks.get(key)
    now = time.time()
    if seen is not None and seen[0] == avatar_key and (now - seen[1]) < RECHECK_TTL_S:
        return False
    _recent_checks[key] = (avatar_key, now)
    if len(_recent_checks) > 10_000:  # cheap bound; this is a debounce, not a ledger
        cutoff = now - RECHECK_TTL_S
        for k, v in list(_recent_checks.items()):
            if v[1] < cutoff:
                _recent_checks.pop(k, None)
    return True


async def _check(member: discord.Member, *, trigger: str) -> None:
    if not _should_check(member):
        return
    try:
        match = await check_member(member)
        if match is not None:
            await _post_and_maybe_ban(member, match, trigger)
    except Exception as e:  # noqa: BLE001
        log.warning("check failed for %s: %s", member, e)


_warmed_up = False


async def _warm_up(guilds: Optional[Iterable[discord.Guild]] = None) -> None:
    """Fingerprint the given guilds' admins and say so out loud.

    Without this the admin cache is built lazily on the first join/avatar
    change, so a quiet server gives no evidence the bot works at all — you
    cannot tell "no impersonators" apart from "silently misconfigured".
    """
    for guild in (bot.guilds if guilds is None else guilds):
        try:
            cache = await _refresh_protected(guild)
        except Exception as e:  # noqa: BLE001
            log.warning("warm-up failed for guild %s: %s", guild.id, e)
            continue

        channel = resolve_mod_log(guild)
        mode = resolve_mode(guild.id)
        threshold_ban, threshold_alert = resolve_thresholds(guild.id)
        log.info(
            "guild %s (%s): mod-log=%s, protected=%d, mode=%s",
            guild.id, guild.name,
            f"#{channel.name}" if channel else "NONE",
            len(cache.protected), mode,
        )
        if STARTUP_NOTICE and channel is not None:
            mode_txt = "auto-ban armed" if mode == "ban" else "alert-only"
            embed = discord.Embed(
                title="🛡️ Avatar Shield online",
                description=(
                    f"Watching **{len(cache.protected)}** protected avatar"
                    f"{'' if len(cache.protected) == 1 else 's'} in **{guild.name}** — {mode_txt}.\n"
                    f"Ban ≤{threshold_ban} · alert ≤{threshold_alert} pHash distance."
                ),
                color=0x43A047,
                timestamp=datetime.now(timezone.utc),
            )
            try:
                await channel.send(embed=embed)
            except Exception as e:  # noqa: BLE001
                log.warning("startup notice failed in guild %s: %s", guild.id, e)


async def _find_welcome_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """System channel if postable, else the first channel the bot can post in."""
    if guild.system_channel is not None and _can_post(guild, guild.system_channel):
        return guild.system_channel
    for ch in guild.text_channels:
        if _can_post(guild, ch):
            return ch
    return None


async def _post_onboarding(guild: discord.Guild) -> None:
    """Welcome card for a server that just added the bot — the whole self-serve pitch.

    No env edit, no redeploy, no help from us: two slash commands and this
    server is configured. Posted once, on join.
    """
    channel = await _find_welcome_channel(guild)
    if channel is None:
        log.warning(
            "guild %s (%s): joined but there's nowhere the bot can post an onboarding message",
            guild.id, guild.name,
        )
        return
    embed = discord.Embed(
        title="🛡️ Avatar Shield is watching",
        description=(
            "I catch scammers who copy your admins' **profile pictures** to impersonate "
            "them. **Alert-only by default** — I never ban, mute, or touch anyone until "
            "you say so.\n\n"
            "**Get set up (2 steps):**\n"
            "1️⃣ `/shield setup` — pick the channel where alerts post.\n"
            "2️⃣ *(optional)* `/shield protect` — protect a face beyond your Administrators.\n\n"
            "Run `/shield status` any time to see your current config, or `/shield test` "
            "to see a sample alert card."
        ),
        color=0x43A047,
    )
    try:
        await channel.send(embed=embed)
    except Exception as e:  # noqa: BLE001
        log.warning("onboarding post failed in guild %s: %s", guild.id, e)


@bot.event
async def on_ready():
    global _warmed_up
    log.info(
        "Avatar Shield online as %s — %d guild(s)",
        bot.user, len(bot.guilds),
    )
    if not intents.members:
        log.error("Server Members Intent is OFF — the bot is deaf to joins and avatar changes.")
    if _warmed_up:
        return  # a reconnect, not a fresh boot — don't re-announce
    _warmed_up = True
    await _warm_up()


@bot.event
async def on_guild_join(guild: discord.Guild):
    log.info("joined guild %s (%s)", guild.id, guild.name)
    _invalidate(guild.id)
    _mod_log_resolved.pop(guild.id, None)
    await _warm_up([guild])
    await _post_onboarding(guild)


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    if _mod_log_resolved.get(channel.guild.id) == channel.id:
        _mod_log_resolved.pop(channel.guild.id, None)


@bot.event
async def on_member_join(member: discord.Member):
    await _check(member, trigger="join")


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    admin_changed = before.guild_permissions.administrator != after.guild_permissions.administrator
    avatar_changed = (
        getattr(before, "guild_avatar", None) != getattr(after, "guild_avatar", None)
        or getattr(before, "avatar", None) != getattr(after, "avatar", None)
    )
    # An admin changing their OWN avatar must re-fingerprint immediately.
    # check_member skips admins, so without this the new face stays unprotected
    # until the hourly TTL — a window an impersonator can copy into.
    if admin_changed or (avatar_changed and _is_protected(after)):
        _invalidate(after.guild.id)
    if avatar_changed:
        await _check(after, trigger="avatar_change")


@bot.event
async def on_user_update(before: discord.User, after: discord.User):
    # Global avatar swap propagates to every shared guild.
    if getattr(before, "avatar", None) == getattr(after, "avatar", None):
        return
    for guild in bot.guilds:
        m = guild.get_member(after.id)
        if m is None:
            continue
        if _is_protected(m):
            _invalidate(guild.id)
            continue
        await _check(m, trigger="global_avatar_change")


# ---- Slash commands (/shield) --------------------------------------------
# Manage Server is the default requirement (server owners can further
# restrict it themselves in Integrations settings). guild_only=True keeps
# every subcommand out of DMs, since all of them act on one specific server.
shield_group = app_commands.Group(
    name="shield",
    description="Configure Avatar Shield for this server",
    default_permissions=discord.Permissions(manage_guild=True),
    guild_only=True,
)

SCAN_MAX_MEMBERS = 500
SCAN_BATCH_SIZE = 10
SCAN_BATCH_DELAY_S = 1.0


@shield_group.command(name="setup", description="Set the channel where Avatar Shield posts alerts")
@app_commands.describe(channel="Text channel for impersonation alerts")
async def shield_setup(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
    guild = interaction.guild
    assert guild is not None  # guild_only=True guarantees this
    if not _can_post(guild, channel):
        await interaction.response.send_message(
            f"I can't post in {channel.mention} — grant my role View Channel, "
            "Send Messages, and Embed Links there (green ✅, not the gray neutral "
            "toggle), then run this again.",
            ephemeral=True,
        )
        return
    store.set_mod_log_channel(guild.id, channel.id)
    _mod_log_resolved.pop(guild.id, None)
    await interaction.response.send_message(
        f"✅ Alerts will post in {channel.mention}.", ephemeral=True
    )


@shield_group.command(name="protect", description="Protect an extra member's face, beyond Administrators")
@app_commands.describe(user="Member whose avatar should be protected")
async def shield_protect(interaction: discord.Interaction, user: discord.Member) -> None:
    guild = interaction.guild
    assert guild is not None
    store.add_protected_user(guild.id, user.id)
    _invalidate(guild.id)
    await interaction.response.send_message(
        f"🛡️ {user.mention}'s avatar is now protected in this server.", ephemeral=True
    )


@shield_group.command(name="unprotect", description="Stop protecting an extra member's face")
@app_commands.describe(user="Member to stop protecting")
async def shield_unprotect(interaction: discord.Interaction, user: discord.Member) -> None:
    guild = interaction.guild
    assert guild is not None
    store.remove_protected_user(guild.id, user.id)
    _invalidate(guild.id)
    await interaction.response.send_message(
        f"{user.mention} is no longer specially protected (Administrators still are).",
        ephemeral=True,
    )


@shield_group.command(name="mode", description="Alert-only, or auto-ban ban-tier matches")
@app_commands.describe(mode="alert = never touches anyone. ban = auto-bans ban-tier matches.")
@app_commands.choices(mode=[
    app_commands.Choice(name="alert — never bans, just posts", value="alert"),
    app_commands.Choice(name="ban — auto-bans ban-tier matches", value="ban"),
])
async def shield_mode(interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
    guild = interaction.guild
    assert guild is not None
    if mode.value == "ban":
        me = guild.me
        has_ban = bool(me and me.guild_permissions.ban_members)
        bot_pos = me.top_role.position if me else 0
        highest = max((r.position for r in guild.roles), default=0)
        allowed, message = ban_mode_check(has_ban, bot_pos, highest)
        if not allowed:
            await interaction.response.send_message(f"⚠️ {message}", ephemeral=True)
            return
        store.set_mode(guild.id, "ban")
        reply = "🚨 Mode set to **ban** — ban-tier matches are now auto-banned."
        if message:
            reply += f"\n\n⚠️ {message}"
        await interaction.response.send_message(reply, ephemeral=True)
        return
    store.set_mode(guild.id, "alert")
    await interaction.response.send_message(
        "👁️ Mode set to **alert** — I'll post matches for review and never touch anyone.",
        ephemeral=True,
    )


@shield_group.command(name="status", description="Show Avatar Shield's current configuration for this server")
async def shield_status(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    assert guild is not None
    await interaction.response.defer(ephemeral=True)
    channel = resolve_mod_log(guild)
    mode = resolve_mode(guild.id)
    threshold_ban, threshold_alert = resolve_thresholds(guild.id)
    cache = await _get_cache(guild)
    embed = discord.Embed(title="🛡️ Avatar Shield status", color=0x5865F2)
    embed.add_field(name="Alert channel", value=channel.mention if channel else "⚠️ not set — run `/shield setup`", inline=False)
    embed.add_field(name="Mode", value="🚨 ban" if mode == "ban" else "👁️ alert-only", inline=True)
    embed.add_field(name="Protected faces", value=str(len(cache.protected)), inline=True)
    embed.add_field(name="Thresholds", value=f"ban ≤{threshold_ban} · alert ≤{threshold_alert}", inline=True)
    embed.add_field(
        name="Members intent",
        value="✅ on" if intents.members else "❌ off — the bot can't see joins or avatar changes",
        inline=False,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


@shield_group.command(name="test", description="Post a sample alert card to confirm your setup")
async def shield_test(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    assert guild is not None
    channel = resolve_mod_log(guild)
    if channel is None:
        await interaction.response.send_message(
            "No alert channel is configured yet — run `/shield setup` first.", ephemeral=True
        )
        return
    threshold_ban, threshold_alert = resolve_thresholds(guild.id)
    embed = discord.Embed(
        title="👁️ Avatar similarity alert (TEST)",
        description="This is a sample alert card — no real match was found.",
        color=0xFDD835,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="User", value=f"{interaction.user.mention} (`{interaction.user}`)", inline=False)
    embed.add_field(name="Resembles protected member", value="example admin", inline=False)
    embed.add_field(name="pHash distance", value=f"**3** (ban ≤{threshold_ban}, alert ≤{threshold_alert})", inline=True)
    embed.add_field(name="Action", value="Alert only — review", inline=True)
    embed.set_footer(text="trigger: /shield test")
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message(
            f"I can't post in {channel.mention} — check my permissions there.", ephemeral=True
        )
        return
    await interaction.response.send_message(f"✅ Sample alert posted in {channel.mention}.", ephemeral=True)


@shield_group.command(name="scan", description="Re-check current members against protected faces right now")
async def shield_scan(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    assert guild is not None
    candidates = [m for m in guild.members if not m.bot and not _is_protected(m)][:SCAN_MAX_MEMBERS]
    await interaction.response.send_message(
        f"🔍 Scanning {len(candidates)} member(s) — this may take a minute...", ephemeral=True
    )
    hits = 0
    for i in range(0, len(candidates), SCAN_BATCH_SIZE):
        batch = candidates[i:i + SCAN_BATCH_SIZE]
        for m in batch:
            try:
                match = await check_member(m)
                if match is not None:
                    await _post_and_maybe_ban(m, match, trigger="manual_scan")
                    hits += 1
            except Exception as e:  # noqa: BLE001
                log.warning("scan check failed for %s: %s", m, e)
        if i + SCAN_BATCH_SIZE < len(candidates):
            await asyncio.sleep(SCAN_BATCH_DELAY_S)
    await interaction.followup.send(
        f"✅ Scan complete — checked {len(candidates)} member(s), {hits} alert(s) raised.",
        ephemeral=True,
    )


tree.add_command(shield_group)


def main() -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "DISCORD_BOT_TOKEN is not set. Copy .env.example to .env and fill it in, "
            "or export the variable before starting."
        )
    if MOD_LOG_CHANNEL_ID is None and not MOD_LOG_CHANNELS:
        log.info(
            "Neither MOD_LOG_CHANNEL_ID nor MOD_LOG_CHANNELS is set — servers that "
            "haven't run /shield setup will fall back to auto-discovering a channel "
            "named one of: %s",
            ", ".join(DISCOVER_CHANNEL_NAMES),
        )
    if PROTECTED_USER_IDS:
        log.info("PROTECTED_USER_IDS (global): %s", ", ".join(str(i) for i in sorted(PROTECTED_USER_IDS)))
    log.info("settings DB: %s", AVATAR_SHIELD_DB)
    bot.run(token)


if __name__ == "__main__":
    main()
