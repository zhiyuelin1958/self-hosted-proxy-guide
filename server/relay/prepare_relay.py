"""Prepare the additive relay services. Does not open ports or start services.

Run on the entry server as root, from this directory:  sudo python3 prepare_relay.py
The main Xray configuration is only read (to copy the second-exit outbound), never changed.
"""
import base64
import grp
import hashlib
import json
import os
import pathlib
import plistlib
import secrets
import shutil
import subprocess
import urllib.request
import uuid

from relay_config import build_envoy_config
from relay_settings import EGRESS_TAG, NAME, PUBLIC_HOST, RELAY_PORT, TEST_DOMAIN, USERS

ROOT = pathlib.Path('/etc')/NAME
BIN = pathlib.Path('/opt')/NAME/'bin'
DATA = pathlib.Path('/var/lib')/NAME
MAIN_XRAY = pathlib.Path('/usr/local/etc/xray/config.json')
# Pinned Envoy release and its published SHA-256. Update both together when upgrading.
ENVOY_URL = 'https://github.com/envoyproxy/envoy/releases/download/v1.40.2/envoy-1.40.2-linux-x86_64'
ENVOY_SHA256 = '1d64506e25c1844f146162ddb2ece7010fa4e784faddb40a079021491f1f03cc'


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def write(filename, text, mode=0o640, group=None):
    path = pathlib.Path(filename)
    path.write_text(text)
    path.chmod(mode)
    if group is not None:
        os.chown(path, 0, group)


def identifier(user, key):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'local.'+NAME+'/'+user+'/'+key)).upper()


def test_profile(user):
    name = user['username']
    auth = base64.b64encode((name+':'+user['password']).encode()).decode()
    payload = {'PayloadType': 'com.apple.relay.managed', 'PayloadVersion': 1,
               'PayloadIdentifier': 'local.'+NAME+'.'+name+'.test.rule',
               'PayloadUUID': identifier(name, 'test-rule'), 'RelayUUID': identifier(name, 'test-relay'),
               'PayloadDisplayName': '独立中继测试', 'MatchDomains': [TEST_DOMAIN],
               'AllowDNSFailover': False, 'UIToggleEnabled': True,
               'Relays': [{'HTTP2RelayURL': 'https://'+PUBLIC_HOST+':'+str(RELAY_PORT)+'/',
                           'AdditionalHTTPHeaderFields': {'Proxy-Authorization': 'Basic '+auth}}]}
    root = {'PayloadType': 'Configuration', 'PayloadVersion': 1,
            'PayloadIdentifier': 'local.'+NAME+'.'+name+'.test',
            'PayloadUUID': identifier(name, 'test-profile'),
            'PayloadDisplayName': '独立中继测试（'+name+'）',
            'PayloadDescription': '仅测试 '+TEST_DOMAIN+'：经服务器独立中继、从第二出口连接。不含根证书或 MDM 管理。',
            'PayloadContent': [payload]}
    return plistlib.dumps(root, sort_keys=False).decode()


