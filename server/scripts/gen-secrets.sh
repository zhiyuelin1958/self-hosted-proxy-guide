#!/usr/bin/env bash
# Generate UUIDs, one REALITY key pair and shortIds for N users.
# Usage: bash gen-secrets.sh [N]     (default N=2; requires xray and openssl)
# The output contains secrets: save it to a private local file, never commit it.
set -euo pipefail

n="${1:-2}"
command -v xray >/dev/null || { echo "xray not found; install it first (docs/04)" >&2; exit 1; }

keys="$(xray x25519)"
# Older Xray prints "Private key:/Public key:", newer prints "PrivateKey:/Password:" (Password = public key).
private="$(printf '%s\n' "$keys" | grep -iE '^private ?key:' | head -n1 | awk -F': *' '{print $2}')"
public="$(printf '%s\n' "$keys" | grep -iE '^(public ?key|password)' | head -n1 | awk -F': *' '{print $2}')"

echo "# REALITY"
echo "REALITY_PRIVATE_KEY=$private   # server only"
echo "REALITY_PUBLIC_KEY=$public     # client pbk"
echo
for i in $(seq 1 "$n"); do
  echo "# user$i"
  echo "UUID_$i=$(xray uuid)"
  echo "SHORT_ID_$i=$(openssl rand -hex 4)"
  echo
done
echo "# Raw x25519 output (for reference):"
printf '%s\n' "$keys" | sed 's/^/#   /'
