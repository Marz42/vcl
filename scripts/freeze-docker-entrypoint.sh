#!/usr/bin/env bash
# Entrypoint for freeze tests inside Ubuntu 22.04 container (systemd as PID1 preferred).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq systemd systemd-sysv dbus curl ca-certificates python3 \
  iproute2 procps openssl sqlite3 jq coreutils grep sed gawk tar gzip sudo \
  >/dev/null

# If not already PID1 systemd, just run the freeze script under fake systemctl? Prefer real.
if [[ "$(cat /proc/1/comm 2>/dev/null || true)" != "systemd" ]]; then
  echo "WARN: PID1 is not systemd ($(cat /proc/1/comm)); attempting freeze anyway"
fi

SRC=/opt/vincula-src
STAGE=/opt/vincula-freeze/vincula-0.2.4
rm -rf /opt/vincula-freeze
mkdir -p "$STAGE"
cp -a "$SRC/vincula.sh" "$SRC/bin" "$SRC/lib" "$SRC/scripts" "$SRC/release.lock" "$SRC/vincula.sh.sha256" "$STAGE/" 2>/dev/null || \
  cp -a "$SRC/vincula.sh" "$SRC/bin" "$SRC/lib" "$SRC/scripts" "$STAGE/"
# refresh lock inside stage
( cd "$STAGE" && bash scripts/gen-release-lock.sh >/dev/null )
export VCL_TREE_024=$STAGE
export VCL_EVID=/root/vcl-rc-evidence/freeze
export VCL_PORT=8443
bash "$STAGE/scripts/freeze-run-ubuntu2204.sh"
