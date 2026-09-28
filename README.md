# SONiC Learning Lab

Hands-on notes from bringing up SONiC-VS (SONiC's virtual switch) on a laptop and tracing its internal code flow, starting with VLAN configuration.

## What's in this repo

| File | What it covers |
|---|---|
| [`SONIC switch bringup.docx`](./SONIC%20switch%20bringup.docx) | Step-by-step setup of SONiC-VS via Docker inside WSL2 — from enabling WSL2 through logging into the SONiC CLI, running basic interface commands, redis-db sample output and debug commands and sample debug syslog for vlan config |
| [`sonic-vlan-config-codeflow.md`](./sonic-vlan-config-codeflow.md) | How a VLAN configuration command flows through SONiC internally — CONFIG_DB → orchagent → APPL_DB → syncd → ASIC_DB — with the exact `redis-cli` commands used to inspect each stage. |

## Why this repo exists

SONiC doesn't work like a traditional monolithic NOS — each function (interfaces, VLANs, routing, etc.) is handled by a separate daemon, and these daemons talk to each other through Redis databases rather than direct function calls. This repo documents that pipeline hands-on: standing up a real (virtual) switch, running config commands, and watching the resulting state changes ripple through each database in order.

## Quick start

1. Follow `SONIC switch bringup.docx` to get a running SONiC-VS container.
2. Once it's up, use `sonic-vlan-config-codeflow.md` to configure a VLAN and trace it through CONFIG_DB, APPL_DB, ASIC_DB, and STATE_DB.

## Environment

- Windows laptop, WSL2 (Ubuntu), Docker Engine
- SONiC-VS (virtual switch) container image




