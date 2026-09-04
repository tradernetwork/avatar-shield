#!/usr/bin/env python3
"""
Avatar Shield — standalone admin-impersonation detector (alert-only tier).

Scammers copy your admins' profile pictures to DM your members with fake
"support" / "airdrop" links. Name filters miss this — they change the name,
not the face. Avatar Shield fingerprints every server admin's avatar with a
perceptual hash and posts a mod-log alert when a member shows up wearing a
close copy — even a re-encoded or lightly-cropped one.

This free tier is ALERT-ONLY: it never bans, mutes, or touches anyone. It just
tells you. Flip ENFORCE_BAN=true once you trust it and the bot has Ban Members.

Setup
-----
1. pip install -r requirements.txt
2. Discord Developer Portal -> your app -> Bot -> enable the
   **Server Members Intent** (privileged). Without it the bot can't see joins
   or avatar changes.
3. Copy .env.example to .env and fill in:
     DISCORD_BOT_TOKEN=...        # bot token
     MOD_LOG_CHANNEL_ID=...       # default channel where alerts are posted
     MOD_LOG_CHANNELS=...         # optional per-guild override, guild:channel,...
     PROTECTED_USER_IDS=...       # optional extra faces to protect (non-admins)
     ENFORCE_BAN=false            # true = auto-ban ban-tier matches (needs Ban perm)
     THRESHOLD_BAN=6              # <= this distance = ban tier
     THRESHOLD_ALERT=10           # <= this distance = alert tier
4. python bot.py

The protected set is derived automatically from anyone with the Administrator
permission, plus anyone named in PROTECTED_USER_IDS — warmed at startup and
refreshed hourly. No database required; the cache lives in memory.
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
from PIL import Image, UnidentifiedImageError

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
    return member.id in PROTECTED_USER_IDS or _is_admin(member)


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
    people: list[tuple[discord.Member, str]] = []
    for m in guild.members:
        if m.bot or not _has_custom_avatar(m):
            continue
        if m.id in PROTECTED_USER_IDS:
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
    missing = PROTECTED_USER_IDS - {m.id for m, _ in people}
    if missing:
        log.warning(
            "guild %s (%s): PROTECTED_USER_IDS %s are not members here (or have no "
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

    return best_match(mhash, cache.protected, exclude_user_id=member.id)


# ---- Bot -----------------------------------------------------------------
intents = discord.Intents.default()
intents.members = True  # REQUIRED — join + avatar-change events
bot = discord.Client(intents=intents)


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

    Order: explicit per-guild mapping -> the global default (only if it really
    lives in *this* guild) -> a conventionally-named channel the bot can post
    in. The middle step is what stops a second server from silently swallowing
    every alert, because ``guild.get_channel`` on another guild's id is None.
    """
    cached = _mod_log_resolved.get(guild.id)
    if cached is not None:
        ch = _text_channel(guild, cached)
        if ch is not None:
            return ch
        _mod_log_resolved.pop(guild.id, None)  # deleted — re-resolve below

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

    banned = False
    if match.severity == "ban" and ENFORCE_BAN:
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

    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="User", value=f"{member.mention} (`{member}` · `{member.id}`)", inline=False)
    embed.add_field(name="Resembles protected member", value=target, inline=False)
    embed.add_field(name="pHash distance", value=f"**{match.distance}** (ban ≤{THRESHOLD_BAN}, alert ≤{THRESHOLD_ALERT})", inline=True)
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
        log.info(
            "guild %s (%s): mod-log=%s, protected=%d, enforce_ban=%s",
            guild.id, guild.name,
            f"#{channel.name}" if channel else "NONE",
            len(cache.protected), ENFORCE_BAN,
        )
        if STARTUP_NOTICE and channel is not None:
            mode = "auto-ban armed" if ENFORCE_BAN else "alert-only"
            embed = discord.Embed(
                title="🛡️ Avatar Shield online",
                description=(
                    f"Watching **{len(cache.protected)}** protected avatar"
                    f"{'' if len(cache.protected) == 1 else 's'} in **{guild.name}** — {mode}.\n"
                    f"Ban ≤{THRESHOLD_BAN} · alert ≤{THRESHOLD_ALERT} pHash distance."
                ),
                color=0x43A047,
                timestamp=datetime.now(timezone.utc),
            )
            try:
                await channel.send(embed=embed)
            except Exception as e:  # noqa: BLE001
                log.warning("startup notice failed in guild %s: %s", guild.id, e)


@bot.event
async def on_ready():
    global _warmed_up
    log.info(
        "Avatar Shield online as %s — %d guild(s), enforce_ban=%s",
        bot.user, len(bot.guilds), ENFORCE_BAN,
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


def main() -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "DISCORD_BOT_TOKEN is not set. Copy .env.example to .env and fill it in, "
            "or export the variable before starting."
        )
    if MOD_LOG_CHANNEL_ID is None and not MOD_LOG_CHANNELS:
        log.warning(
            "Neither MOD_LOG_CHANNEL_ID nor MOD_LOG_CHANNELS is set — the bot will "
            "try to auto-discover a channel named one of: %s",
            ", ".join(DISCOVER_CHANNEL_NAMES),
        )
    if PROTECTED_USER_IDS:
        log.info("PROTECTED_USER_IDS: %s", ", ".join(str(i) for i in sorted(PROTECTED_USER_IDS)))
    bot.run(token)


if __name__ == "__main__":
    main()
