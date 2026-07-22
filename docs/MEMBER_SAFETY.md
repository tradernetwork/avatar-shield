# 🕳️ The impersonation loophole & how to close it

Avatar Shield auto-bans impersonators who **join your server**. But the most
determined scammers never join — and understanding why is the difference between
a member who gets drained and one who blocks and moves on.

## How the loophole works

1. A throwaway alt quietly joins your server and **scrapes the member list**.
2. The scammer sets up a **second account** that copies an admin's name and
   profile picture. This account **never joins your server.**
3. It **DMs your members directly** — "claim your allocation," "verify your
   wallet," "join my private group" — from outside.

Because that second account never joins, **no server bot ever sees it.**
Discord does not let bots read, scan, or block DMs sent by accounts they can't
observe — that's a hard platform **privacy** rule, not a limitation we can code
around. Avatar Shield (or any bot) simply cannot touch an outside DM.

## 🔑 The one rule that beats it

There is a dead-simple tell that works every single time:

> ### ✅ A real admin shares **this server** with you.
> If someone DMs you claiming to be staff, open their profile and check
> **"Mutual Servers."** If they don't share this server with you → **they are an
> impersonator.** Block and report. No exceptions.

An outside impersonator can copy a face and a name, but they **cannot fake being
in a server they never joined.** The mutual-servers list doesn't lie.

Two more habits that make members bulletproof:

- 🚫 **Admins never DM you first** — not for giveaways, allocations, "verification,"
  support, or anything. If a "mod" slides into your DMs, assume scam.
- 💸 **No real admin will ever** ask for a wallet seed phrase, a payment to
  "unlock" something, a login code, or connection to a random dApp.

---

## 📋 Copy-paste this into your server

Drop this into `#announcements`, `#start-here`, or a pinned `#read-me` message.
Edit the bracketed bits.

```
🛡️ **HOW TO SPOT A FAKE ADMIN — 30-SECOND READ**

Scammers copy our admins' names AND profile pictures to DM you fake
"allocations," "verifications," and "private groups." Here's how to never fall
for it:

✅ **CHECK MUTUAL SERVERS.** Real staff are IN this server with you. Tap the
person's profile → look at **"Mutual Servers."** If [YOUR SERVER NAME] isn't
listed, it's a **fake** — block and report. This works 100% of the time.

🚫 **We NEVER DM you first.** No admin will ever message you first about
giveaways, allocations, "verifying" a wallet, or support. Ever.

💸 **We NEVER ask for** seed phrases, payments to "unlock" anything, login
codes, or you to connect a wallet to a random link.

If you get a suspicious DM: **don't reply, don't click** — screenshot it and
post in [#report-a-scam] or ping a mod here in the server (where we can see the
real vs. fake).

🛡️ *This server is protected by Avatar Shield — anyone who copies an admin's
picture and joins gets auto-removed. But the smart ones DM from outside, so the
rule above is your real armor.*
```

---

## 🔨 Once auto-ban is on

When you flip `ENFORCE_BAN=true`, Avatar Shield handles the **in-server** side
automatically — copycats who join get banned before they can DM anyone from a
shared-server context. That already removes the scariest version of the attack
(the one where the fake *does* share your server, so mutual-servers wouldn't
save your members).

What's left after that is purely the **outside-DM** version above — which is
exactly what the mutual-servers rule is for. Pin the notice, and you've covered
both halves: 🤖 the bot guards the door, 🧠 your members guard their DMs.
