# Plan 13 — Quatre imposé, traces complètes et gameplan cohérent

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Garantir que B joue notre sélection recommandée, que les choix et changements sont fidèlement enregistrés, et que E conseille uniquement notre quatre à partir de véritables historiques D complets.

**Architecture:** Renforcer le bridge existant par une capture des requêtes, décisions acceptées et événements, puis normaliser ces informations avec des identités stables. Les agrégations conservent les décisions initiales séparément de leurs résolutions. E vérifie la qualité des sources et les références Pokémon avant publication ; Angular restitue les changements observés.

**Tech Stack:** VGC-Bench/poke-env/Showdown, Python, Pydantic, PostgreSQL/JSONB/PostGraphile, LangGraph existant, ChatOpenAI via DeepInfra, Angular/Transloco.

**Prérequis obligatoire :** [plan 12 — cibles des capacités](2026-11-01-12-cibles-capacites-showdown.md) terminé, y compris contrats et Angular.

**Spec :** demande utilisateur et diagnostic du 1er novembre 2026. Ce plan corrige l'implémentation des [ouvertures conditionnées](2026-11-01-10-ouvertures-conditionnees-au-lead.md), de [D global](2026-11-01-11-phase-d-affinage-global.md) et de [E](2026-10-31-09-phase-e-gameplan-llm.md), sans ajouter de phase métier.

## Constats vérifiés et limites du diagnostic

- Run inspecté : `ba80b8d0-81de-4013-8ffc-ed7e70a6a427`. C et les deux combats D enregistrent notre quatre `[3,5,0,1]` : Staraptor, Gholdengo, Excadrill, Tyranitar. D passe déjà un quatre imposé au moteur ; préserver ce fonctionnement, renforcer sa preuve plutôt que le remplacer.
- `vgc_real._first_turn` ignore `ourSelection`, pourtant envoyé par `VgcBenchAdapter.first_turn`. B impose le lead mais laisse le modèle choisir notre back. `aggregate_openings` attache ensuite ces observations à la sélection C sans contrôle du quatre réellement joué.
- `extract_turn_one.py` lit les événements `move`, ignore les switches et retombe sur une dernière capacité ou `Unknown` s'il ne trouve pas deux attaques. Un choix non exécuté (flinch, KO, etc.) ne peut pas être retrouvé de façon fiable par cette méthode.
- La ligne `Fake Out → Tyranitar (1/5)` existe en base. Une reproduction en mémoire confirme qu'un switch Staraptor → Tyranitar produit ce rendu sans préserver le switch. Les traces B sauvegardées ne permettent pas d'affirmer que ce switch précis explique l'occurrence historique.
- `battle_runner._run_full_battle` fournit un `FullBattleTrace()` vide à `build_turns_from_battle_summary`. Les deux D inspectés ont 12 et 8 entrées de tours, avec des actions seulement au T1 et zéro événement. Le validateur E accepte leur nombre de tours comme preuve de complétude.
- `prepare_sources` transmet les six membres de notre équipe. `validate_strategy_against_sources` contrôle les références de `strengths`, pas les noms cités dans les phrases. E recommande ainsi Sinistcha hors du quatre.

## Contraintes globales

- Ordre **A → C → B → D → synthesis**, budgets actuels inchangés, D global sur les leads A et backs B, sélection C fixe. E ne rejoue aucun combat et ne reçoit pas les agrégats A/B/C.
- Garder DeepInfra, `deepseek-ai/DeepSeek-V4.1-Flash-1017`, `ChatOpenAI`, `DEEPINFRA_API_KEY`. Ne jamais journaliser le secret ni changer de fournisseur/modèle pour masquer un défaut de sources.
- Garder les quotas de sélection E : 15 % victoires, 15 % défaites, 20 % parties serrées ; conserver les règles d'arrondi/déduplication déjà implémentées et leurs tests. Pas de catégorie atypique.
- Conserver les deux nœuds séquentiels du graphe, le stockage réel, le schéma Pydantic et l'échec explicite validés par l'utilisateur. Un appel métier LLM, pas de boucle de réparation ni moteur de preuve stratégique.
- Utiliser `langgraph-generate-graph` pour les modifications du graphe ; ses décisions structurelles sont déjà validées. Utiliser `angular-developer` et `design-system` pour les changements frontend.
- Pas de nouvelle version de résultat. Mettre à jour les contrats actuels de façon coordonnée et nettoyer les analyses locales obsolètes lors de la bascule, en préservant équipes et matchups. Ne pas poursuivre un ancien run comme si ses traces étaient devenues fiables.
- Le nettoyage n'est pas exécuté par la rédaction de ce plan. Préparer une commande ciblée avec aperçu des lignes concernées ; arrêter les workers avant son exécution pour éviter les publications concurrentes.

