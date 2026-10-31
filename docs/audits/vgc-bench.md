# Audit VGC-Bench (plan 04 tâche 1 / plan 04b)

Commit épinglé : `d79f9532947ac114dce1dda2456a590afcd375b2` ([vgc-bench](https://github.com/cameronangliss/vgc-bench/commit/d79f9532947ac114dce1dda2456a590afcd375b2)).

Manifeste PokeCoach : `engine-runtime/manifest.json`.

## Interfaces PokeCoach (contrats maison)

| Mode | Méthode adaptateur | Statut |
| --- | --- | --- |
| Preview (phase A) | `EngineAdapter.preview` | Stub local ; `vgc_bench` → subprocess JSONL (`pokecoach_vgc_bridge`) |
| Tour 1 (phase B) | `first_turn` | Idem ; moves depuis sets via bridge (fixture CI ou BC réel) |
| Combat complet (C/D) | `full_battle` | Idem ; exige `terminalEvidence` en meta |

`VgcBenchEngineAdapter` **ne délègue plus** au stub. Checkpoint ou bridge fixture requis.

## Vérification locale

```bash
cd pokecoach2-python && devbox run engine-setup
devbox run engine-check -- --our-team … --opponent-team … --modes preview,first_turn,full_battle
```

Recette détaillée : [moteur-reel.md](../recettes/moteur-reel.md).

## Prochaines étapes moteur

1. Installer VGC-Bench épinglé dans `engine-runtime` (Torch, poke-env fork, sous-module Showdown).
2. Implémenter `vgc_real.RealRuntime` (policy_player + rejet preview conditionnel phase B).
3. Rejouer recettes smoke/standard A→D avec checkpoint BC compatible teampreview appris.
