# Ouvertures conditionnées (plan 10)

## Ordre des phases

`A → C → B → D` (puis `synthesis` réservée). Checkpoints : `[]`, `[A]`, `[A,C]`, `[A,C,B]`, `[A,C,B,D]`.

## Contrat

- **A** : `opponentLeads` (sans tour 1 embarqué).
- **C** : `leadPick` (sans `firstTurns`).
- **B** : `openings` (sélection = celle de C, recommandation = mode de `ourActions`).
- **D** : `refinement` (back adverse depuis `openings.byOpponentLead`).

## Capabilities

`GET /analysis-capabilities` expose `phaseOrder: ["A","C","B","D"]` et `phases` filtrées par le moteur.

## Bascule base locale

1. Arrêter workers et lancements en cours.
2. `psql … -f pokecoach2-conception/scripts/reset-analysis-data.sql`
3. Appliquer Flyway jusqu’à **V1.0.13** (`is_valid_simulation_result_v2` + immutabilité `openings`).
4. Redémarrer API/worker avec `ANALYSIS_DEPLOYED_PHASES=A,C,B,D,synthesis`.

## Tests

```bash
cd pokecoach2-python
uv run pytest tests/unit/test_conditioned_result.py tests/unit/test_conditioned_openings.py \
  tests/unit/test_phase_b.py tests/unit/test_phase_c.py tests/unit/test_phase_d.py -q
```

Smoke jusqu’à C puis B :

```bash
uv run python scripts/analysis-smoke.py --profile smoke --target C
# continuer vers B puis D via l’API ou --target D
```

Exemples JSON : `contracts/examples/openings/*.json`.
