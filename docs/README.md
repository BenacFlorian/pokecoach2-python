# Documents Python

Ces documents préparent le développement ; ils ne signifient pas que le serveur ou les simulations sont déjà implémentés.

1. [Initialisation Python](plans/2026-10-31-01-python-initialisation.md) — Devbox, uv, FastAPI, connexion PostgreSQL et image pour la stack existante.
2. [Route de démonstration](plans/2026-10-31-02-python-demo-seed.md) — réinstallation complète de la seed via FastAPI, appel Angular et relecture PostGraphile.
3. [Adaptations du système existant](plans/2026-10-31-03-adaptations-resultats-progressifs.md) — tout le §10 de la spec : SQL, droits, contrats v2, résultats partiels et lecteur Angular.
4. [Socle du workflow](plans/2026-10-31-04-socle-workflow-python.md) — audit/adaptateur VGC-Bench, commandes HTTP, worker, idempotence, pause/continuation et outils de recette.
5. [Phase A — Leads adverses](plans/2026-10-31-05-phase-a-leads.md) — premier résultat réel dans « Opponent Leads ».
6. [Phase B — Tour 1 et back](plans/2026-10-31-06-phase-b-tour1-back.md) — enrichissement du premier onglet pour chaque lead.
7. [Phase C — Sélection et premier tour](plans/2026-10-31-07-phase-c-selection.md) — calculs déterministes de « Lead & pick » et stockage des combats complets.
8. [Phase D — Affinage](plans/2026-10-31-08-phase-d-affinage.md) — configuration ciblée et résultats supplémentaires, sans LLM.
9. [Phase E — Gameplan et win condition](plans/2026-10-31-09-phase-e-gameplan-llm.md) — LLM sur les seuls combats complets C/D, puis rapport complet.

Complément au socle : [plan 04b — moteur réel VGC-Bench](plans/2026-10-31-04b-moteur-reel-vgc-bench.md), à réaliser **avant le plan 09 LLM**. Il raccorde preview, tour 1 et combats complets, puis fait rejouer les recettes B/C/D avec le checkpoint BC.

État moteur (plan 04b en cours) : protocole subprocess, bridge `engine-runtime/`, plus de repli stub dans `VgcBenchEngineAdapter`. Le runtime BC + Showdown (`vgc_real`) reste à brancher une fois VGC-Bench installé dans le venv moteur ; le bridge **fixture** (`POKECOACH_BRIDGE_FIXTURE=1`) sert aux tests et au diagnostic sans Torch. Recette : [moteur-reel.md](recettes/moteur-reel.md).

Pour reprendre le développement actuel : terminer 04b, rejouer A–D avec des **nouveaux runs réels**, puis réaliser E. La [spécification du workflow réel](specs/2026-10-31-workflow-analyse-matchup.md) définit le contrat commun. Ne pas continuer un run créé avec le stub en basculant simplement le `.env` vers le moteur réel.

Après chaque plan A/B/C/D, lancer le process jusqu’à la phase concernée : le même run stocke son résultat partiel, se met en pause et reste consultable après rechargement du frontend. Le plan suivant le continue et l’enrichit sans recalculer ses phases validées. E ajoute uniquement le plan global et la win condition, puis publie le rapport complet.

Chaque plan de phase se termine par une recette avec les vrais services : profil `smoke` pour vérifier le câblage, puis budget `standard`. La dernière recette teste aussi un run neuf de A à E sans pause. Les points 1–4 ne dépendent jamais du LLM.

Le choix validé pour la démonstration est de **réinstaller la seed complète**, pas d’associer le rapport fictif à n’importe quel matchup choisi dans l’interface.
