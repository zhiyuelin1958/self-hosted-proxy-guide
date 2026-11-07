#!/usr/bin/env bash
# Run a command only if the current egress matches the expected IP and location.
#
# Usage: egress-guard <TRACE_URL> <EXPECTED_IP> <EXPECTED_LOC> -- <command> [args...]
#   TRACE_URL must return Cloudflare-style "key=value" lines, e.g. https://www.cloudflare.com/cdn-cgi/trace
#   EGRESS_GUARD_TIMEOUT (seconds, default 4) limits the check.
#
# This is a start-time check only. It does not protect a command that is already running.
set -u

if [ "$#" -lt 5 ] || [ "$4" != "--" ]; then
  sed -n '4,6p' "$0" >&2
  exit 2
fi
url="$1"; want_ip="$2"; want_loc="$3"; shift 4

trace="$(curl -fsS --max-time "${EGRESS_GUARD_TIMEOUT:-4}" "$url" 2>/dev/null)" || {
  echo "egress-guard: check failed or timed out ($url); not starting." >&2
  exit 1
}
got_ip="$(printf '%s\n' "$trace" | sed -n 's/^ip=//p' | head -n1)"
got_loc="$(printf '%s\n' "$trace" | sed -n 's/^loc=//p' | head -n1)"

if [ "$got_ip" = "$want_ip" ] && [ "$got_loc" = "$want_loc" ]; then
  echo "egress-guard: egress verified ($got_ip / $got_loc)." >&2
  exec "$@"
fi
echo "egress-guard: unexpected egress '${got_ip:-none} / ${got_loc:-none}', expected '$want_ip / $want_loc'; not starting." >&2
exit 1
