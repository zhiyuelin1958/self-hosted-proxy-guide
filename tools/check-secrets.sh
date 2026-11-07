#!/usr/bin/env bash
# Scan the repository for things that look like real secrets before committing.
# Usage: bash tools/check-secrets.sh [path ...]     (default: the repository root)
# Exit code 1 if anything suspicious is found. This is a safety net, not a guarantee.
set -u
cd "$(dirname "$0")/.." || exit 2
paths=("$@"); [ "${#paths[@]}" -eq 0 ] && paths=(.)
found=0

scan() {  # scan <description> <extended-regex>
  local hits
  hits="$(grep -rInE --exclude-dir=.git --exclude=check-secrets.sh "$2" "${paths[@]}" 2>/dev/null)"
  if [ -n "$hits" ]; then
    echo "== $1"; echo "$hits"; echo; found=1
  fi
}

scan "UUID (VLESS user id?)"            '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
scan "vless:// link with a real UUID"    'vless://[0-9a-fA-F]{8}-'
scan "Proxy-Authorization credentials"   'Basic [A-Za-z0-9+/]{12,}={0,2}'
scan "43-char base64url (x25519 key?)"   '(^|[^A-Za-z0-9_-])[A-Za-z0-9_-]{43}([^A-Za-z0-9_-]|$)'
scan "/install/<token> download link"    '/install/[A-Za-z0-9_-]{20,}'

# IPv4 addresses outside documentation, private and well-known public resolver ranges.
ips="$(grep -rIhoE --exclude-dir=.git --exclude=check-secrets.sh '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' "${paths[@]}" 2>/dev/null | sort -u)"
bad=""
for ip in $ips; do
  case "$ip" in
    203.0.113.*|198.51.100.*|192.0.2.*) ;;                      # RFC 5737 documentation
    10.*|127.*|192.168.*|169.254.*|0.0.0.0|0.*|224.*|240.*|255.*) ;;
    172.1[6-9].*|172.2[0-9].*|172.3[01].*) ;;
    100.6[4-9].*|100.[7-9][0-9].*|100.1[01][0-9].*|100.12[0-7].*) ;;
    1.1.1.1|8.8.8.8|223.5.5.5) ;;                               # public DoH resolvers used in docs
    *) bad="$bad $ip" ;;
  esac
done
if [ -n "$bad" ]; then
  echo "== IPv4 addresses to review:$bad"
  for ip in $bad; do grep -rInF --exclude-dir=.git --exclude=check-secrets.sh "$ip" "${paths[@]}"; done
  echo; found=1
fi

if [ "$found" -eq 0 ]; then echo "check-secrets: nothing suspicious found."; fi
exit "$found"
