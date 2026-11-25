"""Builds the Envoy configuration used by the independent relay."""
import base64
import json


def download_headers(filename):
    """Response headers for a file served at a secret download path, chosen by its suffix."""
    suffix = str(filename).rsplit('.', 1)[-1].lower()
    content_type = {'yaml': 'application/yaml; charset=utf-8',
                    'html': 'text/html; charset=utf-8'}.get(suffix, 'application/x-apple-aspen-config')
    download_name = {'yaml': 'clashmi-phone.yaml'}.get(suffix, 'iPhone-relay.mobileconfig')
    disposition = 'inline' if suffix == 'html' else 'attachment; filename="'+download_name+'"'
    headers = [{'header': {'key': 'content-type', 'value': content_type}},
               {'header': {'key': 'content-disposition', 'value': disposition}},
               {'header': {'key': 'cache-control', 'value': 'no-store'}},
               {'header': {'key': 'referrer-policy', 'value': 'no-referrer'}}]
    if suffix == 'yaml':
        # Clash Mi reads this header as the subscription update interval in hours.
        headers.append({'header': {'key': 'profile-update-interval', 'value': '24'}})
    return headers


def build_envoy_config(certificate, key, users, downloads=None, diagnostics=False):
    """Return an Envoy static configuration.

    certificate, key: paths to the TLS chain and private key.
    users: list of {'username', 'password'} accepted in Proxy-Authorization.
    downloads: {url_path: filename} served without authentication (profile downloads).
    """
    downloads = downloads or {}
    accepted = ['Basic '+base64.b64encode((user['username']+':'+user['password']).encode()).decode()
                for user in users]
    checks = ' or '.join('auth == '+json.dumps(value) for value in accepted) or 'false'
    download_checks = ' or '.join('path == '+json.dumps(value) for value in downloads) or 'false'
    lua = '''
function envoy_on_request(handle)
  local headers = handle:headers()
  local method = headers:get(":method") or ""
  local path = headers:get(":path") or ""
  if method == "GET" and (DOWNLOADS) then return end
  local auth = headers:get("proxy-authorization") or ""
  if not (ACCEPTED) then
    handle:respond({[":status"]="407", ["proxy-authenticate"]='Basic realm="Relay"'}, "Proxy authentication required")
    return
  end
  if string.find(path, "/.well-known/masque/udp/", 1, true) == 1 then
    local host, port = string.match(path, "^/%.well%-known/masque/udp/([^/]+)/(%d+)/$")
    if not host or not port then handle:respond({[":status"]="400"}, "Invalid UDP target"); return end
    host = string.gsub(host, "%%(%x%x)", function(hex) return string.char(tonumber(hex,16)) end)
    if string.find(host, ":", 1, true) then host = "[" .. host .. "]" end
    headers:replace(":authority", host .. ":" .. port)
  elseif method ~= "CONNECT" then
    handle:respond({[":status"]="405"}, "CONNECT required")
  end
end
'''.replace('DOWNLOADS', download_checks).replace('ACCEPTED', checks)
    routes = []
    for url_path, filename in downloads.items():
        routes.append({'match': {'path': url_path}, 'direct_response': {'status': 200, 'body': {'filename': str(filename)}},
                       'response_headers_to_add': download_headers(filename)})
    routes += [
        {'match': {'prefix': '/.well-known/masque/udp/'}, 'route': {
            'cluster': 'relay-targets', 'timeout': '0s',
            'upgrade_configs': [{'upgrade_type': 'CONNECT-UDP', 'connect_config': {}}]}},
        {'match': {'connect_matcher': {}}, 'route': {
            'cluster': 'relay-targets', 'timeout': '0s',
            'upgrade_configs': [{'upgrade_type': 'CONNECT', 'connect_config': {}}]}}
    ]
    cache = {'name': 'relay-dns', 'dns_lookup_family': 'V4_ONLY'}
    hcm = {
        '@type': 'type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager',
        'stat_prefix': 'relay', 'codec_type': 'AUTO', 'stream_idle_timeout': '0s',
        'http2_protocol_options': {'allow_connect': True},
        'upgrade_configs': [{'upgrade_type': 'CONNECT'}, {'upgrade_type': 'CONNECT-UDP'}],
        'route_config': {'name': 'relay', 'max_direct_response_body_size_bytes': 16384,
                         'virtual_hosts': [{'name': 'relay', 'domains': ['*'], 'routes': routes}]},
        'http_filters': [
            {'name': 'envoy.filters.http.lua', 'typed_config': {
                '@type': 'type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua',
                'default_source_code': {'inline_string': lua}}},
            {'name': 'envoy.filters.http.dynamic_forward_proxy', 'typed_config': {
                '@type': 'type.googleapis.com/envoy.extensions.filters.http.dynamic_forward_proxy.v3.FilterConfig',
                'dns_cache_config': cache}},
            {'name': 'envoy.filters.http.router', 'typed_config': {
                '@type': 'type.googleapis.com/envoy.extensions.filters.http.router.v3.Router'}}]
    }
    if diagnostics:
        # The DNS and upstream fields tell where a 503 comes from; download paths and headers are not logged.
        hcm['access_log_options'] = {'flush_log_on_tunnel_successfully_established': True}
        hcm['access_log'] = [{'name': 'envoy.access_loggers.stdout', 'typed_config': {
            '@type': 'type.googleapis.com/envoy.extensions.access_loggers.stream.v3.StdoutAccessLog',
            'log_format': {'json_format': {
                'time': '%START_TIME%', 'target': '%REQ(:AUTHORITY)%', 'method': '%REQ(:METHOD)%',
                'status': '%RESPONSE_CODE%', 'protocol': '%PROTOCOL%',
                'response_details': '%RESPONSE_CODE_DETAILS%', 'response_flags': '%RESPONSE_FLAGS%',
                'upstream': '%UPSTREAM_HOST%', 'duration_ms': '%DURATION%',
                'dns_ms': '%COMMON_DURATION(envoy.dynamic_forward_proxy.dns_start_ms:envoy.dynamic_forward_proxy.dns_end_ms:ms)%'}}}}]
    return {'static_resources': {
        'listeners': [{'name': 'relay', 'address': {'socket_address': {'address': '10.231.252.2', 'port_value': 18443}},
                       'filter_chains': [{'transport_socket': {'name': 'envoy.transport_sockets.tls', 'typed_config': {
                           '@type': 'type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext',
                           'common_tls_context': {'tls_certificates': [{'certificate_chain': {'filename': str(certificate)},
                               'private_key': {'filename': str(key)}}], 'alpn_protocols': ['h2', 'http/1.1']}}},
                           'filters': [{'name': 'envoy.filters.network.http_connection_manager', 'typed_config': hcm}]}]}],
        'clusters': [{'name': 'relay-targets', 'connect_timeout': '10s', 'lb_policy': 'CLUSTER_PROVIDED',
                      'cluster_type': {'name': 'envoy.clusters.dynamic_forward_proxy', 'typed_config': {
                          '@type': 'type.googleapis.com/envoy.extensions.clusters.dynamic_forward_proxy.v3.ClusterConfig',
                          'dns_cache_config': cache}}}]}}
