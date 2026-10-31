# API de démonstration et parcours Angular complet — Plan d’implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre au frontend d’appeler FastAPI pour réinstaller la seed complète, puis afficher ses données persistées via PostGraphile.

**Architecture:** Une commande HTTP synchrone appelle une fonction PostgreSQL limitée aux identifiants de démonstration. Après commit, Angular invalide ses données chargées et relit équipes, matchup et rapport via ses services GraphQL existants. Le rapport reste explicitement fictif.

**Tech Stack:** Fondation du plan 1, PostgreSQL/Flyway, FastAPI, SQLModel/psycopg, Angular HttpClient, tests pytest/SQL/Playwright.

**Spec:** Choix explicite de l’utilisateur : **« Réinstaller la seed complète »**. Ce plan utilise la [seed actuelle](../../../pokecoach2-conception/tests/fixtures/demo.sql) et ses [données générées](../../../pokecoach2-conception/tests/fixtures/demo.generated.sql). Le [workflow réel](../specs/2026-10-31-workflow-analyse-matchup.md) constitue un chantier distinct.

## Contraintes et décisions

- Prérequis : [plan d’initialisation](2026-10-31-01-python-initialisation.md) terminé et base migrée.
- Réinstaller les **trois équipes, le matchup et le rapport** de la seed. Ne pas appliquer ce rapport à un matchup arbitraire passé par le client.
- Les UUID de démonstration sont réservés. Leurs données modifiées et l’historique des runs de ce matchup sont remplacés ; les autres équipes et matchups sont conservés.
- Une référence depuis un autre matchup vers une équipe de la seed provoque un conflit et un rollback intégral. Aucune suppression en cascade hors périmètre.
- `source='mock'`, `report_version=1`, `status='succeeded'`, `process_status='SUCCESS'` : rester compatible avec les validateurs SQL et Angular existants.
- L’API reste worker, sans identifiants administrateur ni privilège `DELETE` général. L’installation Flyway n’exécute pas la réinitialisation.
- `ENABLE_DEMO_SEED=false` par défaut. Activer explicitement cette commande dans l’environnement local de démonstration.
- Aucun délai artificiel, LLM ou simulation. La commande teste HTTP → Python → SQL → PostGraphile → Angular, mais pas la progression d’un calcul long.
- Toutes les modifications SQL restent dans conception ; toutes les modifications d’interface restent dans Angular. Ce document est hébergé dans le dépôt Python comme demandé.

## État actuel et choix technique

La seed contient `BEGIN`, des suppressions puis une inclusion `\ir demo.generated.sql`. Ce script psql n’est pas directement exécutable par une session psycopg. De plus, `pokecoach_worker` ne peut actuellement ni créer les équipes ni supprimer les données.

Choix proposé : une fonction SQL `core.reset_demo_dataset()` sans argument, contenant les seules données de la seed, exécutée avec des droits encadrés (`SECURITY DEFINER`). Cela permet de conserver le compte worker. Un appel à `psql` avec le mot de passe administrateur depuis FastAPI élargirait inutilement les pouvoirs de l’API ; réécrire manuellement le rapport en Python ferait diverger les fixtures.

La source des données reste le [générateur Angular](../../../pokecoach2-angular/pokecoach-angular/scripts/generate-demo-seed.mts) et les fixtures qu’il importe. Produire un manifeste JSON commun pour générer les artefacts SQL sans parser du SQL dans Python. Les migrations déjà appliquées sont immuables ; une nouvelle version de fixture déployée passe par une nouvelle migration.

## Contrat HTTP

`POST /api-python/demo/seed`, corps JSON `{}` obligatoire, aucun paramètre de matchup ni données SQL. Champs supplémentaires rejetés avec 422. Réponse 200 **après commit** :

```json
{
  "source": "mock",
  "fixtureVersion": 1,
  "ownedTeamIds": [
    "a1111111-1111-4111-8111-111111111101",
    "a1111111-1111-4111-8111-111111111102"
  ],
  "opponentTeamId": "b2222222-2222-4222-8222-222222222201",
  "matchupId": "c3333333-3333-4333-8333-333333333301",
  "runId": "<UUID du run nouvellement créé>",
  "counts": { "teams": 3, "matchups": 1, "runs": 1 }
}
```

Les compteurs portent sur les lignes réinstallées, pas sur toute la base. Deux appels successifs gardent ces cardinalités ; le `runId` peut changer. Aucun rapport complet n’est renvoyé par cette route.

