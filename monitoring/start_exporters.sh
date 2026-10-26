#!/usr/bin/env bash
# Start one node_exporter sidecar per SONiC-VS switch.
# "--network container:<switch>" makes the sidecar share the switch network
# namespace, so it sees the switch interfaces (Ethernet0, eth1, ...).
# Re-run this script after every "containerlab deploy".
set -e
LAB=${LAB:-sonic-bgp}
cd "$(dirname "$0")/"

for sw in sw1 sw2 sw3; do
  mkdir -p "textfiles/$sw"
  docker rm -f "ne-$sw" >/dev/null 2>&1 || true
  docker run -d --name "ne-$sw" \
    --network "container:clab-$LAB-$sw" \
    -v "$PWD/textfiles/$sw:/textfiles:ro" \
    prom/node-exporter:latest \
    --collector.disable-defaults \
    --collector.netdev \
    --collector.textfile \
    --collector.textfile.directory=/textfiles
  echo "started ne-$sw"
done
