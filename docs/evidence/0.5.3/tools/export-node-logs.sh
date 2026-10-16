#!/usr/bin/env bash
# Export one Node's journal (plus the facts needed to interpret it) to this
# machine, without leaving anything behind on the Node.
#
#   bash export-node-logs.sh NODE [options]
#
#   --since WHEN        journalctl --since (e.g. "2026-10-15 00:00:00", "-24h")
#   --until WHEN        journalctl --until
#   --boot N            journalctl -b N (0 = current boot, -1 = previous)
#   --units "a b"       default "sing-box.service vincula-accountd.service"
#   --class admin|observe   which credential class to use (default admin)
#   --out DIR           default ./node-logs-<node>-<UTC>
#   --no-lossless       skip the `-o export` (lossless) copy
#   --dry-run           print the exact ssh command and remote script, run nothing
#
# Env: VCL_FLEET_HOME (workspace), VCL_FLEET_LOCAL_STATE, XDG_CONFIG_HOME,
#      VCL_FLEET_BIN (default: <repo>/bin/vcl-fleet), SSH_BIN, SCP_BIN.
#
# Never writes on the Node: the journal is streamed over ssh and gzipped here.
set -uo pipefail

NODE=""
SINCE=""
UNTIL=""
BOOT=""
UNITS="sing-box.service vincula-accountd.service"
CLASS="admin"
OUT=""
LOSSLESS=1
DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --since) SINCE=${2:?}; shift 2 ;;
    --until) UNTIL=${2:?}; shift 2 ;;
    --boot) BOOT=${2:?}; shift 2 ;;
    --units) UNITS=${2:?}; shift 2 ;;
    --class) CLASS=${2:?}; shift 2 ;;
    --out) OUT=${2:?}; shift 2 ;;
    --no-lossless) LOSSLESS=0; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) if [[ -z "$NODE" ]]; then NODE=$1; shift; else echo "unexpected arg: $1" >&2; exit 2; fi ;;
  esac
done
[[ -n "$NODE" ]] || { echo "usage: $0 NODE [--since ...] [--units ...] [--dry-run]" >&2; exit 2; }
[[ "$CLASS" == "admin" || "$CLASS" == "observe" ]] || { echo "--class must be admin or observe" >&2; exit 2; }

REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
FLEET=${VCL_FLEET_BIN:-$REPO/bin/vcl-fleet}
SSH=${SSH_BIN:-ssh}
SCP=${SCP_BIN:-scp}
[[ -f "$FLEET" ]] || { echo "missing vcl-fleet: $FLEET" >&2; exit 2; }

show=$("$FLEET" node show "$NODE" 2>&1) || { echo "node show failed:" >&2; echo "$show" >&2; exit 2; }
field() { printf '%s\n' "$show" | sed -n "s/^$1=//p" | head -1; }
HOST=$(field ssh_host); USER=$(field ssh_user); PORT=$(field ssh_port)
ADMIN_REF=$(field admin_credential_ref); OBSERVE_REF=$(field observe_credential_ref)
LEGACY=$(field identity_file); OBSERVE_USER=$(field observe_ssh_user)
[[ -n "$HOST" ]] || { echo "node $NODE has no ssh_host" >&2; exit 2; }
PORT=${PORT:-22}
USER=${USER:-root}
[[ "$USER" != "-" ]] || USER=root
[[ "$OBSERVE_USER" == "-" ]] && OBSERVE_USER=""

if [[ "$CLASS" == "observe" ]]; then
  REF=$OBSERVE_REF; [[ "$REF" == "-" ]] && REF=""
  [[ -n "$OBSERVE_USER" ]] && USER=$OBSERVE_USER
  if [[ -z "$REF" ]]; then
    if [[ -z "$ADMIN_REF" || "$ADMIN_REF" == "-" ]]; then
      KEY=$LEGACY; [[ "$KEY" == "-" ]] && KEY=""
    else
      echo "STOP: node $NODE has an admin ref but no observe ref (observe credential not configured)" >&2
      exit 2
    fi
  fi
