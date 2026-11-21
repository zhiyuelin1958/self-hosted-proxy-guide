"""Build iPhone profiles for the protected domain list; with --publish, activate them.

Usage (as root, from this directory):
  sudo python3 publish_profiles.py              # build and validate only
  sudo python3 publish_profiles.py --publish    # replace the live Envoy config and restart the relay

The domain list is read from ./protected-domains.json if present, else from /etc/<NAME>/domains.json.
Optional /etc/<NAME>/client-downloads.json maps more secret paths to files under /etc/<NAME>/profiles/,
e.g. {"/install/<token>/phone.yaml": "/etc/<NAME>/profiles/phone.yaml"} for the phone's Clash Mi profile.
All of these are reachable only through the VLESS tunnel.
"""
import argparse
import base64
import grp
import json
import os
import pathlib
import plistlib
import subprocess
import uuid

from relay_config import build_envoy_config
from relay_settings import NAME, PUBLIC_HOST, RELAY_PORT

ROOT = pathlib.Path('/etc')/NAME
RELAY_URL = 'https://'+PUBLIC_HOST+':'+str(RELAY_PORT)


def uid(user, item):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'local.'+NAME+'/'+user+'/'+item)).upper()


def save(path, content):
    path.write_bytes(content)
    path.chmod(0o640)
    os.chown(path, 0, grp.getgrnam(NAME).gr_gid)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    users = json.loads((pathlib.Path('/var/lib')/NAME/'credentials.json').read_text())
    domain_source = pathlib.Path(__file__).with_name('protected-domains.json')
    if not domain_source.exists():
        domain_source = ROOT/'domains.json'
    domains = json.loads(domain_source.read_text(encoding='utf-8-sig'))
    if not domains or not all(isinstance(item, str) and '.' in item for item in domains):
        raise RuntimeError('Protected domain list is empty or malformed')
    downloads, links = {}, {}
    for user in users:
        name = user['username']
        authorization = 'Basic '+base64.b64encode((name+':'+user['password']).encode()).decode()
        payload = {'PayloadType': 'com.apple.relay.managed', 'PayloadVersion': 1,
                   'PayloadIdentifier': 'local.'+NAME+'.'+name+'.rule',
                   'PayloadUUID': uid(name, 'rule'), 'RelayUUID': uid(name, 'relay'),
                   'PayloadDisplayName': '指定服务独立中继', 'MatchDomains': domains,
                   'AllowDNSFailover': False, 'UIToggleEnabled': True,
                   'Relays': [{'HTTP2RelayURL': RELAY_URL+'/',
                               'AdditionalHTTPHeaderFields': {'Proxy-Authorization': authorization}}]}
        profile = {'PayloadType': 'Configuration', 'PayloadVersion': 1,
                   'PayloadIdentifier': 'local.'+NAME+'.'+name, 'PayloadUUID': uid(name, 'profile'),
                   'PayloadDisplayName': '指定服务防直连（'+name+'）',
                   'PayloadDescription': '名单内域名经服务器独立中继、从第二出口连接。中继只能经代理隧道到达，代理客户端关闭或改用其他代理时，这些域名不可用。不含根证书或 MDM 管理。',
                   'PayloadContent': [payload]}
        filename = ROOT/'profiles'/(name+'.mobileconfig')
        save(filename, plistlib.dumps(profile, sort_keys=False))
        route = '/install/'+user['downloadToken']+'/relay.mobileconfig'
        downloads[route] = str(filename)
        downloads['/install/'+user['downloadToken']+'/test.mobileconfig'] = str(ROOT/'profiles'/(name+'-test.mobileconfig'))
        links[name] = RELAY_URL+route
    extra_file = ROOT/'client-downloads.json'
    if extra_file.exists():
        for url_path, filename in json.loads(extra_file.read_text()).items():
            if not url_path.startswith('/install/') or                     not pathlib.Path(filename).resolve().is_relative_to((ROOT/'profiles').resolve()):
                raise RuntimeError('Invalid client download entry: '+url_path)
            downloads[url_path] = filename
    save(ROOT/'domains.json', json.dumps(domains).encode())
    config = build_envoy_config(ROOT/'tls/fullchain.pem', ROOT/'tls/privkey.pem', users, downloads, diagnostics=True)
    candidate = ROOT/'envoy.candidate.json'
    save(candidate, json.dumps(config).encode())
    subprocess.run([str(pathlib.Path('/opt')/NAME/'bin'/'envoy'), '--mode', 'validate', '-c', str(candidate),
                    '--log-level', 'error'], check=True, stdout=subprocess.DEVNULL)
    if args.publish:
        backup = ROOT/'envoy.before-publish.json'
        if not backup.exists():
            save(backup, (ROOT/'envoy.json').read_bytes())
        candidate.replace(ROOT/'envoy.json')
        subprocess.run(['systemctl', 'restart', NAME+'.target'], check=True)
    # Download links contain secret tokens: send each one privately to its user.
    print(json.dumps({'published': args.publish, 'domains': len(domains), 'links': links}, ensure_ascii=False))


if __name__ == '__main__':
    main()
