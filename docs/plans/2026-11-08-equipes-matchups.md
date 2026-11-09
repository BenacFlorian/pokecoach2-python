# Plan d'implémentation — analyses après suppression d'une équipe

> **Pour Composer / agent exécutant :** utiliser `superpowers:executing-plans` si disponible, tâche par tâche, et `superpowers:verification-before-completion` avant de conclure. Les cases servent au suivi de l'implémentation.

**Objectif :** permettre de supprimer une équipe pendant une analyse sans travail qui continue inutilement, publication tardive ou erreur serveur trompeuse.

**Architecture :** la suppression reste une mutation SQL/PostGraphile. Python constate qu'un run ou son droit d'exécution n'existe plus, abandonne coopérativement, ferme son moteur et libère le worker. Les transactions d'écriture conservent leurs contrôles de lease et de révision.

**Stack :** Python, FastAPI, SQLModel/SQLAlchemy, worker à threads, adaptateur VGC-Bench, pytest, Ruff.

**Spécification :** [README commun](../../../README-refonte-equipes-matchups.md). Étape 2, après le [plan conception](../../../pokecoach2-conception/docs/plans/2026-11-08-equipes-matchups.md), avant Angular. Les noms de fichiers gardent la date de début du chantier, le 8 novembre 2026.

## Contraintes globales

- Ne créer ni endpoint de gestion d'équipe ni deuxième implémentation de la cascade. Ne pas accorder DELETE à `pokecoach_worker`.
- Ne changer ni l'algorithme d'analyse, ni les budgets, seeds, phases, contrats de résultat, modèle ou checkpoint partagé.
- Une suppression n'est pas une nouvelle analyse `failed` à enregistrer : la ligne n'existe plus. Ne jamais la recréer pour journaliser l'arrêt.
- Un appel moteur/LLM déjà en cours peut finir ou atteindre son timeout configuré ; ensuite, aucun nouvel appel, retry, combat ou résultat ne doit être produit pour le run disparu.
- Les tests utilisent moteur stub/fixture, faux client de synthèse et base dédiée. Aucun GPU, training ou appel LLM payant n'est nécessaire.

## Points de revue

1. Suppression après contrôle de lease mais avant INSERT : pas de combat orphelin ni exception générique absorbée comme simple simulation ratée.
2. Suppression pendant un appel moteur : après son retour, aucune nouvelle tentative de simulation.
3. Suppression pendant la synthèse : pas de deuxième appel fournisseur ni publication tardive.
4. Heartbeat perdu : pas de claim du run suivant pendant que le thread précédent calcule encore.
5. Suppression concurrente au POST start/continue/cancel : HTTP 404 pertinent, vrais conflits 409 et indisponibilités 503 conservés.

## État actuel et fichiers concernés

| Fichier sous `src/pokecoach_python/` | Constat / responsabilité |
| --- | --- |
| `worker.py` | Heartbeat toutes les 10 s ; après sa perte, `join(timeout=5)` peut laisser un thread actif puis reprendre la file. |
| `workflow/runner.py` | Détecte certaines pertes de lease via la progression ; toutes les exceptions passent aujourd'hui par le chemin d'échec. |
| `workflow/types.py` | `PhaseContext` transmet les callbacks et adaptateurs aux phases. |
| `workflow/phases/phase_a.py` à `phase_e.py` | Appels moteur, retries et synthèse ; plusieurs `except Exception` doivent laisser passer l'arrêt coopératif. |
| `db/analysis_repository.py` | Leases, commandes, publications et combats. `is_cancelled()` retourne faux si le run est absent ; certaines publications utilisent `.one()`. |
| `services/analysis_commands.py` | Préflight puis création du run ; disparition concurrente susceptible d'être transformée en 503. |
| `llm/client.py` | `StrategyClient.generate()` possède sa propre deuxième tentative sur erreur transitoire. |
| `engine/subprocess_client.py` | Les appels ont des délais et un nettoyage ; conserver un seul thread propriétaire du client. |

Les sources de synthèse sont stockées dans `matchup_runs.execution_metadata`, pas dans une table supplémentaire. Elles disparaissent avec le run. Ne pas inventer un nettoyage de fichiers ou une autre table de sources.

## Tâche 1 — erreurs métier et garde d'exécution

**Créer :** `src/pokecoach_python/core/analysis_errors.py`, `tests/unit/test_run_lifecycle.py`. **Modifier :** `db/analysis_repository.py`.

**Interfaces à produire :**

