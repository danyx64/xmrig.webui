#!/bin/sh
set -eu

explicit_threads=0
for arg in "$@"; do
    case "$arg" in
        -t|--threads|--threads=*|-t[0-9]*)
            explicit_threads=1
            ;;
    esac
done

threads=""

if [ "$explicit_threads" -eq 0 ]; then
    case "${XMRIG_THREADS:-auto}" in
        all|max|100%)
            threads="$(nproc)"
            ;;
        auto|"")
            threads=""
            ;;
        *[!0-9]*)
            echo "[xmrig-entrypoint] invalid XMRIG_THREADS='${XMRIG_THREADS}'. Use auto, all or a positive integer." >&2
            exit 2
            ;;
        *)
            if [ "${XMRIG_THREADS}" -lt 1 ]; then
                echo "[xmrig-entrypoint] XMRIG_THREADS must be >= 1." >&2
                exit 2
            fi
            threads="${XMRIG_THREADS}"
            ;;
    esac

    if [ -n "$threads" ]; then
        set -- "$@" "--threads=$threads"
    fi
fi

echo "[xmrig-entrypoint] logical CPUs visible: $(nproc); thread mode: ${XMRIG_THREADS:-auto}${threads:+ -> $threads threads}" >&2

exec /usr/local/bin/xmrig "$@"
