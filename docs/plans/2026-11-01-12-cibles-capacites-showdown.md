# Plan 12 — Cibles des capacités issues du Dex Showdown

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher la portée réelle de chaque capacité, notamment `Tailwind (camp du lanceur)`, sans inventer de cible individuelle pour une capacité collective.

**Architecture:** Résoudre les métadonnées dans le bridge Python à partir du Dex du Showdown local utilisé pour les simulations. Transmettre une catégorie canonique dans les actions persistées ; Angular traduit cette catégorie. Aucun appel PokeAPI depuis les composants ni requête réseau par action.

**Tech Stack:** Showdown/Dex local, Node pour l'export JSON du catalogue, bridge Python/poke-env, Pydantic, JSONB/PostGraphile, Angular 22/Transloco.

**Spec:** Demande utilisateur du 1er novembre 2026 : rechercher la cible de chaque move dans Showdown ou PokeAPI et afficher toutes les catégories disponibles. Ce plan précède obligatoirement le [plan 13 — fiabilité des simulations et des sources](2026-11-01-13-fiabilite-simulations-traces-gameplan.md).

## Décisions et limites

- Choix technique proposé : **Showdown local**, déjà dépendance du moteur, plutôt que PokeAPI dont le catalogue peut différer du format/mod joué. Ne pas utiliser une version npm « latest » indépendante du serveur.
- Référence inspectée : `engine-runtime/vendor/vgc-bench/pokemon-showdown/sim/dex-moves.ts`, type `MoveTarget` ; `sim/dex.ts`, `Dex.forFormat`. [Source officielle du type et de sa documentation](https://github.com/smogon/pokemon-showdown/blob/master/sim/dex-moves.ts). La révision locale fait foi si elle diffère de la branche distante.
- `poke_env.battle.Move.target` expose aussi les catégories, mais son catalogue embarqué n'est pas automatiquement celui du serveur. Utiliser le `target` de la requête moteur lorsqu'il existe ; sinon le Dex local correspondant au format.
- Une capacité sans **choix individuel** a néanmoins une portée : ne pas remplacer toutes ces catégories par « sans cible ». `self` désigne le lanceur ; `randomNormal` et `scripted` ne sont pas des zones de dégâts.
- Distinguer portée déclarée, choix initial et exécution. Une attaque collective reste collective même si une seule cible a survécu ou reçu des dégâts. Une attaque individuelle redirigée reste individuelle.
- Ce plan corrige la classification et l'affichage, pas la capture des switches ni les historiques complets. Ces corrections appartiennent au plan 13. Ne pas déclarer B ou E fiables à la seule réussite de ce plan.
- Garder l'enveloppe `SimulationResultV2` et les budgets existants. Pas de nouvelle version de résultat ni conversion supposée fiable des anciens rapports. À la livraison, utiliser des analyses neuves ; le nettoyage local sera explicite et préservera les équipes.
- Lire les skills `angular-developer` et `design-system` avant les changements Angular.

## Contrat partagé et matrice d'affichage

Créer `ShowdownMoveTarget` avec **les 15 valeurs exactes** ci-dessous. Ajouter aux actions `kind='move'` : `moveId: string | null`, `targetType: ShowdownMoveTarget | null`, `targetSource: 'request' | 'dex' | 'unknown'`. Garder `move` pour le nom affiché, `actor`, `targets`, tera et les switches existants.

Pour les catégories sans cible individuelle choisie, `targets` contient un seul `{kind:'zone', zone:<valeur Showdown>}` : ici `zone` est le discriminant historique du contrat, pas l'affirmation d'une attaque de zone. Pour les catégories individuelles choisies, conserver les références Pokémon disponibles. La portée a priorité sur le token de cible apparent d'un message `|move|`.

| `targetType` | Représentation / libellé FR attendu |
| --- | --- |
| `normal` | `→ <Pokémon>` ; un Pokémon adjacent, allié ou adverse selon le choix |
| `adjacentFoe` | `→ <Pokémon adverse adjacent>` |
| `adjacentAlly` | `→ <allié adjacent>` |
| `adjacentAllyOrSelf` | `→ <allié ou lanceur effectivement choisi>` |
| `any` | `→ <Pokémon choisi>` ; **ne signifie pas tous les Pokémon** |
| `self` | `(lanceur)` |
| `allAdjacent` | `(tous les Pokémon adjacents, alliés compris)` |
| `allAdjacentFoes` | `(tous les adversaires adjacents)` |
| `allies` | `(tous les Pokémon actifs du camp du lanceur)` |
| `allySide` | `(camp du lanceur)` |
| `allyTeam` | `(équipe du lanceur)` ; inclut le back selon la mécanique de la capacité |
| `foeSide` | `(camp adverse)` |
| `all` | `(terrain / ensemble du combat)` ; la catégorie seule ne prouve pas que tous les Pokémon sont touchés |
| `randomNormal` | `(adversaire adjacent choisi aléatoirement)` |
| `scripted` | `(cible déterminée par la mécanique de la capacité)` |

Le dernier groupe ne reçoit pas de flèche vers un Pokémon sur la base du seul replay. Les destinataires réellement observés pourront être détaillés séparément par le plan 13. Ne pas inventer une sous-classification de `all` à partir du nom de la capacité.

Capacité non reconnue : `targetType=null`, `targetSource='unknown'`, affichage « portée non déterminée ». Pour une catégorie individuelle connue mais une référence absente : « cible non déterminée ». Aucune transformation silencieuse en `field`, en slot 0 ou en cible arbitraire. Ce mode diagnostique permet le premier jalon malgré les `Unknown` actuels ; le plan 13 refusera ces actions comme décisions valides de B.

## Points de revue

| Cas à risque | Vérification propriétaire |
| --- | --- |
| Tailwind accompagné d'un token Pokémon dans le replay | Tâches 2 et 3 : `allySide` gagne |
| Earthquake/Make It Rain avec une seule cible visible | Tâche 2 : la portée collective reste intacte |
| `any`, `adjacentAllyOrSelf`, cible alliée | Tâches 1–3 : pas de confusion collectif/individuel |
| Même capacité dans deux mods, ou cible modifiée en combat | Tâches 1–2 : format/cache et priorité de la requête |
| Move ou enum inconnu | Tâches 1 et 3 : diagnostic explicite, aucune cible inventée |

## Tâche 1 — Catalogue du Showdown réellement utilisé

**Créer :** `engine-runtime/scripts/export_move_targets.cjs`, `engine-runtime/src/pokecoach_vgc_bridge/move_targets.py`, `engine-runtime/tests/test_move_targets.py`.
**Modifier :** `engine-runtime/src/pokecoach_vgc_bridge/vgc_real.py`, `vgc_source.py` et la recette de démarrage si nécessaire.

**Interfaces :** `load_move_catalog(showdown_root, battle_format) -> MoveTargetCatalog` ; `resolve_move_target(move_id, catalog, request_target=None) -> MoveTargetInfo`. `MoveTargetInfo` contient id canonique, nom, catégorie et provenance. Le catalogue conserve format/mod, génération et empreinte de la révision locale.

- [ ] Écrire les tests paramétrés des 15 catégories, des alias de noms et des identifiants inconnus ; tester deux catalogues de mods différents sans collision de cache.
- [ ] Exporter les données via le Dex **compilé du serveur local** avec `Dex.forFormat(battle_format)` et ses entrées de moves résolues. Inclure les héritages/modifications du mod. Aucun parsing regex de `moves.ts`, aucun catalogue manuel par nom.
- [ ] Charger une fois le catalogue par processus/format/empreinte, avec cache mémoire. Ne pas lancer Node par simulation ni par attaque. Échec de chargement explicite avant lancement des simulations si le serveur ou son catalogue n'est pas identifiable.
- [ ] Préférer `request_target` valide à la valeur statique pour les variations de cible selon l'état du Pokémon ; garder les deux dans la provenance technique si elles diffèrent. Sans contexte pour une variation dynamique, ne pas prétendre connaître la portée effective : conserver le diagnostic et la limite pour le plan 13.
- [ ] Vérifier dans le Dex local Tailwind, Protect, Helping Hand, Fake Out, Rock Slide, Earthquake et Make It Rain. Comparer les sorties du helper aux entrées du même Dex ; aucun besoin de réseau.
- [ ] Depuis `engine-runtime`, exécuter `uv run pytest tests/test_move_targets.py -q` ; résultat attendu : suite verte, y compris les tests utilisant le Dex local pour le format courant.

## Tâche 2 — Normalisation et propagation du contrat

**Modifier runtime :** `extract_turn_one.py`, `normalization.py`, `battle_runner.py`, `fixture_sim.py` ; tests `test_extract_turn_one.py` et `test_full_battle_trace.py`.
**Modifier backend :** `src/pokecoach_python/engine/contracts.py`, `engine/stub_adapter.py`, `schemas/analysis_result.py`, `workflow/aggregation/turn_one.py`, `contracts/simulation-result-v2.schema.json`, `contracts/battle-trace-v1.schema.json`, exemples et fixtures concernés.
**Créer :** `src/pokecoach_python/schemas/battle_actions.py`, `tests/unit/test_battle_action_targets.py` pour centraliser la validation des actions aujourd'hui largement typées `Any`.

- [ ] Ajouter un test reproduisant `Tailwind` avec token cible `p2a: Aerodactyl` : le résultat porte `targetType='allySide'` et `targets=[{kind:'zone',zone:'allySide'}]`.
- [ ] Tester les capacités de zone avec token individuel, Protect, Helping Hand, attaque ciblant un allié, `any`, aléatoire et scripted. Vérifier qu'aucune catégorie n'est perdue lors du passage bridge → backend → JSON.
- [ ] Remplacer les listes hardcodées `_FIELD_MOVE_IDS`/`_SELF_TARGET_MOVE_IDS` et les heuristiques de `_targets_for_move` par le résolveur. La recherche des destinataires ne décide plus de la portée du move.
- [ ] Ajouter une validation partagée des actions et réutiliser ses types dans les sections B/D et traces, sans changer les autres sections du résultat. Séparer erreur de contrat, portée inconnue et cible individuelle inconnue.
- [ ] Adapter les clés canoniques : id de capacité, acteur, catégorie, cibles individuelles pertinentes et tera ; exclure provenance du catalogue et texte traduit. Deux Tailwind ne deviennent pas deux choix différents à cause d'un token de replay décoratif.
- [ ] Mettre à jour stub/fixtures avec le même contrat ; conserver leur provenance fictive. Exporter les schémas et exemples à jour.
- [ ] Vérifier les contraintes SQL existantes dans conception : si elles inspectent les anciennes valeurs de zone, ajouter une migration Flyway au prochain numéro libre et ses tests/profil, sans modifier une migration appliquée. Sinon documenter qu'aucune modification SQL n'est nécessaire.
- [ ] Exécuter les tests runtime ciblés et `uv run pytest tests/unit/test_battle_action_targets.py tests/unit/test_conditioned_openings.py -q` dans le backend ; vérifier que les dénominateurs sont inchangés et que seuls les regroupements corrigés peuvent évoluer.

## Tâche 3 — Affichage Angular exhaustif

**Base :** `../pokecoach2-angular/pokecoach-angular/`.
**Modifier :** `src/app/core/models/matchup.model.ts`, `core/models/simulation-result.model.ts`, `core/graphql/simulation-result-validator.ts`, `core/matchup/battle-action-display.ts`, leurs tests, `core/matchup/simulation-display.ts`, `public/i18n/fr.json`, `en.json` et les appelants du formatter.

- [ ] Écrire les tests de rendu des 15 catégories et des références individuelles de chaque côté. Cas obligatoire : `Aerodactyl : Tailwind (camp du lanceur)` ; jamais `Tailwind → Aerodactyl`.
- [ ] Étendre le type `ActionTarget` et le parseur avec le contrat ci-dessus ; valider réellement catégories et références au lieu de vérifier seulement que `targets` est un tableau.
- [ ] Injecter les libellés Transloco dans le formatter pur ou lui transmettre une fonction de traduction ; aucun appel PokeAPI et aucune liste de capacités dans Angular. Garder le code Showdown dans les données, jamais un libellé FR comme clé d'agrégation.
- [ ] Appliquer le même rendu aux ouvertures B, à notre recommandation, à leurs alternatives et aux T1 D dans la modal. Afficher les états inconnus explicitement, sans fausse flèche.
- [ ] Tester FR/EN et passage par le validateur GraphQL. Depuis l'application Angular : `npm test -- --watch=false`, `npm run lint`, `npm run build` ; résultat attendu : succès.

## Tâche 4 — Recette et livraison autonome

**Créer :** `docs/recettes/cibles-capacites.md`. Actualiser les contrats et liens de documentation des deux dépôts.

- [ ] Sur base de test, lancer une analyse neuve jusqu'à B avec le moteur réel et des sets comportant Tailwind et des attaques ciblées/collectives. Vérifier le Dex utilisé, le JSON enregistré, la réponse GraphQL et le rendu après refresh.
- [ ] Vérifier également le rendu D, sans considérer ses historiques complets comme corrigés à ce stade. Ne pas imposer à un run BC aléatoire de produire chaque capacité : couvrir les 15 classes par fixtures et les exemples centraux par une recette Showdown contrôlée.
- [ ] Archiver les identifiants de runs et la correspondance « capacité → catégorie → libellé ». Vérifier l'absence de requêtes PokeAPI ajoutées et de lancement Node par action.
- [ ] Préparer un nettoyage ciblé des anciennes analyses locales lors de la livraison coordonnée backend/frontend, conformément au choix utilisateur ; ne pas effacer équipes, migrations ou checkpoints. Ne pas normaliser rétrospectivement des actions dont la provenance manque.

**Terminé lorsque :** chaque catégorie Showdown a un rendu explicite, les capacités collectives ne portent plus de cible individuelle trompeuse et la même information traverse tous les composants. Le plan 13 peut alors utiliser ce contrat sans réimplémenter la classification.
