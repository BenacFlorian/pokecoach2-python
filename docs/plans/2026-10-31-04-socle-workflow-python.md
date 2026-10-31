# Socle transversal du workflow Python — Plan d’implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fournir lancement, continuation, worker, adaptateur VGC-Bench, persistance et commandes frontend avant d’implémenter les calculs de chaque phase.

**Architecture:** FastAPI enregistre les commandes ; un processus worker lit la file PostgreSQL. Les handlers A/B/C/D/E partagent un contexte et publient des checkpoints atomiques. Le moteur et les processus Showdown sont isolés des requêtes HTTP.

**Tech Stack:** Fondation uv/FastAPI, PostgreSQL, processus Python, VGC-Bench/checkpoint BC et Showdown local après audit, Angular.

**Spec:** [Workflow §§2–3, 9, 11–15](../specs/2026-10-31-workflow-analyse-matchup.md). Prérequis : [plan 03](2026-10-31-03-adaptations-resultats-progressifs.md).

## Contraintes globales

- Aucun handler factice enregistré dans le serveur normal. Le registre expose seulement les phases réellement implémentées ; le socle seul refuse leur lancement avec 422.
- Les contrats ci-dessous sont **nos interfaces**, pas des API présumées de VGC-Bench. Les appels externes doivent être trouvés et exercés dans le code audité.
- Pas de LLM avant E ; pas de Redis, MinIO ou entraînement. Un worker initial, parallélisation ultérieure seulement après mesures.
- La continuation conserve les phases validées du même run. Elle accepte le déploiement d’une nouvelle phase sans exiger le même commit applicatif global ; elle vérifie en revanche le checkpoint, format, adaptateur et paramètres scientifiques déjà figés.

## Points de revue

Tester les commandes répétées/concurrentes (2), le bail perdu/annulé (3), les capacités réelles du moteur (1), la publication partielle interrompue (3), et le choix du run après rechargement de page (4).

## Tâche 1 — Audit exécutable et frontière du simulateur

**Fichiers Python :** créer `docs/audits/vgc-bench.md`, `src/pokecoach_python/engine/contracts.py`, `engine/vgc_bench_adapter.py`, `engine/check.py`, `contracts/battle-record-v1.schema.json`, `tests/integration/test_engine_adapter.py` ; modifier `pyproject.toml`, `uv.lock`, `devbox.json`, `.env.example` et `README.md`.

**Interfaces :** `EngineAdapter.preflight(config, snapshots) -> EngineCapabilities`, `preview(request) -> PreviewRecord`, `first_turn(request) -> TurnOneRecord`, `full_battle(request) -> BattleRecord`, `close()`. `SimulationRequest` contient snapshots, format, checkpoint, graine, limite de durée, lead adverse optionnel, quatre adverse optionnel et sélection de notre côté optionnelle.

