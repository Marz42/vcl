#!/usr/bin/env python3
"""Deterministic ssh-add stand-in for credential tests.

VCL_FAKE_AGENT_MODE=unavailable -> agent connection error
VCL_FAKE_AGENT_MODE=empty       -> no identities
VCL_FAKE_AGENT_KEYS=FILE        -> print the public key lines in FILE
VCL_FAKE_AGENT_COUNT=N          -> print N deterministic ssh-ed25519 keys
No private material is ever emitted.
"""
import base64
import hashlib
import os
import struct
import sys

TYPE = b"ssh-ed25519"


def key_line(index: int) -> str:
    seed = hashlib.sha256(f"vcl-test-agent-key-{index}".encode("ascii")).digest()
    blob = struct.pack(">I", len(TYPE)) + TYPE + struct.pack(">I", len(seed)) + seed
    encoded = base64.b64encode(blob).decode("ascii")
    return f"ssh-ed25519 {encoded} vcl-test-{index}"


def main(argv: list[str]) -> int:
    mode = os.environ.get("VCL_FAKE_AGENT_MODE", "").strip()
    if mode == "unavailable":
        sys.stderr.write(
            "Could not open a connection to your authentication agent.\n"
        )
        return 2
    if mode == "empty":
        sys.stderr.write("The agent has no identities.\n")
        return 1
    if argv != ["-L"]:
        sys.stderr.write("fake-ssh-add: only -L is supported\n")
        return 2
    path = os.environ.get("VCL_FAKE_AGENT_KEYS", "").strip()
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        sys.stdout.write(line.strip() + "\n")
        except OSError as exc:
            sys.stderr.write(f"fake-ssh-add: cannot read {path}: {exc}\n")
            return 2
        return 0
    try:
        count = int(os.environ.get("VCL_FAKE_AGENT_COUNT", "3"))
    except ValueError:
        count = 3
    for index in range(max(0, count)):
        sys.stdout.write(key_line(index) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
