#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root: sudo ./native-linux/install-fedora.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if command -v dnf >/dev/null 2>&1; then
  dnf install -y python3 python3-pip
fi

install -d -m 0755 /opt/xmrig-webui-agent
cp "${REPO_DIR}/agent.py" /opt/xmrig-webui-agent/agent.py
cp "${REPO_DIR}/requirements.txt" /opt/xmrig-webui-agent/requirements.txt

python3 -m venv /opt/xmrig-webui-agent/venv
/opt/xmrig-webui-agent/venv/bin/pip install --upgrade pip
/opt/xmrig-webui-agent/venv/bin/pip install -r /opt/xmrig-webui-agent/requirements.txt

install -m 0755 "${SCRIPT_DIR}/run-xmrig.sh" /usr/local/bin/xmrig-native-node
install -m 0644 "${SCRIPT_DIR}/systemd/xmrig-native.service" /etc/systemd/system/xmrig-native.service
install -m 0644 "${SCRIPT_DIR}/systemd/xmrig-agent.service" /etc/systemd/system/xmrig-agent.service

if [[ ! -f /etc/xmrig-native.env ]]; then
  install -m 0600 "${SCRIPT_DIR}/xmrig-native.env.example" /etc/xmrig-native.env
  echo
  echo "Created /etc/xmrig-native.env."
  echo "Edit XMRIG_BIN, XMR_WALLET and WORKER_NAME before starting the miner."
fi

systemctl daemon-reload
systemctl enable --now xmrig-agent.service
systemctl enable xmrig-native.service

echo
echo "Temperature agent: http://THIS-PC-IP:18089/v1/metrics"
echo "XMRig API after miner start: http://THIS-PC-IP:18088/2/summary"
echo
echo "Edit configuration:"
echo "  sudo nano /etc/xmrig-native.env"
echo
echo "Then start/restart miner:"
echo "  sudo systemctl restart xmrig-native"
echo
echo "Check:"
echo "  systemctl status xmrig-native --no-pager"
echo "  curl http://127.0.0.1:18088/2/summary"
echo "  curl http://127.0.0.1:18089/v1/metrics"
