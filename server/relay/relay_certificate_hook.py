"""Install a renewed IP certificate and reload only the independent relay.

Called by certbot's deploy hook (and once by enable_renewal.py). The two constants
below are rewritten by enable_renewal.py from relay_settings.py.
"""
import grp
import os
import pathlib
import shutil
import subprocess

NAME = 'app-relay'
CERT_NAME = 'app-relay-ip'


def main():
    lineage = pathlib.Path(os.environ.get('RENEWED_LINEAGE', '/etc/letsencrypt/live/'+CERT_NAME))
    if lineage.name != CERT_NAME:
        raise RuntimeError('Unexpected certificate lineage')
    group = grp.getgrnam(NAME).gr_gid
    destination = pathlib.Path('/etc')/NAME/'tls'
    for name in ('fullchain.pem', 'privkey.pem'):
        temporary = destination/(name+'.new')
        shutil.copyfile(lineage/name, temporary)
        os.chown(temporary, 0, group)
        temporary.chmod(0o640)
        temporary.replace(destination/name)
    subprocess.run(['systemctl', 'try-restart', NAME+'-envoy.service'], check=True)


if __name__ == '__main__':
    main()
