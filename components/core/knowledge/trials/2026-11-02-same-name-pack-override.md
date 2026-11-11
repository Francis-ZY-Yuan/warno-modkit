---
id: 2026-11-02-same-name-pack-override
kind: launch
build: ab1807d
game_version: 201602
mechanisms: [mod-version-and-config-lines, operation-menu-registration]
outcome: fail
symptom: The mod was listed as outdated; once active, the stock Operation still showed its stock title and briefing
cause: The mod had no Gen/Version.ndf; and a scenario pack with a stock pack's name in a mod does not replace the stock pack
result: Every build ships Gen/Version.ndf and an empty [Config] (modkit.core.packaging); a custom Operation gets a new scenario id
---
A test mod re-shipped Survivors' Definition pack under its stock name with one visible change in the script and one
in the menu (the control). The Mod Center first listed the mod as outdated; with `Gen/Version.ndf` and an empty
`[Config]` it showed as active with the scenario-type icon, so the game does scan a mod's `Scenarios/` folder. The
control never showed: the stock pack still won. The next test used a new scenario id
([[2026-11-02-new-scenario-id-loads]]).
