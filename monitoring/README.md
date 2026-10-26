# Monitoring SONiC-VS with node_exporter, Prometheus and Grafana

A beginner-friendly, hands-on guide. A 3-switch SONiC-VS network (Containerlab) is monitored with Prometheus and Grafana. BGP session state and port traffic are shown on a dashboard, an alert is sent to a webhook when a BGP peer goes down, and dashboard images are rendered as PNG files.

Tested on: Windows 11, WSL2 (Ubuntu), Docker Desktop.

## What is built

```
 sw1 ---- sw2 ---- sw3            (SONiC-VS switches, eBGP, from the BGP lab)
  |        |        |
 node_exporter sidecar on each switch
   - interface traffic, errors, drops
   - BGP state (written by bgp_textfile.py)
          |
          v
     Prometheus   (collects metrics every 15 s)
          |
          v
       Grafana    (dashboard, alerts, images)
          |
          +--> Webhook (alert message)
          +--> Image renderer (PNG of dashboards and panels)
```

## What each tool does

| Tool | What it is | Role here |
|---|---|---|
| SONiC-VS | Virtual SONiC network switch | The device that is monitored |
| Containerlab | Tool to build network labs with containers | Runs the 3 switches |
| node_exporter | Small program that exposes metrics over HTTP | Interface counters and the BGP file, one per switch |
| Prometheus | Time series database that pulls (scrapes) metrics | Stores metrics and runs queries |
| PromQL | Prometheus query language | Used in panels and alerts |
| Grafana | Dashboard and alerting tool | Graphs and alert rules |
| Webhook | An HTTP URL that receives a message | Receives the alert notification |
| Image renderer | Headless Chromium in a container | Makes PNG pictures of dashboards |

## Where everything runs

Prometheus, Grafana, the renderer, the exporters and the switches are all **Docker containers**. On Windows 11 they run inside the WSL2 virtual machine of Docker Desktop. Commands are typed in the Ubuntu (WSL2) terminal, and the web pages are opened in the Windows browser (Docker forwards the ports).

Two facts follow from this, and they cause most beginner errors:

- Containers talk to each other by container name (for example `http://prometheus:9090`).
- `localhost` inside a container means that container itself, not the host computer.

## Prerequisites

- The SONiC-VS BGP lab is running with BGP configured. See the BGP lab guide: https://github.com/anbarasi-dev/SONiC/tree/main/bgp.
- Docker and Docker Compose are installed.
- Python 3 is installed on the host.
- The lab name is `sonic-bgp`, so the containers are named `clab-sonic-bgp-sw1`, `clab-sonic-bgp-sw2` and `clab-sonic-bgp-sw3`.

Checks:

```bash
docker ps --format '{{.Names}}'        # clab-sonic-bgp-sw1 ...
docker network ls | grep clab          # network named "clab"
docker exec clab-sonic-bgp-sw1 vtysh -c "show bgp summary"    # neighbors Established
```

If the lab name is different, `sonic-bgp` is replaced in `prometheus/prometheus.yml`, and the scripts are run with `LAB=<lab-name>`.

## Repo layout

```
sonic_bgp/monitoring/
├── README.md
├── docker-compose.yml                    # Prometheus, Grafana, renderer
├── .env.example                          # renderer token (copied to .env)
├── .gitignore
├── prometheus/
│   ├── prometheus.yml                    # scrape targets
│   └── rules.yml                         # Prometheus alert rules
├── grafana/
│   ├── provisioning/datasources/
│   │   └── prometheus.yml                # adds the Prometheus data source
│   └── dashboards/
│       └── sonic-bgp-overview.json       # dashboard to import
── bgp_textfile.py                   # BGP state -> Prometheus text file
└── start_exporters.sh                # node_exporter sidecars
└── stop_exporters.sh
```

## Quick start

All commands are run from the `sonic_bgp/monitoring` folder, in the order below.

```bash
# 1. Create the token file for the image renderer
cp .env.example .env
sed -i "s/^RENDERER_TOKEN=.*/RENDERER_TOKEN=$(openssl rand -hex 16)/" .env

# 2. Terminal 1: start the BGP collector (left running)
python3 bgp_textfile.py

# 3. Terminal 2: start the node_exporter sidecars
chmod +x  *.sh
./start_exporters.sh

# 4. Start Prometheus, Grafana and the renderer
docker compose up -d
docker compose ps
```

The web pages are then available in the browser:

