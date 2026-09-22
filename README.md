# XMRig Unified WebUI

Self-hosted dashboard for XMRig nodes with pool statistics from **SupportXMR** and **MoneroOcean**.

The dashboard is intentionally separate from the miner process: one central container can monitor multiple Linux/Fedora/ZimaOS servers, while an optional lightweight agent exposes CPU temperatures. Configuration is stored in SQLite under a Docker volume, not in the Git repository or browser localStorage.

## Features

- SupportXMR and MoneroOcean auto-detection from the pool URL.
- Pending XMR (`amtDue`) and total paid XMR (`amtPaid`).
- Pool-side hashrate and worker statistics.
- Live hashrate from every configured XMRig HTTP API.
- Total live hashrate across all servers.
- Accepted/rejected shares and XMRig pool/worker status.
- Optional CPU temperature agent for Linux hosts.
- Local SQLite history with hashrate and temperature mini charts.
- Persistent configuration across container restarts/recreates.
- Standard Docker Compose deployment.
- ZimaOS/CasaOS-compatible `Apps/XMRigWebUI/docker-compose.yml` with top-level `x-casaos` metadata.
- Multi-architecture dashboard image (`amd64`, `arm64`) via GitHub Actions/GHCR.
- Optional XMRig worker stack built from the official XMRig source tag.

## Privacy / repository safety

The repository contains **no wallet, private IP, password, API token or personal miner name**.

Do not commit `.env` files. They are ignored by `.gitignore`.

Pool/wallet settings entered in the WebUI are stored in:

```text
/data/xmrig-webui.db
```

inside the persistent Docker volume.

## Quick start: dashboard

Clone and run:

```bash
git clone https://github.com/danyx64/xmrig.webui.git
cd xmrig.webui
cp .env.example .env
docker compose up -d --build
```

Open:

```text
http://SERVER-IP:8080
```

Then open **Impostazioni** and enter either:

```text
https://supportxmr.com
```

or:

```text
https://moneroocean.stream
```

plus your Monero wallet address.

### Add an XMRig node

XMRig must expose its HTTP API to the dashboard host. Example fields in the WebUI:

```text
Name:       Fedora44
XMRig API:  http://192.168.1.20:18088
Agent:      http://192.168.1.20:18089   (optional)
Token:      optional XMRig HTTP API token
```

A typical XMRig config section is:

```json
{
  "api": {
    "worker-id": "my-worker"
  },
  "http": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 18088,
    "access-token": null,
    "restricted": true
  }
}
```

Keep ports `18088` and `18089` limited to a trusted LAN/VPN. Do not expose an unauthenticated miner API directly to the public Internet.

## CPU temperature agent

XMRig does not provide CPU temperature in its summary API, so this project includes a small read-only Linux sensor agent.

On each miner host:

```bash
docker compose -f docker-compose.agent.yml up -d --build
```

The agent listens on:

```text
http://HOST:18089/v1/metrics
```

It reads Linux `hwmon`/thermal data from `/sys` mounted read-only. No `privileged: true` is required for the agent.

## Optional full worker stack (XMRig + temperature agent)

The `worker-stack/` directory can build XMRig from the official source tag and run it with the temperature agent.

```bash
cd worker-stack
cp .env.example .env
nano .env
```

Example `.env`:

```dotenv
XMRIG_VERSION=6.26.0
XMR_POOL=pool.supportxmr.com:3333
XMR_WALLET=YOUR_MONERO_WALLET
WORKER_NAME=my-worker
XMRIG_THREADS=all
CPU_THREADS_HINT=100
```

Run:

```bash
docker compose up -d --build
```

The worker stack uses host networking so its APIs are available on `18088` and `18089`.

### CPU thread mode

The miner image supports `XMRIG_THREADS`:

```text
XMRIG_THREADS=all   # force one XMRig thread per logical CPU visible to Docker
XMRIG_THREADS=auto  # use XMRig automatic RandomX thread selection
XMRIG_THREADS=8     # force exactly 8 threads
```

