#!/usr/bin/env python3
"""Print the OAuth2 invite URL for the Avatar Shield bot.

Usage:
    python make_invite.py <APPLICATION_ID>          # with Ban Members (recommended)
    python make_invite.py <APPLICATION_ID> --alert  # alert-only, no Ban perm

APPLICATION_ID is the "Application ID" on your app's General Information page
in the Discord Developer Portal (it is NOT the bot token).
"""
import sys

# Discord permission bits (https://discord.com/developers/docs/topics/permissions)
VIEW_CHANNEL = 1 << 10          # 1024   — see channels/members
SEND_MESSAGES = 1 << 11         # 2048   — post the alert embed
EMBED_LINKS = 1 << 14           # 16384  — render the alert as an embed
READ_MESSAGE_HISTORY = 1 << 16  # 65536
BAN_MEMBERS = 1 << 2            # 4      — only needed when ENFORCE_BAN=true

ALERT_ONLY = VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | READ_MESSAGE_HISTORY
WITH_BAN = ALERT_ONLY | BAN_MEMBERS


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    app_id = sys.argv[1]
    perms = ALERT_ONLY if "--alert" in sys.argv[2:] else WITH_BAN
    tier = "alert-only" if perms == ALERT_ONLY else "with Ban Members"
    url = (
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={app_id}&permissions={perms}&scope=bot"
    )
    print(f"\nInvite URL ({tier}, permissions={perms}):\n\n{url}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
