# Initialisation du backend Python — Plan d’implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Démarrer une API FastAPI avec Devbox et uv, connectée au PostgreSQL existant, utilisable sur l’hôte et dans la stack Docker.

**Architecture:** Angular continue à lire les données métier via PostGraphile. FastAPI portera les commandes et traitements Python et accèdera directement à PostgreSQL avec le rôle `pokecoach_worker`. Flyway reste responsable du schéma dans `pokecoach2-conception`.

**Tech Stack:** Python 3.13, uv, Devbox, FastAPI, Uvicorn, pydantic-settings, SQLModel/SQLAlchemy, psycopg 3, pytest, HTTPX, Ruff.

**Spec:** Demande utilisateur du 31 octobre 2026 : initialisation inspirée de PerfAO ; [frontières du futur workflow](../specs/2026-10-31-workflow-analyse-matchup.md). Ce plan ne réalise pas les simulations.

## Contraintes et décisions

- Projet Python directement à la racine de `pokecoach2-python`, package `src/pokecoach_python`. Pas de second dossier `pokecoach2-python` imbriqué.
- Reprendre de PerfAO le couple Devbox/uv, les responsabilités `main`, `api`, `db`, la session par requête et le cycle de vie FastAPI. Ne pas copier ses dépendances documentaires, MinIO, Socket.IO ou ses services IA.
- Python 3.13 pour cette fondation, comme PerfAO. Épingler la version corrective effectivement installée ; la compatibilité future avec VGC-Bench/PyTorch fera l’objet d’un audit séparé.
- `uv.lock` et `devbox.lock` versionnés. Résoudre les versions compatibles à l’implémentation, puis les verrouiller ; ne pas recopier aveuglément les versions de PerfAO.
- Aucun `SQLModel.metadata.create_all()`, Alembic ou appel automatique à Flyway au démarrage de l’API.
- Aucun accès administrateur PostgreSQL dans le processus FastAPI. Ne pas publier les secrets dans les logs, réponses HTTP ou fichiers versionnés.
- Pas encore de LangGraph, LLM, VGC-Bench, scraper, entraînement ni serveur Showdown.

## Points de revue

| Cas | Comportement attendu | Vérification |
| --- | --- | --- |
| Mot de passe avec caractères réservés | Connexion sans concaténation incorrecte d’URL | Tâche 1 |
| PostgreSQL absent au démarrage | Échec explicite et borné du démarrage | Tâche 2 |
| PostgreSQL tombe après démarrage | Santé HTTP 503 sans fuite de configuration | Tâche 2 |
| Requêtes concurrentes / exception SQL | Sessions isolées, rollback et fermeture | Tâche 2 |
| Exécution hôte puis Docker | Bon hôte DB, bon port et même package verrouillé | Tâche 3 |

## Références inspectées

Exemple local : `/home/webinage/Documents/RD/PerfAO/workspace/perfao-python` : `devbox.json`, `Dockerfile`, `perfao-python/pyproject.toml`, `perfao-python/src/perfao_python/main.py` et `db/session.py`.

Intégration existante : [extension Compose Python](../../../pokecoach2-conception/deployment/local/compose.python.yml), [script de lancement](../../../pokecoach2-conception/scripts/compose-python.sh), [droits SQL](../../../pokecoach2-conception/modules/1.0-core/sql/afterMigrate.sql).

