#!/usr/bin/env python3
"""
Read BGP state from each SONiC-VS switch (vtysh JSON) and write it as a
Prometheus text file. node_exporter's textfile collector then exposes it.

Runs on the host (WSL2). It uses `docker exec`, so nothing is installed
inside the switches.
"""
import json
import os
import subprocess
import sys
import time

LAB = os.environ.get("LAB", "sonic-bgp")
SWITCHES = os.environ.get("SWITCHES", "sw1 sw2 sw3").split()
OUT_DIR = os.environ.get("OUT_DIR", "textfiles")
INTERVAL = int(os.environ.get("INTERVAL", "15"))


def bgp_summary(sw):
    cmd = ["docker", "exec", f"clab-{LAB}-{sw}",
           "vtysh", "-c", "show bgp summary json"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "vtysh failed")
    return json.loads(res.stdout)


def write_file(sw, ok, peers):
    # Group all lines of one metric together (required by the text format)
    metrics = {
        "sonic_bgp_peer_up": ("gauge", "1 if BGP session is Established"),
        "sonic_bgp_peer_prefixes_received": ("gauge", "Prefixes received from peer"),
        "sonic_bgp_peer_uptime_seconds": ("gauge", "Session uptime in seconds"),
        "sonic_bgp_peer_messages_received_total": ("counter", "BGP messages received"),
        "sonic_bgp_peer_messages_sent_total": ("counter", "BGP messages sent"),
    }
    lines = [
        "# HELP sonic_bgp_collect_ok 1 if BGP state was read successfully",
        "# TYPE sonic_bgp_collect_ok gauge",
        f'sonic_bgp_collect_ok{{switch="{sw}"}} {1 if ok else 0}',
    ]
    for name, (mtype, helptext) in metrics.items():
        lines.append(f"# HELP {name} {helptext}")
        lines.append(f"# TYPE {name} {mtype}")
        for p in peers:
            labels = (f'switch="{sw}",peer="{p["peer"]}",'
                      f'remote_as="{p["remote_as"]}"')
            lines.append(f"{name}{{{labels}}} {p[name]}")

    path = os.path.join(OUT_DIR, sw, "bgp.prom")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)  # atomic, so node_exporter never reads half a file


def parse(data):
    peers = []
    for body in data.values():          # e.g. "ipv4Unicast"
        if not isinstance(body, dict):
            continue
        for ip, p in body.get("peers", {}).items():
            peers.append({
                "peer": ip,
                "remote_as": p.get("remoteAs", ""),
                "sonic_bgp_peer_up": 1 if p.get("state") == "Established" else 0,
                "sonic_bgp_peer_prefixes_received": p.get("pfxRcd", 0) or 0,
                "sonic_bgp_peer_uptime_seconds": (p.get("peerUptimeMsec", 0) or 0) / 1000,
                "sonic_bgp_peer_messages_received_total": p.get("msgRcvd", 0),
                "sonic_bgp_peer_messages_sent_total": p.get("msgSent", 0),
            })
    return peers


def main():
    for sw in SWITCHES:
        os.makedirs(os.path.join(OUT_DIR, sw), exist_ok=True)
    print(f"Collecting BGP state for {SWITCHES} every {INTERVAL}s -> {OUT_DIR}/")
    while True:
        for sw in SWITCHES:
            try:
                peers = parse(bgp_summary(sw))
                write_file(sw, True, peers)
            except Exception as e:  # keep going if one switch fails
                print(f"[{sw}] error: {e}", file=sys.stderr)
                write_file(sw, False, [])
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
