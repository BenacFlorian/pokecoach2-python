# Recette phase A

1. Lancer stack, API, worker et Angular (voir [analyses-progressives.md](analyses-progressives.md)).
2. Matchup quelconque : le serveur force `regulation = M-B` au lancement.
3. `uv run python scripts/analysis-smoke.py --matchup-id <UUID> --target A --profile smoke`
4. Vérifier 20 leads agrégés, `turn1` absent, statut « En pause après A ».
5. Run standard : `--profile standard` → 1000 observations (durée à consigner ici).