else
  REF=$ADMIN_REF; [[ "$REF" == "-" ]] && REF=""
  [[ -z "$REF" ]] && { KEY=$LEGACY; [[ "$KEY" == "-" ]] && KEY=""; }
fi
if [[ -n "${REF:-}" ]]; then
  line=$("$FLEET" access list 2>/dev/null | awk -F'\t' -v r="$REF" '$1==r{print; exit}')
  if [[ -z "$line" ]]; then echo "STOP: ref $REF is not bound on this machine (run access bind/verify)" >&2; exit 2; fi
  rtype=$(printf '%s' "$line" | cut -f2); rpath=$(printf '%s' "$line" | cut -f3)
  if [[ "$rtype" == "identity_file" ]]; then KEY=$rpath; else KEY=""; fi   # openssh-default -> no -i
fi
KEY=${KEY:-}

WS=${VCL_FLEET_HOME:-}
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
if [[ -n "$WS" && -f "$WS/workspace.json" ]]; then
  SSH_OPTS=(-o "UserKnownHostsFile=$WS/trust/known_hosts" -o StrictHostKeyChecking=yes "${SSH_OPTS[@]}")
fi
[[ -n "$KEY" ]] && SSH_OPTS+=(-i "$KEY" -o IdentitiesOnly=yes)
SSH_CMD=("$SSH" -p "$PORT" "${SSH_OPTS[@]}" "$USER@$HOST" --)

journal_args() {
  local fmt=$1
  local -a a=(-o "$fmt" --no-pager)
  for u in $UNITS; do a+=(-u "$u"); done
  [[ -n "$SINCE" ]] && a+=(--since "$SINCE")
  [[ -n "$UNTIL" ]] && a+=(--until "$UNTIL")
  [[ -n "$BOOT" ]] && a+=(-b "$BOOT")
  printf '%s ' "${a[@]}"
}

META_SCRIPT=$(cat <<'REMOTE'
set -u
echo "== identity =="
hostname; date -u +'%Y-%m-%dT%H:%M:%SZ'; uname -a
echo; echo "== versions =="
cat /etc/vincula/VERSION 2>/dev/null || echo "(no /etc/vincula/VERSION)"
/usr/local/bin/sing-box version 2>/dev/null || sing-box version 2>/dev/null || echo "(sing-box version unavailable)"
echo; echo "== sing-box log config (proves stdout/journald, no output file) =="
python3 -c 'import json;print(json.load(open("/etc/sing-box/config.json"))["log"])' 2>&1
echo; echo "== unit properties =="
for u in sing-box.service vincula-accountd.service; do
  echo "-- $u"; systemctl show "$u" -p FragmentPath -p StandardOutput -p StandardError -p User -p Group -p ActiveState -p NRestarts 2>&1
done
echo; echo "== unit files =="
for u in sing-box.service vincula-accountd.service; do echo "-- $u"; systemctl cat "$u" 2>&1; done
echo; echo "== journald storage =="
journalctl --disk-usage 2>&1
grep -E '^[[:space:]]*(Storage|SystemMaxUse|RuntimeMaxUse|MaxRetentionSec|MaxFileSec)=' /etc/systemd/journald.conf 2>/dev/null || echo "(journald.conf: no explicit limits)"
ls -d /var/log/journal /run/log/journal 2>/dev/null || echo "(no journal directory found)"
echo; echo "== boots =="
journalctl --list-boots --no-pager 2>&1 | tail -20
echo; echo "== selected journal size (lines bytes) =="
REMOTE
)
WINDOW_SCRIPT=$(cat <<REMOTE
echo; echo "== selected journal first/last line =="
journalctl $(journal_args short-iso) | sed -n '1p;\$p'
REMOTE
)
SIZE_SCRIPT=$(cat <<REMOTE
journalctl $(journal_args short-iso) | wc -lc
REMOTE
)

