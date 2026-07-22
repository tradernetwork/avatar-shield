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
     MOD_LOG_CHANNEL_ID=...       # channel where alerts are posted
     ENFORCE_BAN=false            # true = auto-ban ban-tier matches (needs Ban perm)
     THRESHOLD_BAN=6              # <= this distance = ban tier
     THRESHOLD_ALERT=10           # <= this distance = alert tier
4. python bot.py

The admin fingerprint set is derived automatically from anyone with the
Administrator permission, refreshed hourly. No database required — the cache
lives in memory.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import discord
import imagehash
from PIL import Image, UnidentifiedImageError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("avatar-shield")

# ---- Config (env-driven) -------------------------------------------------
TOKEN = os.environ["DISCORD_BOT_TOKEN"]
MOD_LOG_CHANNEL_ID = int(os.environ["MOD_LOG_CHANNEL_ID"])
ENFORCE_BAN = os.environ.get("ENFORCE_BAN", "false").lower() in ("1", "true", "yes")
THRESHOLD_BAN = int(os.environ.get("THRESHOLD_BAN", "6"))
THRESHOLD_ALERT = int(os.environ.get("THRESHOLD_ALERT", "10"))

# ---- pHash constants -----------------------------------------------------
PHASH_SIZE = 8                    # 8x8 = 64-bit fingerprint
ADMIN_HASH_TTL_S = 3600           # refresh admin fingerprints hourly
MAX_AVATAR_BYTES = 8 * 1024 * 1024
AVATAR_ASSET_SIZE = 128
AVATAR_ASSET_FORMAT = "png"


# ---- Cache types ---------------------------------------------------------
@dataclass
class _AdminEntry:
    user_id: int
    phash: imagehash.ImageHash


@dataclass
class _GuildCache:
    admins: list[_AdminEntry] = field(default_factory=list)
    refreshed_at: float = 0.0


@dataclass(frozen=True)
class AvatarMatch:
    impersonated_user_id: int
    distance: int
    severity: str  # 'ban' | 'alert'


_cache: dict[int, _GuildCache] = {}


def _invalidate(guild_id: int) -> None:
    _cache.pop(guild_id, None)


def _is_default_avatar(user: discord.abc.User) -> bool:
    # Users who never uploaded an avatar have .avatar is None. Never
    # fingerprint defaults — every default collides with every other one.
    return getattr(user, "avatar", None) is None


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


def _phash_from_bytes(data: bytes) -> Optional[imagehash.ImageHash]:
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            return imagehash.phash(im, hash_size=PHASH_SIZE)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


async def _compute_phash(member: discord.abc.User) -> Optional[imagehash.ImageHash]:
    if _is_default_avatar(member):
        return None
    data = await _fetch_avatar_bytes(member.display_avatar)
    if data is None:
        return None
    # imagehash/PIL are CPU-bound — keep them off the event loop.
    return await asyncio.to_thread(_phash_from_bytes, data)


# ---- Admin cache ---------------------------------------------------------
async def _refresh_admins(guild: discord.Guild) -> _GuildCache:
    cache = _GuildCache(refreshed_at=time.time())
    admins: list[discord.Member] = []
    for m in guild.members:
        if m.bot or _is_default_avatar(m):
            continue
        try:
            if m.guild_permissions.administrator:
                admins.append(m)
        except AttributeError:
            continue

    if admins:
        results = await asyncio.gather(
            *(_compute_phash(m) for m in admins), return_exceptions=True
        )
        for m, r in zip(admins, results):
            if isinstance(r, imagehash.ImageHash):
                cache.admins.append(_AdminEntry(user_id=m.id, phash=r))

    log.info("guild %s: cached %d admin fingerprints", guild.id, len(cache.admins))
    _cache[guild.id] = cache
    return cache


async def _get_cache(guild: discord.Guild) -> _GuildCache:
    c = _cache.get(guild.id)
    if c is not None and (time.time() - c.refreshed_at) < ADMIN_HASH_TTL_S:
        return c
    return await _refresh_admins(guild)


# ---- Match ---------------------------------------------------------------
async def check_member(member: discord.Member) -> Optional[AvatarMatch]:
    if member.bot or _is_default_avatar(member):
        return None
    try:
        if member.guild_permissions.administrator:
            return None  # admins ARE the protected set
    except AttributeError:
        pass

    cache = await _get_cache(member.guild)
    if not cache.admins:
        return None

    mhash = await _compute_phash(member)
    if mhash is None:
        return None

    best: Optional[AvatarMatch] = None
    for entry in cache.admins:
        if entry.user_id == member.id:
            continue
        distance = mhash - entry.phash
        if distance > THRESHOLD_ALERT:
            continue
        severity = "ban" if distance <= THRESHOLD_BAN else "alert"
        if best is None or distance < best.distance:
            best = AvatarMatch(entry.user_id, distance, severity)
    return best


# ---- Bot -----------------------------------------------------------------
intents = discord.Intents.default()
intents.members = True  # REQUIRED — join + avatar-change events
bot = discord.Client(intents=intents)


async def _post_and_maybe_ban(member: discord.Member, match: AvatarMatch, trigger: str) -> None:
    channel = member.guild.get_channel(MOD_LOG_CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        log.warning("mod-log channel %s not found in guild %s", MOD_LOG_CHANNEL_ID, member.guild.id)
        return

    impersonated = member.guild.get_member(match.impersonated_user_id)
    target = f"{impersonated.mention} (`{impersonated}`)" if impersonated else f"user {match.impersonated_user_id}"

    banned = False
    if match.severity == "ban" and ENFORCE_BAN:
        try:
            await member.ban(
                reason=f"Avatar impersonation of admin {match.impersonated_user_id} "
                       f"(pHash distance={match.distance}, trigger={trigger})",
                delete_message_days=1,
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
    embed.add_field(name="Resembles admin", value=target, inline=False)
    embed.add_field(name="pHash distance", value=f"**{match.distance}** (ban ≤{THRESHOLD_BAN}, alert ≤{THRESHOLD_ALERT})", inline=True)
    embed.add_field(name="Action", value=action, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"trigger: {trigger}")
    try:
        await channel.send(embed=embed)
    except Exception as e:  # noqa: BLE001
        log.warning("mod-log post failed: %s", e)


async def _check(member: discord.Member, *, trigger: str) -> None:
    try:
        match = await check_member(member)
        if match is not None:
            await _post_and_maybe_ban(member, match, trigger)
    except Exception as e:  # noqa: BLE001
        log.warning("check failed for %s: %s", member, e)


@bot.event
async def on_ready():
    log.info("Avatar Shield online as %s — enforce_ban=%s", bot.user, ENFORCE_BAN)


@bot.event
async def on_member_join(member: discord.Member):
    await _check(member, trigger="join")


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.guild_permissions.administrator != after.guild_permissions.administrator:
        _invalidate(after.guild.id)  # admin set changed — drop cache
    avatar_changed = (
        getattr(before, "guild_avatar", None) != getattr(after, "guild_avatar", None)
        or getattr(before, "avatar", None) != getattr(after, "avatar", None)
    )
    if avatar_changed:
        await _check(after, trigger="avatar_change")


@bot.event
async def on_user_update(before: discord.User, after: discord.User):
    # Global avatar swap propagates to every shared guild.
    if getattr(before, "avatar", None) == getattr(after, "avatar", None):
        return
    for guild in bot.guilds:
        m = guild.get_member(after.id)
        if m is not None:
            await _check(m, trigger="global_avatar_change")


if __name__ == "__main__":
    bot.run(TOKEN)
