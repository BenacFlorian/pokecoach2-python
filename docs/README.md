# Documents Python

Ces documents préparent le développement ; ils ne signifient pas que le serveur ou les simulations sont déjà implémentés.

**Suite du POC — corrections du 1er novembre 2026, dans cet ordre :**

1. [Plan 12 — Cibles des capacités issues de Showdown](plans/2026-11-01-12-cibles-capacites-showdown.md) : les 15 catégories du Dex local, normalisation backend et affichage Angular des portées individuelles/collectives. Corrige notamment `Tailwind → Aerodactyl`.
2. [Plan 13 — Quatre imposé, traces complètes et gameplan cohérent](plans/2026-11-01-13-fiabilite-simulations-traces-gameplan.md) : imposition du quatre en B, décisions acceptées et switches, historiques complets C/D, contrôles des sources et des références LLM, détails de résolution Angular.

Ces deux plans couvrent les changements Python **et Angular** et sont à implémenter, pas déjà exécutés. Ils partent du code actuel où E existe : le diagnostic a trouvé des traces D limitées au T1 et des conseils mentionnant un Pokémon hors du quatre. Les mentions historiques « E reste à implémenter » ci-dessous ne décrivent plus l'état courant. Le plan 13 conserve l'architecture de E et dépend du contrat de ciblage du plan 12.

Évolution validée le 1er novembre 2026 : [plan backend 10 — ouvertures conditionnées à notre sélection](plans/2026-11-01-10-ouvertures-conditionnees-au-lead.md), puis [plan frontend 5](../../pokecoach2-angular/docs/plans/2026-11-01-05-ouvertures-conditionnees-lead-pick.md). Ils couvrent **A → C → B → D**, le remplacement du contrat actuel après nettoyage des anciennes analyses et les tours 1 des deux côtés pour notre quatre/lead fixes. **E est hors périmètre** : son plan dédié reste à implémenter et viendra conclure le processus. Les plans historiques ci-dessous décrivent l’ancien ordre jusqu’à l’application de cette évolution.

Nouvelle évolution à implémenter : [plan 11 — phase D, évaluation globale de notre sélection](plans/2026-11-01-11-phase-d-affinage-global.md). Il remplace l’affinage sur un scénario unique par un échantillonnage sur **tous les leads de A et leurs backs B**, avec notre sélection C fixe. Budget conservé à **2 standard / 2 smoke pour tester**, correction des contraintes du moteur réel et adaptation du bloc Angular D incluses. Les anciennes analyses seront nettoyées à la bascule, sans nouvelle version de résultat ; E reste hors périmètre. Les descriptions de D dans les plans 08 et 10 restent historiques jusqu’à cette refonte.

1. [Initialisation Python](plans/2026-10-31-01-python-initialisation.md) — Devbox, uv, FastAPI, connexion PostgreSQL et image pour la stack existante.
2. [Route de démonstration](plans/2026-10-31-02-python-demo-seed.md) — réinstallation complète de la seed via FastAPI, appel Angular et relecture PostGraphile.
3. [Adaptations du système existant](plans/2026-10-31-03-adaptations-resultats-progressifs.md) — tout le §10 de la spec : SQL, droits, contrats v2, résultats partiels et lecteur Angular.
4. [Socle du workflow](plans/2026-10-31-04-socle-workflow-python.md) — audit/adaptateur VGC-Bench, commandes HTTP, worker, idempotence, pause/continuation et outils de recette.
5. [Phase A — Leads adverses](plans/2026-10-31-05-phase-a-leads.md) — premier résultat réel dans « Opponent Leads ».
6. [Phase B — Tour 1 et back](plans/2026-10-31-06-phase-b-tour1-back.md) — enrichissement du premier onglet pour chaque lead.
7. [Phase C — Sélection et premier tour](plans/2026-10-31-07-phase-c-selection.md) — calculs déterministes de « Lead & pick » et stockage des combats complets.
8. [Phase D — Affinage](plans/2026-10-31-08-phase-d-affinage.md) — configuration ciblée et résultats supplémentaires, sans LLM.
9. [Phase E — Synthèse des combats D](plans/2026-10-31-09-phase-e-gameplan-llm.md) — plan révisé : stats sur tous les D, logs sélectionnés à 15 % de victoires / 15 % de défaites / 20 % de parties serrées, graphe LangGraph à deux nœuds, conseils early/mid/endgame, menaces, Pokémon forts et win condition. Aucune simulation supplémentaire en E.

Complément au socle : [plan 04b — moteur réel VGC-Bench](plans/2026-10-31-04b-moteur-reel-vgc-bench.md), à réaliser **avant le plan 09 LLM**. Il raccorde preview, tour 1 et combats complets, puis fait rejouer les recettes B/C/D avec le checkpoint BC.

État moteur (plan 04b) : subprocess JSONL, bridge `engine-runtime/` (`fixture` CI + `vgc_real` si deps), phases **A–D** sur combats Showdown+BC quand `POKECOACH_ENGINE=vgc_bench`. Clôture : [cloture-04b.md](recettes/cloture-04b.md). Recette : [moteur-reel.md](recettes/moteur-reel.md), audit : [audits/vgc-bench.md](audits/vgc-bench.md).

Chantier actuel : A–D et la refonte frontend sont validées par l’utilisateur ; implémenter le plan E révisé ci-dessus. Il commence par vérifier et compléter la capture des historiques D, survivants et dégâts nécessaires à ses sources. Les traces limitées au T1 ne sont pas des sources complètes pour E. Le plan E prime sur les passages historiques C/D de la [spécification du workflow réel](specs/2026-10-31-workflow-analyse-matchup.md), à aligner lors de son implémentation. Ne pas continuer un run créé avec le stub en basculant simplement le `.env` vers le moteur réel.

Après chaque plan A/B/C/D, lancer le process jusqu’à la phase concernée : le même run stocke son résultat partiel, se met en pause et reste consultable après rechargement du frontend. Le plan suivant le continue et l’enrichit sans recalculer ses phases validées. E ajoute uniquement le plan global et la win condition, puis publie le rapport complet.

Chaque plan de phase se termine par une recette avec les vrais services : profil `smoke` pour vérifier le câblage, puis budget `standard`. Les effectifs par phase sont centralisés dans [`src/pokecoach_python/simulation_budgets.py`](../src/pokecoach_python/simulation_budgets.py). La dernière recette teste aussi un run neuf de A à E sans pause. Les points 1–4 ne dépendent jamais du LLM.

Le choix validé pour la démonstration est de **réinstaller la seed complète**, pas d’associer le rapport fictif à n’importe quel matchup choisi dans l’interface.
