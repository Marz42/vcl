#!/usr/bin/env python3
"""Generate fixed source/test/build/CI inputs for the 0.5.5 candidate.

Derived from the historical 0.5.3 helper. Hash only tracked release inputs;
write canonical LF output on Windows as well as Linux.

Inputs are the tracked files that produce or verify the release:
tests/, lib/, scripts/, schemas/, bin/, .github/ and the named root files.
Bytes are hashed with CRLF normalised to LF so a Windows checkout of the same
commit yields the same digests.

Usage:
  python3 docs/evidence/0.5.5/tools/gen-source-inputs.py <out.json> \
      --base-commit SHA --source-date-epoch EPOCH \
      --artifact dist/... --log tmp/....log [--log ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PREFIXES = ("tests", "lib", "scripts", "schemas", "bin", ".github")
ROOT_FILES = (
    "README-controller.md",
    "release.lock",
    "sing-box.lock",
    "vincula.sh",
    "vincula-bootstrap.sh",
    "vincula.sh.sha256",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_lf(path: Path) -> str:
    return sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def tracked_inputs(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", *PREFIXES, *ROOT_FILES],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    return sorted(p for p in out if (root / p).is_file())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--root", default=".")
    ap.add_argument("--base-commit", required=True)
    ap.add_argument("--source-date-epoch", type=int, required=True)
    ap.add_argument("--artifact", action="append", default=[])
    ap.add_argument("--log", action="append", default=[])
    ap.add_argument("--payload-manifest", default=None)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    version = None
    for line in (root / "vincula.sh").read_text(encoding="utf-8").splitlines():
        if line.startswith("readonly VINCULA_VERSION="):
            version = line.split('"')[1]
            break
    control = None
    for line in (root / "lib" / "vincula-fleet.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("VCL_FLEET_VERSION"):
            control = line.split('"')[1]
            break
    if not version or not control:
        print("could not parse versions", file=sys.stderr)
        return 2

    artifacts: dict[str, str] = {}
    for item in args.artifact:
        p = Path(item)
        artifacts[p.name] = sha256_file(p)
        sidecar = Path(str(p) + ".sha256")
        if sidecar.is_file():
            artifacts[sidecar.name] = sha256_file(sidecar)

    logs = []
    for item in args.log:
        p = Path(item)
        if p.is_file():
            logs.append({"path": str(p).replace("\\", "/"), "sha256": sha256_file(p)})

    doc = {
        "version": version,
        "controller_version": control,
        "branch": subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip(),
        "base_commit": args.base_commit,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source_date_epoch": args.source_date_epoch,
        "status": "FROZEN CANDIDATE / UNRELEASED / PENDING LIVE / PENDING HUMAN",
        "stop_before": "0.6.x implementation",
        "source_files": [
            {"path": p, "sha256_lf": sha256_lf(root / p)}
            for p in tracked_inputs(root)
        ],
        "artifacts": artifacts,
        "logs": logs,
        "generator": "docs/evidence/0.5.5/tools/gen-source-inputs.py",
        "generator_sha256_lf": sha256_lf(Path(__file__)),
    }
    if args.payload_manifest:
        doc["payload_manifest"] = {
            "path": args.payload_manifest,
            "sha256": sha256_file(Path(args.payload_manifest)),
        }
    Path(args.out).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest_sha = sha256_file(Path(args.out))
    print(f"wrote {args.out}")
    print(f"inputs={len(doc['source_files'])}")
    print(f"manifest_sha256={manifest_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