## Contrat de capture et restitution

1. **Identité :** `PokemonRef={side,slot}` indexe le snapshot original ; `ActivePosition={side,position:'a'|'b'}` indexe une position du terrain. Maintenir un mapping explicite entre identifiants Showdown, snapshots et positions, jamais déduit du rang courant dans un dictionnaire. Résoudre p1/p2 à partir des joueurs réels.
2. **Choix initial :** conserver les deux décisions légales acceptées avant résolution, y compris switch, tera et autres modificateurs du format réellement utilisés (ex. méga-évolution). Pour une capacité à cible choisie : position choisie et occupant initial ; les catégories du plan 12 restent la référence de portée.
3. **Résolution :** événements ordonnés du tour, occupant après switch, redirection éventuelle, exécution ou non-exécution, destinataires et dégâts observés. Un ordre envoyé puis rejeté n'est pas un choix accepté. Une décision n'est pas une preuve d'impact réussi.
4. **Statistiques B :** clé canonique de la paire de décisions initiales, identique pour deux décisions qui ont ensuite touché des occupants différents de la même position. Ne pas utiliser le Pokémon entré après switch comme si le modèle l'avait connu au moment du choix.
5. **Détails B :** enrichir les lignes de fréquence par `resolutions: [{value: ActionPairResolution, count: int}]`. Leur somme vaut le `count` de cette ligne. `ActionPairResolution` contient deux éléments alignés sur les acteurs : `actor`, `executed`, `reason` nullable, `selectedTarget` nullable, `resolvedTargets`, `cause` (`unchanged`, `switch`, `redirect`, `other`, `not-executed`). Une cible sélectionnée contient position et occupant initial ; les cibles résolues sont des références Pokémon. Ne pas transformer une capacité collective en attaque ciblée ; ses destinataires restent des observations séparées.
6. **Pas de fausse association :** distributions adverse et nôtre distinctes. Les détails de résolution viennent des mêmes échantillons que chaque ligne affichée, jamais de la juxtaposition des deux modes. Conserver une clé d'échantillon interne pour l'audit, sans prétendre que notre recommandation répond à l'ordre adverse exact.

Pour une attaque réellement exécutée après un switch identifié, le détail affiche `Incineroar : Fake Out → Tyranitar (slot Staraptor)`. Si plusieurs résolutions existent, afficher d'abord la cible initiale puis leurs variantes et effectifs ; ne pas attribuer la variante à toutes les occurrences. Une redirection est libellée « redirigée », pas « switch ». Sans preuve, aucune annotation inventée.

## Points de revue

| Risque | Test propriétaire |
| --- | --- |
| Notre back libre en B, ou lead réordonné par canonicalisation | Tâche 1 : vérification des requêtes et sélections acceptées |
| Switch/flinch assimilé à `Unknown`, cible alliée ou p1/p2 inversés | Tâche 2 : traces contrôlées et mapping stable |
| Tours vides acceptés comme historique complet ; dégâts absents devenant zéro | Tâche 3 : source complète/incomplète et qualité des statistiques |
| Agrégation mélangeant décision initiale et occupant après switch | Tâche 4 : une décision, plusieurs résolutions |
| Sinistcha dans les deux équipes, interdit chez nous mais permis comme menace adverse | Tâche 5 : références avec côté et validation des phrases |

## Tâche 1 — Imposer et vérifier notre quatre en B

