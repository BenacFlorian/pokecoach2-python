# Clôture officielle — plan 04b (moteur réel)

## Ce qu’on attend à la fin du 4b

**Oui** : les phases **A, B, C et D** (seules phases moteur implémentées aujourd’hui) doivent consommer des **vraies parties simulées** :

| Phase | Appel moteur | Donnée produite |
| --- | --- | --- |
| **A** | `preview` | Leads adverses (preview BC sur Showdown) |
| **B** | `first_turn` | Actions tour 1 + back pair (combat réel arrêté après T1) |
| **C / D** | `full_battle` | Combats terminés (issue win/loss/draw, tours, actions T1) |

Ce ne sont **pas** les libellés fictifs du stub (`Stub Move A`, etc.). C’est le checkpoint BC + serveur Showdown local, via le subprocess `engine-runtime/`.

**Hors périmètre 4b** : phase **E / synthesis** (LLM, plan 09). Les runs **déjà en base** créés en stub restent marqués stub ; il faut un **nouveau run depuis A** après passage réel.

## Prérequis `.env` worker + API

```env
POKECOACH_ENGINE=vgc_bench
VGC_CHECKPOINT_PATH=...
VGC_CHECKPOINT_SHA256=...
SHOWDOWN_SERVER_URL=ws://127.0.0.1:8090/showdown/websocket
ANALYSIS_DEPLOYED_PHASES=A,B,C,D,synthesis   # synthesis = UI seulement tant que E non branchée
```

Ne **pas** définir `POKECOACH_BRIDGE_FIXTURE=1` sur worker/API (réservé CI).

**Worker / API** : après changement de `.env`, redémarrer **API** (`devbox run start`) et **worker** (`devbox run worker`). Au démarrage d’un run, le worker logue `POKECOACH_ENGINE=…`. Vérifier `vgc_bench` + chemin checkpoint. Sans redémarrage, un worker lancé en stub peut continuer à simuler en stub malgré un `.env` à jour.

Showdown : serveur **séparé** — le worker/API ne le démarrent pas ; ils se connectent à `SHOWDOWN_SERVER_URL`. Lancer depuis le clone **`pokecoach2/pokemon-showdown`** (recommandé) : `node pokemon-showdown start 8090 --no-security`. Éviter le clone vendu sous `engine-runtime/vendor/vgc-bench/pokemon-showdown` pour le serveur (souvent cassé au `npm ci`).

## Preuves automatisées (obligatoires)

Depuis `pokecoach2-python/` :

```bash
set -a && source .env && set +a

# 1) Intégration BC + Showdown
export POKECOACH_VGC_REAL=1
uv run pytest tests/integration/test_vgc_preview_real.py \
  tests/integration/test_vgc_first_turn_real.py \
  tests/integration/test_vgc_full_battle_real.py \
  tests/integration/test_vgc_constraints_real.py -q

# 2) Diagnostic moteur (3 modes + contraintes D + reproductibilité preview)
uv run python -m pokecoach_python.engine.check \
  --our-team tests/fixtures/engine-real/mb-regmb-our.json \
  --opponent-team tests/fixtures/engine-real/mb-regmb-opp.json \
  --regulation M-B \
  --seed 42 \
  --modes preview,first_turn,full_battle \
  --test-d-constraints \
  --output /tmp/pokecoach-04b-engine-report.json
echo exit=$?
```

Succès : pytest **7 passed**, `engine-check` **exit 0**, rapport avec `"engineMode": "vgc_bench"`, `"terminalEvidence"` en full_battle, `reproduciblePreview` et `reproduciblePreviewFreshRuntime` à true.

## Preuve produit (run neuf A→D)

1. Stack : PostgreSQL/PostGraphile (conception), `devbox run start`, `devbox run worker`, Angular.
2. Créer ou choisir un **matchup** avec les deux snapshots Reg M-B (ou équipes équivalentes légales).
3. Lancer un **nouveau** run (pas continuer un ancien stub) :

```bash
uv run python scripts/analysis-smoke.py --matchup-id <UUID> --target A --profile smoke
# puis continuer B → C → D (UI ou --target B / C / D)
```

4. Vérifier dans l’UI :
   - **Opponent Leads** : leads cohérents, pas de moves stub ;
   - **Tour 1** : noms de capacités issus des sets ;
   - **Lead & pick / affinage** : combats C/D terminés, provenance moteur réelle (pas « simulé / stub »).
5. Recharger la page : données persistées.

Profil **smoke** : budgets réduits (recettes [phase-a](phase-a.md) … [phase-d](phase-d.md)). Profil **standard** : optionnel pour charge réelle, pas bloquant pour déclarer le 4b clos si smoke + preuves ci-dessus passent.

## Checklist de clôture

- [ ] `.env` : `POKECOACH_ENGINE=vgc_bench`, checkpoint + Showdown OK
- [ ] `POKECOACH_VGC_REAL=1` pytest intégration : 7/7
- [ ] `engine-check` Reg M-B : exit 0, rapport archivé
- [ ] Nouveau run smoke **A→D** sur matchup réel, UI vérifiée
- [ ] Anciens runs stub toujours lisibles, non mélangés avec le run de clôture

Une fois coché : le plan 04b est **clos** pour le socle moteur ; enchaîner recettes **standard** B/C/D et plan **09 (E)** sans re-brancher le stub.
