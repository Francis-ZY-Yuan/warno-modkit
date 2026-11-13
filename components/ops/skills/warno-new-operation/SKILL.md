---
name: warno-new-operation
description: Use when building a new WARNO Operation (a scripted scenario mod) with modkit.ops, or adding beats, zones, deck cards or strings to one.
---

# New Operation

## Overview

An Operation here is a clone of a stock challenge, re-keyed to its own identity and moved onto a stock map, with a
generated LevelDesign, zone files, GDScript and English and Chinese dictionaries
([[custom-operation-from-stock-parts]]). The shared driver `modkit.ops.build` builds it: every gate but the
read-back runs before anything is written, and the read-back checks the written packs. It ships scenario packs only,
with stock units ([[gameplay-mod-relaunch]]).

Two worked examples sit in `${CLAUDE_PLUGIN_ROOT}/examples/` (this plugin's folder, two levels above this skill's
base directory; `components/ops/examples/` in a clone):

- `probes/`: four small ops, one module each. `probes/empty.py` is the smallest op the driver builds (one tank
  holds a point for ten minutes). Start from it.
- `open-door/`: a full mission (deployment phase, tiered arrivals, waves, zone races, endings) with its design,
  play sheet and storyline map. Copy its patterns as your mission grows.

`python` is your venv's interpreter (see `warno-setup`).

## Steps

1. **Prove the setup.** `python "${CLAUDE_PLUGIN_ROOT}/examples/probes/build.py" --content empty --out
   build/probes/empty` prints a line per gate and exits 0. A `FAILED:` line naming `warno-setup` means the
   extraction or the game folder is not configured.
