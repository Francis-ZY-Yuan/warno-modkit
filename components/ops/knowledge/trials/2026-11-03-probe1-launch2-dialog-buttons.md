---
id: 2026-11-03-probe1-launch2-dialog-buttons
kind: launch
build: 46dccf8
game_version: 201602
mechanisms: [dialog-button-ingame-dictionary, crash-dump-names-the-error, start-camera-before-loading-done]
outcome: fail
symptom: WARNO has stopped working, right after Launch battle
cause: The start dialog's button tokens were the scenario's own; button labels resolve only in INTERFACE_INGAME
result: The buttons use stock CMP_EASY/CMP_HARD, named in the dialog text; a gate checks button tokens against INTERFACE_INGAME in all 8 languages
---
The Operation loaded with the camera fixed in a map corner; the crash came when "Launch battle" opened the start
dialog. The crash dump held a dictionary error naming the token and the in-game list
([[crash-dump-names-the-error]]). The camera was left for later.
