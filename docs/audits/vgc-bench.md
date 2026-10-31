# Audit VGC-Bench (plan 04 tâche 1)

Commit épinglé : *à documenter lors du branchement subprocess* ([vgc-bench](https://github.com/cameronangliss/vgc-bench)).

## Interfaces PokeCoach (contrats maison)

| Mode | Méthode adaptateur | Statut |
| --- | --- | --- |
| Preview (phase A) | `EngineAdapter.preview` | Implémenté via `POKECOACH_ENGINE=stub` ; `vgc_bench` délègue au stub en attendant le worker JSON |
| Tour 1 (phase B) | `first_turn` | Non branché |
| Combat complet (C/D) | `full_battle` | Non branché |

## Vérification locale

```bash
cd pokecoach2-python && devbox run engine-check
```

Attendu : capacités JSON, preview reproductible à seed identique, arrêt via `close()`.

## Prochaines étapes moteur

1. Isoler Python/Torch VGC-Bench dans un venv uv dédié si incompatible 3.13.
2. Protocole JSON versionné (stdin/stdout) appelé depuis `VgcBenchEngineAdapter`.
3. Trace expurgée de référence dans `tests/fixtures/engine-preview-reference.json`.
