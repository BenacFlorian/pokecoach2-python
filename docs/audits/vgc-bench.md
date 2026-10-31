# Audit VGC-Bench (plan 04 tâche 1)

Commit épinglé : *à documenter lors du branchement subprocess* ([vgc-bench](https://github.com/cameronangliss/vgc-bench)).

## Interfaces PokeCoach (contrats maison)

| Mode | Méthode adaptateur | Statut |
| --- | --- | --- |
| Preview (phase A) | `EngineAdapter.preview` | Stub implémenté ; `vgc_bench` délègue au stub |
| Tour 1 (phase B) | `first_turn` | Stub implémenté avec moves synthétiques ; `vgc_bench` délègue au stub, moteur réel non branché |
| Combat complet (C/D) | `full_battle` | Stub implémenté avec un seul tour synthétique et une issue artificielle ; `vgc_bench` délègue au stub, moteur réel non branché |

Le raccordement réel et sa recette sont décrits dans le [plan 04b](../plans/2026-10-31-04b-moteur-reel-vgc-bench.md). Ce tableau décrit le code observé avant ce raccordement ; il ne constitue pas un audit d’exécution du checkpoint amont.

## Vérification locale

```bash
cd pokecoach2-python && devbox run engine-check
```

Contrôle actuel : capacités JSON et comparaison de deux previews sur snapshots vides. Il valide le câblage stub uniquement, même si le mode configuré est `vgc_bench`. Il ne démontre ni chargement BC, ni tour 1 réel, ni combat complet, ni reproductibilité du simulateur Showdown.

## Prochaines étapes moteur

1. Isoler Python/Torch VGC-Bench dans un venv uv dédié si incompatible 3.13.
2. Protocole JSON versionné (stdin/stdout) appelé depuis `VgcBenchEngineAdapter`.
3. Trace expurgée de référence dans `tests/fixtures/engine-preview-reference.json`.
