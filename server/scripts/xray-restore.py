#!/usr/bin/env python3
"""Validate and restore an Xray snapshot made by xray-snapshot.

Install:  sudo install -m 700 xray-restore.py /usr/local/sbin/xray-restore
Usage:    sudo xray-restore /var/backups/xray/<snapshot> --check   # verify only, changes nothing
          sudo xray-restore /var/backups/xray/<snapshot>           # snapshot current state, restore, restart

Restoring restarts Xray and interrupts every connection, including the one you may be using.
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path('/var/backups/xray').resolve()
PREFIXES = ['usr/local/bin/xray', 'usr/local/etc/xray/config.json', 'etc/systemd/system/xray.service',
            'usr/local/share/xray', 'etc/systemd/system/xray.service.d']
CONFIG = pathlib.Path('/usr/local/etc/xray/config.json')


def main():
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != '--check'):
        raise SystemExit('Usage: sudo xray-restore /var/backups/xray/<snapshot-directory> [--check]')
    snapshot = pathlib.Path(sys.argv[1]).resolve()
    if ROOT not in snapshot.parents:
        raise SystemExit('Snapshot must be inside /var/backups/xray')
    archive = snapshot/'xray-state.tar.gz'
    manifest = json.loads((snapshot/'manifest.json').read_text())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['archive_sha256']:
        raise SystemExit('Archive checksum mismatch')

    with tempfile.TemporaryDirectory(prefix='xray-restore-', dir=str(ROOT)) as tmp:
        stage = pathlib.Path(tmp)
        with tarfile.open(archive) as tar:
            for item in tar.getmembers():
                path = pathlib.PurePosixPath(item.name)
                if path.is_absolute() or '..' in path.parts or not (item.isfile() or item.isdir()):
                    raise SystemExit('Unexpected archive entry')
            tar.extractall(stage)
        env = os.environ.copy()
        env['XRAY_LOCATION_ASSET'] = str(stage/'usr/local/share/xray')
        subprocess.run([str(stage/'usr/local/bin/xray'), 'run', '-test', '-config',
                        str(stage/'usr/local/etc/xray/config.json')], env=env, check=True)
        if len(sys.argv) == 3:
            print('Snapshot checksum, extraction and Xray configuration validation passed. No live files changed.')
            return

        # Keep the live config's owner and mode (the installer's default service user differs between setups).
        config_stat = CONFIG.stat() if CONFIG.exists() else None
        before = subprocess.check_output(['/usr/local/sbin/xray-snapshot', 'before-restore'], text=True).strip()
        print('Saved current state:', before)
        for prefix in PREFIXES:
            source = stage/prefix
            if not source.exists():
                continue
            files = [source] if source.is_file() else [p for p in source.rglob('*') if p.is_file()]
            for file in files:
                destination = pathlib.Path('/')/file.relative_to(stage)
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(destination.name+'.restore-tmp')
                shutil.copy2(file, temporary)
                os.replace(temporary, destination)
        if config_stat is not None:
            os.chown(CONFIG, config_stat.st_uid, config_stat.st_gid)
            os.chmod(CONFIG, config_stat.st_mode & 0o777)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        # Restart a few seconds later so this command can finish reporting over SSH.
        subprocess.run(['systemd-run', '--unit=xray-restore-'+str(os.getpid()), '--on-active=3s',
                        '/bin/systemctl', 'restart', 'xray'], check=True)
        print('Validated and restored. Restart scheduled. After 5 seconds verify SSH, the xray service and the exit traces.')


if __name__ == '__main__':
    main()
