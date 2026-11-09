# Recette — moteur réel VGC-Bench (plan 04b)

## Prérequis

1. `devbox run engine-setup` — venv isolé dans `engine-runtime/`.
2. Télécharger le checkpoint BC amont, renseigner `VGC_CHECKPOINT_PATH` et `VGC_CHECKPOINT_SHA256` (voir `engine-runtime/manifest.json`).
3. Showdown local sur le port configuré (`SHOWDOWN_SERVER_URL`, par défaut 8090). **Utiliser le clone à la racine du monorepo** (`../../pokemon-showdown` depuis `pokecoach2-python/`), pas le sous-module vendu sous `engine-runtime/vendor/…` : sur Node récent, `node pokemon-showdown start` y échoue souvent (`npm ci` sans `package-lock.json` valide).
4. `POKECOACH_ENGINE=vgc_bench` dans `.env` (jamais committer les poids).

## Diagnostic

```bash
devbox run engine-setup
devbox run engine-fetch-checkpoint
# Copier dans .env les lignes VGC_CHECKPOINT_PATH et VGC_CHECKPOINT_SHA256 affichées

# Showdown local (clone repo racine pokecoach2/pokemon-showdown, port 8090)
cd ../pokemon-showdown && node pokemon-showdown start 8090 --no-security

uv run python -m pokecoach_python.engine.check \
  --our-team tests/fixtures/engine-real/mb-regmb-our.json \
  --opponent-team tests/fixtures/engine-real/mb-regmb-opp.json \
  --regulation M-B \
  --modes preview,first_turn,full_battle --seed 42 --test-d-constraints \
  --output /tmp/engine-report.json
```

### Dépendances VGC-Bench (runtime réel)

Dans `engine-runtime/`, installer le dépôt épinglé (retirer `open-spiel` du pyproject amont si l’install échoue) :

```bash
cd engine-runtime && uv pip install "vgc-bench @ git+https://github.com/cameronangliss/vgc-bench.git@d79f9532947ac114dce1dda2456a590afcd375b2"
```

Sans ces paquets, seul le bridge **fixture** (`POKECOACH_BRIDGE_FIXTURE=1`) ou l’échec explicite s’appliquent.

Avec le stub : mêmes flags, `POKECOACH_ENGINE=stub`.

## Bridge fixture (CI / tests unitaires)

```bash
export POKECOACH_BRIDGE_FIXTURE=1
export POKECOACH_ENGINE=vgc_bench
uv run pytest tests/unit tests/integration -q
POKECOACH_BRIDGE_FIXTURE=1 POKECOACH_ENGINE=vgc_bench devbox run engine-check -- \
  --our-team tests/fixtures/engine-real/sample-team.json \
  --opponent-team tests/fixtures/engine-real/sample-team.json \
  --modes preview,first_turn,full_battle --seed 1 --test-d-constraints
```

## Clôture plan 04b

Checklist complète (preuves + run A→D smoke) : [cloture-04b.md](cloture-04b.md).

Équipes Reg M-B de référence pour `engine-check` : `tests/fixtures/engine-real/mb-regmb-our.json` et `mb-regmb-opp.json`.

## Tests moteur réel (BC + Showdown)

```bash
export POKECOACH_VGC_REAL=1
uv run pytest tests/integration/test_vgc_preview_real.py tests/integration/test_vgc_first_turn_real.py tests/integration/test_vgc_full_battle_real.py tests/integration/test_vgc_constraints_real.py -q
```

Optionnel : `POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS=1` réactive les open team sheets Showdown (défaut `0`, plus fiable avec le serveur local).

## Nouveau run après changement moteur

Toujours relancer **depuis la phase A** après passage stub → réel ou changement de checkpoint. Les runs existants restent consultables avec leur provenance d’origine.

## Limite opérationnelle

Le runtime réel (`vgc_real`, `battle_runner`, `battle_session`) exige `devbox run engine-setup` (clone `vgc-bench` + deps), checkpoint BC local et Showdown sur `SHOWDOWN_SERVER_URL`. Chaque session bridge utilise des comptes Showdown éphémères pour éviter les combats zombies sur le serveur local.
