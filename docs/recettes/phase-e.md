# Recette Phase E — synthèse gameplan LLM

## Checklist recette

1. Auditer un run D : `turnCount == len(turns)`, `terminalState` présent, pas de stub/fixture.
2. Continuer le **même** run vers `synthesis` (UI ou smoke CLI).
3. Vérifier `execution_metadata.synthesis.sources` : stats sur N, manifeste 15/15/20, logs uniques.
4. Contrôler le gameplan : `strengths`, `threats`, win condition, IDs cités.
5. Archiver runId, empreintes, durées ; tokens/coût seulement si mesurés par DeepInfra.


## Prérequis

- Run D **terminé** avec traces complètes (tâche 1 moteur) et `DEEPINFRA_API_KEY` dans le `.env` Python.
- Worker et API Python démarrés ; phases déployées incluant `synthesis`.

## Continuation D → E (sans relancer le moteur)

1. Ouvrir un matchup avec un run en pause après D (`completedPhases` contient `D`, pas `synthesis`).
2. Cliquer **Générer le gameplan** (continuation `targetPhase: synthesis`, même `runId`).
3. Vérifier le polling pendant E, A–D toujours visibles, puis gameplan + win condition après succès.

## Smoke CLI

```bash
cd pokecoach2-python
uv run python scripts/analysis-smoke.py --run-id <UUID> --target synthesis
```

## Contrôles

- `execution_metadata.synthesis.sources` : stats sur N, manifeste 15/15/20, logs normalisés.
- Aucun nouvel appel `preview` / `full_battle` pendant E.
- Rapport final : `strengths` + menaces `{side, slot}`, pas de `preserve` / `eliminate` / `adaptations`.
