# Adaptations SQL, contrats et Angular — Plan d’implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Réaliser tout le §10 de la spécification pour stocker et afficher un résultat réel enrichi progressivement, sans casser la démonstration mock v1.

**Architecture:** PostgreSQL porte les checkpoints, statuts, commandes idempotentes et combats complets. Python et Angular partagent une enveloppe simulation v2 ; Angular lit le run sélectionné via PostGraphile même avant son succès. Les traitements de phases arrivent dans les plans suivants.

**Tech Stack:** PostgreSQL/Flyway, PostGraphile existant, Pydantic, Angular/HttpClient, pytest, tests SQL et Vitest.

**Spec:** [Workflow révisé, §§9, 10 et 14](../specs/2026-10-31-workflow-analyse-matchup.md).

## Contraintes globales

- Prérequis : plans 01 et 02 réalisés ; revalider les migrations présentes au début de l’exécution. Les numéros proposés ci-dessous supposent V1.0.8 réservée à la route demo ; prendre les prochaines versions libres sans modifier une migration appliquée.
- Les paramètres, snapshots et résultats de phases déjà validées sont conservés. `paused` est non terminal ; un résultat partiel n’est pas un rapport complet réussi.
- Les points 1–4 sont déterministes ; le modèle ne peut écrire que `gameplan`/`winCondition`.
- Pas d’accès administrateur pour l’API ; droits GraphQL en lecture sur les résultats. Pas d’exposition des baux, clés de commandes ou historiques de combats dans le schéma GraphQL public.
- Appliquer les skills Angular et design-system pour les composants modifiés. Conserver les trois onglets et les anciens rapports mock.

## Points de revue

Tester particulièrement : migration d’une base déjà peuplée (tâche 1), verrouillage SQL avec le vrai rôle worker (2), progression sans changement de statut (2), JSON partiel/inconnu (3–4), sélection de run et réponses réseau obsolètes (4).

## Tâche 1 — Schéma de stockage progressif

**Fichiers conception :** créer `modules/1.0-core/sql/core/V1.0.9__add_progressive_analysis_storage.sql` et son `_repoindex.md`, `tests/sql/050_progressive_storage.sql`. Modifier `docs/data-contract.md`.

**Interface SQL :** étendre `core.matchup_runs` :

| Champ | Type et règle |
| --- | --- |
| `status` | CHECK étendu avec `paused` |
| `target_phase` | text nullable pour mock, A/B/C/D/synthesis obligatoire pour simulation v2 |
| `partial_result` | jsonb nullable pour mock, enveloppe v2 obligatoire pour simulation v2 |
| `result_revision` | integer ≥ 0, initial 0, +1 par phase publiée |
| `progress` | jsonb `{phase, completed, total}`, nombres non négatifs, compteur ≤ total |
| `execution_metadata` | jsonb `{}` : versions, mesures et entrée LLM tracées par phase |
| `lease_token` | uuid nullable, renouvelé à chaque acquisition |
| `lease_expires_at`, `heartbeat_at` | timestamptz nullables |

Créer `core.analysis_commands(idempotency_key uuid PRIMARY KEY, operation text, request_hash text, run_id uuid REFERENCES core.matchup_runs, created_at timestamptz)` ; opérations `start`, `continue`, `cancel`. Stocker la commande dans la même transaction que sa mutation de run.

Créer `core.matchup_run_battles(id uuid PRIMARY KEY, run_id uuid REFERENCES core.matchup_runs, phase text CHECK C/D, sample_key text, format_version integer, outcome text CHECK win/loss/draw, payload jsonb, sha256 text, created_at timestamptz)` ; unicité `(run_id, phase, sample_key)`. `payload` contient un historique normalisé complet, pas un résumé d’agrégats. FK avec suppression RESTRICT ; le reset demo ne concerne aucun combat simulation.

- [ ] Écrire les tests sur base existante : mock v1 inchangé, simulation v2 vide acceptée, phase invalide refusée, doublon de commande/échantillon refusé, deux runs `queued/running` d’un matchup refusés.
- [ ] Ajouter un index unique partiel sur `matchup_id` pour `status IN ('queued','running')`, un index d’acquisition des queued et un index sur les combats `(run_id, phase)`. Avant création, détecter d’éventuels doublons existants et échouer avec diagnostic, sans les supprimer automatiquement.
- [ ] Ne pas convertir un ancien rapport mock ou une ancienne simulation incompatible en v2. Les nouvelles contraintes v2 s’appliquent à `source='simulation' AND report_version=2` ; un ancien format reste consultable comme non pris en charge si nécessaire.
- [ ] Exécuter `./scripts/test-db.sh` sur base jetable migrée depuis zéro et sur un état peuplé avant migration. Mettre à jour le contrat documenté et le profil SQL en anglais.

