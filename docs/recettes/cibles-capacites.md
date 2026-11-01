# Recette — cibles des capacités (plan 12)

## Prérequis

- Moteur réel configuré (`devbox run engine-setup`, Showdown local, checkpoint BC).
- Stack Python + worker + Angular.

## Vérifier le catalogue

Depuis `pokecoach2-python/engine-runtime` :

```bash
uv run pytest tests/test_move_targets.py tests/test_extract_turn_one.py -q
```

Optionnel (Dex Showdown compilé) :

```bash
node scripts/export_move_targets.cjs vendor/vgc-bench/pokemon-showdown gen9championsvgc2026regma | head -c 200
```

Si le build Showdown manque, le bridge charge le catalogue Gen 9 via poke-env (même enum `target`).

## Analyse de bout en bout

1. Choisir un matchup avec Tailwind et une attaque collective (Earthquake, Rock Slide).
2. Lancer une analyse jusqu’à la phase B (ou synthesis).
3. Vérifier dans l’UI ouvertures : `Pokémon : Tailwind (camp du lanceur)` — jamais `Tailwind → …`.
4. Vérifier JSON des actions : `targetType`, `targetSource`, `targets[].zone` Showdown.

## Tests automatisés

```bash
# Python backend
cd pokecoach2-python && uv run pytest tests/unit/test_battle_action_targets.py -q

# Angular
cd pokecoach2-angular/pokecoach-angular && npm test -- --watch=false
```

## Nettoyage

Les anciennes analyses conservent les zones legacy (`field`, `all-opponents`). Relancer une analyse pour bénéficier du contrat plan 12.
