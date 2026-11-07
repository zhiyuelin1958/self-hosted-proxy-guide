"""Owned network namespace for the independent relay, run by systemd as root.

Everything leaving the namespace is marked and handed by TPROXY to the relay's own
Xray (port 18445), whose only outbound is the second exit. The namespace therefore
has no direct path to the Internet: if the second exit is down, connections fail.
"""
import json
import pathlib
import shutil
import subprocess
import sys

NS, HOST, PEER, CHAIN = 'app-relay', 'rly-host', 'rly-ns', 'APP_RELAY'
TABLE, PRIORITY = '65401', '10010'
STATE = pathlib.Path('/run/app-relay-network.json')


def run(*args, check=True):
    value = subprocess.run(args, capture_output=True, text=True)
    if check and value.returncode:
        raise RuntimeError(args[0]+': '+value.stderr[-600:])
    return value


def stop():
    if not STATE.exists():
        return
    owned = json.loads(STATE.read_text())
    if 'jump' in owned:
        run('iptables', '-t', 'mangle', '-D', 'PREROUTING', '-i', HOST, '-s', '10.231.252.2/32', '-j', CHAIN, check=False)
    if 'input' in owned:
        run('iptables', '-D', 'INPUT', '-i', HOST, '-s', '10.231.252.2/32', '-m', 'mark', '--mark', TABLE, '-j', 'ACCEPT', check=False)
    if 'chain' in owned:
        run('iptables', '-t', 'mangle', '-F', CHAIN, check=False)
        run('iptables', '-t', 'mangle', '-X', CHAIN, check=False)
    if 'rule' in owned:
        run('ip', 'rule', 'del', 'fwmark', TABLE, 'table', TABLE, 'priority', PRIORITY, check=False)
    if 'route' in owned:
        run('ip', 'route', 'flush', 'table', TABLE, check=False)
    if 'namespace' in owned:
        run('ip', 'netns', 'del', NS, check=False)
    if 'link' in owned:
        run('ip', 'link', 'del', HOST, check=False)
    if 'resolver' in owned:
        shutil.rmtree(pathlib.Path('/etc/netns')/NS, ignore_errors=True)
    STATE.unlink()


def start():
    if STATE.exists():
        raise RuntimeError('Relay network is already owned; stop its service before restarting')
    rules = json.loads(run('ip', '-j', 'rule', 'list').stdout)
    if any(str(rule.get('table')) == TABLE or str(rule.get('priority')) == PRIORITY for rule in rules):
        raise RuntimeError('Relay policy routing identifiers are already in use')
    if run('ip', 'link', 'show', HOST, check=False).returncode == 0:
        raise RuntimeError('Relay veth name is already in use')
    owned = []

    def mark(name):
        owned.append(name)
        STATE.write_text(json.dumps(owned))
        STATE.chmod(0o600)

    try:
        run('ip', 'netns', 'add', NS)
        mark('namespace')
        run('ip', 'link', 'add', HOST, 'type', 'veth', 'peer', 'name', PEER)
        mark('link')
        run('ip', 'link', 'set', PEER, 'netns', NS)
        run('ip', 'addr', 'add', '10.231.252.1/30', 'dev', HOST)
        run('ip', 'link', 'set', HOST, 'up')
        run('ip', 'netns', 'exec', NS, 'ip', 'addr', 'add', '10.231.252.2/30', 'dev', PEER)
        run('ip', 'netns', 'exec', NS, 'ip', 'link', 'set', PEER, 'up')
        run('ip', 'netns', 'exec', NS, 'ip', 'link', 'set', 'lo', 'up')
        run('ip', 'netns', 'exec', NS, 'ip', 'route', 'add', 'default', 'via', '10.231.252.1')
        run('ip', 'netns', 'exec', NS, 'iptables', '-A', 'OUTPUT', '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT')
        for private in ('0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16',
                        '172.16.0.0/12', '192.168.0.0/16', '224.0.0.0/4', '240.0.0.0/4'):
            run('ip', 'netns', 'exec', NS, 'iptables', '-A', 'OUTPUT', '-d', private, '-j', 'REJECT')
        resolver = pathlib.Path('/etc/netns')/NS
        resolver.mkdir(parents=True)
        mark('resolver')
        (resolver/'resolv.conf').write_text('nameserver 1.1.1.1\noptions timeout:2 attempts:2\n')
        run('ip', 'rule', 'add', 'fwmark', TABLE, 'table', TABLE, 'priority', PRIORITY)
        mark('rule')
        run('ip', 'route', 'add', 'local', '0.0.0.0/0', 'dev', 'lo', 'table', TABLE)
        mark('route')
        run('iptables', '-t', 'mangle', '-N', CHAIN)
        mark('chain')
        run('iptables', '-t', 'mangle', '-A', CHAIN, '-d', '10.231.252.0/30', '-j', 'RETURN')
        for protocol in ('tcp', 'udp'):
            run('iptables', '-t', 'mangle', '-A', CHAIN, '-p', protocol, '-j', 'TPROXY',
                '--on-ip', '127.0.0.1', '--on-port', '18445', '--tproxy-mark', TABLE)
        run('iptables', '-t', 'mangle', '-I', 'PREROUTING', '1', '-i', HOST, '-s', '10.231.252.2/32', '-j', CHAIN)
        mark('jump')
        run('iptables', '-I', 'INPUT', '1', '-i', HOST, '-s', '10.231.252.2/32', '-m', 'mark', '--mark', TABLE, '-j', 'ACCEPT')
        mark('input')
    except Exception:
        stop()
        raise


if __name__ == '__main__':
    {'start': start, 'stop': stop}[sys.argv[1]]()
