"""Install the IP certificate, its automatic renewal timer, and start the relay.

Run after `certbot certonly ... --cert-name <CERT_NAME>` has succeeded (docs/07):
  sudo python3 enable_renewal.py
"""
import os
import pathlib
import subprocess

from relay_settings import CERT_NAME, NAME

BIN = pathlib.Path('/opt')/NAME/'bin'


def main():
    source = pathlib.Path(__file__).with_name('relay_certificate_hook.py')
    hook = BIN/'relay_certificate_hook.py'
    hook.write_text(source.read_text().replace("NAME = 'app-relay'", "NAME = '"+NAME+"'")
                    .replace("CERT_NAME = 'app-relay-ip'", "CERT_NAME = '"+CERT_NAME+"'"))
    hook.chmod(0o755)
    deploy = pathlib.Path('/etc/letsencrypt/renewal-hooks/deploy')/NAME
    deploy.parent.mkdir(parents=True, exist_ok=True)
    deploy.write_text('#!/bin/sh\nif [ "${RENEWED_LINEAGE##*/}" = "'+CERT_NAME+'" ]; then\n'
                      '  exec /usr/bin/python3 '+str(hook)+'\nfi\n')
    deploy.chmod(0o755)
    units = {
        NAME+'-renew.service': f'''[Unit]
Description=Renew the independent relay IP certificate
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/opt/{NAME}/acme/bin/certbot renew --cert-name {CERT_NAME} --quiet
''',
        # IP certificates are short-lived (about 6 days), so check twice a day.
        NAME+'-renew.timer': '''[Unit]
Description=Check relay IP certificate renewal twice daily
[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=1800
Persistent=true
[Install]
WantedBy=timers.target
'''}
    for name, content in units.items():
        path = pathlib.Path('/etc/systemd/system')/name
        path.write_text(content)
        path.chmod(0o644)
    subprocess.run(['/usr/bin/python3', str(hook)],
                   env={**os.environ, 'RENEWED_LINEAGE': '/etc/letsencrypt/live/'+CERT_NAME}, check=True)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', NAME+'-renew.timer', NAME+'.target'], check=True)


if __name__ == '__main__':
    main()
