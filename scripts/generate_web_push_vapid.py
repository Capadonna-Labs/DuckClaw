#!/usr/bin/env python3
"""Generate VAPID keys for DuckClaw Web Push notifications."""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric import ec


@dataclass(frozen=True)
class VapidKeys:
    public_key: str
    private_key: str
    subject: str


def _b64url_no_padding(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def generate_vapid_keys(subject: str) -> VapidKeys:
    private = ec.generate_private_key(ec.SECP256R1())
    numbers = private.private_numbers()
    public = numbers.public_numbers
    private_raw = int(numbers.private_value).to_bytes(32, "big")
    public_raw = b"\x04" + int(public.x).to_bytes(32, "big") + int(public.y).to_bytes(32, "big")
    return VapidKeys(
        public_key=_b64url_no_padding(public_raw),
        private_key=_b64url_no_padding(private_raw),
        subject=subject,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DuckClaw Web Push VAPID .env entries.")
    parser.add_argument(
        "--subject",
        default="mailto:admin@duckclaw.local",
        help="VAPID subject claim, usually mailto:admin@example.com or https://your-domain.",
    )
    args = parser.parse_args()
    keys = generate_vapid_keys(args.subject.strip() or "mailto:admin@duckclaw.local")
    print(f"WEB_PUSH_VAPID_PUBLIC_KEY={keys.public_key}")
    print(f"WEB_PUSH_VAPID_PRIVATE_KEY={keys.private_key}")
    print(f"WEB_PUSH_SUBJECT={keys.subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())