| Code | Situation | Code applicatif |
| --- | --- | --- |
| 404 | Commande désactivée | `DEMO_DISABLED` |
| 409 | Autre réinstallation en cours | `DEMO_BUSY` |
| 409 | Équipe de la seed référencée ailleurs | `DEMO_REFERENCED` |
| 503 | PostgreSQL indisponible | `DATABASE_UNAVAILABLE` |
| 500 | Erreur interne / déploiement incomplet | `DEMO_RESET_FAILED` |

Erreurs JSON `{ "detail": { "code": "...", "message": "..." } }`, sans SQL ni secret. Les erreurs de validation 422 suivent le format FastAPI standard.

## Points de revue

| Cas | Résultat attendu | Tâche |
| --- | --- | --- |
| Double clic ou appels concurrents | Bouton bloqué ; conflit SQL contrôlé | 2, 4 |
| Autres équipes / références vers la seed | Préservation ou rollback intégral | 2 |
| Réponse HTTP perdue après commit | Relire GraphQL, pas de retry POST automatique | 3, 4 |
| Rapport incompatible avec les snapshots | Transaction annulée, aucune moitié de seed | 1, 2 |
| Réponse GraphQL ancienne reçue après reset | Cache invalidé et réponse obsolète ignorée | 4 |

## Tâche 1 — Partager la fixture sans dupliquer le rapport

**Fichiers :** modifier `pokecoach2-angular/pokecoach-angular/scripts/generate-demo-seed.mts` et son `package.json` ; créer `pokecoach2-conception/tests/fixtures/demo.manifest.json`, `pokecoach2-conception/scripts/generate-demo-reset.mjs` et `pokecoach2-conception/tests/demo-generation.test.mjs`. Conserver `tests/fixtures/demo.generated.sql` comme sortie du générateur existant.

**Interface :** manifeste versionné `{fixtureVersion, teams, matchup, run}` : trois équipes complètes avec les UUID ci-dessus ; un matchup avec les deux UUID de ses équipes ; un run avec `source`, `reportVersion`, `report`, `finishedAt`, `provenance`. Reprendre les champs, valeurs et dates de la seed actuelle. Les snapshots sont créés par les triggers SQL.

- [ ] Modifier le générateur Angular pour construire une seule représentation des données, puis émettre le SQL historique et le manifeste JSON. Fixer des séparateurs SQL déterministes et non présents dans le contenu, sans tirage aléatoire.
- [ ] Ajouter un mode `--check` sans écriture pour comparer les sorties attendues aux artefacts versionnés. Déclarer `tsx` dans les dépendances de développement Angular et éviter le téléchargement implicite par `npx --yes`.
- [ ] Écrire le test de génération : UUID attendus, deux équipes `owned`, une `opponent`, six slots par équipe, rapport identique à celui généré pour les mêmes équipes, génération reproductible.
- [ ] Ajouter `generate-demo-reset.mjs <manifest> <output>` : produire le corps de fonction et les instructions SQL de la tâche 2 à partir du manifeste. Refuser d’écraser un fichier existant ; ne jamais modifier automatiquement une ancienne migration.
- [ ] Vérifier la parité manifeste/SQL et exécuter `node --test tests/demo-generation.test.mjs` dans conception. Les tests métier de validation du rapport restent ceux déjà présents côté Angular/SQL.

## Tâche 2 — Commande SQL atomique et droits limités

**Fichiers conception :** créer `modules/1.0-core/sql/core/V1.0.8__add_demo_reset_function.sql` et son profil `_repoindex.md`, `tests/sql/040_demo_reset.sql` ; modifier `modules/1.0-core/sql/afterMigrate.sql` pour les grants et `docs/data-contract.md`. **Si V1.0.8 est occupée à l’exécution, prendre la prochaine version libre.**

**Interface :** `core.reset_demo_dataset() RETURNS jsonb` renvoie les champs du contrat HTTP. Exceptions métier : SQLSTATE `PDC01` pour référence externe, `PDC02` pour reset concurrent.

