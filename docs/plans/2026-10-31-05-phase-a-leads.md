# Phase A — Leads adverses observés

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lancer de vrais previews avec le modèle BC, enregistrer la distribution des leads et la voir dans « Opponent Leads ».

**Architecture:** Un handler A utilise l’adaptateur du socle, agrège les paires adverses puis publie un premier checkpoint v2. Le run s’arrête en pause si la cible est A ; aucun combat complet ni appel LLM n’est nécessaire.

**Tech Stack:** Worker Python, adaptateur VGC-Bench/Showdown, PostgreSQL/PostGraphile, Angular.

**Spec:** [Workflow §§4, 9 et 14](../specs/2026-10-31-workflow-analyse-matchup.md). Prérequis : [socle plan 04](2026-10-31-04-socle-workflow-python.md).

## Contraintes et points de revue

- Budget standard : 1 000 previews valides ; smoke : 20. Erreurs et rejets ne sont pas des observations.
- Paires de slots triés pour les statistiques ; conserver l’ordre réel des positions dans les traces. Pas de regroupement par simple nom d’espèce.
- Tester ordre inversé d’un lead (tâche 1), équipe/sampling incompatibles (2), dépassement du budget d’erreurs (2), résultat partiel rafraîchi ou ancien run sélectionné (3).
- Pas de faux tour 1, de sélection de notre quatre recommandée ou de texte LLM. `turn1`, `leadPick`, `refinement`, `gameplan`, `winCondition` restent NULL.

## Tâche 1 — Agrégation déterministe

**Fichiers Python :** créer `src/pokecoach_python/workflow/phases/phase_a.py`, `workflow/aggregation/leads.py`, `tests/unit/test_phase_a.py` ; compléter `schemas/analysis_result.py` et `contracts/examples/simulation-a.json` si nécessaire.

**Interfaces :** `canonical_lead(slots: tuple[int,int]) -> tuple[int,int]` ; `aggregate_leads(records: Sequence[PreviewRecord]) -> OpponentLeadsSection` ; `PhaseA.run(context: PhaseContext) -> PhaseOutput`.

- [ ] Écrire un test avec `[0,1]`, `[1,0]`, `[2,3]` : deux leads, effectifs 2 et 1, dénominateur 3, fréquences calculables 2/3 et 1/3. Tester lead invalide, doublon de slot, slot hors 0–5 et ordre stable en cas d’égalité.
- [ ] Implémenter les identifiants canoniques `lead-0-1` et le tri par effectif décroissant puis tuple de slots. Garder les effectifs entiers ; ne pas stocker de pourcentages arrondis.
- [ ] Valider `sum(count)=sampleSize`, maximum quinze paires, chaque `turn1=null`. Le résultat enrichi contient exactement `completedPhases=['A']`.
- [ ] Exécuter `uv run pytest tests/unit/test_phase_a.py -q` avec vérification de l’échec initial puis du succès.

## Tâche 2 — Exécution et publication réelle

**Fichiers Python :** compléter `workflow/phases/phase_a.py`, `workflow/registry.py` ; créer `tests/integration/test_phase_a_run.py` et `docs/recettes/phase-a.md`.

- [ ] Boucler sur `EngineAdapter.preview` avec graines dérivées de la graine du run et de l’index de tentative. Respecter les timeouts et plafonds du socle. Vérifier la stochasticité identifiée par l’audit, sans exiger artificiellement plusieurs leads si le modèle n’en choisit qu’un.
- [ ] Mettre à jour `progress` pour les observations valides et les compteurs d’essais dans les métadonnées, sans publier de faux résultat B. Conserver une petite trace de contrôle A localement avec empreinte, sans la rendre accessible au futur LLM.
- [ ] Publier la section A, ses mesures et `result_revision=1` via le repository. En cible A, obtenir paused/PENDING STATS, bail libéré, `report=NULL`, `finished_at=NULL`.
- [ ] Enregistrer A comme première capacité disponible. Un lancement ciblant B reste refusé tant que le plan B n’est pas déployé.
- [ ] Tester une vraie transaction de publication, un moteur contrôlé qui échoue entre deux previews, et une perte de bail : aucune réussite partielle annoncée pour une phase incomplète, aucune écriture après annulation.
- [ ] Exécuter `uv run pytest tests/integration/test_phase_a_run.py -q` sur base jetable et les tests de contrats SQL concernés.

## Tâche 3 — Lecture frontend et recette de fin de plan

**Fichiers Angular :** compléter `src/app/features/matchup/opponent-leads.ts/html`, `matchup.ts/html` et `e2e/analysis-progressive-live.spec.ts`. Pas de nouvel écran ; utiliser les contrôles du socle.

- [ ] Afficher les leads triés avec `count/sampleSize` et pourcentage, le profil et « En pause après A ». Au clic sur un lead, le détail indique que tour 1 et back ne sont pas encore calculés. Les deux autres onglets restent accessibles avec un état d’attente explicite.
- [ ] Tester une seule paire observée, plusieurs paires, sélection conservée après refresh, absence de zéros fictifs pour B et absence de badge « rapport complet ».
- [ ] Démarrer stack/API/worker/Angular selon la recette commune. Depuis un matchup compatible, lancer jusqu’à A en smoke, ou exécuter `uv run python scripts/analysis-smoke.py --matchup-id UUID --target A --profile smoke`.
- [ ] Ouvrir l’URL avec runId, vérifier **20 observations**, les leads et leur somme ; recharger la page et constater le même checkpoint en base. Aucune interception du moteur ou de GraphQL pour cette recette.
- [ ] Lancer un **nouveau run standard** jusqu’à A : 1 000 observations ; mesurer durée et ressources. Garder son runId pour poursuivre avec B. Le profil ne se change pas sur un run existant.
- [ ] Exécuter tests Angular/lint/build et `npm run e2e:analysis-live` configuré pour A ; consigner versions, effectifs, URL et capture dans `docs/recettes/phase-a.md`.

**Résultat visible attendu :** classement réel des leads adverses dans le premier onglet. Suite : [phase B](2026-10-31-06-phase-b-tour1-back.md), enrichissement du même run.
