---
id: 2026-11-19-twin-strike-212400-workshop-copy
kind: launch
# the Workshop copy of update 1795053656, as Steam downloaded it; its packs and Gen/Version.ndf are byte-identical to main's build at f9df8e5
build: f9df8e5
game_version: 212400
mechanisms: [txn-tag-config-hash, mod-version-and-config-lines]
outcome: pass
result: The copy downloaded from the Workshop loads on 212400. It is the first Workshop-downloaded Twin Strike to be played; until then every play had loaded a local folder with the same ID
---
Twin Strike's re-upload for 212400 (update 1795053656, [[2026-11-18-twin-strike-212400-workshop-launch]]), launched
from the copy Steam downloaded. The local copy was moved aside, the Workshop copy was the only active mod, and the
Operation was started from the Operations menu. It loaded with no error: the copy whose 211352 tags had stopped every
player now loads after the rebuild from 212400's stock.

The copy is what the upload left: `Gen/Version.ndf` and `ModGenVersion` both 212400, and a `Config.ini` with no
`[Config]` section and no `Description` or `CosmeticOnly` line. The tag-sources gate passed the same packs before the
upload ([[txn-tag-config-hash]]).
