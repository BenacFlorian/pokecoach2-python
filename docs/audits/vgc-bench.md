# Audit VGC-Bench (plan 04b)

Commit épinglé amont : `d79f9532947ac114dce1dda2456a590afcd375b2` ([vgc-bench](https://github.com/cameronangliss/vgc-bench/commit/d79f9532947ac114dce1dda2456a590afcd375b2)).

Manifeste PokeCoach : `engine-runtime/manifest.json` (SHA checkpoint référence `57f5edcab415cf6ccc1b6231923c8b66d3b1b7249b6b2562b97531471e4ca60b`).

## État implémentation (code)

| Composant | Statut |
| --- | --- |
| `VgcBenchEngineAdapter` | Subprocess JSONL uniquement ; **pas** de repli stub |
| Bridge `pokecoach_vgc_bridge` | `server.py`, `runtime.py`, `fixture_sim` (CI), `vgc_real` + `battle_runner` (Showdown + BC si deps installées) |
| Protocole | `hello`, `preflight`, `preview`, `first_turn`, `full_battle`, `shutdown` |
| Normalisation | `normalization.py`, `extract_turn_one.py`, `contracts/battle-trace-v1.schema.json` |
| Worker / provenance | `provenance.py`, graine stable `seeds.py`, compat moteur au claim |
| Capacités API | `capabilities.py` + preflight sur vrais snapshots matchup |
| Validation C/D | `validate_real_engine_battle` à l’insert si `vgc_bench` |

## Preuve locale (sans Torch)

Bridge fixture (`POKECOACH_BRIDGE_FIXTURE=1`) :

```bash
cd pokecoach2-python
devbox run engine-setup
POKECOACH_BRIDGE_FIXTURE=1 devbox run test
POKECOACH_BRIDGE_FIXTURE=1 devbox run test-integration
POKECOACH_BRIDGE_FIXTURE=1 devbox run engine-check -- \
  --our-team tests/fixtures/engine-real/sample-team.json \
  --opponent-team tests/fixtures/engine-real/sample-team.json \
  --modes preview,first_turn,full_battle --seed 1
```

Créer `tests/fixtures/engine-real/sample-team.json` à partir d’un export Showdown expurgé si absent (voir README du dossier).

## Preuve moteur réel (BC + Showdown)

1. `devbox run engine-fetch-checkpoint` puis `VGC_CHECKPOINT_PATH` + `VGC_CHECKPOINT_SHA256` dans `.env`.
2. Installer VGC-Bench / Torch / poke-env dans `engine-runtime` (voir [moteur-reel.md](../recettes/moteur-reel.md) — `open-spiel` peut bloquer l’install complète).
3. Serveur Showdown local (port documenté dans `.env.example`).
4. `POKECOACH_VGC_REAL=1 uv run pytest tests/integration/test_vgc_*_real.py -q`
5. `devbox run engine-check` avec les mêmes snapshots et `--test-d-constraints`.

Critères de fin plan 04b §154–161 : la preuve **BC réelle** repose sur les étapes 1–5 ci-dessus ; le code refuse stub/mixte et exige `terminalEvidence` pour persistance réelle.