2. **Copy the probes example into your project** as your own package: `build.py`, plus a folder holding
   `__init__.py`, `profile.py`, `geisa.py` and `empty.py` (renamed for your op). Rename the `probes` imports, and cut
   `CONTENTS` in the copied `__init__.py` down to your op's one content: it still imports `spike` and `spike2`, which
   you did not copy. The build folder needs no edit: `modkit.core.paths.build_root()` gives it (`build/` beside your
   `modkit.local.toml`, or the toml's `build_dir`, or `MODKIT_BUILD`; see `warno-setup`). `--out` defaults to it,
   and a rebuild deletes an earlier output only inside it.
3. **Give it its own identity** ([[content-identity-unique]]): a new scenario id `challenge_<YourOp>` (a stock name
   is never overridden: [[operation-menu-registration]]), a mod folder, a GUID namespace, the seven menu tokens
   and four camp-name tokens renamed to a prefix no stock token uses ([[localisation-tokens-packed]]), and its menu
   order (`MENU_ORDER`, the `OrderToChainMission` the profile writes) set to
   `modkit.ops.leveldesign.derived_menu_order(SCENARIO, GUID_NAMESPACE)`, as Twin Strike's profile does: a hash of
   the scenario GUID, so no Workshop mod is likely to share it. Never a hand pick: the copied probes' 1001 is their
   frozen baselines' ([[derive-cross-mod-ids-from-a-hash]]). Keep every
   other profile value as the example has it until you know why it should change:
   [references/op-anatomy.md](references/op-anatomy.md) says what each one does.
4. **Place the items.** Points are minimap pixels on Geisa (`modkit.ops.maps.GEISA`, `GEISA_POINTS`).
   `modkit.ops.shapes.Minimap` turns them into LevelDesign items, zones and detector rings. Check every point on the
   review picture each build writes (`od_overlay.png`). Scripts find items by tag ([[leveldesign-guid-binding]]) and
   zones by a tag's point ([[zone-lookup-by-point]]).
5. **If the player buys units, add a deployment phase** with all six parts ([[deployment-phase-recipe]]):
   `modkit.ops.script.deploy_phase` with `hud_restore(deploy=True)`, a player deployment zone, and player arrivals
   whose Ends lie in a player zone ([[arrival-end-in-zone]]). Open Door's `profile.deploy_phase` and `op.items` show
   all of it.
6. **Write the mission as beats.** Grow from `hold_script` into the beat frame (`modkit.ops.mission.script_frame`,
   as Open Door's `op.script` calls it): a `Ctx`, a list of `shapes.Beat`, each timed beat in its own branch.
   [references/script-recipes.md](references/script-recipes.md) maps each thing a mission does to the block that
   builds it and the record that proves it, and says how to search stock for the rest. Anything no example uses goes through `warno-stock-precedent` first.
7. **Write the strings** for exactly the profile's three dictionaries, each token as `{"US": ..., "SC": ...}`, one
   key per language (a language left out shows the English; `(English, Chinese)` is shorthand). Each language uses
   only characters its stock text uses ([[chinese-text-stock-glyphs]]), and dialog text carries no live numbers
   ([[dialog-text-takes-no-variables]]). Menu titles stay within 30 UTF-16 units: a toolkit convention, not a game
   limit. Gate 1 holds the tokens in `Content.menu_tokens` to it, so list only the titles there. Open Door and the
   probes list all seven menu tokens; Twin Strike lists its two titles, and its briefing, forces line, background and
   outcome texts take stock's form and lengths (the briefing past 1,000 units; `twinstrike/strings.py`). Translate
   with `warno-localization`.
8. **Build:** `python build.py --content <name>`. Read the gate lines. A `FAILED:` line is the game's rule, so fix
   the content, never the gate (`warno-gates`). Then pin each rule the mission relies on in a test, as
   `${CLAUDE_PLUGIN_ROOT}/tests/test_probes.py` does; `modkit.ops.testing` reads a built script back.
9. **Play it** with every Gameplay mod switched off (`warno-probe-and-playtest`). A failure goes to
   `warno-launch-triage`, and every outcome to `warno-record-finding`.
10. **Publish** (`warno-ship`). The upload writes the new Workshop item's ID into the installed `Config.ini` only, and
    every build writes `ID = 0`. Right after the first upload, put that ID into the profile's `mod_id` (Twin Strike
    names it `WORKSHOP_ID`) and commit: a rebuild then keeps it, and the next upload updates the same item instead of
    creating a second one. The share installer also keeps an installed non-zero ID over a build's 0.

## Red flags

- "The class has this action, so the script can use it." Search stock for it, in the same position.
- "Then the next step, right after the SetEffect (or the dialog, or the objective)."
- "Reuse the probes' scenario id or namespace; it's only a test." Two mods sharing one replace each other.
- "Add a reviewed-pending entry and ship." It is for a failure under review, never a way round a gate.

## Common mistakes

| Mistake | What it cost | Fix |
| --- | --- | --- |
| A node after a SetEffect or LockDeckUnit in a Sequential | Every later beat stalled ([[seteffect-never-finishes]]) | Run it beside the rest of the beat (`shapes.reveal`, `shapes.lock_card`) |
| Player arrival Ends outside every player zone | Land units bought after the launch never arrived | End them in the player deployment zone |
| A dialog button labelled with the scenario's own token | "WARNO has stopped working" ([[dialog-button-ingame-dictionary]]) | Stock in-game interface tokens only |
| An objective with no position | Its label pinned the map corner ([[objective-label-needs-position]]) | Pin it on a place's tag |
| MoveAndAttack for a road march | Columns drove through the woods ([[fast-move-and-attack-keeps-roads]]) | FastMoveAndAttack |
| Scripted infantry boarding a helicopter | Failed twice ([[helicopter-boarding]]) | Create or reveal the squad at the landing zone |
| Waiting for the battle to end itself | Only the script ends it ([[mission-ends-only-by-script]]) | One end funnel, every ending through it |
| A camera snap before LoadingDone in an Operation that opens in the deployment phase | The camera sat on the ground ([[start-camera-before-loading-done]]) | The opening move and the snap to its last key, after LoadingDone |

The opening camera starts at the engine's default, in a map corner or on the ground, unless the script sets one
([[start-camera-before-loading-done]]). Open Door and the probes don't, and their play sheets say so. Twin Strike does,
not yet played: `modkit.ops.maps.OpeningCamera` ships a move and its end as the camera paths file, held to the camera
gate, and its two `bricks.g_camera` cutscenes run right after LoadingDone (`mission.script_frame`'s `opening`).

## References

- [references/op-anatomy.md](references/op-anatomy.md): what a build ships, the profile and content fields, the
  gates in order, the extension points, and what moving to another map takes.
- [references/script-recipes.md](references/script-recipes.md): mission recipes by block and record, and how to
  search stock Operations.
- `${CLAUDE_PLUGIN_ROOT}/examples/open-door/docs/design.md`: a full mission design, section by section.