**Modifier :** `src/pokecoach_python/engine/contracts.py`, `engine/vgc_bench_adapter.py`, `workflow/phases/phase_b.py`, `workflow/aggregation/openings.py` ; runtime `vgc_real.py`, `battle_runner.py`, `battle_session.py`, `normalization.py`, `fixture_sim.py` ; adapter le stub.
**Tests :** créer `engine-runtime/tests/test_conditioned_first_turn.py`, compléter `tests/unit/test_phase_b.py`, `tests/unit/test_conditioned_openings.py` et `tests/integration/test_phase_b_run.py`.

**Interfaces :** `_run_first_turn_battle(..., our_four, our_lead)` impose le quatre ordonné avec le lead en tête ; `TurnOneRecord.payload` expose `ourFourSlots`, `ourLeadSlots`, `opponentLeadSlots`, `opponentBackPair` et une preuve du preview accepté. Réutiliser le mécanisme d'imposition de D.

- [ ] Écrire un test où la politique choisirait un autre back sans contrainte : la commande preview et la requête Showdown suivante doivent confirmer exactement le quatre de C.
- [ ] Transmettre `ourSelection` jusqu'à `create_policy_pair(our_imposed_four=...)`. Préserver l'ordre des deux leads et leur correspondance a/b ; la canonicalisation d'une clé non ordonnée ne doit pas réordonner les positions réellement jouées.
- [ ] Enregistrer commande soumise puis sélection confirmée par le simulateur ; ne pas recopier la demande comme seule preuve. Valider avant agrégation l'égalité du quatre, du lead et des positions avec C, ainsi que le lead adverse demandé.
- [ ] Tester rejet d'un mauvais quatre, mauvaise orientation et preview non confirmé ; ces échantillons ne comptent pas dans le budget valide. Les reprises bornées existantes restent en place.
- [ ] Vérifier la confidentialité : notre politique voit l'état légal de son joueur, pas le choix adverse en cours ou son back caché. Le contrôleur qui impose les sélections n'enrichit pas les observations des politiques.
- [ ] Exécuter les tests cités ; faire un appel réel `first_turn` avec un quatre fixé dont le back diffère du choix libre. Archiver demande et confirmation. Rejouer les tests D pour vérifier l'absence de régression de ses contraintes.

## Tâche 2 — Capturer les décisions et les événements avec leurs identités

**Créer runtime :** `src/pokecoach_vgc_bridge/battle_capture.py`, `pokemon_identity.py`, `tests/test_battle_capture.py`, `tests/test_pokemon_identity.py`.
**Modifier runtime :** `battle_session.py`, `extract_turn_one.py`, `battle_runner.py`, `full_battle_trace.py`, `normalization.py`, tests existants d'extraction.

**Interfaces :** `BattleCapture` accumule requêtes, ordres, rejets/confirmations et événements ordonnés par battle/turn/request ; `PokemonIdentityMap` résout snapshot, identifiant de protocole et position active. `normalize_turn(capture, identities, move_catalog, turn) -> NormalizedTurn` restitue choix initiaux et résolutions.

- [ ] Écrire des traces de test pour switch Staraptor → Tyranitar avant Fake Out, flinch, KO avant action, miss/Protect, cible alliée, redirection et deux côtés inversés. Le switch est un choix ; le choix du Pokémon empêché d'agir subsiste sans attaque exécutée inventée.
- [ ] Installer les hooks dans les joueurs réels et le traitement des messages de la version poke-env utilisée. Définir l'acceptation par la progression des requêtes/résolution après l'ordre sans erreur ; écarter les ordres rejetés/remplacés, conserver la preuve. Les doubles demandes et reconnects ne doivent pas compter deux décisions.
- [ ] Construire les identités depuis les snapshots/équipes envoyées et requêtes de chaque côté. Gérer surnoms, changements de forme et méga-évolution sans changer le slot snapshot. Utiliser les identifiants privés du contrôleur lorsque le protocole public est ambigu (ex. Illusion), sans les révéler aux politiques. Une identité non résolue produit une erreur de capture, jamais un index supposé.
- [ ] Capturer l'occupant initial puis chaque switch/drag, et distinguer choix sélectionné, redirection et destinataire observé. Utiliser `move_targets` du plan 12 ; résoudre aussi les cibles modifiées dynamiquement depuis la requête/l'exécution moteur, avec provenance.
- [ ] Retirer les fallbacks `last_move`, `Unknown`, slot 0 et back inventé pour les nouveaux échantillons admis en B. Une action réellement choisie mais non exécutée reste valide ; une décision perdue ne l'est pas.
- [ ] Tester les capacités appelées par une autre capacité : conserver l'ordre choisi et les effets exécutés séparément ; ne pas remplacer la décision du modèle par le move appelé.
- [ ] Exécuter les tests runtime, puis une recette Showdown contrôlée prouvant le switch et le choix empêché. Ces contrôles ne dépendent pas de la chance qu'un BC les produise pendant un smoke.