- Prometheus: http://localhost:9090 (under **Status > Targets**, all three targets should be UP)
- Grafana: http://localhost:3000 (login `admin` / `admin`, with the password changed after the first login)

## Step by step, with checks

### Step 1: node_exporter on each switch

node_exporter runs as a **sidecar**: a separate container that shares the network namespace of the switch (`--network container:<switch>`). It can then see the interfaces of the switch without anything being installed inside SONiC. Only the `netdev` (interface counters) and `textfile` (the BGP file) collectors are kept.

```bash
./start_exporters.sh
docker ps | grep ne-
docker exec ne-sw1 wget -qO- http://localhost:9100/metrics | head
```

`# HELP` lines should appear. The script is re-run after every `containerlab deploy`, because a sidecar is tied to the old switch container.

Note: `http://clab-sonic-bgp-sw1:9100/metrics` does not open in the browser. That name works only inside the Docker network. The test is done from a container instead:

```bash
docker exec prometheus wget -qO- http://clab-sonic-bgp-sw1:9100/metrics | head
```

### Step 2: BGP metrics (textfile collector)

node_exporter has no BGP data, so `bgp_textfile.py` reads `show bgp summary json` from each switch and writes a `.prom` file. node_exporter then exposes it.

```bash
python3 bgp_textfile.py
cat textfiles/sw1/bgp.prom
docker exec ne-sw1 ls -l /textfiles
docker exec ne-sw1 wget -qO- http://localhost:9100/metrics | grep sonic_bgp
```

Metrics created:

| Metric | Meaning |
|---|---|
| `sonic_bgp_peer_up` | 1 if the session is Established, else 0 |
| `sonic_bgp_peer_prefixes_received` | Prefixes received from the peer |
| `sonic_bgp_peer_uptime_seconds` | Session uptime |
| `sonic_bgp_peer_messages_received_total` / `..._sent_total` | BGP message counters |
| `sonic_bgp_collect_ok` | 1 if the collector could read BGP from the switch |

Important: the collector writes to `textfiles/` and the sidecars mount that same folder. Both must be started from the project folder, or an absolute path can be used:

```bash
OUT_DIR=/home/<username>/sonic_bgp/monitoring/textfiles python3 bgp_textfile.py
```

### Step 3: Prometheus

`prometheus/prometheus.yml` lists one scrape target per switch (`clab-sonic-bgp-sw1:9100` and so on) with a `switch` label. `prometheus/rules.yml` holds alert rules.

Queries to try in **Prometheus > Graph**:

```
sonic_bgp_peer_up
sonic_bgp_peer_prefixes_received
rate(node_network_receive_bytes_total{device=~"Ethernet.*"}[1m]) * 8
```

If the `Ethernet.*` query returns nothing, the real device names are listed with:

```bash
curl -s localhost:9090/api/v1/label/device/values
```

### Step 4: Grafana and the data source

Grafana starts with a Prometheus data source from `grafana/provisioning/datasources/prometheus.yml`. If a data source is added by hand, this URL is used:

```
http://prometheus:9090
```

`http://localhost:9090` must not be used. Inside the container of Grafana, `localhost` is Grafana itself, and the result is `connection refused`. Port `9090` is used even if Prometheus is published on another host port.

### Step 5: Dashboard

The ready dashboard is imported as follows:

1. **Dashboards > New > Import**
2. **Upload dashboard JSON file**, then `grafana/dashboards/sonic-bgp-overview.json`
3. The **Prometheus** data source is selected and **Import** is clicked

The dashboard has 13 panels and two drop-downs (Switch, Port):

| Panel | Type | Shows |
|---|---|---|
| Switches scraped (UP) | Stat | Exporters that are reachable |
| Established BGP sessions | Gauge | Sessions up, out of 4 |
| BGP prefixes received | Stat | Total prefixes |
| BGP collector status | Stat | OK or FAIL |
| BGP session state | State timeline | Up or Down for each peer over time |
| Prefixes per peer | Time series | Prefixes over time |
| BGP session uptime | Bar gauge | How long each session has been up |
| BGP messages per second | Time series | Keepalive and update rate |
| Port receive / transmit | Time series | Bits per second |
| Packets per second | Time series | Packet rate |
| Errors and drops | Time series | Should stay at 0 |
| BGP peers (now) | Table | Current snapshot |

The way a panel is built is seen by pressing `e` over it, which opens its query and settings. Changes are saved with **Export > Export as JSON**, and the file is kept in this repo.

