#!/usr/bin/env bash
# Print a VLESS + REALITY + Vision import link for one user.
# Usage: bash make-vless-link.sh <UUID> <SERVER_IP> <SNI_DOMAIN> <PUBLIC_KEY> <SHORT_ID> [NAME] [PORT]
set -euo pipefail

if [ "$#" -lt 5 ]; then
  sed -n '2,3p' "$0" >&2
  exit 1
fi
uuid="$1"; host="$2"; sni="$3"; pbk="$4"; sid="$5"; name="${6:-JP-User}"; port="${7:-443}"

printf 'vless://%s@%s:%s?encryption=none&flow=xtls-rprx-vision&security=reality&sni=%s&fp=chrome&pbk=%s&sid=%s&type=tcp&headerType=none#%s\n' \
  "$uuid" "$host" "$port" "$sni" "$pbk" "$sid" "$name"
