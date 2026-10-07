# BGP Hands-on Lab on SONiC-VS

My notes and commands from learning BGP step by step on SONiC-VS using Containerlab.

## What I learned

- What BGP is and how it differs from L2 protocols
- eBGP neighbor setup between 3 switches
- Why a loopback interface is used
- How routes travel (AS_PATH, NEXT_HOP)
- How a BGP route moves through the SONiC pipeline (FRR -> APPL_DB -> ASIC_DB)
- Failure testing and BGP timers
- Capturing and reading BGP packets in Linux

## BGP in simple words

- BGP tells other networks (Autonomous Systems, AS) which prefixes I can reach.
- It runs over TCP port 179.
- Neighbors are configured by hand. There is no auto-discovery.
- It does not pick the shortest path. It compares path attributes (AS_PATH, LOCAL_PREF, MED, and others).
- AS_PATH is the list of AS numbers a route passed through. A router drops a route that already contains its own AS. This prevents loops.
- eBGP is between different AS numbers. iBGP is inside the same AS.

## Topology

```
sw1 (AS 65001) ---- sw2 (AS 65002) ---- sw3 (AS 65003)
 Lo0 1.1.1.1/32      Lo0 2.2.2.2/32      Lo0 3.3.3.3/32

 sw1 Ethernet0 = 10.0.12.1/30  <->  sw2 Ethernet0 = 10.0.12.2/30
 sw2 Ethernet4 = 10.0.23.1/30  <->  sw3 Ethernet0 = 10.0.23.2/30
```

Topology file: [sonic-bgp.clab.yml](sonic-bgp.clab.yml)

```
sudo containerlab deploy -t sonic-bgp.clab.yml
docker exec -it clab-sonic-bgp-sw1 bash
```

In SONiC-VS, container `eth1` maps to `Ethernet0`, and `eth2` maps to `Ethernet4`.

## Why a loopback?

- It is always up, so it gives the switch a stable identity.
- It gives BGP a prefix to advertise (`network 1.1.1.1/32`).
- It is often used for the router-id, and for iBGP sessions later.

## Step 1: Interfaces and loopback

Ports are admin down by default in SONiC, so start every port you use.

**sw1**
```
config loopback add Loopback0
config interface ip add Loopback0 1.1.1.1/32
config interface ip add Ethernet0 10.0.12.1/30
config interface startup Ethernet0
```

**sw2**
```
config loopback add Loopback0
config interface ip add Loopback0 2.2.2.2/32
config interface ip add Ethernet0 10.0.12.2/30
config interface ip add Ethernet4 10.0.23.1/30
config interface startup Ethernet0
config interface startup Ethernet4
```

**sw3**
```
config loopback add Loopback0
config interface ip add Loopback0 3.3.3.3/32
config interface ip add Ethernet0 10.0.23.2/30
config interface startup Ethernet0
```

Check with `show ip interfaces`, and ping the direct neighbor.

## Step 2: BGP configuration (vtysh)

**sw1**
```
vtysh
configure terminal
router bgp 65001
 bgp router-id 1.1.1.1
 no bgp ebgp-requires-policy
 neighbor 10.0.12.2 remote-as 65002
 address-family ipv4 unicast
  network 1.1.1.1/32
 exit-address-family
end
write memory
```

**sw2**
```
vtysh
configure terminal
router bgp 65002
 bgp router-id 2.2.2.2
 no bgp ebgp-requires-policy
 neighbor 10.0.12.1 remote-as 65001
 neighbor 10.0.23.2 remote-as 65003
 address-family ipv4 unicast
  network 2.2.2.2/32
 exit-address-family
end
write memory
```

**sw3**
```
vtysh
configure terminal
router bgp 65003
 bgp router-id 3.3.3.3
 no bgp ebgp-requires-policy
 neighbor 10.0.23.1 remote-as 65002
 address-family ipv4 unicast
  network 3.3.3.3/32
 exit-address-family
end
write memory
```

Notes:

- FRR blocks eBGP route exchange until a route policy is attached. `no bgp ebgp-requires-policy` turns that off for the lab. Real networks use route-maps.
- Configure sw1 and sw2 first, confirm the session, then add sw3.
- Without `write memory`, the config can be lost after a restart.

## Step 3: Verify

```
show ip bgp summary
show ip bgp
show ip route bgp
```

- In the summary, a number in the PfxRcd column means the session is Established. `Idle` or `Active` means it is not up.
- On sw1, `3.3.3.3/32` should show AS_PATH `65002 65003`.

## Step 4: Trace the route in the SONiC pipeline

FRR zebra gives the route to `fpmsyncd`, which writes it to APPL_DB. Then orchagent and SAI program it to ASIC_DB.

```
redis-cli -n 0 keys "ROUTE_TABLE:*"    # APPL_DB
redis-cli -n 1 keys "*ROUTE_ENTRY*"    # ASIC_DB
```

## Step 5: Failure testing

### SONiC `shutdown` does not drop the peer's link in SONiC-VS

`config interface shutdown Ethernet0` only disables the virtual port on that switch. The Containerlab cable (veth) stays up, so the other switch still shows the link as oper up. Real hardware would show link-down on the peer.

To simulate a real cable failure, bring down the Linux interface from the host:

```
docker exec clab-sonic-bgp-sw3 ip link set eth1 down
docker exec clab-sonic-bgp-sw3 ip link set eth1 up
```

Check the peer with `show interfaces status`.

### BGP timers

When the peer does not see a link-down event, the session stays Established until the hold timer expires. Defaults are keepalive 60 seconds and hold 180 seconds.

To use faster timers (do it on both sides):

```
vtysh
configure terminal
router bgp 65002
 neighbor 10.0.23.2 timers 3 9
```

Real networks also use link-down events and BFD for fast failure detection.

## Step 6: Capture BGP packets

BGP is normal TCP on port 179, and it is control-plane traffic (sent to and from the switch CPU, not forwarded by the ASIC).

Packet path: `bgpd` -> Linux TCP -> `Ethernet0` -> container `eth1` (veth) -> peer `eth1` -> peer `Ethernet0` -> peer `bgpd`.

```
tcpdump -ni eth1 tcp port 179
tcpdump -ni eth1 tcp port 179 -vv
tcpdump -ni eth1 tcp port 179 -w /tmp/bgp.pcap
docker cp clab-sonic-bgp-sw1:/tmp/bgp.pcap .
```

If `tcpdump` is not in the container, run it from the host:

```
sudo ip netns exec clab-sonic-bgp-sw1 tcpdump -ni eth1 tcp port 179
```

Open the pcap in Wireshark with the filter `bgp`.

Exercise: start the capture, then run `clear ip bgp *` in vtysh. You will see:

1. TCP 3-way handshake
2. OPEN (AS number, hold time, router-id, capabilities)
3. KEEPALIVE (session becomes Established)
4. UPDATE (prefixes with AS_PATH and NEXT_HOP)
5. Periodic KEEPALIVE

Also try a wrong `remote-as` and look for the NOTIFICATION message. eBGP to a directly connected neighbor uses IP TTL 1.

## SONiC-VS limits

- The virtual ASIC is not a real forwarding plane. BGP and route programming work, but a ping that transits a middle switch (sw1 to 3.3.3.3) may fail. Judge success by the BGP tables and Redis entries.
