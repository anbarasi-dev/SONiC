# Command Reference — Multi-Switch SONiC Lab Bring-Up

Environment: WSL2 host with Docker + Containerlab. Topology file: `sonic-fabric.clab.yml` (1 spine, 2 leaves).

## 1. Deploy the topology
Run from the WSL2 host, in the directory containing the topology file.

```bash
sudo containerlab deploy -t sonic-fabric.clab.yml
```

Confirm all three containers are up:

```bash
sudo containerlab inspect -t sonic-fabric.clab.yml
```

## 2. Attach to a node
No `sonic-cli` is needed — attach directly to bash and use the native `show`/`config` commands.

```bash
docker exec -it clab-sonic-fabric-leaf2 bash
docker exec -it clab-sonic-fabric-spine1 bash
docker exec -it clab-sonic-fabric-leaf1 bash
```

## 3. Identify the linked port
Inside each node:

```bash
show interface status -d all
```

Mapping notes for this topology:
- `leaf1` and `leaf2` each have one data link → `Ethernet0`
- `spine1` has two data links → `Ethernet0` (to leaf1), `Ethernet4` (to leaf2)

## 4. Bring the interface administratively up
Required on both ends of every link — SONiC ports are admin-down by default.

```bash
sudo config interface startup Ethernet0
```

Re-check:

```bash
show interface status Ethernet0
```

`Admin` should now read `up`. `Oper` will only read `up` once the peer side is also enabled.

## 5. Assign IP addresses
On each end of each link, from bash:

```bash
sudo config interface ip add Ethernet0 <ip-address>/<mask>
```

Example addressing used for this lab:

| Node   | Interface | IP address     |
|--------|-----------|-----------------|
| spine1 | Ethernet0 | 10.0.0.0/31     |
| leaf1  | Ethernet0 | 10.0.0.1/31     |
| spine1 | Ethernet4 | 10.0.0.2/31     |
| leaf2  | Ethernet0 | 10.0.0.3/31     |

## 6. Verify Layer 3 connectivity
From leaf1:

```bash
ping 10.0.0.0
```

From leaf2:

```bash
ping 10.0.0.2
```

Both should succeed once interfaces are admin-up on both ends and IPs are assigned correctly.

## 7. Save the configuration
Run on every node once verified — otherwise changes are lost on container restart.

```bash
sudo config save -y
```

## Troubleshooting checklist
- `Oper: down` after `config interface startup` → check the peer side is also admin-up
- Still down after both sides are up → check `sudo ip link show eth1` inside the container to confirm the Containerlab veth pair exists
- Ping fails but both interfaces show `Oper: up` → double-check the IP/mask on both ends are in the same subnet