### Step 6: Alerts to a webhook

The contact point is created as follows:

1. A unique URL is copied from https://webhook.site.
2. In Grafana, **Alerting > Contact points > Add contact point** is opened.
3. Name `lab-webhook`, integration **Webhook**, and the copied URL is pasted.
4. **Test** is clicked. The message appears on webhook.site. Then **Save**.
5. Under **Alerting > Notification policies**, the contact point of the default policy is set to `lab-webhook`.

The alert rule is created under **Alerting > Alert rules > New alert rule**:

| Setting | Value |
|---|---|
| Name | `BGP peer down` |
| Query A | `sonic_bgp_peer_up` (Prometheus data source) |
| Expression B | Reduce, input A, function Last |
| Expression C | Threshold, input B, IS BELOW `1` (set as alert condition) |
| Folder / group | `SONiC` / `bgp`, interval `15s` |
| Pending period | `30s` |
| No data state | Keep Last State |
| Label | `severity = critical` |
| Summary | `BGP peer {{ $labels.peer }} on {{ $labels.switch }} is down` |
| Contact point | `lab-webhook` |

Two more rules are added in the same way, so that a broken monitoring chain is not mistaken for "no alerts":

| Alert | Query | Condition |
|---|---|---|
| Collector failing | `sonic_bgp_collect_ok` | IS BELOW 1 |
| Exporter down | `up{job="sonic"}` | IS BELOW 1 |

Test (one BGP neighbor is shut down, which drops the session at once):

```bash
docker exec clab-sonic-bgp-sw2 vtysh -c "configure terminal" -c "router bgp 65002" -c "neighbor 10.0.23.2 shutdown"
```

The alert goes **Normal > Pending > Firing** in about 1 to 1.5 minutes (collector 15 s + scrape 15 s + evaluation 15 s + pending 30 s). The message arrives at the webhook. The **Resolved** message is received after the neighbor is restored:

```bash
docker exec clab-sonic-bgp-sw2 vtysh -c "configure terminal" -c "router bgp 65002" -c "no neighbor 10.0.23.2 shutdown"
```

A rule is kept in Git by opening it and using **More > Export**.

### Step 7: Image rendering

The renderer runs as its own container (remote rendering). Grafana and the renderer share a secret token from the `.env` file. Grafana refuses to start the rendering service with the default token.

The image is large and downloads can time out on slow networks, so it is pulled first with retries:

```bash
for i in 1 2 3 4 5; do docker pull grafana/grafana-image-renderer:latest && break; sleep 5; done
docker compose up -d
```

With a logged-in Grafana session in the browser, a render URL is opened:

```
http://localhost:3000/render/d/sonic-vs-bgp/sonic-vs-bgp-and-interfaces?width=1600&height=-1&from=now-30m&to=now&kiosk&timeout=60
```

| Parameter | Meaning |
|---|---|
| `width`, `height` | Image size in pixels. `height=-1` fits the full dashboard height. A fixed height cuts off the lower panels |
| `kiosk` | Hides the Grafana menus |
| `timeout` | Seconds to wait for panels to load |

If `height=-1` still cuts the page, a large fixed value such as `height=2200` is used.

One panel only (good for posts):

```
http://localhost:3000/render/d-solo/sonic-vs-bgp/sonic-vs-bgp-and-interfaces?panelId=5&width=1000&height=500&from=now-30m&to=now
```

`panelId` is replaced with the ID of the panel (the panel menu > Share gives the link).

**Images in alerts:** `GF_UNIFIED_ALERTING_SCREENSHOTS_CAPTURE=true` is already set. The alert rule is linked to a panel (rule settings > **Link dashboard and panel**, then **BGP session state**). A contact point that shows images is needed, such as Discord, Telegram or email. A plain webhook is meant for text and usually does not show the picture.

## Test scenarios

```bash
# Traffic: the port panels rise
docker exec clab-sonic-bgp-sw1 ping -c 300 -i 0.2 10.0.12.2

# Instant BGP failure: the state turns red
docker exec clab-sonic-bgp-sw2 vtysh -c "configure terminal" -c "router bgp 65002" -c "neighbor 10.0.23.2 shutdown"

# Cable failure (short timers are needed for a fast reaction, see below)
docker exec clab-sonic-bgp-sw3 ip link set eth1 down
docker exec clab-sonic-bgp-sw3 ip link set eth1 up
```

