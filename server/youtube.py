"""Server-only YouTube egress; client subscriptions keep their existing routes."""
import copy

NAIVE_TAG = 'naive-egress'
NAIVE_PORT = 1089
UPSTREAM_TAG = 'youtube-vpn'

# Keep Google Search, Gmail, account sign-in and unrelated Google APIs on the VPS.
DOMAINS = [
    'domain:youtube.com', 'domain:youtube-nocookie.com', 'domain:youtu.be',
    'domain:googlevideo.com', 'domain:ytimg.com', 'domain:yt.be',
    'domain:youtubei.googleapis.com', 'domain:youtube.googleapis.com',
    'domain:youtubeembeddedplayer.googleapis.com',
    'domain:youtubekids.com', 'domain:youtubegaming.com',
    'full:yt3.ggpht.com', 'full:yt4.ggpht.com', 'full:yt3.googleusercontent.com',
]


def apply(config, private):
    """Apply the server-owned outbound without placing its credentials in client profiles."""
    outbound = copy.deepcopy(private['outbound'])
    if outbound.get('protocol') != 'vless':
        raise ValueError('YouTube upstream must be a VLESS outbound')
    outbound['tag'] = UPSTREAM_TAG
    config['outbounds'].append(outbound)
    config['inbounds'].append({
        'tag': NAIVE_TAG, 'listen': '127.0.0.1', 'port': NAIVE_PORT, 'protocol': 'socks',
        'settings': {'auth': 'noauth', 'udp': False},
        'sniffing': {'enabled': True, 'destOverride': ['http', 'tls'], 'routeOnly': True},
    })
    # Caddy's upstream mode delegates its ACL to this loopback proxy.
    # Keep private-target and ad blocking ahead of the YouTube exception.
    dns_rule = config['routing']['rules'][1]
    dns_rule['inboundTag'] = list(dict.fromkeys(dns_rule['inboundTag'] + [NAIVE_TAG]))
    config['routing']['rules'].extend([
        {'type': 'field', 'inboundTag': [NAIVE_TAG], 'ip': ['ff00::/8'], 'outboundTag': 'blocked'},
        {'type': 'field', 'ruleTag': 'youtube-quic-to-tcp', 'domain': DOMAINS,
         'network': 'udp', 'port': '443', 'outboundTag': 'blocked'},
        {'type': 'field', 'ruleTag': 'youtube-upstream', 'domain': DOMAINS,
         'outboundTag': UPSTREAM_TAG},
    ])
    return config
