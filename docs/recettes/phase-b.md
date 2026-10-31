# Recette phase B

1. Stack locale : Postgres migré, API Python `:8042`, worker (`devbox run worker`), Angular.
2. Sur un matchup avec run **en pause après A** (smoke) : **Continuer** avec cible B, ou :
   ```bash
   uv run python scripts/analysis-smoke.py --run-id <UUID> --target B
   ```
3. Vérifier **même runId**, champs A inchangés (`id`, `slots`, `count`, `sampleSize` section A).
4. Chaque lead affiche **3** observations tour 1 (smoke) : actions conjointes, paires de back, marges par slot.
5. Run **paused** après B si la cible dépasse B ; refresh navigateur conserve le checkpoint.
6. Profil **standard** : **50** observations par lead observé en A.

Scripts : `uv run pytest tests/unit/test_phase_b.py tests/integration/test_phase_b_run.py -q`