```python
class RunExecutionStopped(Exception):
    # reason: missing_run | lease_lost | cancelled | supervisor_stop
    ...

class AnalysisTargetNotFound(Exception):
    # resource: matchup | run ; resource_id: UUID
    ...

# Méthode d'AnalysisRepository
def ensure_run_active(self, run_id: UUID, token: UUID) -> None: ...
```

- [ ] Écrire les tests `test_missing_run_stops_execution`, `test_wrong_or_expired_lease_stops_execution`, `test_cancelled_run_stops_execution`, `test_running_owned_lease_is_allowed`. Utiliser les types UUID actuels, pas une nouvelle représentation.
- [ ] Faire échouer ces tests avant d'ajouter les interfaces. Implémenter `ensure_run_active` par une lecture courte : ligne présente, statut running, token correspondant, `lease_expires_at > now()` selon l'horloge PostgreSQL.
- [ ] Lever `RunExecutionStopped` pour absence, annulation ou lease invalide ; laisser remonter une vraie erreur de connexion SQL. Aucun verrou ni transaction ne reste ouvert durant le calcul.
- [ ] Garder `is_cancelled` pour ses appelants existants si nécessaire ; ne plus l'utiliser comme preuve que le run existe encore.
- [ ] Utiliser une exception dérivée directement d'`Exception`, pas de `BaseException`, `ValueError` ou `RuntimeError`, afin d'éviter de la confondre avec une donnée invalide ou un problème moteur.
- [ ] Exécuter `uv run pytest tests/unit/test_run_lifecycle.py -q` : tous les cas passent, notamment une vraie erreur SQL qui n'est pas transformée en arrêt normal.

## Tâche 2 — écritures atomiques face à la suppression

**Modifier :** `db/analysis_repository.py`. **Créer :** `tests/integration/test_team_deletion.py` ; réutiliser les fixtures SQL valides existantes.

- [ ] Tester une suppression entre deux opérations du worker : `update_progress`, `insert_battle`, `publish_phase`, `publish_complete`, `pause_for_implementation`, écriture/suppression de sources de synthèse. Aucune ne recrée un run.
- [ ] Dans `insert_battle`, verrouiller le run au sein de la transaction qui valide la lease puis insère le combat, par `SELECT ... FOR UPDATE`. La suppression attend la fin de cette courte transaction, ou l'insertion constate l'absence et lève `RunExecutionStopped`.
- [ ] Remplacer les `.one()` des chemins concernés par une lecture qui distingue l'absence : absence ou lease perdue → `RunExecutionStopped`. Révision incorrecte, contenu incohérent et doublon de combat avec hash différent restent de vraies erreurs.
- [ ] Préserver les booléens existants de `heartbeat` et `update_progress`. Le runner convertira `False` en arrêt coopératif ; ne pas casser silencieusement tous leurs appelants.
- [ ] Vérifier aussi `_write_synthesis_sources` et `delete_synthesis_sources`. Les écritures restent conditionnées au run et au token, sans UPSERT de run.
- [ ] Ne pas appeler `ensure_run_active` **après** une publication qui a volontairement passé le run à paused/succeeded : ce changement de statut est une réussite normale. Avant publication, le contrôle transactionnel fait foi.
- [ ] Conserver `fail_run` sans effet si le run a disparu ou n'appartient plus au token ; une erreur métier encore valide doit toujours être journalisée/traitée comme auparavant.
- [ ] Test à deux connexions avec barrières : INSERT combat commencé puis suppression, et suppression commencée puis INSERT. Après commit de la suppression, aucune ligne liée ne subsiste ; pas de test basé sur des `sleep` arbitraires.
- [ ] Lancer `uv run pytest tests/integration/test_team_deletion.py -q` avec la base de test migrée. Un test ignoré parce que `TEST_DATABASE_URL` manque n'est pas une validation de concurrence.

## Tâche 3 — arrêt coopératif dans le runner et les phases

**Modifier :** `workflow/runner.py`, `workflow/types.py`, `workflow/phases/phase_a.py`, `phase_b.py`, `phase_c.py`, `phase_d.py`, `phase_e.py`, `llm/client.py`. **Tests :** `tests/unit/test_run_lifecycle.py` et les tests des phases/client existants.

**Interfaces :**

```python
WorkflowRunner.run_claimed(claim: ClaimedRun, *, stop_event: Event | None = None) -> None
# Champ supplémentaire de PhaseContext, à la fin des champs existants :
ensure_active: Callable[[], None]  # valeur par défaut : fonction sans effet
# Argument optionnel de StrategyClient.__init__, après chat_factory :
ensure_active: Callable[[], None] | None = None
```