## Tâche 2 — Triggers, droits et validation de publication

**Fichiers conception :** créer `modules/1.0-core/sql/trigger_functions/V1.0.10__support_analysis_checkpoints.sql`, son `_repoindex.md`, `tests/sql/060_analysis_checkpoints.sql` ; modifier `modules/1.0-core/sql/afterMigrate.sql`.

**Interfaces :** `core.is_valid_simulation_result_v2(payload jsonb, require_complete boolean) RETURNS boolean` ; transitions autorisées pour simulation v2 : queued→queued/running/failed/cancelled ; running→running/paused/succeeded/failed/cancelled ; paused→queued/cancelled/failed. Aucun changement sur un run terminal.

- [ ] Écrire les tests de transitions et d’invariants avant la migration : progression `running→running`, pause sans `finished_at`, continuation, finalisation sans E refusée, report non NULL avant succès refusé, snapshots/paramètres immuables.
- [ ] Remplacer par migration les fonctions de trigger concernées, y compris l’ordre de validation de `process_status`. Un succès exige les cinq phases, les deux champs LLM, `report=partial_result`, `finished_at`, `SUCCESS`. Une pause exige la cible atteinte, pas de rapport final et aucun bail. Les mêmes statuts sont permis pour les mises à jour techniques autorisées.
- [ ] Restreindre le changement de `target_phase` à une continuation `paused→queued`, vers une cible supérieure au préfixe acquis. Figer les paramètres scientifiques dès l’insertion, y compris lors de ce retour à queued ; les timestamps `started_at` et snapshots du run ne sont pas réinitialisés.
- [ ] Faire valider l’enveloppe et son préfixe de phases en SQL. Une publication ajoute exactement une phase et incrémente la révision ; un heartbeat n’en change aucune. Interdire de modifier les champs déjà acquis : A reste identique lorsque B remplit les `turn1`, A/B restent identiques en C, puis ajout seul de `refinement`, puis de `gameplan`/`winCondition`. Des états impossibles ou phases réordonnées sont rejetés.
- [ ] Garder `parameters` et `provenance` initiaux figés ; autoriser l’ajout de métadonnées d’exécution de nouvelles phases dans `execution_metadata`, sans réécriture d’un bloc de phase validé. Ne pas essayer de compléter la provenance initiale en fin de run malgré son trigger actuel.
- [ ] Corriger le trigger de snapshot en fonction de trigger `SECURITY DEFINER`, propriétaire migrateur, `search_path` sûr et tables qualifiées. Verrouiller matchup puis équipes dans un ordre stable et vérifier archivage. Il ne fait que capturer les snapshots de la ligne insérée ; aucune autorisation d’UPDATE d’équipe n’est donnée au worker. Vérifier les grants des validateurs utilisés par les CHECK/triggers avec le vrai rôle worker.
- [ ] Autoriser au worker les opérations strictement nécessaires sur commandes/combats, sans mutation publique GraphQL. Rendre les combats insérés immuables ; interdire l’ajout à une phase déjà publiée ou à un run non `running`. La vérification de bail et le verrou de la ligne parent font partie de chaque transaction du repository (§ plan 04).
- [ ] Masquer les tables de commandes/combats et champs de bail (`@omit`) ; révoquer PUBLIC/authenticated_user sur ces tables. Conserver SELECT des résultats et snapshots pour GraphQL ; conserver l’omission des mutations de runs.
- [ ] Exécuter les tests SQL : vraie insertion worker, refus d’écriture d’équipe par worker, refus de mutation via rôle GraphQL, champs terminaux et combats immuables. Rejouer le reset demo pour vérifier sa compatibilité.

## Tâche 3 — Contrat v2 partagé et exemples

**Fichiers Python :** créer `contracts/simulation-result-v2.schema.json`, `contracts/examples/simulation-empty.json`, `simulation-a.json`, `simulation-ab.json`, `simulation-abc.json`, `simulation-abcd.json`, `simulation-complete.json`, `src/pokecoach_python/schemas/analysis_result.py`, `tests/unit/test_analysis_result.py`.

