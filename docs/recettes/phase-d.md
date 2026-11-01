# Recette — phase D (évaluation globale)

> **Remplace** l’affinage ciblé lead/back unique ([plan 08](../plans/2026-10-31-08-phase-d-affinage.md)). Voir [plan 11](../plans/2026-11-01-11-phase-d-affinage-global.md).

## Prérequis

- Phases **A → C → B** déjà publiées sur le run (cible **D** au lancement).
- Contrat `refinement` avec `samplingPolicy: "weighted-ab"` (migration **V1.0.14** côté conception).
- Worker avec handler **D** ; moteur réel recommandé pour prouver preview/back (`POKECOACH_ENGINE=vgc_bench`).

## Nettoyage bascule

Avant de relire des runs anciens :

```bash
psql … -1 -v ON_ERROR_STOP=1 -f pokecoach2-conception/scripts/reset-analysis-data.sql
```

Purger aussi le cache navigateur / commandes d’analyse en cours.

## Smoke

```bash
devbox run start
devbox run worker
```

Continuer le run smoke jusqu’à **D** (**2 combats** au total, scénarios tirés sur A/B).

Attendu :

- `completedPhases` : `A`, `C`, `B`, `D`.
- Onglet **Lead & pick** : bloc **Évaluation globale de notre sélection**, issues W/L/T, taux `wins/sampleSize`, histogramme repliable des scénarios joués.
- `refinement.samplingPolicy` = `weighted-ab`, `scenarioCounts` somme = `sampleSize`.
- `opponentLeads`, `leadPick`, `openings` **octet-identiques** à avant D.
- En base : 2 lignes `matchup_run_battles` avec `phase='D'`, métadonnées `refinementSampling.planIndex` uniques 0 et 1.

## Standard

Même logique avec profil **standard** : budget **D = 2** (total, pas par lead). Ne pas interpréter N=2 comme validation stratégique.

Conserver le `runId` pour la phase **E** (LLM).

## Moteur réel (spot-check)

Sur au moins deux seeds forcées en test moteur : vérifier que le preview impose notre quatre C, le lead C, le lead adverse tiré et le back tiré ; `participants.opponentBackPair` provient du preview observé, pas d’un simple écho du payload.
