# Multi-Switch SONiC Lab — Bring-Up and Connectivity

## Overview
This is the first hands-on milestone in a broader SONiC upskilling track: standing up a multi-switch SONiC topology in Containerlab, bringing the inter-switch links up, and confirming Layer 3 connectivity between independent SONiC nodes. Earlier work covered a single-switch config and basic SONiC architecture; this step moves from one node to a real multi-node fabric.

## Topology

```
        spine1
        /    \
   Eth0/      \Eth4
      /        \
  leaf1        leaf2
```

- **spine1** — SONiC-VS node with two data links, one to each leaf
- **leaf1**, **leaf2** — SONiC-VS nodes, each with a single uplink to spine1
- A 1-spine / 2-leaf layout was chosen over a flat mesh because it mirrors a real fabric design and keeps each peering relationship unambiguous (leaves never talk to each other directly)

All three nodes run as `sonic-vs` containers under Containerlab, wired together with Containerlab-managed veth links.

## What was accomplished
1. Deployed a 3-node SONiC-VS topology in Containerlab (WSL2 + Docker environment)
2. Identified how Containerlab's topology-level interface names (`eth1`, `eth2`) map onto SONiC's native port naming (`Ethernet0`, `Ethernet4`, ...)
3. Brought the leaf–spine links up administratively (SONiC ports default to admin-down)
4. Assigned IP addresses to the linked interfaces on both ends of each link
5. Verified end-to-end Layer 3 reachability with `ping` between leaf1 ↔ spine1 and leaf2 ↔ spine1

## Key learnings
- **Interface name mapping isn't 1:1 with the topology file.** Containerlab's `eth1`/`eth2` labels are link identifiers, not SONiC port names — the first data link typically lands on `Ethernet0`, the second on `Ethernet4`, and so on, since SONiC groups ports by lane count.
- **SONiC CLI tooling lives outside the container by default.** Standard `sonic-vs` images don't include `sonic-cli`; the native `show` / `config` command set (from `sonic-utilities`) is what's actually used, run directly from the container's bash shell.
- **Two conditions gate a link showing "up."** The interface needs to be administratively enabled (`config interface startup <port>`) *and* the peer side needs to be enabled too — oper status won't flip until both ends agree.
- **Runtime changes don't persist by default.** `config save -y` is required on each node after verifying the setup, or the enabled interfaces revert on container restart.

## Next step
With basic multi-switch connectivity confirmed, the next milestone is configuring eBGP peering between the leaves and the spine using SONiC's FRR-based routing stack (`vtysh`), followed by gNMI-based telemetry streaming from all three nodes into Prometheus/Grafana.

## Environment
- Containerlab on WSL2 (Docker Desktop backend)
- SONiC-VS container image
- Topology file: `sonic-fabric.clab.yml`
