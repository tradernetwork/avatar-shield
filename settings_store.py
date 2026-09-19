"""Per-guild settings persistence layer for Avatar Shield, backed by SQLite.

Avatar Shield's env vars (MOD_LOG_CHANNEL_ID, MOD_LOG_CHANNELS,
PROTECTED_USER_IDS, ENFORCE_BAN) remain the defaults/fallbacks for the
single server this bot already runs in. This store lets any other server
override them for itself via `/shield` slash commands, without an env edit
or redeploy. Resolution order (enforced by callers in bot.py, not here):
guild DB setting -> env fallback -> channel-name auto-discovery.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("avatar-shield.settings")


@dataclass
class GuildSettings:
    guild_id: int
    mod_log_channel_id: Optional[int] = None
    mode: Optional[str] = None  # None = no explicit setting saved; else "alert" | "ban"
    protected_user_ids: set[int] = field(default_factory=set)
    threshold_ban: Optional[int] = None
    threshold_alert: Optional[int] = None


def resolve_db_path(configured: str) -> str:
    """Resolve the database path, falling back to a local file if the configured directory is not writable."""
    directory = os.path.dirname(configured) or "."
    try:
        os.makedirs(directory, exist_ok=True)
        test_file = os.path.join(directory, ".avatar_shield_write_test")
        with open(test_file, "w") as f:
            f.write("")
        os.remove(test_file)
    except OSError:
        log.warning(
            "The directory for the configured settings path (%s) is not writable; "
            "settings will NOT survive a restart. Mount a persistent volume there. "
            "Falling back to ./avatar-shield.db",
            configured,
        )
        return "./avatar-shield.db"
    return configured


class SettingsStore:
    """Per-guild settings persistence backed by SQLite."""

    def __init__(self, db_path: str) -> None:
        """Initialize the settings store with a SQLite database path."""
        self.db_path = db_path
        self._lock = threading.Lock()
        try:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_schema()
        except (OSError, sqlite3.Error) as exc:
            log.error("Failed to initialize settings database at %s: %s", db_path, exc)
            raise

    def _init_schema(self) -> None:
        """Create the necessary tables if they do not exist."""
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS guild_settings ("
                "guild_id INTEGER PRIMARY KEY, "
                "mod_log_channel_id INTEGER, "
                "mode TEXT, "
                "threshold_ban INTEGER, "
                "threshold_alert INTEGER)"
            )
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS guild_protected_users ("
                "guild_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, "
                "PRIMARY KEY (guild_id, user_id))"
            )

    def get(self, guild_id: int) -> GuildSettings:
        """Retrieve the GuildSettings for a guild, returning an empty settings object if none are stored."""
        with self._lock:
            row = self._conn.execute(
                "SELECT mod_log_channel_id, mode, threshold_ban, threshold_alert "
                "FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
            protected = {
                user_id
                for (user_id,) in self._conn.execute(
                    "SELECT user_id FROM guild_protected_users WHERE guild_id = ?",
                    (guild_id,),
                ).fetchall()
            }
            if row is None:
                return GuildSettings(guild_id=guild_id, protected_user_ids=protected)
            mod_log_channel_id, mode, threshold_ban, threshold_alert = row
            return GuildSettings(
                guild_id=guild_id,
                mod_log_channel_id=mod_log_channel_id,
                mode=mode,
                threshold_ban=threshold_ban,
                threshold_alert=threshold_alert,
                protected_user_ids=protected,
            )

    def _ensure_row(self, guild_id: int) -> None:
        """Ensure a guild_settings row exists (caller must hold the lock)."""
        self._conn.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))

    def set_mod_log_channel(self, guild_id: int, channel_id: int) -> None:
        """Set the mod log channel ID for a guild."""
        with self._lock, self._conn:
            self._ensure_row(guild_id)
            self._conn.execute(
                "UPDATE guild_settings SET mod_log_channel_id = ? WHERE guild_id = ?",
                (channel_id, guild_id),
            )

    def set_mode(self, guild_id: int, mode: str) -> None:
        """Set the protection mode for a guild ('alert' or 'ban')."""
        if mode not in ("alert", "ban"):
            raise ValueError(f"invalid mode: {mode!r}")
        with self._lock, self._conn:
            self._ensure_row(guild_id)
            self._conn.execute(
                "UPDATE guild_settings SET mode = ? WHERE guild_id = ?",
                (mode, guild_id),
            )

    def set_thresholds(self, guild_id: int, threshold_ban: Optional[int], threshold_alert: Optional[int]) -> None:
        """Set the ban and alert thresholds for a guild."""
        with self._lock, self._conn:
            self._ensure_row(guild_id)
            self._conn.execute(
                "UPDATE guild_settings SET threshold_ban = ?, threshold_alert = ? WHERE guild_id = ?",
                (threshold_ban, threshold_alert, guild_id),
            )

    def add_protected_user(self, guild_id: int, user_id: int) -> None:
        """Add a user ID to the protected list for a guild."""
        with self._lock, self._conn:
            self._ensure_row(guild_id)
            self._conn.execute(
                "INSERT OR IGNORE INTO guild_protected_users (guild_id, user_id) VALUES (?, ?)",
                (guild_id, user_id),
            )

    def remove_protected_user(self, guild_id: int, user_id: int) -> None:
        """Remove a user ID from the protected list for a guild."""
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM guild_protected_users WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()