- [ ] Dans `run_claimed`, construire une garde : si l'Event est positionné, lever `RunExecutionStopped`; sinon appeler `repo.ensure_run_active(run_id, token)`. Conserver la compatibilité des appels existants sans Event.
- [ ] Faire un premier contrôle avant de construire/démarrer le moteur, puis transmettre la garde au `PhaseContext`. Construction du moteur, exécution et fermeture doivent être dans un cycle try/finally qui ferme exactement une fois un moteur effectivement créé.
- [ ] Contrôler avant chaque phase, avant/après chaque appel coûteux moteur et au début de chaque retry. Contrôler aussi avant une publication ou une écriture de combat. Le contrôle transactionnel du repository reste indispensable, car une suppression peut survenir juste après la garde.
- [ ] Ajouter `except RunExecutionStopped: raise` **avant** les captures larges des phases A/B/C/D/E et des boucles de retries. Ne pas compter une suppression comme échantillon technique raté et poursuivre le budget.
- [ ] Dans le callback progress, convertir un `update_progress` faux en `RunExecutionStopped`; ne pas tenter ensuite une publication normale.
- [ ] Dans le runner, intercepter séparément `RunExecutionStopped`, journaliser run_id et raison à niveau INFO, puis sortir. Ne pas appeler `fail_run` pour cet arrêt attendu. Les autres exceptions conservent le traitement d'échec existant.
- [ ] Pour la phase E, transmettre la garde au `StrategyClient` créé par défaut. Dans `generate`, contrôler avant chaque tentative, après `llm.invoke`, et avant d'envisager une nouvelle tentative. L'arrêt doit traverser le graph et remonter sans changer les schémas de sortie ni les prompts.
- [ ] Préserver les doubles de test injectés via `context.synthesis_client`. Entourer l'appel de synthèse dans la phase E de contrôles avant/après ; les tests du vrai `StrategyClient` vérifient sa boucle interne.
- [ ] Respecter les timeouts existants moteur/LLM. Ne pas appeler `close()` sur le même client depuis le thread superviseur pendant que le thread de calcul utilise le protocole JSONL.
- [ ] Tests : run supprimé avant construction (0 moteur créé), pendant preview/full_battle (pas d'appel suivant), avant INSERT (0 publication), pendant LLM avec erreur transitoire (pas de seconde tentative), fermeture une fois même en erreur.
- [ ] Test de non-régression : analyse complète et pause réussies ne sont pas transformées en arrêt de lease après leur publication ; une vraie erreur de simulation continue à suivre la politique existante.
- [ ] Lancer `uv run pytest tests/unit -q` après les tests ciblés. Examiner toute capture large qui pourrait masquer `RunExecutionStopped`.

## Tâche 4 — superviseur : ne jamais abandonner un thread encore actif

**Modifier :** `worker.py`. **Créer :** `tests/unit/test_worker_supervisor.py`.

- [ ] Extraire au besoin la gestion d'un claim dans `_process_claim(claim: ClaimedRun) -> None` pour la tester sans lancer une boucle infinie ni installer des signaux dans un thread de test.
- [ ] Créer un `stop_event` distinct du `done` pour chaque claim, le passer à `run_claimed`, et capturer les références runner/claim dans la fonction du thread. Ne pas laisser le thread utiliser un futur `self._runner` réassigné.
- [ ] Si heartbeat retourne faux alors que le thread n'a pas fini, positionner le stop_event. Même chose à l'arrêt du superviseur. Attendre réellement la fin du thread avec des attentes courtes ; `join(timeout=5)` ne doit plus autoriser un nouveau claim si `is_alive()` est vrai.
- [ ] Ne vider `_active` et ne passer au run suivant qu'après fin du thread et fermeture du moteur. Un appel en cours reste borné par son timeout existant, augmenté du nettoyage ; documenter ce délai plutôt que promettre un arrêt instantané.
- [ ] Une perte de heartbeat pour un run qui vient de terminer/pauser normalement n'est pas une erreur bruyante. Une erreur de connexion de heartbeat doit être journalisée et traitée sans lancer un deuxième calcul concurrent au premier.
- [ ] Tester avec Events/barrières : run A bloqué dans le faux moteur, heartbeat perdu, stop_event positionné, aucun claim B tant que A n'est pas libéré, puis B traité normalement.
- [ ] Tester arrêt du superviseur, run absent dès le départ, fin normale et exception réelle du runner. Vérifier qu'aucun thread de test ne reste vivant.
- [ ] Lancer `uv run pytest tests/unit/test_worker_supervisor.py tests/unit/test_run_lifecycle.py -q`.

Cette tâche ne remplace pas la politique existante d'expiration de lease. Elle empêche simplement le superviseur de prétendre être libre alors que son calcul précédent tourne encore.

## Tâche 5 — démarrage et commandes sur une ressource disparue

**Modifier :** `db/analysis_repository.py`, `services/analysis_commands.py`. **Tests :** `tests/unit/test_analysis_commands.py`, `tests/integration/test_team_deletion.py`.

- [ ] Ajouter un test où le matchup existe lors du préflight, puis disparaît avant `record_start_command` : HTTP 404 `MATCHUP_NOT_FOUND`, aucune commande orpheline.
- [ ] Dans la transaction de `record_start_command`, laisser le nouveau trigger SQL SECURITY DEFINER prendre les verrous **owned → opponent → matchup** pendant l'INSERT. Ne pas pré-verrouiller le matchup et ne pas exécuter de `FOR SHARE` sur les équipes avec le rôle worker : il n'a pas le droit UPDATE sur `teams` nécessaire à ce verrouillage. Insérer run et commande dans la même transaction courte, sans élargir les droits du worker.
- [ ] Le plan conception réserve SQLSTATE `P0002` à la disparition d'une ressource requise dans ce trigger. Intercepter ce code sur l'INSERT du run, après rollback de la transaction, et le traduire en `AnalysisTargetNotFound('matchup', matchup_id)`. Une lecture préalable peut détecter l'absence tôt, mais ne remplace pas ce contrôle concurrent du trigger.
- [ ] Le préflight moteur reste hors transaction verrouillée. Ne pas conserver une connexion en `FOR SHARE` pendant une simulation.
- [ ] Adapter le service pour traduire cette exception précise en 404. Ne pas convertir tous les `DBAPIError`, erreurs de validation ou timeouts de base en 404.
- [ ] Tester aussi la disparition après commit mais avant construction de la réponse : réponse 404 cohérente si le run a déjà disparu, sans `NoResultFound` non géré. Si le 202 est parti avant suppression, le prochain GET peut normalement constater l'absence.
- [ ] Vérifier les chemins `continue_analysis`, `cancel_analysis` et la relecture d'une commande idempotente : si le run n'existe plus, 404 `RUN_NOT_FOUND`, aucun rétablissement d'un ancien run.
- [ ] Après cascade, une ancienne clé d'idempotence peut ne plus exister. Rejouer start sur le matchup supprimé doit rester 404, pas recréer un matchup ou un run.
- [ ] Préserver les conflits existants : même clé utilisée pour un autre contenu, run déjà actif, phase incompatible. Les exceptions SQLSTATE de concurrence restent des erreurs réessayables si elles ne correspondent pas à une ressource réellement absente.
- [ ] Test SQL à deux connexions : démarrage ayant pris les verrous avant suppression → la suppression attend puis supprime tout ; suppression gagnante → démarrage refusé proprement. Pas de verrou permanent ni cascade partielle.
- [ ] Lancer `uv run pytest tests/unit/test_analysis_commands.py tests/integration/test_team_deletion.py -q` sur l'environnement de test.

## Tâche 6 — validation et transmission

Depuis la racine de `pokecoach2-python` :

```bash
uv run ruff check .
uv run pytest tests/unit -q
uv run pytest tests/integration/test_team_deletion.py -q
uv run pytest tests/integration/test_database.py tests/integration/test_phase_c_run.py tests/integration/test_phase_d_run.py tests/integration/test_synthesis_sources_store.py -q
```

Pour les tests SQL, configurer `TEST_DATABASE_URL` vers une base explicitement dédiée (`*_test`) et les credentials des rôles de test suivant les fixtures existantes. La connexion de suppression utilise le rôle autorisé à appeler la fonction, celle du worker reste `pokecoach_worker`. Ne pas élargir les droits du worker pour faciliter les tests.

- [ ] Compléter `tests/integration/test_team_deletion.py` avec le scénario entier : claim A, calcul suspendu par barrière, suppression GraphQL/SQL de A, reprise du faux appel, abandon propre, puis analyse de B fonctionnelle.
- [ ] Vérifier que fichiers modèle/checkpoint et données de B sont inchangés.
- [ ] Documenter la borne d'arrêt : prochaine garde après l'appel en cours, timeouts configurés et fermeture du moteur. Conserver les logs d'arrêt à niveau INFO, sans traceback pour la suppression attendue.
- [ ] Dans le compte rendu, distinguer unitaires exécutés, tests SQL exécutés, et tests ignorés faute d'environnement. Transmettre à Angular les codes métier effectivement utilisés.

**Critère de fin :** la suppression de l'équipe réussit dans tous les statuts de run ; un calcul déjà en cours s'arrête sans nouvelle publication et ne bloque pas durablement les analyses des équipes restantes.
