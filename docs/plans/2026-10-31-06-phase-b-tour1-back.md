# Phase B — Tour 1 et back par lead adverse

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrichir chaque lead de A avec ses actions adverses du tour 1 et ses backs observés, visibles au clic dans Angular.

**Architecture:** Le handler B lit le checkpoint A, joue un premier tour avec chaque lead imposé, agrège puis complète les champs `turn1`. La section A est préservée et aucun LLM n’intervient.

**Tech Stack:** Adaptateur VGC-Bench/Showdown, agrégation Python, checkpoint PostgreSQL v2, Angular/PostGraphile.

**Spec:** [Workflow §§5 et 14](../specs/2026-10-31-workflow-analyse-matchup.md). Prérequis : [phase A](2026-10-31-05-phase-a-leads.md).

## Contraintes et points de revue

- Standard : 50 simulations valides par lead réellement observé en A ; smoke : 3 par lead. Ne pas limiter B aux seuls leads du top C.
- Le back est celui du preview, pas les Pokémon hors terrain après les changements du tour 1.
- Tester permutation gauche/droite (1), mêmes capacités vers cibles différentes (1), changement et Téracristallisation (1–2), rejet d’un lead imposé (2), échec après certains leads sans altérer A (2).

## Tâche 1 — Distributions conditionnelles

**Fichiers Python :** créer `workflow/phases/phase_b.py`, `workflow/aggregation/turn_one.py`, `tests/unit/test_phase_b.py` sous les racines Python ; compléter `schemas/analysis_result.py` et `contracts/examples/simulation-ab.json`.

**Interfaces :** `aggregate_turn_one(records: Sequence[TurnOneRecord], lead_slots: tuple[int,int]) -> TurnOneSection` ; `PhaseB.run(context: PhaseContext) -> PhaseOutput`.

- [ ] Écrire les tests de normalisation : actions conjointes indexées par acteur réel, cibles gardant côté/slot, capacités identiques mais cibles différentes dans des groupes distincts, changements vers leur vraie destination.
- [ ] Compter paires de back et marges par Pokémon, jointures lead/actions/back et contexte de notre lead. Tester trois parties dont les marges de back totalisent six présences, et des modes action/back qui ne coïncident dans aucune partie.
- [ ] Trier par fréquence puis clé canonique ; ne pas appeler une paire de modes « configuration la plus probable » sans fréquence conjointe. Conserver effectifs et dénominateurs propres à chaque distribution, plus les états observables de fin de tour.
- [ ] Garantir par test que les champs `id`, `slots`, `count`, `sampleSize` de A restent strictement égaux ; seules les sections `turn1` passent de NULL à calculées.
- [ ] Exécuter `uv run pytest tests/unit/test_phase_b.py -q` et les validations des exemples de contrat.

## Tâche 2 — Simulation imposée et checkpoint B

**Fichiers Python :** compléter `workflow/phases/phase_b.py`, `workflow/registry.py` ; créer `tests/integration/test_phase_b_run.py`, `docs/recettes/phase-b.md`.

- [ ] Pour chaque lead A, appeler `EngineAdapter.first_turn` avec contrainte de lead adverse, sélection de back conditionnelle et politique documentée de notre côté. Vérifier le lead effectivement obtenu ; rejets comptés séparément, jamais inclus dans les 50/3 observations.
- [ ] Arrêter après résolution réelle du premier tour, pas après réception du premier choix d’action. Libérer la bataille sans perdre l’information sur le back initial.
- [ ] Afficher la progression en nombre de tours 1 valides sur `nombreLeads × budgetB`. Les statistiques B restent non publiées jusqu’au checkpoint complet ; pendant le calcul, A demeure visible.
- [ ] Publier A+B avec `result_revision=2` et pause si cible B. Tester continuation du run A sans aucun nouvel appel `preview`, puis lancement neuf jusqu’à B exécutant A et B.
- [ ] Tester erreur d’un des derniers leads : run failed, A conservé, B non déclaré terminé, compteurs/raison consultables. Ne pas copier un résultat d’un autre lead pour compléter le budget.
- [ ] Exécuter `uv run pytest tests/integration/test_phase_b_run.py -q` et les tests SQL de progression/immutabilité.

## Tâche 3 — Détails dans Opponent Leads et recette réelle

**Fichiers Angular :** compléter `features/matchup/opponent-leads.ts/html` et ses tests sous `src/app`, ainsi que `e2e/analysis-progressive-live.spec.ts`.

- [ ] Au clic sur un lead, afficher actions conjointes les plus fréquentes avec cibles, backs par paire et présences individuelles, dénominateurs et alternatives. Garder le classement A inchangé ; pas de texte stratégique généré.
- [ ] Distinguer un mode d’action d’un mode de back, et afficher leur fréquence conjointe seulement si elle existe. Afficher les données indisponibles explicitement selon l’adaptateur audité.
- [ ] Redémarrer le worker avec B disponible. Sur le run smoke en pause après A, cliquer Continuer jusqu’à B ou utiliser `uv run python scripts/analysis-smoke.py --run-id UUID --target B`.
- [ ] Constater le même runId, trois observations par lead, les champs A inchangés, puis la pause B et la persistance après refresh. « Lead & pick » et « Gameplan » restent en attente.
- [ ] Continuer le run standard de A jusqu’à B et vérifier **50 observations par lead**. Enregistrer mesures et runId pour C.
- [ ] Lancer tests Angular/lint/build et la recette Playwright cible B. Consigner les résultats dans `docs/recettes/phase-b.md`.

**Résultat visible attendu :** premier onglet entièrement alimenté par les phases A+B. Suite : [phase C](2026-10-31-07-phase-c-selection.md).
