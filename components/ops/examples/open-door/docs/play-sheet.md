# Operation Open Door: play sheet

One Medium run of the playable core, step by step, with what to look at. The mission shows as **Operation Open Door**
in the Operations menu (mod folder `OpenDoor`). The design is in `design.md`; the storyline map in
`storyline-map.html`.

**Not in this build:** decoys, forest probes and the screen's rings, artillery and air strikes, Apaches, the airborne
landing, the Soviet relief force, the camera cut and the intro film. The camera may start in a corner.

## Install

1. Build it: `python build.py --content op` (the README).
2. Install the built `OpenDoor` folder into your `Saved Games\EugenSystems\WARNO\mod\` folder and switch it on in the
   Mod Center, or make a one-click installer with `python -m modkit.core.install <out>/OpenDoor --title "Operation
   Open Door"` (the `warno-ship` skill).
3. Switch every Gameplay mod off first: an Operation relaunches without mods while one is active, and Open Door
   disappears with them [[gameplay-mod-relaunch]].
4. Open Door installs beside the probes: it has its own scenario, mod folder, GUID and menu texts.

## One run, Medium, playing it straight

Questions 1–4 are what this build is for. If you only notice a few things, notice these.

**Deployment**

1. **Soviet cards.** A hint says your deck holds captured Soviet equipment: two T-80U tanks, two Ka-50 helicopters and
   two TOS-1 rocket launchers.
   - Can you find all three? Where are they in Groups mode?
   - The production menu should have its switch between Groups and the factory tabs. Are they in the Tanks, Helis and
     Art tabs?
   - Are the US rearguard cards there too (M1 Abrams ×6, Rifles in M113A3)? They're added the same way.
   - Buy one T-80U now, then try to buy a Ka-50 after Launch. Does each arrive?
2. The same hint names the deploy areas: the three east towns, SHOULDER, or the ANVIL in the west.

**Phase 1 (from H+0 to the fall of PL BLUE)**

3. **H+0:30: the captured T-80U.**
   - A T-80U in your colours appears on the road west of Village E, with a hint.
   - Is it yours, can you order it, and does it look like a Soviet tank?
4. **Where bought units arrive.** Each time, buy one cheap unit and send it to the spot named.
   1. Before any town falls: send it to Village E. Does it arrive just west of the town, or at the west edge?
   2. After a town falls (it turns red, and a hint says reinforcements no longer arrive there): send one to it. Where
      does it arrive now?
   3. After the "PL GREEN is over" hint (both necks turn red): send one to NECK MID. Does it come in at the ANVIL or
      the west edge?
   4. After you seal a neck (it turns blue again): send one to it. Does it arrive at that neck again?
   5. Do you see reinforcement arrows on the map? If so, where?
5. The first echelon attacks the three towns at H+1. B1 ("MAKE THEM PAY") should count your kills up. Does it jump
   suddenly, or never move?
6. P1 shows a countdown to H+12. Does it tick down every minute?

**Phase 2 (after "the door is open")**

7. Six Soviet waves come down the passage (MID) and the defile (BOTTOM), a minute apart. Do they keep to the roads and
   reach the sack west of the necks, or do any get stuck?
8. P4 counts Soviet vehicles in the sack. When it's full, the spring dialog asks FIRE AT WILL (spring now) or HOLD
   FIRE (asked again in 2 minutes).
   - Corps springs the trap by itself at H+30, or as soon as any Soviet unit reaches an ANVIL zone (Town SW included).
   - Which came first, the FIRE AT WILL dialog or "CORPS SPRINGS THE TRAP"? Roughly when?

**Phases 3 and 4 (the spring)**

9. **The spring.**
   - The codeword dialog appears.
   - An M1A1HA company appears at RESERVE N (north) and Leopards at HIDE S (south).
   - New cards appear: M1A1HA, Leopard 2A4, OH-58D. The A-10s become usable.
10. Seal both necks (your units in it, no Soviet unit, for 30 s).
    - P6 then counts the pocket down to a surrender number.
    - At that number, or 15 minutes after the seal, the Soviets in the pocket vanish (they surrender).
    - THE CATCH row, a grade dialog, then the end screen.
    - Does the catch number look about right for what you killed, plus what was left in the pocket?

**Anytime**

11. Defeats: Soviets holding an ANVIL zone for 30 s, 6 Soviet vehicles at the rear exit (the west edge), or your whole
    force lost.
12. The objective panel: are all rows readable, or does it overflow? Do two hints ever cover each other? Does a
    difficulty hint show at H+0:15?

## Report

Answer 1, 3, 4, 7, 9 and 10 in a line each, plus anything that broke, crashed or looked wrong. Record what you saw as a
trial in the ops knowledge base (the `warno-record-finding` skill), citing the mechanisms it confirms or contradicts.