**Why does a cable failure take about 3 minutes to show?** In SONiC-VS, `ip link set eth1 down` does not tell FRR that the link failed, so BGP waits for the 180-second hold timer. For a reaction in about 9 seconds, 3/9 timers are set on both ends and the session is reset:

```bash
docker exec clab-sonic-bgp-sw2 vtysh -c "configure terminal" -c "router bgp 65002" -c "neighbor 10.0.23.2 timers 3 9"
docker exec clab-sonic-bgp-sw3 vtysh -c "configure terminal" -c "router bgp 65003" -c "neighbor 10.0.23.1 timers 3 9"
docker exec clab-sonic-bgp-sw2 vtysh -c "clear bgp 10.0.23.2"
```

Real networks use link-down detection or BFD for sub-second failure detection.

## Troubleshooting

Problems found while building this lab:

| Problem | Cause | Fix |
|---|---|---|
| Prometheus container exits; log says `rules.yml: is a directory` | Docker creates an empty folder when a mounted file is missing | `docker compose down`, `rmdir prometheus/rules.yml`, the real file is created, then the stack is started again |
| `clab-sonic-bgp-sw1:9100` does not open in the browser | The name works only inside the Docker network | Test with `docker exec prometheus wget -qO- http://clab-sonic-bgp-sw1:9100/metrics`, or open Prometheus **Status > Targets** |
| Grafana data source: `dial tcp [::1]:9090: connection refused` | `localhost` inside Grafana is Grafana itself | Use `http://prometheus:9090` |
| No `sonic_bgp_*` metrics; `/textfiles` empty in `ne-sw1` | Collector and sidecar use different host folders, or the sidecar has a stale mount | Check `docker inspect ne-sw1 --format '{{json .Mounts}}'`, use one absolute path, and run `./start_exporters.sh` again |
| `sonic_bgp_collect_ok` is 0 | Collector cannot read BGP | Check `docker exec clab-sonic-bgp-sw1 vtysh -c "show bgp summary json"` |
| `rm: can't remove ... Permission denied` | The command was run inside a container with a read-only mount | Files are removed on the host, not with `docker exec` |
| Grafana exits; log says `renderer_token ... not allowed` | Default renderer token is rejected | `RENDERER_TOKEN` is set in `.env`, used by both Grafana and the renderer |
| Renderer image pull times out | Slow or unstable network, large image | Retry the pull loop, set `"max-concurrent-downloads": 1` in the Docker Engine settings of Docker Desktop, or try without a VPN |
| Rendered image shows only the top half | Fixed `height` is smaller than the dashboard | Use `height=-1`, or a larger fixed height |
| BGP still shows Up after `ip link set eth1 down` | Hold timer is 180 s, and SONiC-VS does not pass link-down to FRR | Use 3/9 timers, or the `neighbor ... shutdown` test |
| Ethernet queries return nothing | Device names differ | List them with `curl -s localhost:9090/api/v1/label/device/values` |
| Sidecars stop working after the lab restarts | Sidecars are tied to the old switch containers | Run `./start_exporters.sh` again |

## Security notes

- `.env` (already in `.gitignore`), tokens, webhook URLs and passwords must never be committed.
- The Grafana admin password is changed after the first login.
- This setup is meant for a lab. For production, fixed image versions, authentication on Prometheus, HTTPS and secrets management are recommended.

## Clean up

```bash
docker compose down            # stops Grafana, Prometheus and the renderer (data is kept)
docker compose down -v         # also deletes dashboards and metrics data
./ stop_exporters.sh
```

Warning: `down -v` deletes the Grafana volume. Dashboards are exported first.

## Learning outcomes

- How Prometheus scrapes and stores metrics, and how data is queried with PromQL
- How a network OS is monitored in a lab with exporters and sidecars
- How dashboards are built, with variables and suitable panel types
- How BGP session state is alerted on and sent to a webhook
- How dashboards are rendered as images
- How BGP failure detection works (hold timer, BFD)

## References

- Prometheus: https://prometheus.io/docs/introduction/overview/
- node_exporter and the textfile collector: https://github.com/prometheus/node_exporter
- Grafana documentation: https://grafana.com/docs/grafana/latest/
- Grafana alerting: https://grafana.com/docs/grafana/latest/alerting/
- Grafana image rendering: https://grafana.com/docs/grafana/latest/setup-grafana/image-rendering/
- Containerlab: https://containerlab.dev
- SONiC: https://github.com/sonic-net/SONiC
- webhook.site (free webhook testing): https://webhook.site