## Tâche 3 — Persister de vrais historiques complets C/D et bloquer E sinon

**Modifier :** runtime `battle_runner.py`, `full_battle_trace.py` ; backend `workflow/battle_records.py`, `llm/battle_sources.py`, `llm/battle_statistics.py`, `db/analysis_repository.py`, `contracts/battle-trace-v1.schema.json`.
**Tests :** `engine-runtime/tests/test_full_battle_trace.py`, `test_fixed_full_battle.py`, `tests/unit/test_battle_sources.py`, `tests/unit/test_phase_e_run.py` ; créer `tests/unit/test_battle_statistics_capture.py`.

- [ ] Écrire un test reproduisant les 12 entrées dont 11 vides : E doit refuser cette source malgré `finished=true`. Écrire aussi un vrai tour sans attaque (switch ou immobilisation) avec événements explicatifs : il doit être accepté.
- [ ] Brancher la capture de la tâche 2 à **tous les tours** C/D. Supprimer la fabrication de tours vides depuis un simple compteur. Gérer les événements avant T1, remplacements après KO et fin de combat ; stocker le terminal à partir du moteur, pas d'une issue reconstruite.
- [ ] Persister ordres acceptés, switches, capacités, cibles, effets utiles (statuts, boosts, météo, terrain, protections, vitesse), HP/dégâts/soins/KO et issue. Conserver un ordre stable des événements et leur provenance ; éliminer uniquement les messages de chat/protocole redondants, pas les événements stratégiques.
- [ ] Vérifier la continuité des requêtes/résolutions et la présence de la preuve terminale. Un simple nombre de tours ou un booléen auto-déclaré n'est pas une preuve de capture complète. Tester l'absence d'un tour intermédiaire et d'un événement terminal.
- [ ] Dériver entrées en jeu et survivants avec le mapping stable. Ne pas déclarer tous les sélectionnés « entrés » lorsque la trace manque. Calculer les dégâts depuis les variations HP observées, séparer dégâts directs, résiduels, soins, substituts et dégâts sans attribution certaine.
- [ ] Si aucun événement de dégâts n'a été capturé dans une bataille ayant des pertes HP, signaler une capture incomplète ; ne pas produire des moyennes nulles présentées comme mesures réelles. Respecter la précision réellement disponible (HP exacts ou arrondis), avec dénominateurs documentés.
- [ ] Refuser les anciennes traces insuffisantes avant tout appel LLM. Conserver A–D visibles en cas d'échec E, sans publication de rapport réussi. Ne pas tenter de compléter une bataille par imagination ou de rejouer silencieusement des combats dans E.
- [ ] Revalider le budget de contexte E avec ces vrais historiques, beaucoup plus riches que les coquilles actuelles. Préserver les règles existantes de sélection et d'échec sur dépassement ; ne jamais tronquer des tours ou envoyer un combat incomplet pour faire tenir le prompt. Tester explicitement ce dépassement.
- [ ] Exécuter les tests runtime et backend cités ; sur un nouveau D réel, comparer au moins un combat complet à sa trace moteur, notamment un tour après T1, les dégâts et le terminal. Les sources normalisées E doivent préserver tous les tours du combat retenu.

## Tâche 4 — Agrégation conditionnelle et affichage des switches

