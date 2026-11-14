# Unfrozen candidate 0.5.5 (21aba22)

Not frozen; not published; not a release announcement.

- Source commit: `21aba22157994d70bfcf2c17c1ec4ff38b9e9880`
- Source manifest: `../FINAL_SOURCE_MANIFEST.txt`, SHA-256
  `252cfc6c519356251a17871e48da14287ee427566e6ab22756ffa0b06a825161`
  (393 supported-source paths; review-only docs outside scope)
- Build epoch: `1794384920`
- Node: `7b7a1b60d5dfa228291b3b99ac2dd87afd97c22d22d86f9d7732c86157b63c4b`
- Controller: `784ca4d0ef6e8181d683ab6f8ee998e216038cbf789c257c7dd50936394c7892`

Reproduce in two independent clean directories:

```bash
git archive 21aba22157994d70bfcf2c17c1ec4ff38b9e9880 | tar -x -C /tmp/candidate
cd /tmp/candidate
export SOURCE_DATE_EPOCH=1794384920
bash scripts/gen-release-lock.sh
bash scripts/build-release.sh
bash scripts/build-controller.sh
sha256sum dist/vincula-node-0.5.5.tar.gz dist/vincula-controller-0.5.5.zip
```

Both independent builds produced the hashes above. `release.lock` and
`controller.lock` verify; extracted Node/Controller `--help` smoke rc=0.
`BUILD_INPUTS.json`, `build-A.log`, `build-B.log` (in
`../review-evidence/build/`), lock verification and `SHA256SUMS` are included.
