# PokeCoach2 — API Python

API FastAPI pour les commandes (réinstallation de la seed de démonstration, futur workflow d’analyse). Les lectures métier restent sur PostGraphile ; Python accède à PostgreSQL avec le rôle `pokecoach_worker`. Le schéma est géré par Flyway dans `pokecoach2-conception`.

## Prérequis

- [Devbox](https://www.jetify.com/devbox) + `uv` (fourni par Devbox)
- PostgreSQL local sur le port **5442** (stack `pokecoach2-conception/deployment/local`)

## Installation

```bash
devbox run setup
cp .env.example .env   # renseigner POSTGRES_PASSWORD (= WORKER_DB_PASSWORD de conception)
```

## Lancer l’API sur l’hôte

```bash
devbox run start
curl --fail http://127.0.0.1:8042/health
```

| Variable | Hôte | Conteneur (`compose.python.yml`) |
| --- | --- | --- |
| `APP_ENV` | `local` | `container` |
| `POSTGRES_HOST` | `127.0.0.1` | `postgres` |
| `POSTGRES_PORT` | `5442` | `5432` |
| `ENABLE_DEMO_SEED` | `true` pour activer la route demo | idem |

## Route de démonstration

Activer explicitement `ENABLE_DEMO_SEED=true`, puis :

```bash
curl --fail-with-body -X POST http://127.0.0.1:8042/api-python/demo/seed \
  -H 'Content-Type: application/json' \
  -d '{}'
```

Ne pas relancer automatiquement en cas de doute réseau après un commit réussi : relire via GraphQL.

## Tests

```bash
devbox run check
devbox run test
# Base jetable migrée (voir pokecoach2-conception/scripts/test-db.sh) :
export WORKER_DB_PASSWORD=…
export TEST_DATABASE_URL=postgresql://pokecoach_worker@127.0.0.1:5442/pokecoach2_test
devbox run test-integration
```

## Image Docker

```bash
docker build -t pokecoach2-python:local .
```

Dans `pokecoach2-conception/deployment/local/.env.python` :

```env
POKECOACH_PYTHON_IMAGE=pokecoach2-python:local
```

Puis depuis conception : `./scripts/compose-python.sh up -d api-python`

Le proxy Angular (`src/proxy.conf.json`) et Nginx en stack complète exposent `/api-python/` vers ce service.

## UUID réservés (démonstration)

- Équipes possédées : `a1111111-…101`, `a1111111-…102`
- Équipe adverse : `b2222222-…201`
- Matchup : `c3333333-…301`

La commande remplace uniquement ces enregistrements et l’historique de runs de ce matchup.