**Modifier Python :** `workflow/aggregation/openings.py`, `turn_one.py`, `refinement.py`, `workflow/phases/phase_b.py`, `schemas/battle_actions.py` créé au plan 12, `schemas/analysis_result.py`, schémas/exemples et tests des agrégations.
**Modifier Angular :** sous `../pokecoach2-angular/pokecoach-angular/`, modèles/validateur/formatter du plan 12, `core/matchup/simulation-display.ts`, `features/matchup/opening-study-panel.ts/html`, modal d'affinage D existante, traductions et tests correspondants.

- [ ] Tester deux échantillons avec la même décision « cibler la position initiale de Staraptor », l'un sans switch, l'autre vers Tyranitar : une seule décision agrégée, deux résolutions distinctes et leurs effectifs exacts.
- [ ] Calculer fréquences et recommandation B depuis les décisions acceptées des deux côtés sur le même ensemble valide. Publier les `resolutions` décrites dans le contrat ; ne pas les intégrer dans la clé de décision ni changer le dénominateur du mode recommandé.
- [ ] Conserver les captures compactes T1 utilisées dans `execution_metadata.phases.B.samples`, avec clé d'échantillon, sélection acceptée, décisions et événements nécessaires à leur audit. Les métadonnées de checkpoint doivent les conserver atomiquement et à la reprise ; ne pas y placer les secrets ni répliquer les longues traces C/D déjà persistées.
- [ ] Afficher la recommandation comme décision avant résolution. Pour les exemples observés, afficher `Fake Out → Tyranitar (slot Staraptor)` seulement lorsque les événements prouvent cette substitution ; montrer le switch de notre côté. Si plusieurs variantes : détail par variante avec count/total de la ligne.
- [ ] Tester rendu sans switch, avec switch, plusieurs variantes, redirection et non-exécution. Ne pas afficher « a touché » pour un move bloqué ou raté. Pour les capacités collectives, garder le libellé de portée du plan 12, même si les occupants ont changé.
- [ ] Appliquer les conventions aux T1 D sans remplacer les recommandations B par des statistiques D. Tester conservation des champs lors du parsing GraphQL et après refresh.
- [ ] Exécuter les suites d'agrégation, les tests Angular concernés, `npm run lint`, `npm run build` et les E2E `conditioned-openings`/`global-refinement`. Si une contrainte SQL inspecte les champs modifiés, créer une nouvelle migration et son test ; ne pas relâcher les protections d'immutabilité ou de bail.

## Tâche 5 — Sources E limitées à notre quatre et conseils référencés

**Modifier :** `llm/source_preparation.py`, `graphs/matchup_gameplan/models.py`, `prompts/generate_gameplan_prompt.py`, `nodes/generate_gameplan_node.py`, `workflow/phases/phase_e.py` et tests existants de sources/graphe/E.
**Créer :** `llm/strategy_references.py`, `tests/unit/test_strategy_references.py`.

**Interfaces :** `validate_source_selection(sources, selection_c)` exige le même quatre/lead dans C, D et les sources ; `render_strategy_references(draft, allowed_refs, team_names) -> StrategyOutput` produit le contrat texte actuel après validation. Garder les deux nœuds existants : ce rendu est un utilitaire du nœud de génération/validation.

