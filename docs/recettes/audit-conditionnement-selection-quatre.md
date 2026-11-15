# Audit du conditionnement bring-four

## Prérequis

- Profil modèle réel (`VGC_MODEL_PROFILE`), OTS aligné entraînement, preview stochastique (plan seeds/OTS).
- Serveur Showdown local, dépôts Python et Angular aux commits attendus.
- Snapshot JSON de notre équipe et **au moins trois** équipes adverses distinctes.

## Commande

```bash
cd pokecoach2-python
uv run python scripts/audit-teampreview-conditioning.py \
  --our-snapshot /chemin/our-team.json \
  --opponent balance=/chemin/opponent-balance.json \
  --opponent trick-room=/chemin/opponent-trick-room.json \
  --opponent offense=/chemin/opponent-offense.json \
  --regulation M-C \
  --checkpoint-id bc-mb-mc-80k-20261109T095752Z \
  --samples 300 \
  --base-seed 1 \
  --output artifacts/teampreview-conditioning.json
```

Codes de sortie : `0` audit complet ; `1` paire `observation-not-different` ; `2` arguments ou réponses invalides.

## Matrice de décision

1. **`observation-not-different`** — bug pipeline (OTS, snapshot, empreinte). Ne pas juger le modèle.
2. **Empreintes différentes + changements appariés** — sélection conditionnée par l’adversaire.
3. **Empreintes différentes, zéro changement apparié** — policy invariante malgré l’observation ; envisager plan dataset/modèle.
4. **Plusieurs quatre mais même gagnant d’agrégation** — lire `comparisons`, couverture et win rate avant de modifier le modèle.

Conserver le JSON d’audit, les run IDs, le fingerprint checkpoint et une courte conclusion.
