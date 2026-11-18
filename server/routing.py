"""Client-side routing for Linea's subscription and sing-box profiles."""
import base64
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PORTAL_DOMAINS = ("linesonline.pro", "www.linesonline.pro")
VPN_ENDPOINT = "217.60.19.243/32"
LOCAL_NETWORKS = (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10",
)
DOMESTIC_DNS = "77.88.8.8"
DOMESTIC_DNS_HOST = "common.dot.dns.yandex.net"


def _load_service_domains():
    path = Path(__file__).with_name("direct-domains.txt")
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    domains = []
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        row = raw.strip()
        if not row or row.startswith("#"):
            continue
        domain = row.removeprefix("domain:").removesuffix(".").encode("idna").decode().lower()
        if (not row.startswith("domain:") or len(domain) > 253
                or not re.fullmatch(rf"{label}(?:\.{label})+", domain)
                or re.fullmatch(r"[0-9.]+", domain) or domain in domains):
            raise ValueError(f"Invalid or duplicate direct domain at {path.name}:{number}")
        domains.append(domain)
    if not domains:
        raise ValueError(f"{path.name} is empty")
    return tuple(domains)


SERVICE_DOMAINS = _load_service_domains()
DIRECT_DOMAINS = [f"domain:{domain}" for domain in SERVICE_DOMAINS] + [
    f"full:{domain}" for domain in PORTAL_DOMAINS
]


def encode(value):
    return base64.b64encode(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).decode()


def happ_profile(name="Linea — RU direct"):
    return {
        "Name": name,
        "GlobalProxy": "true",
        "RemoteDNSType": "DoH", "RemoteDNSIP": "1.1.1.1", "RemoteDNSDomain": "https://cloudflare-dns.com/dns-query",
        "DomesticDNSType": "DoH", "DomesticDNSIP": DOMESTIC_DNS, "DomesticDNSDomain": f"https://{DOMESTIC_DNS_HOST}/dns-query",
        "Geoipurl": "", "Geositeurl": "", "DnsHosts": {"cloudflare-dns.com": "1.1.1.1", DOMESTIC_DNS_HOST: DOMESTIC_DNS},
        "DirectSites": DIRECT_DOMAINS,
        "DirectIp": [*LOCAL_NETWORKS, VPN_ENDPOINT, DOMESTIC_DNS + "/32"],
        "ProxySites": [], "ProxyIp": [], "BlockSites": [], "BlockIp": [],
        "DomainStrategy": "AsIs", "FakeDNS": "true",
    }


def v2raytun_profile():
    return {
        "name": "Linea — RU direct", "id": "AEF980B9-C51B-4D1C-B96B-87B84AC67481",
        "domainStrategy": "AsIs", "domainMatcher": "hybrid", "balancers": [],
        "rules": [{"type": "field", "outboundTag": "direct", "domain": DIRECT_DOMAINS,
                   "domainMatcher": "hybrid", "__name__": "Selected services and portal direct",
                   "id": "FB158062-1A98-4F99-A60C-77A456DE9565"},
                  {"type": "field", "outboundTag": "direct", "ip": [VPN_ENDPOINT, *LOCAL_NETWORKS],
                   "__name__": "VPN endpoint and local network direct", "id": "821C6D72-2CAA-4602-B55E-184F1C193C25"}],
    }


def subscription_headers(agent):
    agent = agent.lower()
    if "v2raytun" in agent:
        return {"routing": encode(v2raytun_profile())}
    if "incy" in agent:
        return {"routing": "incy://routing/onadd/" + encode(happ_profile("Linea — Direct Services"))}
    return {}


def _vless_endpoint(uri):
    link = urlsplit(uri)
    options = parse_qs(link.query)
    endpoint = VPN_ENDPOINT.split('/')[0]
    if (link.scheme != 'vless' or link.port != 443 or link.hostname not in (endpoint, *PORTAL_DOMAINS)
            or options.get('type') != ['ws'] or options.get('security') != ['tls']):
        raise ValueError('Expected a Linea VLESS over WebSocket endpoint')
    return link, options, endpoint


def xray_vless_outbound(uri):
    link, options, endpoint = _vless_endpoint(uri)
    return {
        'tag': 'proxy', 'protocol': 'vless',
        'settings': {'vnext': [{'address': endpoint, 'port': link.port, 'users': [
            {'id': link.username, 'encryption': 'none'},
        ]}]},
        'streamSettings': {
            'network': 'ws', 'security': 'tls',
            'tlsSettings': {'serverName': options['sni'][0], 'fingerprint': 'chrome'},
            'wsSettings': {'path': options['path'][0], 'host': options['host'][0]},
        },
    }


