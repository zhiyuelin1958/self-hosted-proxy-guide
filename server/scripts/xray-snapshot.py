#!/usr/bin/env python3
"""Snapshot the Xray binary, configuration, service units and rule data.

Install:  sudo install -m 700 xray-snapshot.py /usr/local/sbin/xray-snapshot
Usage:    sudo xray-snapshot [label]        -> prints the new snapshot directory
"""
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile

ROOT = pathlib.Path('/var/backups/xray')
ITEMS = ['usr/local/bin/xray', 'usr/local/etc/xray/config.json', 'etc/systemd/system/xray.service',
         'etc/systemd/system/xray.service.d', 'usr/local/share/xray']


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else 'manual'
    if not label.replace('-', '').replace('_', '').isalnum():
        raise SystemExit('Use an alphanumeric backup label')
    ROOT.mkdir(mode=0o700, exist_ok=True)
    os.chmod(ROOT, 0o700)
    now = datetime.datetime.now(datetime.timezone.utc)
    snapshot = ROOT/(now.strftime('%Y%m%dT%H%M%SZ')+'-'+label)
    snapshot.mkdir(mode=0o700)
    archive = snapshot/'xray-state.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for item in ITEMS:
            if pathlib.Path('/'+item).exists():
                tar.add('/'+item, arcname=item)
    manifest = {
        'created_utc': now.isoformat(),
        'version': subprocess.check_output(['/usr/local/bin/xray', 'version'], text=True).splitlines()[0],
        'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'members': ITEMS,
    }
    (snapshot/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    os.chmod(archive, 0o600)
    os.chmod(snapshot/'manifest.json', 0o600)
    print(snapshot)


if __name__ == '__main__':
    main()
