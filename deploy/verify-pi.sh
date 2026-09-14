#!/usr/bin/env bash
# Read-only evidence collection, excluding credentials and environment files.
set -u
uname -a
uname -m
cat /etc/os-release
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,MODEL
findmnt
df -h
systemctl --failed
timedatectl
systemctl --user status digital-azan --no-pager
pactl info
pactl list short sinks
command -v mpv
command -v ffprobe
curl -sS "http://127.0.0.1:${AZAN_PORT:-8080}/health"
