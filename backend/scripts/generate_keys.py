#!/usr/bin/env python3
"""
Generate an RS256 key pair for JWT signing and print the base64-encoded
values ready to paste into .env.

Usage (inside Docker):
    docker compose exec backend python scripts/generate_keys.py

Usage (locally, requires: pip install cryptography):
    python backend/scripts/generate_keys.py
"""

import base64
import sys

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError:
    sys.exit("cryptography package not found. Run: pip install cryptography")

private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
public_pem = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

b64_private = base64.b64encode(private_pem).decode()
b64_public = base64.b64encode(public_pem).decode()

print("# ---- Add these lines to your .env file ----")
print(f"JWT_PRIVATE_KEY={b64_private}")
print(f"JWT_PUBLIC_KEY={b64_public}")
print("# --------------------------------------------")
print("\nDone. Keep JWT_PRIVATE_KEY secret — anyone with it can forge tokens.")
