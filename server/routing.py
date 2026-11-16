"""Client routing formats documented by Happ and v2RayTun.

These rules run on the device. Server freedom routing cannot supply a home IP.
"""
import base64
import json

SUFFIXES = ["domain:ru", "domain:xn--p1ai"]


def encode(value):
    return base64.b64encode(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).decode()


def happ_profile():
    return {
        "Name": "Linea — RU direct",
        "GlobalProxy": "true",
        "RemoteDNSType": "DoU", "RemoteDNSIP": "1.1.1.1", "RemoteDNSDomain": "",
        "DomesticDNSType": "DoU", "DomesticDNSIP": "8.8.8.8", "DomesticDNSDomain": "",
        "Geoipurl": "", "Geositeurl": "", "DnsHosts": {},
        "DirectSites": SUFFIXES,
        "DirectIp": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
        "ProxySites": [], "ProxyIp": [], "BlockSites": [], "BlockIp": [],
        "DomainStrategy": "AsIs", "FakeDNS": "false",
    }


def v2raytun_profile():
    return {
        "name": "Linea — RU direct", "id": "AEF980B9-C51B-4D1C-B96B-87B84AC67481",
        "domainStrategy": "AsIs", "domainMatcher": "hybrid", "balancers": [],
        "rules": [{"type": "field", "outboundTag": "direct", "domain": SUFFIXES,
                   "domainMatcher": "hybrid", "__name__": "RU and RF direct",
                   "id": "FB158062-1A98-4F99-A60C-77A456DE9565"}],
    }


def subscription_headers(agent):
    agent = agent.lower()
    if "happ" in agent:
        return {"routing": "happ://routing/onadd/" + encode(happ_profile())}
    if "v2raytun" in agent:
        return {"routing": encode(v2raytun_profile())}
    return {}