`all` is implemented at container start with `nproc`, so it follows the CPUs actually visible to the container. Docker has no CPU quota in the supplied miner Compose files, so by default all host CPUs are visible.

For RandomX, forcing every logical CPU is not guaranteed to produce the highest hashrate: cache capacity can make XMRig's automatic profile faster even when it uses fewer threads. Use `all` when the goal is maximum CPU occupancy; benchmark `auto` versus `all` when the goal is maximum H/s.

### MSR and Huge Pages

The optional XMRig worker container is intentionally separate from the dashboard because MSR/CPU tuning is host-specific and can require elevated privileges. The worker compose is privileged and mounts `/dev/cpu` so XMRig can use host MSR devices when the host permits it.

For modern Linux kernels, XMRig may require the host boot/module option:

```text
msr.allow_writes=on
```

Huge Pages must also be configured on the host. These settings are not changed automatically by this project.

## ZimaOS / CasaOS

A source app definition is included at:

```text
Apps/XMRigWebUI/docker-compose.yml
```

It follows the current top-level `x-casaos` layout and installs only the non-privileged dashboard. This is deliberate: a NAS dashboard should not need access to CPU MSRs or host sensor devices just to display mining statistics.

After the GHCR image exists, ZimaOS can deploy:

```text
ghcr.io/danyx64/xmrig.webui:latest
```

The app package declares `amd64` and `arm64` dashboard support.

## Pool API mapping

The dashboard currently maps these user-facing URLs automatically:

| Entered URL | API base |
| --- | --- |
| `https://supportxmr.com` | `https://supportxmr.com/api` |
| `https://moneroocean.stream` | `https://api.moneroocean.stream` |

Both are nodejs-pool-style APIs. The backend currently queries:

```text
/miner/<wallet>/stats
/miner/<wallet>/stats/allWorkers
/miner/<wallet>/chart/hashrate
/miner/<wallet>/payments
```

If one optional endpoint is unavailable, the rest of the dashboard continues to work.

## XMRig endpoints

For broad compatibility the dashboard tries:

```text
/2/summary
```

and falls back to:

```text
/1/summary
```

The dashboard uses the XMRig API only for monitoring; it does not alter miner configuration.

## Data model

SQLite stores:

- dashboard settings;
- XMRig node list;
- node URLs and optional API tokens;
- sampled hashrate;
- sampled CPU temperatures;
- online/offline history.

Default history retention is seven days and can be changed with:

```dotenv
HISTORY_DAYS=7
REFRESH_SECONDS=30
```

## Docker commands

Start:

```bash
docker compose up -d
```

Logs:

```bash
docker compose logs -f dashboard
```

Update:

```bash
git pull
docker compose up -d --build
```

Stop:

```bash
docker compose down
```

Remove containers but retain the SQLite volume:

```bash
docker compose down
```

Delete all dashboard data as well:

```bash
docker compose down -v
```

## Security

This is a homelab/LAN dashboard. Recommended deployment:

- expose the WebUI only on a trusted LAN or behind your authenticated reverse proxy/VPN;
- protect XMRig APIs with firewall rules and, where appropriate, an HTTP API token;
- do not publish `18088`/`18089` to the public Internet;
- never commit your wallet-specific `.env` files or database volume.

## Development

Python syntax check:

```bash
python -m compileall app.py agent.py
```

Run without Docker:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
DB_PATH=./data/dev.db python app.py
```

## Upstream references

- XMRig: https://github.com/xmrig/xmrig
- XMRig HTTP API: https://xmrig.com/docs/miner/api
- SupportXMR: https://supportxmr.com
- MoneroOcean: https://moneroocean.stream
- MoneroOcean pool UI: https://github.com/MoneroOcean/mo-pool-ui

## License

MIT. See `LICENSE`.
