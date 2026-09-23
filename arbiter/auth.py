"""Who gets to change anything.

There is exactly one answer: a request that arrived from a tailnet peer. No
passphrase, no session, no token. The TCP peer address is the whole of it.

The public site still shows my library, leaderboards and round history, read
only. Rating, tiers, adding, importing and every other write need a peer
address, and there is no second way to get one. The same model as Spice.

`X-Forwarded-For` is never consulted and must never be. This app is reachable
through a public Cloudflare tunnel at the same moment it is reachable on the
tailnet, so a header claiming a 100.x address would hand every stranger on the
internet a peer's privileges.
"""

from __future__ import annotations

import ipaddress

from . import config

# Tailscale hands every node an address in this range (RFC 6598 shared address
# space). It is the tailnet's own block, and nothing routes into it from the
# public internet.
TAILNET = ipaddress.ip_network('100.64.0.0/10')


def from_tailnet(remote_addr: str) -> bool:
    """Did this request arrive from a tailnet peer?

    Judged on the TCP peer address only. Requests through the public tunnel
    reach the app over loopback (cloudflared runs on this machine), so they
    present as 127.0.0.1 and are strangers, exactly like anyone else out there.
    """
    if not config.TRUST_TAILNET or not remote_addr:
        return False
    try:
        return ipaddress.ip_address(remote_addr) in TAILNET
    except ValueError:
        return False


def is_open() -> bool:
    """The development hatch, off unless `ARBITER_OPEN=1`.

    With the peer address as the only credential, a laptop running the Vite dev
    server against a loopback API could never make a write, so the owner side of
    the app could not be built or tried out. It is an environment variable rather
    than a stored setting so a click can't leave it on, it defaults off, and
    `serve()` prints a warning whenever it is on.
    """
    return config.OPEN_ACCESS


def authorised(remote_addr: str) -> bool:
    """The single gate the API asks. Everything else is a stranger."""
    return is_open() or from_tailnet(remote_addr)