def happ_xray_profile(uri, name):
    sniffing = {"enabled": True, "routeOnly": False, "destOverride": ["http", "tls", "quic"]}
    return {
        "remarks": name,
        "log": {"loglevel": "warning"},
        "dns": {
            "queryStrategy": "UseIPv4",
            "hosts": {DOMESTIC_DNS_HOST: DOMESTIC_DNS},
            "servers": [
                {"address": f"https://{DOMESTIC_DNS_HOST}/dns-query", "domains": DIRECT_DOMAINS, "skipFallback": True},
                "https://1.1.1.1/dns-query",
            ],
        },
        "routing": {"domainStrategy": "AsIs", "rules": [
            {"type": "field", "domain": DIRECT_DOMAINS + [f"full:{DOMESTIC_DNS_HOST}"], "outboundTag": "direct"},
            {"type": "field", "ip": [*LOCAL_NETWORKS, VPN_ENDPOINT, DOMESTIC_DNS + "/32"], "outboundTag": "direct"},
        ]},
        "inbounds": [
            {"tag": "socks", "listen": "127.0.0.1", "port": 10808, "protocol": "socks",
             "settings": {"auth": "noauth", "udp": True}, "sniffing": sniffing},
            {"tag": "http", "listen": "127.0.0.1", "port": 10809, "protocol": "http", "sniffing": sniffing},
        ],
        "outbounds": [xray_vless_outbound(uri),
                      {"tag": "direct", "protocol": "freedom", "settings": {"targetStrategy": "UseIPv4"}}],
    }


def singbox_vless_profile(uri):
    link, options, endpoint = _vless_endpoint(uri)
    return apply_singbox_routing({
        "log": {"level": "warn"},
        "dns": {"servers": [
            {"type": "https", "tag": "secure-dns", "server": "1.1.1.1",
             "detour": "vpn", "tls": {"enabled": True}},
        ], "final": "secure-dns"},
        "inbounds": [
            {"type": "tun", "tag": "tun-in", "address": ["172.28.0.1/30", "fdfe:dcba:9876::1/126"],
             "mtu": 1400, "auto_route": True, "strict_route": True},
        ],
        "outbounds": [
            {"type": "vless", "tag": "vpn", "server": endpoint, "server_port": link.port,
             "uuid": link.username, "tls": {"enabled": True, "server_name": options["sni"][0]},
             "transport": {"type": "ws", "path": options["path"][0], "headers": {"Host": options["host"][0]}}},
            {"type": "direct", "tag": "direct"},
        ],
        "route": {
            "rules": [
                {"action": "sniff"},
                {"protocol": "dns", "action": "hijack-dns"},
                {"port": 53, "action": "hijack-dns"},
                {"domain_suffix": list(SERVICE_DOMAINS), "outbound": "direct"},
                {"ip_cidr": [VPN_ENDPOINT, *LOCAL_NETWORKS], "outbound": "direct"},
            ],
            "final": "vpn", "auto_detect_interface": True,
        },
    })


def apply_singbox_routing(profile):
    """Set the direct split rules while retaining the profile's VPN and remote DNS."""
    domains = {"domain_suffix": list(SERVICE_DOMAINS), "domain": list(PORTAL_DOMAINS)}
    dns = profile["dns"]
    dns["servers"] = [server for server in dns["servers"] if server["tag"] not in {"domestic-dns", "direct-fakeip"}] + [
        {"type": "https", "tag": "domestic-dns", "server": DOMESTIC_DNS,
         "tls": {"enabled": True, "server_name": DOMESTIC_DNS_HOST}},
        {"type": "fakeip", "tag": "direct-fakeip", "inet4_range": "198.18.0.0/15", "inet6_range": "2001:2::/48"},
    ]
    # Remember the DNS name even for apps that connect to the returned IP without a hostname.
    # Resolve real addresses only when the direct outbound dials the connection.
    dns["rules"] = [
        {**domains, "query_type": ["A", "AAAA"], "action": "route", "server": "direct-fakeip"},
        {**domains, "action": "route", "server": "domestic-dns"},
    ]
    route = profile["route"]
    for index, rule in enumerate(route["rules"]):
        if rule.get("outbound") == "direct" and "domain_suffix" in rule:
            route["rules"][index] = {**domains, "action": "route", "outbound": "direct"}
            break
    else:
        raise ValueError("Expected a direct domain rule before the default VPN route")
    direct = next(outbound for outbound in profile["outbounds"] if outbound["tag"] == "direct")
    direct["domain_resolver"] = "domestic-dns"
    return profile
