# Phase C — Notre sélection et notre premier tour déterministes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jouer des combats complets contre les leads dominants, calculer notre quatre/lead et nos premiers tours, puis les afficher dans « Lead & pick ».

**Architecture:** Le handler C persiste chaque combat complet dans la table dédiée et agrège les résultats avec des règles versionnées. Il ajoute `leadPick` au checkpoint A+B. Aucun appel LLM ; les historiques C serviront plus tard à E.

**Tech Stack:** Moteur réel, Python déterministe, PostgreSQL et rendu Angular.

**Spec:** [Workflow §§6, 8 et 14](../specs/2026-10-31-workflow-analyse-matchup.md). Prérequis : [phase B](2026-10-31-06-phase-b-tour1-back.md).

## Contraintes et points de revue

- Standard : 50 combats complets par lead du top 3 (ou top 2 si configuration choisie à la création). Smoke : 3 par lead du top 3. Ce budget n’est pas multiplié par le nombre de nos compositions.
- Fixer le lead adverse, laisser le modèle échantillonner son back et notre sélection. Les égalités sont des issues terminées ; les timeouts sont des erreurs techniques.
- Tester candidat absent d’une confrontation, couverture incomplète, égalités de classement, tour 1 non observé (tâche 1), et stockage tronqué/doublonné d’un combat (2).

## Tâche 1 — Classement et recommandations sans LLM

**Fichiers Python :** créer `workflow/aggregation/selections.py`, `workflow/phases/phase_c.py`, `tests/unit/test_phase_c.py` ; compléter schéma v2 et `contracts/examples/simulation-abc.json`.

**Interfaces :** `aggregate_selections(battles: Sequence[BattleRecord], leads: OpponentLeadsSection, rule_version: str = 'selection-v1') -> LeadPickSection` ; `PhaseC.run(context: PhaseContext) -> PhaseOutput`.

- [ ] Regrouper par quatre trié et lead trié de notre côté, tout en conservant positions réelles dans les combats. Calculer victoires/défaites/nuls, effectifs, taux et couverture pour chaque lead adverse.
- [ ] Implémenter le classement exact du §6 : couverture complète prioritaire, moyenne pondérée par A sur le top ; à défaut, couverture pondérée maximale puis taux pondéré observé. Départager par effectif puis slots. Utiliser des fractions ou une comparaison stable avant tout arrondi d’affichage.
- [ ] Tester un exemple où moyenne simple et pondérée choisissent des candidats différents, un cas sans candidat couvrant tout le top, un taux sur un seul combat, un nul, et une confrontation jamais observée qui ne doit pas devenir une défaite.
- [ ] Pour la sélection retenue, classer nos actions conjointes du premier tour par lead adverse : taux de victoire décroissant, effectif décroissant, clé canonique. Stocker les actions et leurs vraies cibles, les alternatives suivantes et leurs effectifs. Sans observation, fournir un état indisponible avec motif ; aucune capacité suggérée par LLM.
- [ ] Générer la justification par gabarit de calcul (règle, score, effectif, couverture), pas par modèle. Le rapport doit qualifier cette recommandation d’empirique et signaler les faibles effectifs.
- [ ] Exécuter `uv run pytest tests/unit/test_phase_c.py -q` ; vérification que A+B restent identiques et seuls `leadPick`/completedPhases s’enrichissent.

## Tâche 2 — Combats complets et publication C

**Fichiers Python :** compléter `workflow/phases/phase_c.py`, `workflow/registry.py`, `db/analysis_repository.py` ; créer `tests/integration/test_phase_c_run.py`, `docs/recettes/phase-c.md`.

- [ ] Déterminer le top adverse depuis A, stable en cas d’égalité. Exécuter `EngineAdapter.full_battle` pour chaque groupe, avec contraintes vérifiées et budgets propres au profil du run.
- [ ] Valider chaque `BattleRecord` du preview à l’issue, enregistrer un `sample_key` stable (lead canonique + index valide), une empreinte canonique JSON et `phase='C'`. Un enregistrement déjà présent doit être identique ou provoquer une erreur ; ne jamais doubler un échantillon.
- [ ] Persister les combats au fil de l’exécution sous contrôle du bail. Lors du checkpoint C, relire uniquement les combats C valides du run et vérifier les effectifs attendus avant agrégation. Un historique sans issue terminale ne peut alimenter ni les statistiques C ni le futur LLM.
- [ ] Publier `leadPick`, révision 3 et pause si cible C ; les métadonnées enregistrent budgets réellement obtenus, traces, mesures et version `selection-v1`.
- [ ] Tester continuation depuis B sans relancer A/B, panne en cours laissant A+B visibles, token périmé empêchant l’insertion et publication, puis état C validé immuable. Les combats d’une phase non validée ne seront pas éligibles au LLM.
- [ ] Exécuter `uv run pytest tests/integration/test_phase_c_run.py -q` et les tests SQL de la table des combats.

## Tâche 3 — Lead & pick et recette de fin de plan

**Fichiers Angular :** compléter `src/app/features/matchup/lead-pick.ts/html`, ses tests, le validateur v2 si nécessaire et `e2e/analysis-progressive-live.spec.ts`.

- [ ] Afficher notre quatre et notre lead, tableau des résultats avec effectifs/coverage, justification déterministe et premiers tours par lead adverse. Les cases sans observation montrent « Données insuffisantes », pas une recommandation extrapolée.
- [ ] Garder « Opponent Leads » intact et « Gameplan » en attente du LLM. Aucun texte libre de stratégie ne provient des calculs de C ; les libellés expliquent seulement les observations et la règle appliquée.
- [ ] Continuer le run smoke B jusqu’à C depuis le frontend, ou `uv run python scripts/analysis-smoke.py --run-id UUID --target C`. Vérifier trois combats par lead étudié et les onglets A+B+C après refresh.
- [ ] Continuer le run standard : **50 combats complets par lead retenu**. Contrôler en base que les historiques complets existent et que leur nombre recoupe le tableau, sans les charger dans la requête de page.
- [ ] Exécuter tests Angular/lint/build et Playwright cible C. Enregistrer choix, couverture, effectifs, mesures et URL dans `docs/recettes/phase-c.md` ; conserver le runId pour D.

**Résultat visible attendu :** points 1–4 du rapport consultables et calculés sans LLM, avec leurs limites d’échantillonnage. Suite : [phase D](2026-10-31-08-phase-d-affinage.md).
