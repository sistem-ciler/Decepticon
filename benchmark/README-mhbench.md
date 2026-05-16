# MHBench Benchmark Provider — Operator Guide

PR 1 scaffold. Wires the upstream
[MHBench](https://github.com/PurpleAILAB/MHBench) topology orchestrator into
Decepticon's benchmark harness so Decepticon agents can be scored against
multi-host network attack scenarios.

This document is intended for operators with an OpenStack tenant. There is no
local-Docker substitute for MHBench's VM-based topologies.

## What's wired in PR 1

- `benchmark/providers/mhbench.py` — `MHBenchProvider` wraps
  `benchmark/MHBench/main.py` for setup / teardown.
- `--provider mhbench` flag on `python -m benchmark.runner`.
- `--mhbench-config <path>` flag pointing at the upstream MHBench `config.json`.
- **One challenge end-to-end:** `mhbench/chain2hosts` (smallest topology — 2 hosts).

Out of scope for PR 1:
- The remaining 14 hand-tuned spec environments and 30 generated topologies
  (`EquifaxSmall/Medium/Large`, `ICSEnvironment`, `EnterpriseA/B`, etc.).
  These land in PR 2/3.
- Tight expected-flag verification — PR 1 accepts any `FLAG{<hex>}` string in
  agent output. Operator is responsible for seeding the flag via
  `ansible/goals/addFlag.yml` from within their MHBench compile pipeline.
- Caldera C2 / Falco / SysFlow telemetry integration. PR 4 territory.
- Pre-built smoke YAML config — current CLI flags cover the smoke run.

## Prerequisites

| Requirement                  | Notes                                                                                  |
| ---------------------------- | -------------------------------------------------------------------------------------- |
| OpenStack project + creds    | API access; create networks, routers, floating IPs, compute instances. Required — MHBench is hard-coded to OpenStack (Sec. 5 of Singer et al., arXiv:2501.16466). See [Getting an OpenStack tenant](#getting-an-openstack-tenant). |
| Hardware (local OpenStack)   | Upstream README cites 64 vCPU / 128 GB RAM / ~2 TB SSD for the full 40-environment suite; PR 1's single Chain2Hosts spike fits in ~8 vCPU / 16 GB / 50 GB. |
| MHBench `config.json`        | Populate from `benchmark/MHBench/config/config_example.json`. See below.               |
| Decepticon backend up        | `make dev` and wait for LiteLLM + LangGraph healthy (per `feedback_benchmark_startup`). |
| Reachability sandbox→tenant  | Decepticon's sandbox must be able to SSH into the attacker VM's floating IP.           |
| C&C server (optional)        | MHBench bundles MITRE Caldera as the default C&C and runs `ansible/caldera/install_attacker.yml` during compile. Caldera is substitutable per the paper ("Other C&C servers such as Cobalt Strike or Merlin could also be used", Sec. 5 footnote 12). Decepticon attacks the topology by SSH directly into the Kali VM, so a working C&C is **not required** for our scoring path — but `c2_config` must still be filled in for compile to complete without raising. |

## Getting an OpenStack tenant

| Path                                  | Time-to-tenant | Cost (Chain2Hosts smoke run)           | Notes                                                                                |
| ------------------------------------- | -------------- | -------------------------------------- | ------------------------------------------------------------------------------------ |
| **Public cloud (OVHcloud Public Cloud, Open Telekom Cloud, Catalyst Cloud)** | minutes        | ~$0.05/vCPU·hr; ~$0.50 total for the smoke run | Fastest. Credit card; horizon UI gives you the auth_url, region, project name. Quota request needed for full 40-env suite. |
| **Academic cloud (NeCTAR, KISTI, KREONET, JetStream2)** | days to weeks  | free for affiliated researchers        | Standard for research labs. Allocation request varies by provider.                   |
| **MicroStack** (`sudo snap install microstack --beta`) | ~30 min on a workstation | hardware only                          | Single-node OpenStack on Ubuntu 20.04+. ~16 GB RAM minimum. Fine for the Chain2Hosts smoke run; will not host EquifaxLarge.       |
| **DevStack** ([devstack docs](https://docs.openstack.org/devstack/latest/)) | ~1–2 hr on a server | hardware only                          | Single- or multi-node; closer to full feature parity. Recommended once you outgrow MicroStack. |
| **Kolla-Ansible** ([kolla-ansible docs](https://docs.openstack.org/kolla-ansible/latest/)) | ~half day on a cluster | hardware only                          | Production-grade. Use when you want to run the full 40-environment matrix or share the tenant. |

Whichever path you pick, the four things you must end up with are:

1. An `auth_url` (`https://<endpoint>:5000/v3` for Keystone v3),
2. A `username` / `password` (or app credentials),
3. A `project_name` and `region_name` your user can deploy into,
4. A keypair named `perry_key` (MHBench expects that exact name unless you patch the spec classes):
   ```bash
   openstack keypair create perry_key > ~/perry_key.pem
   chmod 600 ~/perry_key.pem
   ```

These four values feed directly into `openstack_config` in step 3 below.

## Initial setup

1. **Initialize the submodule.** From the repo root:

   ```bash
   git submodule update --init --recursive benchmark/MHBench
   ```

   The submodule is pinned to the `decepticon` branch of
   `PurpleAILAB/MHBench` (a fork of `bsinger98/MHBench` carrying Decepticon
   patches if/when needed).

2. **Install MHBench dependencies.** From `benchmark/MHBench/`:

   ```bash
   cd benchmark/MHBench
   uv sync
   ```

3. **Create the MHBench config.** Copy and fill in OpenStack credentials,
   external IP, and Elastic/C2 endpoints:

   ```bash
   cp benchmark/MHBench/config/config_example.json \
      benchmark/MHBench/config/config.json
   $EDITOR benchmark/MHBench/config/config.json
   ```

   What must be filled in for Decepticon's PR 1 scoring path:

   - **`openstack_config`** — all six fields. Required for `compile` and `setup` to talk to your tenant.
   - **`external_ip`** — the host that has internet-facing reachability to the deployed VMs (typically the OpenStack jump host or your workstation if running MicroStack). Used to derive floating IP routing.
   - **`elastic_config` / `c2_config`** — filled with any non-empty placeholders is enough for PR 1. Caldera install will run during compile but no real C&C is needed because Decepticon SSHes into the Kali VM directly. If you want to drive the canonical Caldera-based attacker (for parity with the paper's Incalmo evaluation), stand up Caldera on `external_ip:8888` and fill in `c2_config.api_key` properly.

   The path you supply via `--mhbench-config` is passed verbatim to MHBench's
   `main.py --config-file` flag.

4. **(Optional) Pre-compile a topology snapshot.** Compile can take hours on a
   first run because it provisions VMs, installs packages, and snapshots
   images. Subsequent `setup` runs reuse the snapshots:

   ```bash
   cd benchmark/MHBench
   uv run python main.py --type Chain2Hosts --config-file config/config.json compile
   ```

   The provider's `setup()` calls the `setup` subcommand (not `compile`), so
   it expects this step to be done out-of-band.

## Running

```bash
uv run python -m benchmark.runner \
  --provider mhbench \
  --mhbench-config benchmark/MHBench/config/config.json \
  --ids mhbench/chain2hosts \
  --timeout 7200
```

Per-challenge timeout defaults to 1800s; bump it for MHBench since setup is
materially heavier than for Docker-based providers.

## How scoring works in PR 1

1. `MHBenchProvider.setup()` shells out to `main.py … setup` and parses the
   attacker VM's floating IP from stdout. The result is exposed to the agent
   as `target_url=ssh://kali@<ip>:22`.
2. The Decepticon agent attempts to compromise the topology. Its output and
   any workspace artefacts pass through the harness back to
   `MHBenchProvider.evaluate()`.
3. Evaluate returns `passed=True` iff a `FLAG{<hex>}` token appears anywhere
   in agent output. There is no expected-value comparison in PR 1 — the
   operator is trusted to have seeded the flag (typically via
   `ansible/goals/addFlag.yml` invoked from their compile pipeline).
4. `teardown()` shells out to `main.py … teardown` and frees the OpenStack
   resources.

## Known limitations

- **Stdout parsing is best-effort.** The provider scans MHBench's `setup`
  stdout for a line matching `attacker_floating_ip[:= ]<ip>` or
  `attacker_ip[:= ]<ip>`. Upstream does not (yet) emit a stable
  machine-readable marker for this, so the parse falls back to "no endpoint
  found" on format changes. Watch for the explicit error in setup output if
  the run fails immediately.
- **No CI coverage.** GitHub Actions runners do not have an OpenStack tenant.
  The MHBench provider is excluded from `make test` and `make quality`.
- **Sequential only (practically).** Each MHBench environment owns the
  OpenStack quota during setup, so running `--parallel >1` against the same
  tenant will collide. Run sequentially or use separate tenants per worker.

## Roadmap

| PR | Scope |
| -- | ----- |
| **PR 1 (this)** | Foundation + submodule + Chain2Hosts spike. |
| PR 2            | Remaining 14 spec environments + per-env metadata table. |
| PR 3            | 30 generated topologies (`generated_network_*.json`) + ansible-based exfil verification. |
| PR 4 (optional) | Caldera C2 / Falco / SysFlow telemetry — capability-graded scoring. |
