# Plan 04b — Moteur réel VGC-Bench : preview, tour 1 et combats complets

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alimenter A/B/C/D avec de véritables décisions du checkpoint BC et des combats Showdown, obtenir les vraies distributions du tour 1 dans Angular et rendre les historiques C/D utilisables par le futur LLM.

**Architecture:** Remplacer la délégation de `VgcBenchEngineAdapter` au stub par un processus Python dédié, relié par un protocole JSON versionné. Ce processus charge le checkpoint et pilote uniquement un Showdown local. Les agrégateurs et tables existants restent les consommateurs ; les actions choisies et les événements exécutés sont enregistrés séparément.

**Tech Stack:** FastAPI/worker Python existants, uv, VGC-Bench et son fork poke-env épinglés, PyTorch, Showdown épinglé, PostgreSQL/PostGraphile, Angular pour la recette et l’indication de provenance.

**Spec:** [Workflow A–E](../specs/2026-10-31-workflow-analyse-matchup.md), [socle plan 04](2026-10-31-04-socle-workflow-python.md), demande utilisateur sur les moves fictifs et [audit local](../audits/vgc-bench.md).

## Position dans le développement

Ce plan complète le raccordement moteur du plan 04. Les phases 5–8 déjà développées en stub peuvent être conservées pour leurs calculs et leur interface, mais leur recette réelle doit être rejouée après 04b. Ordre des jalons : moteur/preview réel → B réel → C/D réels → vérification frontend → plan 09 LLM.

Il n’y a pas de nouvelle phase statistique entre D et E : B mesure déjà le tour 1 adverse, C calcule nos premiers tours recommandés, D mesure ceux de la configuration ciblée. Changer uniquement les chaînes « Stub Move A/B » pour des noms tirés des sets ne constituerait pas une simulation BC.

## Constats vérifiés dans le code local

| Zone | État observé | Conséquence pour ce plan |
| --- | --- | --- |
| `engine/vgc_bench_adapter.py` | Les trois méthodes et le preflight délèguent à `StubEngineAdapter` | `POKECOACH_ENGINE=vgc_bench` ne prouve actuellement aucun usage du moteur réel |
| `engine/stub_adapter.py` | Actions synthétiques, cibles arbitraires ; full_battle renvoie un seul tour et une issue tirée par digest | Ne pas utiliser ces combats pour une synthèse stratégique réelle |
| `engine/check.py` | Snapshots vides, test du preview seulement | Étendre le diagnostic aux vrais sets et aux trois modes |
| `workflow/battle_records.py` et `aggregation/refinement.py` | Présence d’au moins un tour suffisante pour certaines validations | Exiger une preuve de fin et une trace complète pour les records réels |
| `services/analysis_commands.py` | Capacités tirées de la configuration ; preflight avec deux objets vides ; format par défaut appliqué au lancement | Séparer disponibilité du moteur et validation des équipes, vérifier le format effectivement joué |
| `workflow/runner.py` | Adaptateur construit depuis la configuration courante ; certains checkpoints intermédiaires différés | Interdire le mélange stub/réel et publier les phases terminées même lors d’une exécution A→D |
| `workflow/phases/phase_b.py`, `phase_c.py`, `phase_d.py` | Réutilisation du timeout preview et captures larges d’erreurs | Timeouts par mode, diagnostics distincts et arrêt immédiat si bail perdu |

La lecture du code permet ces constats ; aucun checkpoint réel n’a été chargé et aucune simulation réelle n’a été exécutée pendant la rédaction du plan.

## Sources amont et choix à confirmer par exécution

