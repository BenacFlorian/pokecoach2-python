# Recette — moteur réel VGC-Bench (plan 04b)

## Prérequis

1. `devbox run engine-setup` — venv isolé dans `engine-runtime/`.
2. Télécharger le checkpoint BC amont, renseigner `VGC_CHECKPOINT_PATH` et `VGC_CHECKPOINT_SHA256` (voir `engine-runtime/manifest.json`).
3. Showdown local sur le port configuré (`SHOWDOWN_SERVER_URL`, par défaut 8090).
4. `POKECOACH_ENGINE=vgc_bench` dans `.env` (jamais committer les poids).

## Diagnostic

```bash
devbox run engine-setup
# Télécharger le checkpoint BC (huggingface_hub requis dans engine-runtime/.venv)
engine-runtime/.venv/bin/python engine-runtime/scripts/fetch_bc_checkpoint.py --output checkpoints/bc-seed1-100.zip

# Showdown local (depuis clone vgc-bench/pokemon-showdown, port 8090)
# node pokemon-showdown start 8090 --no-security

devbox run engine-check -- --our-team chemin/our.json --opponent-team chemin/opp.json \
  --modes preview,first_turn,full_battle --seed 42 --output /tmp/engine-report.json
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
uv run pytest tests/unit/test_engine_protocol.py tests/unit/test_vgc_subprocess.py -q
```

## Nouveau run après changement moteur

Toujours relancer **depuis la phase A** après passage stub → réel ou changement de checkpoint. Les runs existants restent consultables avec leur provenance d’origine.

## Limite actuelle

Le chargement **PyTorch + policy_player VGC-Bench** dans `engine-runtime` est préparé (`vgc_real.py`) ; tant que les dépendances épinglées ne sont pas installées et le hook Showdown branché, seul le bridge **fixture** (tests) ou l’échec explicite `CHECKPOINT_UNAVAILABLE` s’appliquent — pas de repli vers le stub dans `VgcBenchEngineAdapter`.
