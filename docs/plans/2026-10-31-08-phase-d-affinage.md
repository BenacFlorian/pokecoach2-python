# Phase D — Combats ciblés et affinage visible

> **Remplacé par** [plan 11 — évaluation globale](2026-11-01-11-phase-d-affinage-global.md) (novembre 2026). Ce document reste une trace de l’approche « un seul lead + back modal ».

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Observer notre sélection C contre un lead/back adverse précis et ajouter ces résultats au frontend avant toute synthèse LLM.

**Architecture:** Le handler D lit A/B/C, impose les deux sélections et joue les combats complets ciblés. Il persiste leurs historiques et ajoute `refinement` sans modifier les statistiques ou recommandations précédentes.

**Tech Stack:** Adaptateur réel, agrégation Python, table des combats, résultat v2, Angular/PostGraphile.

**Spec:** [Workflow §§7, 8 et 14](../specs/2026-10-31-workflow-analyse-matchup.md). Prérequis : [phase C](2026-10-31-07-phase-c-selection.md).

## Contraintes et points de revue

- Standard : 10 combats au total ; smoke : 2. Ne pas multiplier ce budget par tous les leads C.
- Notre quatre/lead vient de C ; lead adverse = plus fréquent de A parmi ceux étudiés en C, back = paire la plus fréquente en B pour ce lead. Départage stable par slots.
- Aucun mélange implicite entre les statistiques C et celles de la configuration D. Aucun LLM avant le prochain plan.
- Tester back incompatible ou absent (1), sélections réellement imposées (2), ancien résultat C préservé (2–3), faible effectif et coexistence de victoires/défaites (1–3).

## Tâche 1 — Configuration et agrégats d’affinage

**Fichiers Python :** créer `workflow/phases/phase_d.py`, `workflow/aggregation/refinement.py`, `tests/unit/test_phase_d.py` ; compléter `schemas/analysis_result.py` et `contracts/examples/simulation-abcd.json`.

**Interfaces :** `select_refinement_configuration(result: SimulationResultV2) -> FixedBattleConfiguration` ; `aggregate_refinement(battles: Sequence[BattleRecord], configuration: FixedBattleConfiguration) -> RefinementSection` ; `PhaseD.run(context: PhaseContext) -> PhaseOutput`.

- [ ] Tester les choix déterministes en cas d’ex æquo, quatre composé de quatre slots distincts et lead inclus, back adverse disjoint du lead. Une absence de données nécessaires est une erreur explicite, pas une sélection aléatoire.
- [ ] Produire configuration complète, victoires/défaites/nuls, effectif, distributions de premiers tours et identifiants de combats. Ajouter les limites « configuration ciblée » et « faible échantillon » par texte gabarité.
- [ ] Conserver les observations factuelles de séquences sans inférence de win condition. Les références à des combats permettent le contrôle ; l’interface n’a pas besoin de lire tous leurs tours.
- [ ] Vérifier par comparaison JSON que `opponentLeads` et `leadPick` ne changent pas. Exécuter `uv run pytest tests/unit/test_phase_d.py -q`.

## Tâche 2 — Simulations fixées des deux côtés

**Fichiers Python :** compléter `workflow/phases/phase_d.py`, `workflow/registry.py` ; créer `tests/integration/test_phase_d_run.py`, `docs/recettes/phase-d.md`.

- [ ] Appeler `full_battle` avec quatre et leads imposés des deux côtés, décisions BC libres ensuite. Comparer les choix réellement joués aux contraintes avant de compter une partie valide.
- [ ] Persister chaque historique complet avec `phase='D'`, sample_key, résultat et empreinte selon le repository du socle. Compter séparément contraintes non satisfaites et erreurs techniques.
- [ ] Publier `refinement`, phase D complétée et révision 4 ; si cible D, paused/PENDING GAME SIMULATIONS, report NULL. La progression ne doit pas afficher de synthèse LLM fictive.
- [ ] Tester continuation C→D sans nouvelles simulations A/B/C, budgets exacts, publication atomique, perte du bail et erreur après un combat. Tous les points 1–4 restent consultables si D échoue.
- [ ] Exécuter `uv run pytest tests/integration/test_phase_d_run.py -q`, tests de contrat et d’immutabilité SQL.

## Tâche 3 — Affinage à l’écran et recette réelle

**Fichiers Angular :** compléter `src/app/features/matchup/lead-pick.ts/html`, leurs tests et `e2e/analysis-progressive-live.spec.ts`.

- [ ] Ajouter dans « Lead & pick » un bloc « Affinage » : configuration exacte, effectifs, issues et premiers tours observés en D. Le distinguer du tableau C sans changer la recommandation de sélection.
- [ ] Conserver l’onglet « Gameplan » avec l’état « Plan de jeu pas encore généré » ; un résumé déterministe de D ne remplit pas artificiellement cet onglet.
- [ ] Continuer le run smoke C jusqu’à D dans l’interface, ou `uv run python scripts/analysis-smoke.py --run-id UUID --target D`. Voir les deux combats ciblés, le run en pause et les sections A–D après refresh.
- [ ] Continuer le run standard et vérifier **10 combats complets** de D et la conservation des historiques C. Comparer les empreintes des sections A/B/C avant et après D.
- [ ] Exécuter tests Angular/lint/build et Playwright cible D. Documenter URL, configuration, effectifs et mesures dans `docs/recettes/phase-d.md` ; conserver le run pour E.

**Résultat visible attendu :** statistiques A–D disponibles, résultat encore partiel car les points 5–6 sont absents. Suite : [phase E](2026-10-31-09-phase-e-gameplan-llm.md).