if (( DRY )); then
  echo "# ssh:   ${SSH_CMD[*]} bash -s"
  echo "# class: $CLASS  user: $USER  key: ${KEY:-<openssh default>}  ref: ${REF:-<none>}"
  echo "# out:   ${OUT:-./node-logs-$NODE-<UTC>}"
  echo "----- metadata script -----"; printf '%s\n' "$META_SCRIPT" "$SIZE_SCRIPT" "$WINDOW_SCRIPT"
  echo "----- readable stream -----"; echo "journalctl $(journal_args short-iso)"
  (( LOSSLESS )) && { echo "----- lossless stream -----"; echo "journalctl $(journal_args export)"; }
  exit 0
fi

OUT=${OUT:-./node-logs-$NODE-$(date -u +%Y%m%dT%H%M%SZ)}
mkdir -p "$OUT"
STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

FAILED=0
size_of() { local f=$1; if stat -c%s "$f" >/dev/null 2>&1; then stat -c%s "$f"; else wc -c < "$f"; fi; }
echo "== node $NODE ($USER@$HOST:$PORT, class=$CLASS, key=${KEY:-openssh-default}) -> $OUT"
printf '%s\n' "$META_SCRIPT" "$SIZE_SCRIPT" "$WINDOW_SCRIPT" | "${SSH_CMD[@]}" bash -s > "$OUT/METADATA.txt" 2>"$OUT/METADATA.err"
rc=$?
if [[ $rc -eq 0 ]]; then echo "PASS  metadata collected ($(size_of "$OUT/METADATA.txt") bytes)"; else echo "FAIL  metadata rc=$rc (see $OUT/METADATA.err)"; FAILED=1; fi

"${SSH_CMD[@]}" "journalctl $(journal_args short-iso)" 2>"$OUT/readable.err" | gzip -9 > "$OUT/journal-short-iso.txt.gz"
rc=$?
if [[ $rc -eq 0 ]]; then echo "PASS  readable journal ($(size_of "$OUT/journal-short-iso.txt.gz") bytes gz)"; else echo "FAIL  readable journal rc=$rc (see $OUT/readable.err)"; FAILED=1; fi

if (( LOSSLESS )); then
  "${SSH_CMD[@]}" "journalctl $(journal_args export)" 2>"$OUT/lossless.err" | gzip -9 > "$OUT/journal-export.gz"
  rc=$?
  if [[ $rc -eq 0 ]]; then echo "PASS  lossless journal ($(size_of "$OUT/journal-export.gz") bytes gz)"; else echo "FAIL  lossless journal rc=$rc (see $OUT/lossless.err)"; FAILED=1; fi
fi

{
  echo "node=$NODE"
  echo "endpoint=$USER@$HOST:$PORT"
  echo "credential_class=$CLASS"
  echo "credential_ref=${REF:-<none>}"
  echo "identity_file=${KEY:-<openssh default>}"
  echo "units=$UNITS"
  echo "since=${SINCE:-<all retained>}"
  echo "until=${UNTIL:-<now>}"
  echo "boot=${BOOT:-<all retained>}"
  echo "exported_at_utc=$STAMP"
  echo "readable_lines_bytes=$(zcat "$OUT/journal-short-iso.txt.gz" 2>/dev/null | wc -lc | tr -s ' ')"
  for f in METADATA.txt journal-short-iso.txt.gz journal-export.gz; do
    [[ -f "$OUT/$f" ]] && echo "$(sha256sum "$OUT/$f")"
  done
  echo "reimport_hint=journalctl --no-pager -o short-iso < zcat $OUT/journal-short-iso.txt.gz"
} > "$OUT/MANIFEST.txt"
echo "MANIFEST:"; cat "$OUT/MANIFEST.txt"
echo "note: journal content may contain IPs/UUIDs; keep it local and sanitize before committing to docs."
exit $(( FAILED > 0 ? 1 : 0 ))