- [ ] Tester que les sources de notre côté ne contiennent que les slots `[3,5,0,1]`, avec leurs sets exacts et leurs rôles lead/back explicites. Aucun contexte de Sinistcha/Milotic de notre côté. Préserver les slots originaux : ne pas renuméroter le quatre en 0–3.
- [ ] Vérifier chaque bataille D contre la sélection C du run, et non uniquement contre la première bataille D. Charger les six adversaires comme contexte d'équipe si utile, en distinguant sélection/présence observée et inconnue ; une menace présentée comme observée doit être étayée par les combats transmis.
- [ ] Limiter le prompt à la préparation stratégique de ce quatre. Interdire nouvelle sélection, rôle attribué à un Pokémon absent, statistiques inventées et réécriture des recommandations T1. Préserver la distinction observations/inférences.
- [ ] Renforcer la sortie **interne** Pydantic : dans tous les champs de prose, les noms Pokémon sont référencés par jetons `{{ours:3}}` / `{{opponent:4}}`, rendus ensuite en noms lisibles. Valider côté/slot et présence autorisée avant rendu, y compris opening/midgame/endgame, explications des highlights et win condition. Les highlights gardent leurs références structurées.
- [ ] Rejeter jeton inconnu/malformé ou référence de notre côté hors du quatre. Détecter les noms/alias connus des snapshots écrits littéralement hors des jetons pour éviter le contournement évident ; ne pas utiliser un simple blacklist « Sinistcha », puisque le même Pokémon peut être adverse. Ce contrôle porte sur les références, pas sur la vérité de toute la stratégie.
- [ ] Garder le dictionnaire de contrôle des six membres de notre snapshot côté validateur uniquement : les Pokémon exclus ne sont pas réinjectés dans le prompt pour expliquer ce qu'il ne faut pas choisir. Les noms d'espèces totalement inventés et les erreurs tactiques ne sont pas réputés tous détectables par ce garde-fou ; aucune promesse de preuve stratégique.
- [ ] Tester « utiliser notre Sinistcha » rejeté, menace `{{opponent:4}}` acceptée si observée, et `{{ours:3}}` rendu en Staraptor. Tester référence dans chaque champ textuel, citation de combat inexistante et fournisseur renvoyant des noms littéraux au lieu du contrat. Une sortie invalide devient une erreur E ; aucun retrait silencieux de phrase ni sélection modifiée.
- [ ] Vérifier que le rapport public conserve ses champs texte existants après rendu : pas de jetons visibles dans Angular ni nouveau graphe. Enregistrer sources, sortie interne/rendue et contrôles dans les métadonnées techniques sans secret ; garder la publication atomique protégée par le bail.
- [ ] Exécuter les tests unitaires puis intégration E avec client contrôlé. Faire ensuite une recette réelle DeepInfra sur des D nouvellement capturés ; le test unitaire n'appelle jamais le fournisseur.

## Tâche 6 — Recette globale, nettoyage et documentation

**Créer :** `docs/recettes/fiabilite-simulations-gameplan.md`. Actualiser `docs/specs/2026-10-31-workflow-analyse-matchup.md`, `docs/README.md`, les contrats et recettes moteur/E.

- [ ] Préparer la bascule coordonnée : arrêter les acquisitions worker, terminer/annuler les runs actifs par les mécanismes existants, sauvegarder au besoin les exemples fautifs puis nettoyer uniquement leurs analyses/sources/commandes dépendantes. Tester le nettoyage sur une base jetable en respectant FK et triggers ; pas de réécriture manuelle des rapports terminaux ni suppression globale du volume PostgreSQL.
- [ ] Lancer un nouveau run réel jusqu'à C, poursuivre B, D, puis synthesis. À chaque checkpoint vérifier le quatre, les identités, les décisions, les résolutions et la persistance après refresh. L'échec d'une phase conserve le dernier checkpoint valide.
- [ ] Vérifier des traces contrôlées où le switch est certain : le front montre la cible après switch avec le bon occupant initial ; aucun texte n'est reconstruit en joignant deux distributions indépendantes.
- [ ] Sur D, vérifier l'historique complet, les survivants, au moins une attribution de dégâts et les limites de mesure. Sur E, inspecter le payload préparé et les références rendues, notamment l'absence de notre Sinistcha hors du quatre.
- [ ] Rejouer un run neuf jusqu'à synthesis sans pauses. Contrôler budgets, progression, stockage final et résultat de toutes les suites Python/runtime/Angular concernées ; lancer les tests SQL sur base jetable si le contrat SQL a changé.
- [ ] Archiver runIds, empreinte moteur/catalogue, sélection, traces minimales probantes et captures du front dans la recette. Déclarer clairement que les anciens rapports ont été invalidés, sans inventer une réparation rétroactive.

**Terminé lorsque :** B impose réellement le quatre/lead C ; les choix non exécutés et switches sont capturés ; les cibles collectives restent correctes ; les détails individuels distinguent position initiale et destinataire observé ; D fournit des historiques complets ; E refuse les sources insuffisantes et ne conseille aucun Pokémon de notre équipe hors du quatre.