**Interfaces :** `Phase = Literal['A','B','C','D','synthesis']`, `SimulationResultV2`, `validate_result(payload: dict, require_complete: bool = False) -> SimulationResultV2`. Modéliser séparément les sections du §14 et les références côté/slot ; `None` signifie non calculé, pas zéro observation.

- [ ] Écrire les exemples minimaux mais cohérents pour chaque préfixe, avec mêmes snapshots de test, mêmes champs A conservés jusqu’à E. Les exemples sont synthétiques et réservés aux tests.
- [ ] Écrire les validations Python : ordre des phases, sections exigées/absentes, entiers et dénominateurs, slots distincts et valides, lead inclus dans le quatre, refs adverses correctes, champs LLM uniquement après E. Rejeter les champs supplémentaires aux frontières de contrat.
- [ ] Exporter le JSON Schema depuis Pydantic avec une commande reproductible et ajouter un check de non-divergence. Les adaptateurs moteur ajouteront leurs événements au contrat de combat dans le plan 04 ; ils ne modifieront pas implicitement cette enveloppe.
- [ ] Faire consommer les mêmes exemples par les tests SQL et les tests Angular, via un chemin de test documenté ou une copie générée vérifiée par empreinte. Aucun import des fixtures depuis le runtime Angular.
- [ ] Exécuter `uv run pytest tests/unit/test_analysis_result.py -q`, puis les tests SQL de validation des exemples et d’exemples invalides.

## Tâche 4 — Lire et afficher un run partiel dans Angular

**Fichiers Angular**, racine `pokecoach2-angular/pokecoach-angular` : créer `src/app/core/models/simulation-result.model.ts`, `src/app/core/graphql/simulation-result-validator.ts`, son `.spec.ts` ; modifier `core/graphql/coach-dto.ts`, `coach-operations.ts`, `coach-api.ts`, `coach-mappers.ts` et leurs tests, `core/data/coach-store.ts`, `features/matchup/matchup.ts`, `matchup.html`, `opponent-leads.ts/html`, `lead-pick.ts/html`, `gameplan.ts/html` (tous sous `src/app`). Étendre également les messages de statut dans `features/team-detail/team-detail.ts` si leur rendu dépend d’un statut exhaustif.

**Interfaces :** résultat discriminé `mock/v1` ou `simulation/v2`. Ajouter `CoachApi.getRun(teamId, matchupId, runId)` et `CoachStore.loadRun(teamId, matchupId, runId)` ; vérifier l’appartenance au matchup, pas uniquement l’UUID. Conserver les API existantes pour les listes et le dernier succès.

- [ ] Introspecter le vrai schéma PostGraphile après migration. Ajouter `partialResult`, `resultRevision`, `progress`, `targetPhase`, `executionMetadata` aux lectures adaptées ; ne jamais demander `matchupRunBattles` dans la lecture de page.
- [ ] Étendre les types de statut et `shouldPollRun` : seulement queued/running. Mapper le run sélectionné et ses snapshots ; si l’URL n’a pas de `runId`, choisir le plus récent et permettre de consulter l’ancien rapport complet séparément.
- [ ] Découpler les inputs d’onglets de l’obligation d’avoir un `MatchupReport` complet. Le mock garde son lecteur et son rendu ; simulation v2 fournit chaque section disponible. `turn1=null` est différent d’une distribution vide ; `gameplan=null` n’affiche aucun texte inventé.
- [ ] Afficher le profil, la phase, le caractère partiel et les révisions sans remplacer toute la page par un loader à chaque polling. Conserver l’onglet et le lead sélectionnés tant qu’ils existent. Ignorer réponses d’un ancien run ou d’une révision inférieure.
- [ ] Tester les six exemples, un JSON invalide, un format inconnu, run d’un autre matchup, pause/erreur avec données consultables, retour vers un ancien succès, et absence de mélange entre snapshots/runs.
- [ ] Exécuter les tests Angular, lint et build. Sur base de test, insérer les exemples comme fixtures explicites, vérifier le rendu réel via GraphQL et un refresh. Cette recette valide le transport et le rendu, pas encore une simulation.

## Sortie et suite

Tout le §10 est couvert : transitions (2), droits/snapshots (2), persistance et idempotence (1), validation v2 (2–3), lecteur partiel frontend (4), métadonnées séparées (1–2). La prochaine étape est le [socle d’exécution](2026-10-31-04-socle-workflow-python.md).
