# Recettes analyses progressives

## Terminaux

1. Stack conception (PostgreSQL + PostGraphile) — voir `pokecoach2-conception`.
2. API : `cd pokecoach2-python && devbox run start` (port **8042**).
3. Worker : `cd pokecoach2-python && devbox run worker`.
4. Angular : `cd pokecoach2-angular/pokecoach-angular && npm start` (port **4200**).

## Smoke phase A

```bash
cd pokecoach2-python
uv run python scripts/analysis-smoke.py --matchup-id <UUID> --target A --profile smoke
```

Ouvrir l’URL affichée, vérifier **20** observations dans « Opponent Leads », recharger la page.

## Suite

- [Phase A](phase-a.md)
- Benchmarks : dossier `benchmarks/` (manifeste manuel via `scripts/freeze-benchmark.py`).
