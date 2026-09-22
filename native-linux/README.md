# Native Linux / Fedora node

This directory makes a **non-Docker XMRig installation** compatible with the same XMRig Unified WebUI used by the Docker/ZimaOS nodes.

The dashboard reads:

- XMRig HTTP API on TCP **18088**
- optional CPU temperature agent on TCP **18089**

## Install on Fedora/Linux

From a clone of this repository:

```bash
sudo ./native-linux/install-fedora.sh
```

Edit:

```bash
sudo nano /etc/xmrig-native.env
```

Set at least:

```dotenv
XMRIG_BIN=/home/YOUR_USER/xmrig/build/xmrig
XMR_WALLET=YOUR_MONERO_WALLET
WORKER_NAME=PC-01
XMRIG_THREADS=all
```

Then:

```bash
sudo systemctl restart xmrig-native
```

Both services are enabled at boot.

## Verify locally

```bash
systemctl status xmrig-native --no-pager
systemctl status xmrig-agent --no-pager
curl http://127.0.0.1:18088/2/summary
curl http://127.0.0.1:18089/v1/metrics
```

If an API token is configured in `/etc/xmrig-native.env`, test XMRig with:

```bash
curl -H 'Authorization: Bearer YOUR_TOKEN' http://127.0.0.1:18088/2/summary
```

## Add the PC to the central dashboard

For a PC at `192.168.1.50`:

```text
Name:      PC-01
XMRig API: http://192.168.1.50:18088
Agent:     http://192.168.1.50:18089
Token:     leave blank unless XMRIG_API_TOKEN is configured
```

Only the central dashboard host needs access to those ports. Keep **18088/18089** on a trusted LAN/VPN and do not expose them directly to the Internet.

## Fedora firewall

If firewalld blocks the dashboard, allow the two TCP ports on the trusted LAN zone, or preferably restrict access to the dashboard server IP.

Example broad LAN-zone rule:

```bash
sudo firewall-cmd --permanent --add-port=18088/tcp
sudo firewall-cmd --permanent --add-port=18089/tcp
sudo firewall-cmd --reload
```

## Thread mode

`XMRIG_THREADS=all` forces one mining thread per logical CPU. `auto` leaves RandomX thread selection to XMRig. A numeric value forces exactly that many threads.

This controls CPU occupancy, not necessarily maximum RandomX hashrate. Cache-limited CPUs can hash faster with fewer threads.
