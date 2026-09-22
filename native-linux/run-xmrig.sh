#!/usr/bin/env bash
set -euo pipefail

: "${XMRIG_BIN:?Set XMRIG_BIN in /etc/xmrig-native.env}"
: "${XMR_POOL:?Set XMRIG_POOL/XMR_POOL in /etc/xmrig-native.env}"
: "${XMR_WALLET:?Set XMRIG_WALLET/XMR_WALLET in /etc/xmrig-native.env}"
: "${WORKER_NAME:?Set WORKER_NAME in /etc/xmrig-native.env}"

if [[ ! -x "${XMRIG_BIN}" ]]; then
  echo "XMRig executable not found or not executable: ${XMRIG_BIN}" >&2
  exit 1
fi

args=(
  --coin=monero
  "--url=${XMR_POOL}"
  "--user=${XMR_WALLET}"
  "--pass=${WORKER_NAME}"
  "--api-worker-id=${WORKER_NAME}"
  "--http-host=${XMRIG_HTTP_HOST:-0.0.0.0}"
  "--http-port=${XMRIG_HTTP_PORT:-18088}"
  --cpu-max-threads-hint=100
  --cpu-no-yield
  --cpu-priority=5
  --huge-pages-jit
  --keepalive
  --print-time=30
)

case "${XMRIG_THREADS:-auto}" in
  all|max|100%)
    args+=("--threads=$(nproc)")
    ;;
  auto|"")
    ;;
  *[!0-9]*)
    echo "Invalid XMRIG_THREADS='${XMRIG_THREADS}'. Use auto, all, or a positive integer." >&2
    exit 2
    ;;
  *)
    if (( XMRIG_THREADS < 1 )); then
      echo "XMRIG_THREADS must be >= 1" >&2
      exit 2
    fi
    args+=("--threads=${XMRIG_THREADS}")
    ;;
esac

if [[ -n "${XMRIG_API_TOKEN:-}" ]]; then
  args+=("--http-access-token=${XMRIG_API_TOKEN}")
fi

echo "[xmrig-native] worker=${WORKER_NAME} api=${XMRIG_HTTP_HOST:-0.0.0.0}:${XMRIG_HTTP_PORT:-18088} logical_cpus=$(nproc) threads=${XMRIG_THREADS:-auto}" >&2

exec "${XMRIG_BIN}" "${args[@]}"
