# Recette — phase C (Lead & pick)

## Prérequis

- Worker et API Python avec `ANALYSIS_DEPLOYED_PHASES` incluant **C**.
- `POKECOACH_ENGINE=stub` (combats complets stub) ou moteur réel avec `full_battle`.
- Run déjà en pause après **B** ou cible **C** au démarrage.

## Smoke

```bash
devbox run start
devbox run worker
```

Depuis l’UI : continuer le run smoke jusqu’à **C**, ou :

```bash
uv run python scripts/analysis-smoke.py --run-id UUID --target C
```

Attendu :

- `completedPhases` contient `A`, `B`, `C`.
- Onglet **Lead & pick** : quatre, lead, justifications (limitations), premiers tours par lead étudié.
- **3 combats terminés par lead** du top 3 (profil smoke).
- En base : lignes `core.matchup_run_battles` avec `phase='C'` (non exposées GraphQL).

## Standard

Relancer un run standard jusqu’à **C** : **50 combats complets par lead** retenu (top 3 par défaut). Vérifier que le nombre de lignes C en base = `50 × nombre de leads étudiés` et que le tableau « Compositions comparées » recoupe les effectifs affichés.

Conserver le `runId` pour la phase **D**.