- [ ] Écrire des tests SQL en tant que worker : reset sur base vide, reset répété, conservation d’une équipe et d’un matchup hors seed, conflit de référence externe avec conservation de toutes les anciennes lignes.
- [ ] Générer et relire la migration : fonction `SECURITY DEFINER` possédée par le rôle de migration, objets qualifiés `core.*`, `SET search_path = pg_catalog, pg_temp`, aucun SQL dynamique ni argument utilisateur ; `REVOKE ALL ... FROM PUBLIC` puis `GRANT EXECUTE ... TO pokecoach_worker`. Masquer la fonction dans PostGraphile (`@omit`) et vérifier que `authenticated_user` ne peut pas l’exécuter. Suivre les [règles PostgreSQL pour SECURITY DEFINER](https://www.postgresql.org/docs/17/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY).
- [ ] Dans la fonction, acquérir `pg_try_advisory_xact_lock(742031, 1)` ; échouer avec `PDC02` si occupé. Verrouiller les lignes de seed existantes dans un ordre stable ; vérifier les références depuis tous les autres matchups, même archivés.
- [ ] Supprimer seulement les runs du matchup réservé, ce matchup, puis les trois équipes réservées. Recréer les trois équipes, le matchup et un run réussi contenant le rapport intégral. Laisser les triggers de snapshots et d’intégrité actifs ; récupérer l’UUID du run avec `RETURNING`.
- [ ] Laisser la transaction à l’appelant ; aucune instruction `COMMIT` ni inclusion psql dans la fonction. Une erreur de rapport, de droits ou de FK doit annuler la totalité. Mapper aussi un conflit FK concurrent identifié vers le conflit métier, sans masquer les autres violations d’intégrité.
- [ ] Vérifier par tests que le worker ne peut toujours pas supprimer directement une équipe, que le rôle GraphQL ne peut pas appeler la fonction et qu’une panne injectée pendant la réinstallation restaure l’état précédent.
- [ ] Tester deux connexions concurrentes et vérifier un résultat contrôlé ; exécuter `./scripts/test-db.sh` sur la base jetable. Documenter la réservation des UUID et le remplacement de l’historique de démonstration.

La fonction est volontairement limitée à un jeu de données fixe. Ne pas créer un endpoint d’exécution SQL ou une fonction acceptant arbitrairement des équipes à supprimer.

## Tâche 3 — Route FastAPI et transaction

**Fichiers Python :** créer `src/pokecoach_python/api/demo.py`, `schemas/demo.py`, `services/demo_seed.py`, `tests/unit/test_demo_api.py`, `tests/integration/test_demo_seed.py` ; modifier `main.py`, `.env.example` et `README.md`.

**Interfaces :** `DemoSeedRequest` (aucun champ, extras interdits), `DemoSeedResponse` (contrat ci-dessus), `reset_demo_seed(session: Session) -> DemoSeedResponse`. La route est une fonction synchrone, utilisant la session du plan 1.

- [ ] Écrire les tests HTTP : 404 si désactivé sans appel DB, 422 pour corps invalide, réponse 200 conforme, mapping 409/503/500 et absence de secret.
- [ ] Implémenter le service avec `with session.begin()` et `SELECT core.reset_demo_dataset()` ; valider la réponse SQL dans le modèle de sortie avant le commit. Sortir du bloc transactionnel avant de retourner le résultat HTTP.
- [ ] Ajouter le routeur sous `/api-python/demo`, conditionner l’exécution à `ENABLE_DEMO_SEED`, et traduire les SQLSTATE métier connus. Ne pas traiter toute exception SQL comme un conflit utilisateur.
- [ ] Exécuter `uv run pytest tests/unit/test_demo_api.py -q`, puis le test d’intégration contre une base jetable réellement migrée avec le compte worker. Contrôler le rapport via une nouvelle connexion, donc après commit.
- [ ] Tester un échec pendant la transaction et un commit échoué : jamais de 200, état antérieur préservé si la transaction n’a pas été validée. Documenter qu’une perte réseau après commit laisse un résultat incertain pour le client.
- [ ] Documenter l’appel local `curl --fail-with-body -X POST http://127.0.0.1:8042/api-python/demo/seed -H 'Content-Type: application/json' -d '{}'` et l’activation locale explicite. Aucun retry automatique de cette commande destructive.

## Tâche 4 — Appel Angular et relecture via PostGraphile

**Fichiers Angular**, relatifs à `pokecoach2-angular/pokecoach-angular` : créer `src/app/core/python/demo-api.ts`, `demo-api.spec.ts`, `src/app/features/developer/demo-data.ts`, `demo-data.html`, `demo-data.spec.ts`, `src/app/core/data/coach-store.spec.ts`. Modifier `src/app/app.routes.ts`, `src/app/features/home/home.ts`, `home.html`, `src/app/core/data/coach-store.ts`, `src/proxy.conf.json`.

**Interfaces :** `DemoApi.resetSeed(): Observable<DemoSeedResponse>` ; `CoachStore.invalidateAll(): void` annule les requêtes, incrémente leurs générations et vide les ressources. Réutiliser ce mécanisme dans `resetForTests()`.

- [ ] Lire les skills Angular et design-system référencées par `agent.md`. Ajouter une route de développement `/developer/demo-data` et un accès discret depuis l’accueil en mode développement, comme le mécanisme existant de page design-system.
- [ ] Créer l’action **« Réinstaller la démonstration »**, avec texte indiquant le remplacement des équipes de démonstration et de leurs résultats. Demander confirmation dans l’interface avant le POST ; conserver un état de chargement et bloquer les doubles clics.
- [ ] Implémenter `DemoApi` avec HttpClient, URL relative `/api-python/demo/seed`, corps `{}`, réponse typée et validation minimale des UUID/champs avant navigation. Aucun import des fixtures dans le code runtime.
- [ ] Après succès, appeler `invalidateAll()`, puis `loadTeams()` et naviguer vers `/teams/{ownedTeamIds[0]}/matchups/{matchupId}`. La page existante charge équipe et matchup via GraphQL ; conserver les trois onglets et l’indication de données fictives.
- [ ] En cas de 409, afficher la cause utile. En cas d’incertitude réseau, proposer d’actualiser les données via GraphQL avant de relancer explicitement. Si la relecture GraphQL échoue après un POST réussi, réessayer la lecture seule.
- [ ] Ajouter les tests : unique POST, aucun rapport injecté directement depuis sa réponse, invalidation des requêtes en cours, navigation après commit, erreur lisible et récupération après panne GraphQL. Une réponse d’ancienne génération ne doit pas restaurer l’ancien run.
- [ ] Ajouter `/api-python` au proxy Angular vers `http://127.0.0.1:8042`, sans retirer le préfixe. Vérifier `npm test -- --watch=false`, `npm run lint` et `npm run build`.

Le bouton de création de matchup existant conserve son rôle : enregistrer les équipes et le matchup. La commande de démonstration possède son entrée explicite, puisqu’elle réinstalle un scénario fixe. Le lancement d’une analyse sur le matchup sélectionné appartient au workflow réel.

## Tâche 5 — Proxy Docker et validation du parcours réel

**Fichiers conception :** modifier `docker/nginx.conf`, `deployment/local/compose.python.yml`, `deployment/local/.env.python.example`. **Fichiers Angular :** créer `e2e/demo-seed-live.spec.ts`, ajouter le script `e2e:demo-live` au `package.json`. Compléter `pokecoach2-python/README.md`.

- [ ] Ajouter au proxy Nginx `/api-python/` vers `api-python:8000`, préfixe conservé. Comme l’API est optionnelle, utiliser la résolution DNS Docker à la requête (`resolver 127.0.0.11` et cible variable avec URI d’origine), pour que Nginx démarre aussi sans le service Python. Tester les deux configurations.
- [ ] Permettre l’activation explicite `ENABLE_DEMO_SEED=true` dans l’environnement de l’overlay Python. Le flag API reste l’autorité ; le masquage du bouton Angular n’est pas une protection du backend.
- [ ] Écrire le scénario Playwright sur une stack de test isolée : lancer la commande depuis la page dev, vérifier une requête HTTP réelle, deux équipes possédées visibles sur l’accueil, une équipe sans matchup, et les trois onglets remplis pour l’autre équipe.
- [ ] Recharger la page et vérifier la persistance ; relancer la seed et vérifier l’absence de doublons. Conserver une équipe témoin hors seed. Arrêter l’API de test pour vérifier le message d’échec et sa récupération.
- [ ] Exécuter les tests SQL, Python, Angular puis `npm run e2e:demo-live`. Ne pas intercepter les appels FastAPI/PostGraphile dans ce test de parcours ; les images Pokémon peuvent être stabilisées indépendamment.
- [ ] Vérifier aussi le proxy Nginx avec un POST réel sur une stack jetable, y compris si le build Angular de production masque la page dev. Documenter les commandes, ports, UUID réservés, limites et résultats de vérification.

## Critères de fin

L’action du frontend réinstalle atomiquement la seed complète par FastAPI ; les données affichées viennent de PostGraphile et persistent après rechargement. Les autres données sont conservées, les erreurs sont récupérables et le rapport reste identifié comme démonstration. Aucun calcul VGC-Bench n’est annoncé comme réalisé.
