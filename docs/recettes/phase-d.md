# Recette — phase D (affinage ciblé)

## Prérequis

- Phases **A–C** déjà publiées sur le run (ou cible **D** au lancement).
- Migration **V1.0.12** appliquée si la publication C a échoué sur `leadPick` immuable.
- Worker avec handler **D** et `POKECOACH_ENGINE=stub`.

## Smoke

```bash
devbox run start
devbox run worker
```

Continuer le run smoke jusqu’à **D** (2 combats ciblés).

Attendu :

- `completedPhases` : `A`, `B`, `C`, `D`.
- Onglet **Lead & pick** : bloc **Affinage (phase D)** avec issues, limitations et premiers tours D.
- `opponentLeads` et `leadPick` identiques à avant D.
- En base : 2 lignes `matchup_run_battles` avec `phase='D'`.

## Standard

Continuer jusqu’à **D** : **10 combats** au total pour la configuration imposée (lead adverse le plus fréquent parmi le top C, back le plus fréquent en B).

Conserver le `runId` pour la phase **E** (LLM).
