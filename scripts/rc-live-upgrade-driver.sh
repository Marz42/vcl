#!/usr/bin/env bash
# Orchestrate live upgrade RC on a remote Debian VPS.
# Required: VCL_RC_HOST, VCL_RC_PASS (or SSH key via VCL_RC_SSH)
set -Eeuo pipefail
IFS=$'\n\t'

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
HOST=${VCL_RC_HOST:?set VCL_RC_HOST}
USER=${VCL_RC_USER:-root}
PASS=${VCL_RC_PASS:-}
SERVER=${VCL_SERVER:-$HOST}
EVID_LOCAL="${ROOT}/docs/evidence/0.2.4-0.2.6-live"
REMOTE_TREES=/root/vcl-rc-trees
REMOTE_EVID=/root/vcl-rc-evidence/upgrade-246

ASKPASS="${ROOT}/scripts/rc-askpass.sh"
chmod +x "$ASKPASS" 2>/dev/null || true

# Prefer sshpass; else SSH_ASKPASS (no TTY) with VCL_RC_PASS.
ssh_env() {
  if command -v sshpass >/dev/null 2>&1 && [[ -n "$PASS" ]]; then
    export VCL_USE_SSHPASS=1
  elif [[ -n "$PASS" ]]; then
    export VCL_USE_SSHPASS=0
    export SSH_ASKPASS="$ASKPASS"
    export SSH_ASKPASS_REQUIRE=force
    export DISPLAY="${DISPLAY:-:0}"
    export VCL_RC_PASS="$PASS"
  fi
}

ssh_base() {
  if [[ -n "${VCL_RC_SSH:-}" ]]; then
    # shellcheck disable=SC2086
    eval "$VCL_RC_SSH" "$@"
    return
  fi
  ssh_env
  if [[ "${VCL_USE_SSHPASS:-0}" == 1 ]]; then
    sshpass -p "$PASS" ssh -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/vcl-rc-known_hosts \
      -o PreferredAuthentications=password -o PubkeyAuthentication=no \
      "${USER}@${HOST}" "$@"
  elif [[ -n "$PASS" ]]; then
    setsid -w ssh -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/vcl-rc-known_hosts \
      -o PreferredAuthentications=password -o PubkeyAuthentication=no \
      -o NumberOfPasswordPrompts=1 \
      "${USER}@${HOST}" "$@"
  else
    ssh -o StrictHostKeyChecking=accept-new "${USER}@${HOST}" "$@"
  fi
}

scp_to() {
  local src=$1 dest=$2
  ssh_env
  if [[ "${VCL_USE_SSHPASS:-0}" == 1 ]]; then
    sshpass -p "$PASS" scp -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/vcl-rc-known_hosts \
      -o PreferredAuthentications=password -o PubkeyAuthentication=no \
      -r "$src" "${USER}@${HOST}:${dest}"
  elif [[ -n "$PASS" ]]; then
    setsid -w scp -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/vcl-rc-known_hosts \
      -o PreferredAuthentications=password -o PubkeyAuthentication=no \
      -r "$src" "${USER}@${HOST}:${dest}"
  else
    scp -o StrictHostKeyChecking=accept-new -r "$src" "${USER}@${HOST}:${dest}"
  fi
}

scp_from() {
  local src=$1 dest=$2
  ssh_env
  if [[ "${VCL_USE_SSHPASS:-0}" == 1 ]]; then
    sshpass -p "$PASS" scp -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/vcl-rc-known_hosts \
      -o PreferredAuthentications=password -o PubkeyAuthentication=no \
      -r "${USER}@${HOST}:${src}" "$dest"
  elif [[ -n "$PASS" ]]; then
    setsid -w scp -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/vcl-rc-known_hosts \
      -o PreferredAuthentications=password -o PubkeyAuthentication=no \
      -r "${USER}@${HOST}:${src}" "$dest"
  else
    scp -o StrictHostKeyChecking=accept-new -r "${USER}@${HOST}:${src}" "$dest"
  fi
}

printf '== build artifacts ==\n'
if [[ "${VCL_RC_SKIP_BUILD:-0}" == "1" && -d "${ROOT}/dist/rc-live/vincula-0.2.6" ]]; then
  printf 'skip build (VCL_RC_SKIP_BUILD=1)\n'
else
  bash "${ROOT}/scripts/rc-build-artifacts.sh"
fi

printf '== probe host ==\n'
ssh_base "echo OK_HOST; grep PRETTY_NAME= /etc/os-release; uname -m; python3 --version"

printf '== upload trees + onhost script ==\n'
ssh_base "rm -rf ${REMOTE_TREES} && mkdir -p ${REMOTE_TREES}"
scp_to "${ROOT}/dist/rc-live/vincula-0.2.4" "${REMOTE_TREES}/"
scp_to "${ROOT}/dist/rc-live/vincula-0.2.5" "${REMOTE_TREES}/"
scp_to "${ROOT}/dist/rc-live/vincula-0.2.6" "${REMOTE_TREES}/"
scp_to "${ROOT}/scripts/rc-live-onhost.sh" /root/rc-live-onhost.sh
ssh_base "chmod +x /root/rc-live-onhost.sh"

printf '== phases 00-04 then reboot ==\n'
ssh_base "env VCL_SERVER=${SERVER} bash /root/rc-live-onhost.sh all-with-reboot-marker"
printf '== waiting for reboot ==\n'
sleep 15
for i in $(seq 1 60); do
  if ssh_base "true" 2>/dev/null; then
    echo "SSH back after ${i} attempts"
    break
  fi
  sleep 5
  if [[ $i -eq 60 ]]; then
    echo "ERROR: host did not come back" >&2
    exit 1
  fi
done
# give systemd time
sleep 20

printf '== post-reboot phases 05b-07 ==\n'
ssh_base "env VCL_SERVER=${SERVER} bash /root/rc-live-onhost.sh post-reboot"

printf '== pull evidence ==\n'
mkdir -p "$EVID_LOCAL"
scp_from "${REMOTE_EVID}/SUMMARY.md" "${EVID_LOCAL}/SUMMARY.md" || true
scp_from "${REMOTE_EVID}" "${EVID_LOCAL}/remote-copy" || true

printf '== done ==\n'
[[ -f "${EVID_LOCAL}/SUMMARY.md" ]] && cat "${EVID_LOCAL}/SUMMARY.md"
