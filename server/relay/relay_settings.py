"""Settings shared by the relay scripts. Edit before running prepare_relay.py."""

# Public IPv4 of the entry server. The iPhone connects to https://PUBLIC_HOST:RELAY_PORT/.
PUBLIC_HOST = '203.0.113.10'
RELAY_PORT = 8443

# Tag of the second-exit outbound in /usr/local/etc/xray/config.json (chapter 06).
EGRESS_TAG = 'exit2'

# One credential set and one profile per user.
USERS = ('user1', 'user2')

# Name used for the system user, directories, systemd units and profile identifiers.
NAME = 'app-relay'

# Certbot certificate name used in docs/07 (certbot certonly ... --cert-name CERT_NAME).
CERT_NAME = 'app-relay-ip'

# Domain used by the test profile before the real protected list is published.
TEST_DOMAIN = 'www.cloudflare.com'
