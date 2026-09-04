#!/usr/bin/env python3
"""Print the OAuth2 invite URL for the Avatar Shield bot.

Usage:
    python make_invite.py <APPLICATION_ID>                # with Ban Members (recommended)
    python make_invite.py <APPLICATION_ID> --alert        # alert-only, no Ban perm
    python make_invite.py <APPLICATION_ID> --guild <ID>   # pre-select one server

APPLICATION_ID is the "Application ID" on your app's General Information page
in the Discord Developer Portal (it is NOT the bot token).

--guild pre-selects the target server in the authorize screen and locks the
dropdown, so handing the link to a server owner can't land the bot in the wrong
place. You still need Manage Server in that server to accept it.
"""
import sys
from urllib.parse import urlencode

# Discord permission bits (https://discord.com/developers/docs/topics/permissions)
VIEW_CHANNEL = 1 << 10          # 1024   — see channels/members
SEND_MESSAGES = 1 << 11         # 2048   — post the alert embed
EMBED_LINKS = 1 << 14           # 16384  — render the alert as an embed
READ_MESSAGE_HISTORY = 1 << 16  # 65536
BAN_MEMBERS = 1 << 2            # 4      — only needed when ENFORCE_BAN=true

ALERT_ONLY = VIEW_CHANNEL | SEND_MESSAGES | EMBED_LINKS | READ_MESSAGE_HISTORY
WITH_BAN = ALERT_ONLY | BAN_MEMBERS


def build_url(app_id: str, *, alert_only: bool = False, guild_id: str | None = None) -> str:
    params = {
        "client_id": app_id,
        "permissions": ALERT_ONLY if alert_only else WITH_BAN,
        "scope": "bot",
    }
    if guild_id:
        params["guild_id"] = guild_id
        params["disable_guild_select"] = "true"
    return "https://discord.com/api/oauth2/authorize?" + urlencode(params)


def main(argv: list[str]) -> int:
    args = argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 1

    app_id = args[0]
    rest = args[1:]
    alert_only = "--alert" in rest

    guild_id = None
    if "--guild" in rest:
        i = rest.index("--guild")
        if i + 1 >= len(rest):
            print("error: --guild needs a server ID\n")
            print(__doc__)
            return 1
        guild_id = rest[i + 1]

    if not app_id.isdigit():
        print(f"error: {app_id!r} is not an Application ID (it should be all digits).\n")
        print(__doc__)
        return 1

    url = build_url(app_id, alert_only=alert_only, guild_id=guild_id)
    tier = "alert-only" if alert_only else "with Ban Members"
    perms = ALERT_ONLY if alert_only else WITH_BAN
    scope = f", pinned to server {guild_id}" if guild_id else ""
    print(f"\nInvite URL ({tier}, permissions={perms}{scope}):\n\n{url}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