- Le [README VGC-Bench](https://github.com/cameronangliss/vgc-bench#readme) mentionne Python 3.13, le sous-module Showdown et le checkpoint BC. Son [pyproject.toml](https://github.com/cameronangliss/vgc-bench/blob/main/pyproject.toml) déclare Python ≥3.10 et des dépendances épinglées ou issues de forks. **Python 3.13 n’est donc pas une incompatibilité établie.** Tester l’installation sur la machine cible avant de décider de changer de version.
- Dans [policy_player.py](https://github.com/cameronangliss/vgc-bench/blob/main/vgc_bench/src/policy_player.py), `PolicyPlayer.set_policy` charge une policy, `choose_move` utilise son masque d’actions et `deterministic=False` permet le sampling. `teampreview` utilise une sélection aléatoire si `choose_on_teampreview` est faux. Vérifier ce drapeau sur le checkpoint réellement chargé avant de qualifier A de choix BC.
- Le [protocole de simulation Showdown](https://github.com/smogon/pokemon-showdown/blob/master/sim/SIM-PROTOCOL.md) distingue demandes de choix, capacités exécutées, changements, impossibilités d’agir et fin de combat. Les traces d’exécution seules ne suffisent pas à retrouver toutes les décisions sélectionnées.

Ces liens pointent vers des branches consultées pour préparer le plan. À l’implémentation, enregistrer les SHA exacts de VGC-Bench, poke-env et Showdown, les empreintes des poids et les versions Python/Torch ; remplacer les références d’audit par des permaliens épinglés. Les signatures proposées ci-dessous appartiennent à PokeCoach, pas à une API supposée de VGC-Bench.

## Contraintes globales

- Ne pas entraîner de modèle, utiliser de bot ladder, ajouter de LLM ou réécrire le simulateur. Deux joueurs BC utilisent les équipes des snapshots et le checkpoint audité.
- Aucun repli automatique vers stub, joueur aléatoire ou heuristique en mode réel. Une capacité non disponible reste déclarée indisponible.
- Conserver `SimulationResultV2`, `matchup_runs` et `matchup_run_battles` : pas de migration structurelle prévue. Enrichir les JSON de provenance/trace et versionner le protocole interne ; ne pas relabelliser les anciens runs ou modifier leurs snapshots.
- Un changement stub→réel exige **un nouveau run depuis A**. Ne pas continuer un A stub avec un B réel, ni envoyer des combats anciens sans provenance vérifiable au LLM.
- Les noms affichés ne servent pas d’identité : les actions se rattachent au côté, au slot initial 0–5 et à l’identifiant moteur de la capacité. L’affichage reprend le nom correspondant du set quand c’est cette capacité qui a été sélectionnée.
- Les statistiques de tour 1 portent sur les choix légaux acceptés par le serveur, y compris un choix empêché ensuite par flinch/K.-O. Les événements d’exécution, redirections et causes d’échec restent dans la trace, sans remplacer le choix par une autre capacité.

## Points de revue

| Risque | Vérification propriétaire |
| --- | --- |
| Mode réel qui utilise encore le stub / mauvais checkpoint | Tâches 1, 2, 6 |
| Slot de roster confondu avec place active, cible ou pseudonyme | Tâche 3 |
| Une capacité bloquée au T1 disparaît des fréquences | Tâches 3–4 |
| Fin fabriquée, derniers tours manquants, timeout compté comme victoire | Tâche 5 |
| Changement d’environnement entre phases, bail perdu, reprise d’un run stub | Tâche 6 |

## Tâche 1 — Environnement moteur reproductible et preuve de chargement BC

**Fichiers Python :** créer `engine-runtime/pyproject.toml`, `engine-runtime/uv.lock`, `engine-runtime/.python-version`, `engine-runtime/src/pokecoach_vgc_bridge/__init__.py`, `engine-runtime/manifest.json`, `docs/recettes/moteur-reel.md`. Modifier `devbox.json`, `.gitignore`, `.env.example`, `core/config.py` sous `src/pokecoach_python`, et l’audit.

**Décision :** environnement uv moteur séparé, d’abord testé en Python 3.13. L’API reste en 3.13 ; une autre version moteur n’est retenue que sur preuve d’incompatibilité des dépendances utiles. Le manifeste contient des versions/empreintes, pas les gros poids du modèle.

- [ ] Récupérer un commit VGC-Bench, son sous-module Showdown et les révisions de ses dépendances Git. Télécharger le checkpoint BC identifié par l’amont, calculer son SHA-256, documenter origine et chemin local. Ne pas exécuter le pipeline d’entraînement pour simplement obtenir des poids.
- [ ] Résoudre et verrouiller les dépendances moteur avec uv. Tester imports et chargement CPU ; GPU facultatif. Ne pas supprimer silencieusement une dépendance requise : documenter toute exclusion de modules d’évaluation inutiles pour l’inférence.
- [ ] Inspecter espaces observation/action, normalisation et choix du team preview du checkpoint. Tester un ensemble de six sets légal dans un format explicitement compatible. Un checkpoint à preview aléatoire ne satisfait pas le jalon A BC : identifier un checkpoint compatible ou déclarer cette limite bloquante, sans annoncer une distribution apprise.
- [ ] Documenter le mapping explicite entre le nom de réglementation PokeCoach, celui de VGC-Bench et le format Showdown. Ne pas traiter `M-B` ou un autre alias comme une preuve de légalité des équipes.
- [ ] Ajouter configuration typée du Python moteur, racine VGC, chemin/empreinte du checkpoint, serveur local et timeouts séparés de démarrage/preview/tour1/combat. Les chemins sont configurés côté serveur, jamais reçus du navigateur. Le `.env` personnel n’est pas modifié automatiquement.
- [ ] Ajouter `devbox run engine-setup` et les commandes Showdown locales documentées ; choisir un port sans conflit avec FastAPI. Conserver les composants moteur dans la configuration de déploiement existante si Docker est utilisé, avec mêmes versions et volumes de poids. Ne pas publier un serveur Showdown de test sur Internet.
- [ ] Livrer une preuve de chargement du checkpoint et de validation des deux équipes ; noter toute capacité encore non raccordée. Aucun succès de cette tâche ne vaut encore validation de B/C/D.

## Tâche 2 — Protocole subprocess et disparition du repli vers stub

**Fichiers :** créer `engine-runtime/src/pokecoach_vgc_bridge/server.py`, `runtime.py`, `policy.py`, `src/pokecoach_python/engine/protocol.py`, `subprocess_client.py`, `tests/unit/test_engine_protocol.py`, `test_vgc_subprocess.py`. Modifier `engine/contracts.py`, `vgc_bench_adapter.py`, `factory.py` et les tests existants.

**Interfaces :** `EngineHello` décrit identité, versions et modes réellement supportés ; `VgcSubprocessClient.request(mode, payload, timeout_seconds)` et `close()`. Protocole JSONL v1 : requête `{protocolVersion, requestId, mode, payload}`, réponse `{protocolVersion, requestId, ok, result}` ou `{..., ok:false, error:{code,message}}`. Modes : `hello`, `preflight`, `preview`, `first_turn`, `full_battle`, `shutdown`.

- [ ] Démarrer le bridge avec une liste d’arguments, sans shell. Réserver stdout au protocole ; drainer stderr séparément avec une taille bornée. Séparer le timeout de chargement du modèle des timeouts de simulation.
- [ ] Réutiliser le modèle chargé dans un processus persistant pour les simulations séquentielles d’un run. Garantir la remise à zéro des états de partie et RNG entre requêtes, et mesurer le coût de démarrage séparément.
- [ ] Valider version, requestId, structure et taille maximale des messages. Un historique trop volumineux provoque une erreur explicite, pas une troncature cachée. Détecter EOF, processus mort, JSON invalide et retour d’un autre requestId ; tests avec petit subprocess contrôlé, sans Torch.
- [ ] Remplacer toutes les délégations de `VgcBenchEngineAdapter` au stub. Une racine absente, un checkpoint invalide ou un bridge indisponible doit échouer ; rendre ces cas testables sans installer le moteur.
- [ ] Ajouter un signal d’annulation contrôlé par le superviseur : interrompre l’attente, terminer le groupe de processus propre au bridge si nécessaire, fermer ses sockets/parties ; ne pas tuer un Showdown partagé avec d’autres runs. `close()` doit fonctionner après échec partiel de démarrage.
- [ ] Tester timeout, annulation et absence de fuite de processus. Exécuter `uv run pytest tests/unit/test_engine_protocol.py tests/unit/test_vgc_subprocess.py -q`.

## Tâche 3 — Normaliser des décisions et traces réelles

**Fichiers :** créer dans `engine-runtime/src/pokecoach_vgc_bridge/` `teams.py`, `recorder.py`, `normalization.py` ; créer `contracts/battle-trace-v1.schema.json`, `engine-runtime/tests/test_normalization.py`, `tests/fixtures/engine-real/README.md` et des traces de référence expurgées. Modifier `workflow/battle_records.py` seulement pour valider/transport des records normalisés, pas pour inventer des actions.

**Interfaces :** `normalize_choice(choice, request_state, roster_map)` produit les `BattleAction` existantes ; `TraceRecorder` conserve demandes, choix acceptés et événements ordonnés des deux joueurs ; un record complet ajoute dans ses JSON existants `meta.engine`, `meta.engineFingerprint`, `meta.traceVersion`, `meta.terminalEvidence`, les sets participants, et tous les tours avec décisions des deux côtés et événements.

- [ ] Construire les équipes depuis les snapshots sans remplacer leurs capacités, objets, EV/IV ou formes. Associer roster initial → ordre choisi au preview → slots actifs, indépendamment des noms et de l’espèce. Tester inversion p1/p2, gauche/droite, surnoms et changements successifs.
- [ ] Capturer les ordres BC acceptés pour les deux joueurs. Identifier et exclure les choix rejetés/remplacés avant validation du serveur ; ne pas les compter comme décisions jouées. Conserver les demandes d’action pour résoudre leurs index de moves et cibles.
- [ ] Associer l’identifiant canonique de chaque move au slot de move du set puis à son nom. Tester Protect/Fake Out uniquement avec des sets de référence qui les contiennent ; ne pas imposer au BC de les choisir pour réussir le test de distribution. Un simple remplacement des libellés du stub est interdit.
- [ ] Traiter les exceptions légales à l’appartenance au set initial : Struggle, copie/transformation et moves déclenchés par un autre move. Conserver preuve issue de la demande moteur et lien entre capacité choisie et exécutée. Si une mécanique n’est pas prise en charge, retourner un diagnostic explicite ; jamais fabriquer un move du snapshot pour masquer l’écart.
- [ ] Normaliser cibles choisies, zones, allié, soi-même, switch et Téracristallisation. Pour une attaque de zone, ne pas prendre le premier destinataire du log pour une cible unique. Conserver séparément la redirection ou le remplacement de cible intervenu lors de l’exécution.
- [ ] Tester un tour où le deuxième Pokémon flinch/K.-O. avant d’agir : les deux choix initiaux restent dans la paire statistique ; la trace montre que l’un n’a pas été exécuté. Les remplacements forcés et choix ultérieurs du même tour restent des événements séparés.
- [ ] Comparer normalisation à des traces réelles de référence : actions sélectionnées, sets, cibles et fin de tour vérifiables. Les tests de mécaniques peuvent utiliser des ordres contrôlés sur le vrai simulateur ; ils ne valent pas preuve de sampling BC, testé séparément.
- [ ] Exécuter les tests du runtime avec son environnement uv verrouillé. Ajouter les tests de round-trip `BattleRecord` → JSON → `BattleRecord` sans perte de décisions, événements ni preuves de fin.

## Tâche 4 — Preview réel puis first_turn pour B

**Fichiers :** compléter bridge `runtime.py`, `policy.py`, `recorder.py` ; modifier `engine/vgc_bench_adapter.py`, `workflow/phases/phase_a.py`, `phase_b.py` si nécessaire ; créer `tests/integration/test_vgc_preview_real.py`, `test_vgc_first_turn_real.py`.

- [ ] Implémenter le preview réel via le checkpoint pour les deux équipes. Arrêter après sélection connue avec libération de la partie ; ne pas compter l’abandon technique de nettoyage comme une victoire/défaite.
- [ ] Pour B, conditionner le lead adverse sur la paire de slots de A. Méthode de référence : sampling de previews BC complets et rejet des paires non conformes, avec plafond configurable et tentatives comptées. Un hook de sélection conditionnelle peut ensuite remplacer le rejet s’il préserve la distribution souhaitée ; une simple intervention forcée non équivalente doit être identifiée et versionnée comme telle.
- [ ] Conserver l’ordre réellement joué des deux positions, même si A regroupe la paire sans ordre. Le back reste choisi selon cette politique conditionnelle, pas uniformément à la place du modèle. Mesurer le coût du rejet, notamment pour un lead rare ; ne pas augmenter silencieusement les plafonds.
- [ ] Jouer le tour 1 jusqu’à sa résolution complète (ou fin normale du combat au tour 1), avant tout choix stratégique du tour 2. Inclure les effets de fin de tour et remplacements nécessaires dans la trace, sans confondre arrivée du marqueur tour 1 et fin du tour 1.
- [ ] Renvoyer le `TurnOneRecord` attendu par `aggregate_turn_one` : `actions`, `backPair`, `ourLeadSlots`, `endStateNotes`, ainsi que provenance de trace hors clé canonique des actions. Vérifier que le back est celui du preview, pas celui reconstruit après les switches.
- [ ] Exécuter les tests réels explicitement activés, puis un run neuf smoke A→B sur les services réels. Dans « Opponent Leads », confronter une paire d’actions à sa trace et à ses snapshots. Faire ensuite le budget standard B (50 valides par lead après A=1 000), mesurer échecs/rejets/temps et recharger la page.

**Jalon B :** fréquences issues de choix BC réels, noms/cibles justifiés par les sets et les demandes moteur. Aucun appel LLM nécessaire.

## Tâche 5 — Full_battle réel pour C et D

**Fichiers :** compléter bridge/runtime et `engine/vgc_bench_adapter.py` ; modifier `workflow/battle_records.py`, `workflow/aggregation/refinement.py`, `workflow/phases/phase_c.py`, `phase_d.py` ; créer `tests/integration/test_vgc_full_battle_real.py`, `test_vgc_constraints_real.py`.

- [ ] Jouer jusqu’à un signal terminal du simulateur. Mapper win/loss selon notre côté, tie vers draw. Un timeout, une déconnexion ou un arrêt de test restent des erreurs techniques, jamais un draw ou une victoire calculée sur les PV.
- [ ] Conserver preview, les quatre de chaque côté, leurs leads/backs, sets, tous les tours, les décisions et événements des deux côtés et la preuve terminale. Garder `turns[0].ourActions` compatible avec les agrégateurs actuels ; vérifier explicitement qu’il correspond au tour 1 et non au preview.
- [ ] Renforcer la validation des records **réels** : identité moteur, continuité des tours, preuve terminale, sets/slots cohérents et actions vérifiables. Un combat réellement terminé en un tour est valable ; « plusieurs tours présents » ne suffit pas à prouver la complétude.
- [ ] En C, imposer seulement le lead adverse selon la politique auditée, laisser les autres sélections au BC. En D, imposer les quatre et leads des deux côtés, puis laisser le BC décider en combat. Vérifier les contraintes dans les requêtes/choix réels, pas dans des champs copiés de la demande.
- [ ] Comparer `our_selection`, `our_lead_slots`, `opponent_lead`, `opponent_four` et `opponent_back_pair` quand fournis ; refuser leur incohérence. Construire l’état du simulateur sans changer l’ordre des sets ni confondre back trié et positions de lead.
- [ ] Réutiliser les agrégateurs C/D ; ajouter tests sur records réels. Refuser une donnée manquante qui ferait silencieusement ignorer les premiers tours tout en gardant le total des combats comme dénominateur. Si une correction d’agrégation est nécessaire, la tester et versionner sa règle, sans déplacer le calcul vers le LLM.
- [ ] Continuer le **run réel** B vers C puis D : vérifier C=3 combats/lead et D=2 en smoke, puis C=50/lead et D=10 en standard. Recharger « Lead & pick » et l’affinage ; recouper des actions avec les JSON persistés et traces moteur. Comparer les sections A/B/C avant et après enrichissement.

## Tâche 6 — Provenance, capacités et intégration sûre au worker

**Fichiers Python :** modifier `services/analysis_commands.py`, `schemas/analysis_commands.py`, `db/analysis_repository.py`, `workflow/runner.py`, `workflow/types.py`, `worker.py`, `engine/contracts.py`, `core/config.py`. Créer `engine/provenance.py`, `tests/unit/test_real_engine_eligibility.py`, `tests/integration/test_real_engine_workflow.py`.

- [ ] Séparer `hello`/disponibilité du runtime de `preflight` sur **deux vrais snapshots**. Avant création d’un nouveau run réel, vérifier format, équipes et checkpoint ; ne plus valider la compatibilité avec `({}, {})`. Une réglementation absente ou incompatible doit être explicitement résolue, pas écrasée par le premier format configuré.
- [ ] Déclarer les phases disponibles par intersection de configuration, handlers enregistrés et modes moteur supportés. Ne pas annoncer `synthesis` parce qu’elle figure dans `.env.example`, ni B/C/D à partir du seul succès du preview.
- [ ] Figer dans `provenance` à la création l’identité du moteur, SHA des dépendances/poids, politique de preview, sampling et version du normaliseur. Le simple SHA du nom `checkpoint_id` ne constitue pas une empreinte de poids. Répéter les identifiants utiles dans les records et métadonnées de phase.
- [ ] À la continuation et à l’acquisition worker, comparer cette identité au runtime. Refuser un run stub ou de provenance inconnue avec le moteur réel, et un vrai run avec le stub. Les anciens résultats restent consultables ; demander un nouveau run pour changer de moteur/checkpoint.
- [ ] Utiliser des graines dérivées par digest stable pour Python, NumPy, Torch, les joueurs et la RNG Showdown. Remplacer le fallback sur `hash()` de `_parse_seed`. Vérifier le chemin réel de configuration de la graine Showdown sur la version épinglée ; semer seulement Torch ne garantit pas la reproduction du combat.
- [ ] Garder le heartbeat indépendant du subprocess ; propager annulation/perte de bail jusqu’au moteur. Distinguer exception de bail perdu, erreur de contrat, erreur d’infrastructure et rejet de simulation ; ne pas consommer le budget de retries d’une phase pour continuer après annulation.
- [ ] Séparer les timeouts par mode dans `PhaseContext`. Publier réellement chaque checkpoint terminé dans le runner, même en A→D sans pause, avec sa révision et ses métadonnées ; tester l’échec de C laissant A+B persistés. Si un trigger empêche le contrat prévu, isoler et documenter le correctif dans conception par nouvelle migration, sans changer la structure des tables ni réécrire les migrations appliquées.
- [ ] Ajouter `assert_real_battles_eligible(run_provenance, records)` : exige provenance réelle cohérente et traces complètes C/D. Le futur handler E devra l’appeler avant toute requête LLM ; les tests seuls peuvent injecter un connecteur contrôlé. Aucun branchement LLM n’est développé ici.
- [ ] Vérifier les dénominateurs sur données réelles. Notamment, `backSlotMarginals` utilise actuellement `2 × sampleSize` ; le distinguer d’une probabilité de présence par partie prévue dans la spec. Conserver un libellé exact ou corriger ensemble calcul/libellé et tests, sans modifier rétrospectivement les anciens runs.

## Tâche 7 — Diagnostic moteur et recette finale jusqu’à Angular

**Fichiers :** modifier `engine/check.py`, `tests/integration/test_engine_adapter.py`, `README.md`, `.env.example`, `docs/audits/vgc-bench.md`, `docs/recettes/moteur-reel.md`. Si nécessaire, compléter les DTO/lecteurs GraphQL et le bandeau de `pokecoach2-angular/pokecoach-angular/src/app/features/matchup/matchup.ts/html` pour la provenance ; appliquer les skills Angular/design-system.

- [ ] Étendre `engine-check` avec `--our-team`, `--opponent-team` (snapshots JSON validés), `--regulation`, `--seed`, `--modes preview,first_turn,full_battle`, `--output`. Les options doivent être transmises par `devbox run engine-check` ou son équivalent `uv run python -m pokecoach_python.engine.check`. Aucun snapshot vide ni requête DB nécessaire pour ce diagnostic.
- [ ] En mode réel, charger le checkpoint une fois, tester les trois modes et les contraintes D, puis répéter les mêmes requêtes dans un runtime neuf. Comparer choix, événements utiles et résultat, hors identifiants de room, timestamps et métriques. Une reproductibilité non démontrée est un résultat de diagnostic négatif, pas un booléen vrai obtenu seulement sur le lead.
- [ ] Établir une référence CPU séquentielle reproductible ; tester les graines distinctes sans exiger artificiellement des choix différents à chaque partie. Si certaines opérations GPU empêchent l’égalité exacte, documenter et utiliser la référence CPU pour le critère de reproductibilité.
- [ ] Le rapport du diagnostic contient SHA, versions, politique, format, seeds du moteur/Showdown, contraintes demandées et observées, durée/ressources, chemins de traces, et résultat de chaque assertion. Retourner un code non nul si un mode demandé n’est pas réel ou échoue. Conserver le diagnostic stub distinct comme test de câblage.
- [ ] Afficher la provenance depuis les données du **run**, pas depuis le `.env` courant. Les runs stub restent marqués « Données de test — moteur simulé », même si leur source historique vaut `simulation` ; une provenance absente n’est pas présentée comme BC vérifié. Le JSON de rapport v2 et les anciens runs ne sont pas réécrits.
- [ ] Sur une base de recette, lancer un nouveau run réel A→B→C→D et un second parcours avec pauses/continuations. Vérifier via PostGraphile et le frontend les vrais moves, cibles, tera/switch présents, effectifs, provenance et persistance après refresh. Aucun remplacement de move au niveau du template.
- [ ] Exécuter les tests unitaires/protocole, tests runtime, tests PostgreSQL et tests d’intégration moteur réel explicitement activés. Puis `devbox run engine-check`, les recettes smoke et standard B/C/D, et les tests/build Angular uniquement si modifié. Aucun test stub ou test marqué skipped ne vaut validation réelle.
- [ ] Mettre l’audit à jour avec commandes exactes, commits, checkpoint, exemples vérifiés et limites. La preuve de recette doit pouvoir être rejouée par l’utilisateur. Documenter la configuration réelle et le passage obligatoire par un nouveau run ; ne pas éditer son `.env` ni installer/lancer le LLM lors de la simple rédaction de ce plan.

## Critères de fin avant le plan E

1. `vgc_bench` ne délègue plus au stub ; un checkpoint BC réel compatible est chargé et identifié par ses poids.
2. `engine-check` prouve preview, tour 1, combat terminal complet, contraintes des sélections et reproduction des seeds sur l’environnement de référence.
3. B affiche des distributions de choix T1 réels ; les noms correspondent aux capacités des sets, avec exceptions légales explicitement tracées, et les cibles sont vérifiables.
4. C/D conservent de vrais historiques complets avec décisions des deux joueurs et preuve d’issue ; leurs premiers tours alimentent le frontend sans correction par le LLM.
5. Les tables et l’enveloppe v2 restent utilisables ; résultats partiels, snapshots, provenance et distinction des runs stub/réels sont conservés.
6. La sélection d’entrée de E refuse les combats stub, mixtes, incomplets ou de provenance inconnue. E reste limitée au plan global et à la win condition à partir des combats C/D admissibles.

Hors périmètre : amélioration du modèle, fine-tuning, nouvelles analyses métier, collecte de replays, optimisation massive du débit et génération de stratégie par LLM.
