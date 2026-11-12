# Unfrozen candidate 0.5.5 (f86dd5e)

Not frozen; not published; not a release announcement.

- Source commit: `f86dd5e46f44411f539c0fb5dab5cc87172251d8`
- Source manifest: `SOURCE_MANIFEST.txt`, SHA-256
  `c98c3a4480d64c6b276b2a3deed3086d8cf566007f87c518cbe3f5e247924c51`
- Build epoch: `1794384920`
- Node: `34a46feeca3975a4a7a93aee355d7c04495ae76fe9c0e6680995dcfba81aa14e`
- Controller: `b4f51881155f6e14a00a63874dbbec7f0ec2eb68ee081f3889ad927520868b41`

Reproduce in two independent clean directories:

```bash
git archive f86dd5e46f44411f539c0fb5dab5cc87172251d8 | tar -x -C /tmp/candidate
cd /tmp/candidate
export SOURCE_DATE_EPOCH=1794384920
bash scripts/gen-release-lock.sh
bash scripts/build-release.sh
bash scripts/build-controller.sh
sha256sum dist/vincula-node-0.5.5.tar.gz dist/vincula-controller-0.5.5.zip
```

Both independent builds produced the hashes above. `release.lock` and
`controller.lock` verify; extracted Node/Controller `--help` smoke rc=0.
`BUILD_INPUTS.json`, `build-A.log`, `build-B.log`, lock verification and
`SHA256SUMS` are in this directory.