def main():
    if PUBLIC_HOST.startswith('203.0.113.'):
        raise RuntimeError('Edit relay_settings.py: PUBLIC_HOST is still the documentation placeholder')
    if (ROOT/'envoy.json').exists():
        raise RuntimeError('Relay is already prepared; refusing to overwrite its active configuration')
    if subprocess.run(['id', '-u', NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run('useradd', '--system', '--no-create-home', '--shell', '/usr/sbin/nologin', NAME)
    group = grp.getgrnam(NAME).gr_gid
    for directory in (ROOT, ROOT/'tls', ROOT/'profiles', BIN, DATA):
        directory.mkdir(parents=True, exist_ok=True)
    for directory in (ROOT, ROOT/'tls', ROOT/'profiles'):
        os.chown(directory, 0, group)
        directory.chmod(0o750)
    DATA.chmod(0o700)

    binary = BIN/'envoy'
    if not binary.exists():
        with urllib.request.urlopen(ENVOY_URL, timeout=60) as response, open(binary, 'wb') as target:
            shutil.copyfileobj(response, target)
    if hashlib.sha256(binary.read_bytes()).hexdigest() != ENVOY_SHA256:
        raise RuntimeError('Envoy release checksum mismatch')
    binary.chmod(0o755)

    credentials = DATA/'credentials.json'
    if credentials.exists():
        users = json.loads(credentials.read_text())
    else:
        users = [{'username': name, 'password': secrets.token_urlsafe(30),
                  'downloadToken': secrets.token_urlsafe(32)} for name in USERS]
        write(credentials, json.dumps(users), 0o600)
    downloads = {}
    for user in users:
        filename = ROOT/'profiles'/(user['username']+'-test.mobileconfig')
        write(filename, test_profile(user), group=group)
        downloads['/install/'+user['downloadToken']+'/test.mobileconfig'] = str(filename)

    original = MAIN_XRAY.read_bytes()
    main_config = json.loads(original)
    outbound = next((item for item in main_config['outbounds'] if item.get('tag') == EGRESS_TAG), None)
    if outbound is None:
        raise RuntimeError('No outbound tagged '+EGRESS_TAG+' in '+str(MAIN_XRAY)+' (see docs/06)')
    # The relay's own Xray: public RELAY_PORT -> Envoy in the namespace; everything Envoy sends -> second exit.
    # Port 18445 must NOT be opened in ufw or the cloud firewall.
    xray = {'log': {'loglevel': 'warning'}, 'inbounds': [
        {'tag': 'relay-transparent', 'listen': '0.0.0.0', 'port': 18445, 'protocol': 'dokodemo-door',
         'settings': {'network': 'tcp,udp', 'followRedirect': True},
         'streamSettings': {'sockopt': {'tproxy': 'tproxy'}}},
        {'tag': 'relay-ingress', 'listen': '0.0.0.0', 'port': RELAY_PORT, 'protocol': 'dokodemo-door',
         'settings': {'network': 'tcp', 'address': '10.231.252.2', 'port': 18443}}],
        'outbounds': [outbound, {'tag': 'relay-front', 'protocol': 'freedom'}, {'tag': 'relay-block', 'protocol': 'blackhole'}],
        'routing': {'rules': [
            {'type': 'field', 'inboundTag': ['relay-ingress'], 'outboundTag': 'relay-front'},
            {'type': 'field', 'ip': ['geoip:private'], 'outboundTag': 'relay-block'}]}}
    write(ROOT/'xray-egress.json', json.dumps(xray), 0o600)
    config = build_envoy_config(ROOT/'tls/fullchain.pem', ROOT/'tls/privkey.pem', users, downloads)
    write(ROOT/'envoy.json', json.dumps(config), group=group)

    source = pathlib.Path(__file__).parent
    for name in ('relay_network.py', 'relay_config.py'):
        write(BIN/name, (source/name).read_text(), 0o755)

    units = {
        NAME+'-network.service': f'''[Unit]
Description=Independent relay network namespace
After=network-online.target ufw.service
Wants=network-online.target
PartOf={NAME}.target
Before={NAME}-egress.service {NAME}-envoy.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python3 {BIN}/relay_network.py start
ExecStop=/usr/bin/python3 {BIN}/relay_network.py stop
''',
        NAME+'-egress.service': f'''[Unit]
Description=Independent relay second-exit egress and TLS forwarding
Requires={NAME}-network.service
After={NAME}-network.service
PartOf={NAME}.target
[Service]
ExecStart=/usr/local/bin/xray run -config {ROOT}/xray-egress.json
Restart=on-failure
RestartSec=3
''',
        NAME+'-envoy.service': f'''[Unit]
Description=Authenticated independent HTTP/2 relay
Requires={NAME}-network.service {NAME}-egress.service
After={NAME}-network.service {NAME}-egress.service
PartOf={NAME}.target
[Service]
User={NAME}
Group={NAME}
NetworkNamespacePath=/run/netns/{NAME}
BindReadOnlyPaths=/etc/netns/{NAME}/resolv.conf:/etc/resolv.conf
ExecStart={BIN}/envoy -c {ROOT}/envoy.json --concurrency 1 --disable-hot-restart --log-level warning
Restart=on-failure
RestartSec=3
LimitNOFILE=65536
''',
        NAME+'.target': f'''[Unit]
Description=Independent fail-closed iPhone relay
Requires={NAME}-network.service {NAME}-egress.service {NAME}-envoy.service
After={NAME}-network.service {NAME}-egress.service {NAME}-envoy.service
[Install]
WantedBy=multi-user.target
'''}
    for name, content in units.items():
        write(pathlib.Path('/etc/systemd/system')/name, content, 0o644)
    run('/usr/local/bin/xray', 'run', '-test', '-config', str(ROOT/'xray-egress.json'))
    run('systemctl', 'daemon-reload')
    print(json.dumps({'prepared': True, 'servicesStarted': False, 'portsOpened': False,
                      'mainXrayUnchanged': MAIN_XRAY.read_bytes() == original}))


if __name__ == '__main__':
    main()
