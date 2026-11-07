"""Ask STUN servers which public address your UDP traffic appears from.

Usage: python stun_check.py [host:port ...]
Default servers: stun.l.google.com:19302 and stun.cloudflare.com:3478.

Run it with the client in rule mode and TUN enabled (UDP does not follow the HTTP system proxy).
If the STUN rules work, the mapped address equals the exit you expect, not your local public IP.
"""
import os
import socket
import struct
import sys

MAGIC = 0x2112A442
DEFAULT = ['stun.l.google.com:19302', 'stun.cloudflare.com:3478']


def query(host, port, timeout=3.0):
    transaction = os.urandom(12)
    request = struct.pack('!HHI', 0x0001, 0, MAGIC) + transaction   # Binding Request, no attributes
    address = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM)[0][4]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(request, address)
        data, _ = sock.recvfrom(2048)
    kind, length, magic = struct.unpack('!HHI', data[:8])
    if kind != 0x0101 or magic != MAGIC or data[8:20] != transaction:
        raise RuntimeError('unexpected STUN response')
    offset, end = 20, 20 + length
    while offset + 4 <= end:
        attr, size = struct.unpack('!HH', data[offset:offset + 4])
        value = data[offset + 4:offset + 4 + size]
        if attr in (0x0020, 0x0001) and value[1] == 0x01:            # (XOR-)MAPPED-ADDRESS, IPv4
            mapped_port, raw = struct.unpack('!H4s', value[2:8])
            if attr == 0x0020:
                mapped_port ^= MAGIC >> 16
                raw = bytes(a ^ b for a, b in zip(raw, struct.pack('!I', MAGIC)))
            return socket.inet_ntoa(raw), mapped_port
        offset += 4 + size + (-size % 4)
    raise RuntimeError('no mapped address in response')


def main():
    for server in sys.argv[1:] or DEFAULT:
        host, _, port = server.rpartition(':')
        try:
            ip, mapped = query(host, int(port))
            print(f'{server:<28} -> {ip}:{mapped}')
        except Exception as error:   # timeouts are expected when UDP is blocked
            print(f'{server:<28} -> failed: {error}')


if __name__ == '__main__':
    main()