Les connexions sont gérées par le pool SQLAlchemy ; ne pas ajouter un second pool psycopg. Construire le DSN avec [SQLAlchemy URL.create](https://docs.sqlalchemy.org/en/20/core/engines.html#creating-urls-programmatically). Utiliser le [lifespan FastAPI](https://fastapi.tiangolo.com/advanced/events/) pour ouvrir et libérer les ressources.

## Arborescence cible

Tous les chemins ci-dessous sont relatifs à `pokecoach2-python`, sauf mention contraire.

```text
pyproject.toml / uv.lock / .python-version
devbox.json / devbox.lock
.env.example / .gitignore / .dockerignore
Dockerfile / README.md
src/pokecoach_python/
  __init__.py
  main.py                 # factory FastAPI et lifespan
  core/config.py          # configuration typée
  db/session.py           # moteur, sessions, contrôle de connexion
  api/health.py           # santé de l’API et de PostgreSQL
tests/
  conftest.py
  unit/test_config.py
  unit/test_health.py
  integration/test_database.py
```

Ajouter les `__init__.py` des sous-packages. Aucun modèle métier dupliqué n’est nécessaire pour ce premier jalon.

## Tâche 1 — Package, environnement reproductible et configuration

**Fichiers :** créer `pyproject.toml`, `uv.lock`, `.python-version`, `devbox.json`, `devbox.lock`, `.gitignore`, `.env.example`, `src/pokecoach_python/core/config.py`, `tests/unit/test_config.py`.

**Interfaces :** `Settings` lit les variables ci-dessous ; `build_database_url(settings: Settings) -> sqlalchemy.URL` produit une URL `postgresql+psycopg`.

| Variable | Valeur locale / règle |
| --- | --- |
| `APP_ENV` | `local` sur l’hôte, `container` dans Compose |
| `POSTGRES_HOST` | `127.0.0.1` sur l’hôte ; `postgres` dans Compose |
| `POSTGRES_PORT` | `5442` sur l’hôte ; `5432` dans Compose |
| `POSTGRES_DB` | `pokecoach2` |
| `POSTGRES_USER` | `pokecoach_worker` |
| `POSTGRES_PASSWORD` | Obligatoire, secret ; valeur locale correspondant à `WORKER_DB_PASSWORD` de conception |
| `DB_CONNECT_TIMEOUT_SECONDS` | `5` |
| `ENABLE_DEMO_SEED` | `false`, exploité par le plan suivant |

- [ ] Initialiser avec uv le package `pokecoach-python` et le backend de build `uv_build`. Ajouter FastAPI, Uvicorn, pydantic-settings, SQLModel et `psycopg[binary]` ; déclarer SQLAlchemy explicitement si import direct. Mettre pytest, HTTPX et Ruff dans le groupe `dev`.
- [ ] Configurer Devbox pour fournir uv ; laisser uv gérer Python à partir de `.python-version`. Verrouiller les deux environnements et exclure `.env`, `.venv`, `.devbox`, caches et artefacts de build de Git.
- [ ] Écrire `test_config.py` : port hors plage rejeté, secret absent rejeté, mot de passe `a@b:c/d%` conservé exactement dans `URL.password`, rendu usuel de la configuration masquant le secret.
- [ ] Exécuter `uv run pytest tests/unit/test_config.py -q`, constater les échecs avant d’implémenter `Settings` et `build_database_url`, puis obtenir le succès.
- [ ] Ajouter les scripts Devbox : `setup` → `uv sync --locked`, `start` → `uv run uvicorn pokecoach_python.main:create_app --factory --host 127.0.0.1 --port 8042 --reload`, `check` → Ruff, `test` → tests unitaires, `test-integration` → tests PostgreSQL explicitement configurés.
- [ ] Vérifier `devbox run setup`, `uv lock --check`, `devbox run check` et `devbox run test` depuis une installation propre. Aucun Python global ne doit être nécessaire.

## Tâche 2 — FastAPI et connexion réelle à PostgreSQL

**Fichiers :** créer `src/pokecoach_python/main.py`, `db/session.py`, `api/health.py`, `tests/conftest.py`, `tests/unit/test_health.py`, `tests/integration/test_database.py`.

**Interfaces :**

- `create_app(settings: Settings | None = None) -> FastAPI` : factory injectable pour les tests.
- `create_db_engine(settings: Settings) -> sqlalchemy.Engine` : pool limité (`pool_size=5`, `max_overflow=0`, `pool_timeout=5`, `pool_pre_ping=True`).
- `get_session(request: Request) -> Iterator[sqlmodel.Session]` : nouvelle session par requête ; rollback sur exception, fermeture garantie. Chaque service d’écriture contrôle sa transaction.
- `GET /health` : `200 {"status":"ok","database":"ok"}` après `SELECT 1` ; `503 {"status":"unavailable","database":"unavailable"}` en cas de panne. Aucun identifiant ni détail SQL en réponse.

- [ ] Écrire les tests de santé avec moteur/session injectés : succès, panne, fermeture et absence de secret. Vérifier qu’importer le module ne tente aucune connexion.
- [ ] Implémenter le lifespan : créer le moteur dans `app.state`, vérifier effectivement la connexion au démarrage, libérer le moteur dans un `finally`. Une connexion initiale impossible fait échouer le démarrage, sans boucle de retry infinie.
- [ ] Implémenter la dépendance de session et la route de santé synchrone. Les appels SQL synchrones ne doivent pas bloquer la boucle async FastAPI ; utiliser le threadpool pour le contrôle initial dans le lifespan.
- [ ] Ajouter des timeouts de connexion et de requête bornés ; journaliser les erreurs avec un identifiant de requête et un message exploitable, sans DSN complet ni paramètres sensibles.
- [ ] Écrire les tests PostgreSQL utilisant `TEST_DATABASE_URL` vers une base jetable migrée par conception : rôle courant `pokecoach_worker`, `SELECT` sur `core.teams`, deux sessions distinctes, fermeture après exception et aucun changement de schéma. Refuser une cible non explicitement dédiée aux tests.
- [ ] Exécuter `devbox run test` puis `devbox run test-integration` avec cette base. Démarrer localement et vérifier `curl --fail http://127.0.0.1:8042/health` ; arrêter uniquement la DB de test pour vérifier le cas 503 après démarrage.

## Tâche 3 — Image et branchement à la stack existante

**Fichiers :** créer `Dockerfile`, `.dockerignore`, `README.md`. Modifier dans conception `deployment/local/compose.python.yml` et `deployment/local/.env.python.example` pour compléter l’extension existante, sans créer une seconde stack dans Python.

**Interface :** image `pokecoach2-python:local`, service `api-python`, port conteneur `8000`, port hôte par défaut `8042`, endpoint `/health`.

- [ ] Créer une image suivant le [guide Docker uv](https://docs.astral.sh/uv/guides/integration/docker/) : version Python cohérente, uv épinglé, dépendances verrouillées sans groupe dev, application copiée, utilisateur non-root. Exclure `.env`, `.venv`, `.git`, `.devbox` et les caches du contexte.
- [ ] Lancer Uvicorn sur `0.0.0.0:8000`, sans reload, avec les dépendances déjà installées ; aucun téléchargement au démarrage.
- [ ] Construire `docker build -t pokecoach2-python:local .`. Documenter `POKECOACH_PYTHON_IMAGE=pokecoach2-python:local` dans la configuration locale de conception.
- [ ] Compléter l’overlay avec un healthcheck HTTP utilisant Python standard, `APP_ENV=container` et `ENABLE_DEMO_SEED=false` par défaut. Conserver les secrets et `depends_on: flyway` déjà fournis.
- [ ] Depuis conception, vérifier `./scripts/compose-python.sh config --quiet`, puis démarrer `./scripts/compose-python.sh up -d api-python` dans la stack locale prévue. Ne pas afficher de configuration résolue contenant des secrets.
- [ ] Vérifier `/health`, les logs sans secret, l’arrêt propre et le redémarrage. Documenter les deux modes (hôte et Docker), les ports, les commandes de tests et la propriété des migrations dans `README.md`.

## Critères de fin

- Devbox + uv suffisent pour installer, lancer et tester l’API.
- Le service lit PostgreSQL avec le rôle worker et libère ses connexions.
- L’image fonctionne avec l’overlay de conception ; aucun schéma n’est créé par Python.
- La fondation est prête pour le [plan 2 : route de démonstration](2026-10-31-02-python-demo-seed.md). Les tests ne prétendent pas valider VGC-Bench.
