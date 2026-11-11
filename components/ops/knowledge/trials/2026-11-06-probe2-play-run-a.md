---
id: 2026-11-06-probe2-play-run-a
kind: play
build: 8a32df2
game_version: 201602
mechanisms: [zone-capture-command-units, count-race-forced-owner, zone-lookup-by-point, kill-counts-by-type, vanished-removal, dialog-reask-loop, fast-move-and-attack-keeps-roads, mission-ends-only-by-script, objective-waits-until-resolved, seteffect-never-finishes, script-container-semantics, content-identity-unique, objective-counters, add-unit-to-deck, difficulty-branches, gdscript-is-what-loads, operation-menu-registration, custom-operation-from-stock-parts, gameplay-mod-relaunch, load-time-validation-rules, mod-version-and-config-lines, ndfbin-round-trip, localisation-tokens-packed, script-and-battle-scale]
outcome: pass
result: The full mission's zone rules became count races with forced owners; the unread beats stay open
---
The second probe Operation (spike 2) on Geisa: independent beats, each in its own branch, played once on Medium to
15:00 with no crash and no stall. Worked: a scripted enemy command tank captured a zone and a player command tank
won it back; a capturer killed mid-capture left its zone neutral for good; a two-zone count race and its forced
owner; kill counts by type and alive counts by group; units removed with Vanished; a dialog asked again in a loop;
a 20-vehicle column kept to the road; the victory screen.

Not read: whether the Operation has a difficulty picker and which value reached the script; the same-tick ending
race (its runs were not played); the two test cards; capture fill time; Vanished in the loss counts; the objective
panel's overflow; overlapping hints.
