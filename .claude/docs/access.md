# Access: the network is the only credential (don't silently revert)

Same model as my Spice app (its `spice/auth.py` and `ops/README.md`).
Until 2026-09-23 anyone who found curator.yaqzan.dev could rate, re-tier and
delete. The Cloudflare account has no Access apps, so nothing in front of the app
was stopping them.

> A request from `100.64.0.0/10` is me. Everything else is a visitor, and visitors
> can read.

## What a stranger can and cannot reach

| Open to anyone (GET only) | Needs a tailnet peer address |
|---|---|
| `/api/health` (carries `authed`) | every POST/PUT/PATCH/DELETE on `/api` |
| `/api/types` | `/api/rank/set`: the rating surface, only there to be answered |
| `/api/items`, `/api/items/<id>` (without `notes`) | `/api/search`: spends my Plex token on the caller's behalf |
| `/api/rank/stats`, `leaderboard`, `review`, `history` | `/api/import/status`: names a path on this machine |
| the SPA's HTML/JS/CSS (posters load from Plex's CDN) | any `/api` path not on the public list |

- **Default-deny.** `PUBLIC_ENDPOINTS` in `arbiter/api.py` lists what is public;
  a new route is private until someone adds it there. `/api/items/<id>` is public
  through a prefix that accepts digits only, so `/api/items/1/purge-history` stays
  private. Paths are lowercased and stripped of a trailing slash before the check.
- **Mutations always need a peer**, whatever the path, because the public list is
  checked for GET and HEAD only.
- **The guard runs before the example-library 409**, so a stranger hears "read
  only" and never gets told how to start a library on my server.
- **`notes` are stripped for strangers** everywhere an item is serialised, and
  the "on disk" badge (`?ownership=1`) is only looked up for a peer.

## Judged on the TCP peer, never a header

`auth.from_tailnet(request.remote_addr)`. Never `X-Forwarded-For`,
`CF-Connecting-IP`, `Forwarded` or anything else a client can type. cloudflared
runs on this machine, so every request through the public tunnel arrives on
loopback and is a stranger. Whatever loopback can reach, the internet can reach.
`tests/access_test.py` sends forged headers from loopback and expects a 403.

## Two named binds, never 0.0.0.0

`api.serve()` listens on `ARBITER_HOST` (127.0.0.1) and on this machine's
Tailscale IPv4 (`tailscale ip -4`, or `ARBITER_TAILSCALE_IP`). Binding every
interface would let the LAN connect as well, and the whole guarantee is that the
socket proves where a request came from. No Tailscale on the box: the second bind
is skipped and everyone, me included, gets the read-only site. `--debug` serves
loopback only.

The public hostname can't be the way in, even from a phone on the tailnet: it
points at the tunnel, so the app still sees loopback. Changes are made at the
MagicDNS address `serve` prints (`http://<machine>.<tailnet>.ts.net:5002`). That
address is printed and nowhere else; it stays off the public API.

## Switches

- `ARBITER_TRUST_TAILNET` (default `1`). `0` refuses tailnet peers too, which
  makes the whole app read only.
- `ARBITER_OPEN=1` treats every caller as me. **Development only** (the Vite dev
  server talks to a loopback API, which can never write otherwise). Read from the
  real environment only, never from `.env`, because the service reads `.env` too
  and loopback is where the tunnel lands. `serve()` prints a warning while it's on
  and `/api/health` shows `authed: true, via_tailnet: false`. **Never set it in
  server.ps1.** Legacy `CURATOR_OPEN` / `CURATOR_TRUST_TAILNET` still work.

## Frontend

`App.tsx` reads `authed` from `/api/health` once. Anything but `authed: true` is a
visitor: Rank and Add leave the nav (their routes redirect to the leaderboard),
tier pickers render disabled, and the library, review and history actions are
hidden. There's a small "read only" mark by the logo and nothing else: no lock
screen, no passphrase, no copy explaining the tailnet. The server enforces all of
this; the frontend only hides controls that would 403.

## Trade-off I accepted

No way to change anything without Tailscale, me included. Don't add a shared code
or a login to get around it. Spice had one and removed it because a door on the
public site needs a lock screen and copy to explain it.
