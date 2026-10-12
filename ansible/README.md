# Ansible: Configure BGP on SONiC-VS

Ansible playbooks that configure interfaces and eBGP on a 3-switch SONiC-VS lab (Containerlab). They do the same steps as typing the commands by hand, in one command.

## Topology

```
sw1 (AS 65001) ---- sw2 (AS 65002) ---- sw3 (AS 65003)
 Lo0 1.1.1.1/32      Lo0 2.2.2.2/32      Lo0 3.3.3.3/32

 sw1 Ethernet0 = 10.0.12.1/30  <->  sw2 Ethernet0 = 10.0.12.2/30
 sw2 Ethernet4 = 10.0.23.1/30  <->  sw3 Ethernet0 = 10.0.23.2/30
```

The Containerlab topology file is in the main repo (`sonic-bgp.clab.yml`). The lab name is `sonic-bgp`, so the containers are named `clab-sonic-bgp-sw1`, `clab-sonic-bgp-sw2` and `clab-sonic-bgp-sw3`.

## Files

```
ansible/
├── README.md
├── ansible.cfg          # remote tmp path and defaults
├── inventory.yml        # per-switch variables (IPs, AS, neighbors)
├── site.yml             # configures interfaces and BGP
├── verify.yml           # shows BGP summary and BGP table
└── templates/
    └── bgp.conf.j2      # BGP config template for vtysh
```

## How it works

- **Connection:** Ansible runs `docker exec` into each container (`community.docker.docker` connection). No SSH or passwords are needed.
- **Variables:** everything switch-specific is in `inventory.yml`. To change an IP, AS number or neighbor, edit only this file.
- **`site.yml` steps:**
  1. Create `Loopback0`
  2. Set the loopback IP
  3. Set the port IPs
  4. Start the ports (SONiC ports are admin down by default)
  5. Render `templates/bgp.conf.j2` to `/tmp/bgp.conf` on the switch
  6. Apply it with `vtysh -f /tmp/bgp.conf`
  7. Save with `vtysh -c "write memory"`
- **Re-running:** the interface tasks check CONFIG_DB first, so they do not repeat work. The BGP step re-applies every time, which is safe in vtysh (Ansible shows it as "ok", not "changed").

## Requirements

- Linux host with Docker and Containerlab, and the lab already deployed:
  ```
  sudo containerlab deploy -t sonic-bgp.clab.yml
  ```
- Your user can run `docker` without `sudo` (see Troubleshooting)
- Python 3 inside the SONiC containers (the `docker-sonic-vs` image has it)

## Setup and run

```bash
pip install ansible
ansible-galaxy collection install community.docker

cd ansible
ansible-playbook site.yml      # configure interfaces and BGP
ansible-playbook verify.yml    # show BGP summary and table
```

Useful options:

```bash
ansible-playbook site.yml --limit sw1    # run on one switch
ansible-playbook site.yml -vvv           # full debug output
```

## Expected result

In the `verify.yml` output:

- `show ip bgp summary`: each neighbor shows a number in the PfxRcd column. `Idle` or `Active` means the session is not up.
- `show ip bgp` on sw1: `3.3.3.3/32` appears with AS_PATH `65002 65003`.

## Add or change something

- **New prefix to advertise:** add it to `bgp.networks` in `inventory.yml`.
- **New neighbor:** add `{ip: ..., asn: ...}` to `bgp.neighbors`.
- **New BGP setting** (for example `neighbor ... timers 3 9`): add the line to `templates/bgp.conf.j2`, then run `site.yml` again.

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `Failed to create temporary directory` | Container user has no usable home directory | Set `remote_tmp = /tmp/.ansible/tmp` in `ansible.cfg`, and `ansible_user: root` in `inventory.yml` |
| `Could not find or access 'templates/bgp.conf.j2'` | The `template` module already searches the `templates/` folder | Use `src: bgp.conf.j2`, and keep the file at `templates/bgp.conf.j2` |
| `% Unknown command: configure terminal` or `write memory` | `vtysh -f` reads the file like `frr.conf`, which is already in config mode | Keep those two lines out of the template, and run `write memory` as a separate `vtysh -c` task |
| `permission denied ... Docker daemon socket` | User is not in the docker group | `sudo usermod -aG docker $USER`, then log out and in |
| Container not found | Container names do not match | Check `docker ps --format '{{.Names}}'` and fix `ansible_host` in `inventory.yml` |
| `python3` not found | Interpreter path differs | Check `docker exec clab-sonic-bgp-sw1 which python3` and update `ansible_python_interpreter` |



