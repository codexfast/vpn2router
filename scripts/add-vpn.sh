#!/usr/bin/env bash
set -euo pipefail
N=${1:?uso: ./scripts/add-vpn.sh <numero>  (ex: 3)}
USER_VAR="PROTON_USER_${N}"
PASS_VAR="PROTON_PASS_${N}"
CTRY_VAR="SERVER_COUNTRIES_${N}"
grep -q "$USER_VAR" .env 2>/dev/null || cat >> .env <<EOF
$USER_VAR=troque_aqui
$PASS_VAR=troque_aqui
$CTRY_VAR=Netherlands,Switzerland,Germany
EOF
echo "bloco vpn-$N (cole no docker-compose.yml + adicione em HTTP_UPSTREAMS):"
cat <<EOF

  vpn-$N:
    image: qmcgaw/gluetun:latest
    cap_add: [NET_ADMIN]
    devices: [/dev/net/tun:/dev/net/tun]
    environment:
      - VPN_SERVICE_PROVIDER=protonvpn
      - VPN_TYPE=openvpn
      - OPENVPN_USER=\${$USER_VAR}
      - OPENVPN_PASSWORD=\${$PASS_VAR}
      - SERVER_COUNTRIES=\${$CTRY_VAR}
      - FIREWALL_OUTBOUND_SUBNETS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
      - HTTPPROXY=on
      - HTTPPROXY_LISTENING_ADDRESS=:8888
      - HTTPPROXY_STEALTH=on
    expose: ["8888"]
    restart: unless-stopped
    logging: {driver: json-file, options: {max-size: 10m, max-file: "3"}}
EOF
echo "depois: HTTP_UPSTREAMS=vpn-1:8888,...,vpn-$N:8888"
