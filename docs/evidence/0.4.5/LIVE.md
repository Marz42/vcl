# 0.4.5 LIVE handbook — Matrix H (Legacy single-user seed)

Operator checklist for **AC-4.5-04 / 05 / 06** and Matrix **H**.
Record outcomes in [`SUMMARY.md`](SUMMARY.md). **Never** paste IPs, VLESS URIs, UUIDs, Reality private keys, or Clash secrets into evidence.

## Preconditions

- Clean VPS that keeps the **same advertised host** (IP or DNS) the old client already uses.
- Working SSH admin access (key-based); system OpenSSH on the workstation.
- Controller tree / zip stamp **0.4.5** with Node payload **0.3.2**.
- Local secret files only (mode `0600`, regular files, no symlinks):
  - legacy VLESS URI file (single line)
  - Reality private key file (single key line)
- Chosen `--legacy-user-tag` **≠** `owner`.
- URI may omit `sid` / use empty `sid=` (empty Reality short ID).
- Listen port is taken from the URI (not assumed 443).
- Remove leftover non-VCL `sing-box` unit/binary/`/etc/sing-box/config.json` before provision (clean-host refuse otherwise).
- Reality SNI may return HTTP 503; preflight/self-test accept 503 when TLS succeeds.

## Steps

1. Save the old client URI and Reality private key to local files (`0600`). Do not commit them.
2. Confirm URI authority matches the intended `--server` / advertised host. Stop any existing proxy so the URI port is free (and remove any pre-existing `sing-box.service` unit / config if present).
3. Run provision with **all three** legacy flags (paths only):

   ```bash
   vcl-fleet node provision NAME \
     --host SSH_TARGET \
     --server ADVERTISED_HOST \
     --host-key SHA256:… \
     --legacy-vless-uri-file ./legacy-user.uri \
     --legacy-reality-private-key-file ./reality-private.key \
     --legacy-user-tag existing-user
   ```

4. Do **not** change the old client profile.
5. Verify old client reaches the public internet successfully.
6. Fetch a **new owner** link (`vcl-fleet user link owner --node NAME`) and verify that client path works.
7. Run `vcl-fleet probe` / `verify` / `sync` (or `sync --full`) successfully.
8. Confirm public listeners are only original SSH + expected VLESS port from the URI (no new management port).
9. Confirm Clash API remains loopback-only on the node.
10. Confirm remote staging and local temp secret copies are cleaned up after success/failure.
11. (Optional) Adopt the same node into a **second** `VCL_FLEET_HOME` via `node adopt` (do not re-provision).

## Fail-close spot checks (optional; no secrets in notes)

- Wrong Reality key vs URI `pbk` → refuse / zero-install.
- Incomplete legacy flags (only one or two of three) → refuse before install.
- `--legacy-user-tag owner` → refuse.
- Evidence notes may record **path + error type only**.

## Operator record (Matrix H — PASS LIVE)

| Field | Value |
| --- | --- |
| Date | 2026-08-26 |
| Code HEAD | 6fe226d |
| VPS OS / arch | Debian amd64 |
| Privilege | root |
| Old client reconnect | PASS |
| New owner link | PASS |
| probe / verify / sync | PASS |
| Second fleet-home adopt | PASS |
| Public listen check | PASS (SSH + URI VLESS port only; no new public management port) |
| Clash loopback | PASS |
| Staging cleanup | PASS |
| Not recorded | IP, URI, UUID, Reality key, Clash secret |