- [ ] Auditer un commit épinglé du [dépôt VGC-Bench](https://github.com/cameronangliss/vgc-bench) : chargement BC et empreinte des poids, versions Python/Torch, format supporté, injection d’équipes, sampling, contraintes de sélection, points d’arrêt et accès aux historiques. Documenter les appels exacts et leurs limites dans l’audit.
- [ ] Installer les seules dépendances requises et verrouiller Showdown/checkpoint. Si le moteur n’est pas compatible avec Python 3.13, l’isoler dans un environnement uv dédié, appelé par le worker avec un protocole JSON versionné ; ne pas annoncer une compatibilité non testée ni remplacer le modèle par un bot aléatoire.
- [ ] Définir les records à partir de traces réelles : slots stables, choix initiaux, actions/cibles, état fin tour, issue terminale. Un `BattleRecord` conserve preview, tous les tours normalisés, issue et métadonnées participantes ; exclure secrets, messages réseau et redondances. Un abandon technique n’est pas une victoire.
- [ ] Écrire l’adaptateur et une commande `devbox run engine-check` : deux équipes de test compatibles, un preview, un tour 1 et un combat complet. Vérifier arrêt/libération, choix imposés, sampler réellement stochastique et reproductibilité documentée. Sauvegarder une trace de référence expurgée pour les tests de normalisation.
- [ ] Mesurer chaque mode. Si arrêt ou contrainte non fournis nativement, implémenter une adaptation limitée et la tester ; un rejet conditionnel doit être borné et compté. Ne pas continuer le plan en remplaçant silencieusement un résultat réel par une fixture.

## Tâche 2 — API idempotente et repository

**Fichiers Python :** créer `api/analyses.py`, `schemas/analysis_commands.py`, `services/analysis_commands.py`, `db/analysis_repository.py`, `workflow/types.py`, `workflow/registry.py`, `tests/integration/test_analysis_commands.py` sous les racines usuelles `src/pokecoach_python` et `tests`. Modifier `main.py`.

**Interfaces partagées :**

- `PhaseContext` : `run_id`, `lease_token`, snapshots, paramètres figés, `partial_result`, accès contrôlé moteur/combats et `report_progress(completed, total)`.
- `PhaseOutput` : `phase`, résultat v2 enrichi, métadonnées de la phase ; les combats sont persistés séparément avant checkpoint.
- `PhaseHandler.run(context: PhaseContext) -> PhaseOutput` ; registre ordonné A/B/C/D/synthesis.
- Repository : `start_command(key, request)`, `continue_command(key, run_id, target)`, `cancel_command(key, run_id)`, `claim_next() -> PhaseContext | None`, `heartbeat(run_id, token)`, `save_battle(run_id, token, record)`, `publish_phase(run_id, token, expected_revision, output)`, `fail_run(run_id, token, reason)`.

- [ ] Implémenter les quatre routes de la spec : POST lancement, POST continuation, POST annulation et GET capacités. Toutes les commandes POST requièrent une clé ; réponse 202 pour queued/running, 200 pour commande déjà appliquée avec run désormais en pause/terminal.
- [ ] Faire l’idempotence sous contrainte unique en base, transaction courte ; même clé/même requête retrouve le même run même après changement de configuration serveur. Vérifier matchup/archivage, réglementation, profil, cible déployée et disponibilité du moteur avant nouvelle création. Figer les snapshots avec le trigger.
- [ ] Sur continuation, verrouiller le run, vérifier pause, préfixe complété, cible supérieure, capacités et absence d’autre run actif. Ne modifier ni budgets ni sections acquises. Une nouvelle phase enregistre sa version/configuration d’exécution avant de commencer ; ne pas invalider le run simplement parce que cette phase n’existait pas au déploiement précédent.
- [ ] Sur annulation, verrouiller la ligne, passer en cancelled/ERROR, fixer `finished_at`, vider le bail ; le worker observe la perte de token et arrête ses processus. Conserver le résultat partiel, aucune annulation du rapport déjà réussi.
- [ ] Tester doubles requêtes, même clé/autre payload, course entre création et continuation, run d’un autre matchup, archivage et indisponibilité moteur. Le compte worker doit suffire à tous ces cas.

## Tâche 3 — Worker, checkpoints et erreurs

**Fichiers Python :** créer `worker.py`, `workflow/runner.py`, `workflow/metrics.py`, `tests/integration/test_worker_lifecycle.py`, `tests/unit/test_phase_registry.py` ; modifier `db/analysis_repository.py`, `devbox.json`. Compléter l’overlay Python de conception avec un service worker utilisant la même image, sans port HTTP.

- [ ] Acquérir un queued dans une transaction avec `FOR UPDATE SKIP LOCKED`, passer en running, créer un nouveau token et un bail de 60 s. Heartbeat toutes les 10 s depuis le superviseur, y compris pendant un calcul moteur en processus enfant ; ne jamais partager une session SQL entre threads/processus. Voir la [sémantique PostgreSQL des verrous de lignes](https://www.postgresql.org/docs/17/sql-select.html).
- [ ] Implémenter le runner séquentiel à partir de la première phase manquante. Chaque publication verrouille le run et exige token courant, bail non expiré, statut running et révision attendue. Insérer les combats avec la même protection, sans conserver de transaction durant leur calcul.
- [ ] Publier résultat, métadonnées, révision et pause/suite dans une seule transaction. Si cible A–D atteinte : paused et bail libéré ; si E achevée : report complet, succeeded/SUCCESS et finished_at. Les checkpoints A–D restent visibles pendant la phase suivante.
- [ ] Encadrer tentatives et timeouts par configuration. Initialiser le plafond de tentatives à cinq fois le budget de simulations valides, mesuré/révisable après audit ; enregistrer tentatives, rejets et erreurs séparément. Fixer les timeouts par mode à partir des mesures de la tâche 1 et les versionner, sans annoncer un temps de traitement garanti.
- [ ] Détecter les baux expirés au démarrage et périodiquement ; passer les runs correspondants en failed avec conservation des checkpoints. Un worker périmé ne peut publier ni un combat ni un résultat après cette décision. Nettoyer ses processus et connexions.
- [ ] Enregistrer durées par phase, CPU/RAM et GPU si disponible (sinon valeur absente explicite), versions et empreintes des artefacts. Les métadonnées initiales restent figées ; les observations d’exécution vont dans `execution_metadata`.
- [ ] Tester le cycle complet avec handlers contrôlés **dans les tests seulement** : A→pause→B, continuation directe jusqu’à D, crash après A, annulation en cours, perte de token, deux workers, panne DB à la publication et absence de double comptage des combats.
- [ ] Ajouter `devbox run worker` → `uv run python -m pokecoach_python.worker`. Tester arrêt propre et déploiement API/worker séparés. Ne pas utiliser FastAPI BackgroundTasks pour la durée de vie du calcul.

## Tâche 4 — Commandes de lancement et continuation dans le frontend

**Fichiers Angular :** créer `src/app/core/python/analysis-api.ts`, `analysis-api.spec.ts`, `src/app/features/matchup/analysis-controls.ts`, `analysis-controls.html`, `analysis-controls.spec.ts`. Modifier `features/matchup/matchup.ts/html`, `core/data/coach-store.ts`, les opérations GraphQL de liste de runs et, si nécessaire, les proxies déjà installés par le plan 02.

**Interfaces :** `AnalysisApi.capabilities()`, `start(matchupId, request, key)`, `continue(runId, targetPhase, key)`, `cancel(runId, key)`, retournant des Observables typés.

- [ ] Ajouter choix du format si le matchup n’en a pas, sélection du profil/cible, lancement, continuation et annulation. Persister la réglementation via la mutation GraphQL autorisée avant le POST ; ne pas changer le format d’un run en pause.
- [ ] Ne proposer que les cibles déployées ; après une phase en pause, sélectionner la suivante par défaut. Enregistrer `runId` dans les query params, charger ce run et maintenir le polling approprié. La liste des runs permet de revoir un succès ancien.
- [ ] Conserver la clé d’une commande dont l’issue réseau est inconnue pour la réconciliation ; ne pas générer une nouvelle clé à chaque retry. Bloquer les doubles clics ; afficher les erreurs sans supprimer les résultats partiels.
- [ ] Tester chargement des capacités, choix smoke/standard, 202 puis progression, pause et arrêt du polling, continuation et reprise, run terminal sans continuation, annulation, refresh de page et résultat obsolète ignoré.
- [ ] Lancer tests Python/SQL/Angular, lint et build. Avec ce socle seul, le frontend explique qu’aucune phase n’est encore disponible ; `engine-check` démontre la connexion au vrai moteur. Aucun faux résultat de phase n’est publié.

## Tâche 5 — Outils de recette communs aux phases

**Fichiers Python :** créer `scripts/analysis-smoke.py`, `scripts/freeze-benchmark.py`, `scripts/run-benchmark.py`, `benchmarks/README.md`, `docs/recettes/analyses-progressives.md`, `tests/integration/test_analysis_smoke.py` ; compléter `README.md`. **Angular :** créer `e2e/analysis-progressive-live.spec.ts` et le script npm `e2e:analysis-live`.

- [ ] Fournir `uv run python scripts/analysis-smoke.py --matchup-id UUID --target A --profile smoke` et `--run-id UUID --target B` pour continuer : POST réel, attente bornée par délai CLI explicite via lectures PostGraphile, puis affichage de l’URL frontend avec runId. Afficher statut, phase et révision ; ne pas contourner l’API en écrivant directement en base.
- [ ] Le scénario Playwright reçoit le matchup et la cible par configuration de test, utilise les vrais services, vérifie l’onglet attendu puis recharge la page. Images Pokémon stabilisables ; appels de calcul et GraphQL non interceptés pour cette recette.
- [ ] Documenter les terminaux à lancer : stack conception, API `devbox run start`, worker `devbox run worker`, Angular `npm start`. Ajouter les ports réels et la manière de préparer un matchup compatible, indépendant de la seed si son format ne convient pas au checkpoint.
- [ ] Prévoir un dossier de résultats de recette par run : version/profil/cible, comptes obtenus, mesures et captures du frontend. Chaque plan de phase doit produire sa propre recette réelle, sans prétendre valider la stratégie avec le profil smoke.
- [ ] Fournir un export manuel de benchmark à partir d’une liste de matchups compatibles choisis : manifeste avec snapshots, réglementation, paramètres et empreintes. Viser environ dix matchups dès qu’ils sont disponibles ; ne pas inventer leur légalité ou dupliquer un seul matchup pour atteindre dix. Le runner appelle l’API séquentiellement et produit un index expérience→runIds, sans nouvelle fonctionnalité de batch dans l’interface.
- [ ] Tester que le runner refuse une équipe modifiée depuis le manifeste ou une configuration différente de celle de l’expérience, et qu’il reprend la consultation des runIds déjà créés après une coupure plutôt que de lancer des doublons. L’outil est préparé ici ; le benchmark complet devient exécutable après E.

## Sortie

Le socle est opérationnel et testé, les calculs de phases restent absents. Commencer le [plan A](2026-10-31-05-phase-a-leads.md) ; ses résultats seront les premiers résultats réels affichables.
