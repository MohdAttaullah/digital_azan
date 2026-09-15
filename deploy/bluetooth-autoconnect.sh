#!/usr/bin/env bash
# Keep one configured, already-paired Bluetooth speaker connected and selected.
set -euo pipefail

MAC=${AZAN_BLUETOOTH_MAC:-}
INTERVAL=${AZAN_BLUETOOTH_RETRY_SECONDS:-15}
[[ "$MAC" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]] || {
  echo 'AZAN_BLUETOOTH_MAC must contain the paired speaker MAC address.'
  exit 2
}
[[ "$INTERVAL" =~ ^[0-9]+$ ]] && (( INTERVAL >= 5 && INTERVAL <= 300 )) || {
  echo 'AZAN_BLUETOOTH_RETRY_SECONDS must be 5-300.'
  exit 2
}

sink_fragment=${MAC//:/_}
last_state=
while true; do
  connected=no
  if bluetoothctl info "$MAC" 2>/dev/null | grep -q 'Connected: yes'; then
    connected=yes
  else
    bluetoothctl connect "$MAC" >/dev/null 2>&1 || true
    if bluetoothctl info "$MAC" 2>/dev/null | grep -q 'Connected: yes'; then
      connected=yes
    fi
  fi

  sink=
  if [[ "$connected" == yes ]]; then
    for _ in $(seq 1 10); do
      sink=$(pactl list short sinks 2>/dev/null | awk -v fragment="$sink_fragment" '$2 ~ fragment {print $2; exit}')
      [[ -n "$sink" ]] && break
      sleep 1
    done
    if [[ -n "$sink" ]]; then
      pactl set-default-sink "$sink"
    fi
  fi

  state="$connected:${sink:-no-sink}"
  if [[ "$state" != "$last_state" ]]; then
    echo "Bluetooth speaker $MAC state: $state"
    last_state=$state
  fi
  sleep "$INTERVAL"
done
