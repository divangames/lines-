#!/usr/bin/env python3
"""Refresh the Xray domain filter atomically, preserving the previous list on errors."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path('/var/lib/linea-filter')
URL = 'https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/multi-onlydomains.txt'
os.environ['XRAY_LOCATION_ASSET'] = str(BASE)


def varint(value):
    output = bytearray()
    while value > 127:
        output.append((value & 127) | 128)
        value >>= 7
    output.append(value)
    return bytes(output)


def field(number, payload):
    return varint(number * 8 + 2) + varint(len(payload)) + payload


def geosite(domains):
    site = field(1, b'ADS') + b''.join(field(2, b'\x08\x02' + field(2, name.encode('ascii'))) for name in domains)
    return field(1, site)


def main():
    request = urllib.request.Request(URL, headers={'User-Agent': 'Linea-filter/1'})
    raw = urllib.request.urlopen(request, timeout=60).read(32_000_000)
    domains = sorted(set(line.strip().lower() for line in raw.decode('utf-8-sig').splitlines()
                         if line.strip() and not line.startswith(('#', '!'))))
    if not 50_000 <= len(domains) <= 1_000_000:
        raise ValueError('Unexpected domain count; previous filter retained')
    valid = re.compile(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$')
    if any(not valid.fullmatch(name) for name in domains):
        raise ValueError('Invalid domain list; previous filter retained')
    if any(name in domains for name in ('com', 'ru', 'xn--p1ai', 'example.com', 'youtube.com', 'google.com')):
        raise ValueError('Protected domain in filter; previous filter retained')
    data = geosite(domains)
    asset = 'linea-ads-' + hashlib.sha256(data).hexdigest()[:16] + '.dat'
    target = BASE / asset
    status_path = BASE / 'filter-status.json'
    previous = json.loads(status_path.read_text()) if status_path.exists() else {}
    if previous.get('asset') == asset and target.exists():
        print('Filter unchanged:', len(domains), 'domains')
        return
    candidate = BASE / 'linea-ads.next.dat'
    candidate.write_bytes(data)
    candidate.chmod(0o644)
    # Validate the data with the installed Xray parser before replacing it.
    with tempfile.TemporaryDirectory(prefix='linea-filter-') as directory:
        config = Path(directory) / 'test.json'
        config.write_text(json.dumps({'outbounds': [{'protocol': 'blackhole', 'tag': 'blocked'}],
            'routing': {'rules': [{'type': 'field', 'domain': ['ext:' + candidate.name + ':ads'], 'outboundTag': 'blocked'}]}}))
        checked = subprocess.run(['/opt/linea/bin/xray', 'run', '-test', '-config', str(config)], capture_output=True, text=True)
        if checked.returncode:
            raise RuntimeError('Filter validation failed: ' + checked.stdout + checked.stderr)
    os.replace(candidate, target)
    startup_assets = set()
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'linea-xray']).returncode == 0:
        current = json.loads(Path('/var/lib/linea/xray.json').read_text())
        startup_assets = {value.split(':')[1] for rule in current.get('routing', {}).get('rules', [])
                          for value in rule.get('domain', []) if value.startswith('ext:linea-ads')}
        # New names avoid Xray's cache of the previous GeoSite matcher.
        for rule in current.get('routing', {}).get('rules', []):
            if any(value.startswith('ext:linea-ads') for value in rule.get('domain', [])):
                rule['domain'] = ['ext:' + asset + ':ads']
        if 'RoutingService' in current.get('api', {}).get('services', []):
            with tempfile.TemporaryDirectory(prefix='linea-routing-') as directory:
                path = Path(directory) / 'routing.json'
                path.write_text(json.dumps({'routing': current['routing']}))
                subprocess.run(['/opt/linea/bin/xray', 'api', 'adrules', '--server=127.0.0.1:10085',
                                '-timeout=20', str(path)], check=True, capture_output=True)
    # Commit the startup pointer only after validation and a successful live reload.
    status_next = BASE / 'filter-status.next.json'
    status_next.write_text(json.dumps({'asset': asset, 'domains': len(domains), 'source': URL,
        'sha256': hashlib.sha256(raw).hexdigest(), 'updated_at': datetime.now(timezone.utc).isoformat()}, indent=2) + '\n')
    status_next.chmod(0o644)
    os.replace(status_next, status_path)
    for obsolete in sorted(BASE.glob('linea-ads-*.dat'), key=lambda p:p.stat().st_mtime, reverse=True)[3:]:
        if obsolete != target and obsolete.name not in startup_assets:
            obsolete.unlink()
    print('Updated Xray filter:', len(domains), 'domains; no tunnel restart')


if __name__ == '__main__':
    main()
