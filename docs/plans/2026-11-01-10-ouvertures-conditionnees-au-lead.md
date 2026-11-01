# Plan 10 — Backend : ouvertures conditionnées à notre sélection

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Calculer les premiers tours des deux côtés face à chaque lead adverse, avec notre quatre et notre lead recommandés fixés au préalable.

**Architecture:** Réorganiser les phases existantes en **A → C → B → D**. C sélectionne notre quatre/lead avec des combats complets ; B rejoue les ouvertures pour cette sélection fixe et publie les distributions des deux côtés. Remplacer directement le contrat actuel après nettoyage des anciennes analyses, puis transmettre ce contrat unique au frontend.

**Limite du périmètre :** la phase E viendra conclure le processus dans son plan dédié, encore à implémenter. Ce plan s’arrête au checkpoint D et ne prévoit aucune implémentation, adaptation ni recette de E ; son plan reste inchangé.

**Tech Stack:** Python/Pydantic, adaptateur VGC-Bench et bridge existants, PostgreSQL/Flyway, PostGraphile, tests pytest du backend et du runtime moteur.

**Spec:** Décision utilisateur du 1er novembre 2026 et [workflow existant](../specs/2026-10-31-workflow-analyse-matchup.md). Le présent plan remplace ses choix concernant l’ordre des phases et l’origine des recommandations T1. Le [plan frontend associé](../../../pokecoach2-angular/docs/plans/2026-11-01-05-ouvertures-conditionnees-lead-pick.md) consomme le contrat défini ici.

## Décisions métier

| Phase | Rôle dans le nouveau workflow | Résultat disponible |
| --- | --- | --- |
| A | Observer les leads adverses au preview | Fréquences des leads |
| C | Combats complets contre le top adverse de A ; comparer nos sélections | Notre quatre et notre lead recommandés, comparaisons et limites |
| B | Pour chaque lead observé en A, imposer notre sélection C et ce lead adverse, puis jouer le T1 | Actions adverses possibles et notre recommandation T1, cibles, alternatives et back |
| D | Combats complets ciblés avec notre sélection C et le back le plus fréquent de B | Affinage séparé, sans écraser les statistiques B |

- B étudie **tous les leads observés en A**, pas seulement le top étudié en C. Notre quatre et notre lead sont identiques dans toutes ses observations ; le back adverse reste échantillonné selon la politique moteur documentée.
- Les deux joueurs choisissent avant la résolution du tour. Notre modèle n’accède ni à la décision adverse en cours ni à son back caché ; fixer les choix dans le simulateur ne doit pas les révéler à l’autre politique.
- Notre recommandation est la **paire d’actions la plus fréquente du modèle** dans ce contexte, puis les autres paires par fréquence. Aucun classement par taux de victoire B : ces simulations s’arrêtent au premier tour. Les comparaisons de victoire C conservent leur rôle de sélection du quatre/lead.
- Les modes des deux côtés sont deux distributions distinctes. Ne pas présenter leur juxtaposition comme une paire de réponses observée ensemble ou comme une réponse optimale à l’action adverse exacte.
- Préserver les budgets de `simulation_budgets.py` : au moment de la rédaction, standard A=100, B=5/lead, C=5/lead, D=2 ; smoke A=20, B=3/lead, C=3/lead, D=2. **Ne pas remettre les anciens budgets des documents.** Figer les valeurs résolues dans les nouveaux runs pour garder les mêmes volumes après continuation.

## Constats du code à traiter

- `phase_b.py` n’impose aujourd’hui que le lead adverse, sans notre sélection. C exige un checkpoint A+B alors que son agrégation de sélection peut fonctionner à partir des fréquences A et de ses combats complets.
- `aggregate_selections()` calcule aussi des premiers tours issus des combats C. Ils ne doivent plus alimenter les recommandations affichées pour les nouveaux runs.
- Le bridge `extract_turn_one.py` expose surtout les actions adverses. Le chemin `first_turn` sait recevoir un lead de notre côté mais doit aussi imposer le quatre complet et retourner les choix acceptés des deux joueurs.
- Des fallbacks actuels reconstruisent des actions/cibles depuis le replay ou une dernière capacité, avec valeurs par défaut. Ils ne constituent pas une preuve de choix accepté : le nouveau calcul doit utiliser les décisions enregistrées, sans `Unknown`, cible 0 ou back inventé.
- L’ordre A/B/C est présent dans `schemas/analysis_result.py`, le registre, le repository, les validations SQL et le frontend. V1.0.12 fige notamment tout `leadPick` une fois publié : éviter de placer des champs B à l’intérieur de la sélection C immutable.

## Contrat partagé : remplacement du format actuel

**Décision utilisateur : aucun nouveau versionnement des résultats et aucune rétrocompatibilité.** Nettoyer les anciennes analyses avant la bascule, puis produire uniquement le contrat décrit ici, dans le stockage JSONB existant. Ne pas créer de format v3, de `workflowVersion`, de lecteur historique ni de conversion. Les champs techniques de version déjà imposés par le schéma peuvent garder leur valeur actuelle, sans incrément ni branche de compatibilité ; leur suppression physique n’est pas nécessaire à ce chantier.

Préfixes couverts par ce plan : `[]`, `[A]`, `[A,C]`, `[A,C,B]`, `[A,C,B,D]`. `result_revision` suit le nombre de checkpoints publiés, pas l’ordre alphabétique des phases. D reste un checkpoint partiel : ne pas le présenter comme une analyse finale complète.

| Champ de l’enveloppe | Propriétaire et contenu |
| --- | --- |
| `opponentLeads` | A : `{sampleSize, leads:[{id, slots, count}]}` ; pas de `turn1` et aucune modification ultérieure |
| `leadPick` | C : `{selection, comparisons, selectionRuleVersion, limitations}` ; pas de `firstTurns` et aucune modification ultérieure |
| `openings` | B : contexte de notre sélection et observations des deux côtés détaillées ci-dessous |
| `refinement` | D : configuration ciblée, résultats et tours 1 D séparés ; conserver le contrat utile existant |
| `gameplan`, `winCondition` | Réservés, restent `null` dans les nouveaux checkpoints couverts par ce plan |

Tous les champs de section valent `null` avant leur phase. L’enveloppe garde `source`, `schemaVersion` et `completedPhases`.

`openings` :

```text
{
  selection: { ourFourSlots: [slot × 4], ourLeadSlots: [slot × 2] },
  recommendationRule: "model-frequency-v1",
  samplingPolicy: <identifiant/version de la politique conditionnelle>,
  byOpponentLead: [{
    opponentLeadId, opponentLeadSlots: [slot × 2], sampleSize,
    opponentActions: Frequency<ActionPair>[],
    ourActions: Frequency<ActionPair>[],
    recommendation: Frequency<ActionPair>,
    backPairs: Frequency<SlotPair>[],
    backSlotMarginals: Frequency<Slot>[],
    endStateNotes: string[]
  }]
}
```

`Frequency<T>={value:T,count:int,sampleSize:int}` ; `ActionPair` contient exactement les deux choix initiaux, avec acteur côté/slot, move et cibles ou switch, ainsi que tera si choisi. Réutiliser les actions normalisées du moteur. `recommendation` est exactement la première ligne de `ourActions`, triées par count décroissant puis clé canonique stable. `opponentActions` suit le même tri ; aucune nouvelle inférence métier n’est faite par Angular.

`openings.selection` doit égaler la sélection C du même run. Les tuples de lead de cette sélection fixent l’ordre retenu pour nos positions ; garder la correspondance entre positions moteur et slots du snapshot, même lorsque les clés d’agrégation des leads adverses sont non ordonnées. Chaque entrée B référence un lead A, exactement une fois. Les deux distributions d’actions ont le même nombre de parties valides et chacune somme à `sampleSize`. Les marges de back utilisent **le nombre de parties** comme dénominateur, donc leur somme de présences vaut `2 × sampleSize`.

Conserver le back et les observations B dans `openings`, sans dupliquer ces données dans A. Le frontend pourra lire ces backs dans « Opponent Leads » avec un libellé précisant qu’ils sont observés face à notre sélection recommandée.

## Points de revue

| Risque | Test propriétaire |
| --- | --- |
| Anciennes analyses ou commandes encore présentes après nettoyage | Tâches 1–2 |
| Lead fixé mais mauvais back/quatre de notre côté | Tâche 3 |
| Choix adverses révélés à notre politique ou choix non exécutés perdus | Tâche 3 |
| Un seul lead étudié en B ou fallback des anciens T1 C | Tâche 4 |
| Publication B modifiant la sélection C, budget changé en pause | Tâches 1–2 et 4 |

## Tâche 1 — Nettoyage des analyses et remplacement du contrat

**Fichiers Python :** modifier `src/pokecoach_python/schemas/analysis_result.py` et les validateurs existants ; publier `contracts/simulation-result.schema.json`, `contracts/examples/openings/empty.json`, `a.json`, `ac.json`, `acb.json`, `acbd.json` ; créer `tests/unit/test_conditioned_result.py`. Remplacer les anciennes fixtures de résultat, sans maintenir plusieurs lecteurs.

**Fichiers conception :** ajouter une migration Flyway `V<prochaine_version>__replace_conditioned_openings_contract.sql`, son profil `_repoindex.md`, `tests/sql/080_conditioned_openings.sql` et un script de nettoyage local `scripts/reset-analysis-data.sql`. Adapter les validateurs, contraintes, grants dans `sql/afterMigrate.sql` et `docs/data-contract.md`. Conserver l’historique Flyway : numéroter une migration SQL ne signifie pas versionner les résultats métier. Ne pas réécrire les migrations déjà appliquées.

**Interfaces :** adapter le modèle de résultat actuel, `OpeningStudy`, `OpeningsSection`, `validate_partial_result(payload)` ; centraliser l’ordre des phases dans le registre existant. SQL : remplacer les validateurs actuels et adapter les triggers au contrat unique, sans dispatch par version.

- [ ] Préparer le nettoyage pour l’exécution du plan, sans l’exécuter pendant sa rédaction : arrêter les lancements, workers et commandes en cours ; cibler la base locale du projet. Conserver les équipes et les associations de matchup pour relancer les analyses.
- [ ] Dans le script de nettoyage, supprimer les anciennes commandes d’analyse/idempotence, combats, runs et résultats dépendants dans l’ordre des clés étrangères ; vider aussi les rapports et références au dernier run portés par les matchups et réinitialiser leur progression à l’état sans analyse. Inspecter les dépendances réelles et traiter les protections des runs terminaux dans cette opération de maintenance uniquement. Exécuter atomiquement, sans désactiver durablement les contraintes ni toucher à l’historique Flyway.
- [ ] Vérifier après nettoyage : aucun ancien rapport, checkpoint, combat ou commande ne subsiste ; les équipes/matchups conservés n’ont plus de référence orpheline. Appliquer la migration du contrat avant toute relance de calcul. Ne pas réinstaller une seed contenant l’ancien format.
- [ ] Écrire les exemples progressifs : après AC, sélection présente mais ouvertures null ; après ACB, toutes les ouvertures présentes ; champs C identiques dans les fichiers AC, ACB et ACBD. Ajouter un exemple avec plusieurs leads, actions adverses et nôtres différentes, switches, cibles alliées et faibles effectifs.
- [ ] Valider en Python les tuples/slots, côtés, actions, références A, sélection B=C, dénominateurs, sommes, ordre de classement et recommandation exacte. SQL garantit ordre, sections disponibles, invariants d’état et immutabilité ; utiliser les mêmes exemples pour les deux suites.
- [ ] Remplacer les contraintes et triggers : C publiable après A, B après AC ; A/C immuables, seul `openings` apparaît en B, seul `refinement` en D. Les nouveaux checkpoints restent partiels, y compris après D ; ne pas autoriser leur promotion en rapport final complet. Supprimer les branches dédiées aux anciens formats.
- [ ] Vérifier les triggers des combats C/D, pas seulement `partial_result` : C doit pouvoir insérer ses combats après A et D seulement après ACB. Conserver les garanties de bail, d’idempotence et de run terminal immutable.
- [ ] Exécuter `uv run pytest tests/unit/test_conditioned_result.py -q` puis `./scripts/test-db.sh` depuis conception sur une base jetable. Précharger des analyses obsolètes, exécuter le nettoyage, vérifier leur disparition et la conservation des équipes/matchups, puis créer un run conforme au nouveau contrat. Une seconde exécution du nettoyage doit laisser la base dans le même état vide d’analyses.

## Tâche 2 — Orchestration A→C→B et reprise des nouveaux runs

**Fichiers :** modifier `workflow/registry.py`, `workflow/runner.py`, `workflow/types.py`, `db/analysis_repository.py`, `services/analysis_commands.py`, `schemas/analysis_commands.py`, `workflow/budgets.py`, les scripts de recette et les tests de cycle de vie/idempotence.

- [ ] Figer budgets effectifs, top C, checkpoint et politique de sampling dans les paramètres des nouveaux runs. Les accès de budget des phases utilisent ces paramètres, avec la configuration centrale comme valeur de création uniquement. Aucun nouveau champ de version de résultat ou de workflow.
- [ ] Exposer `phaseOrder=['A','C','B','D']` dans `/analysis-capabilities`. `phases` ne contient que le préfixe effectivement exécutable ; si C manque, B n’est pas une cible disponible. D est la cible maximale de cette livraison.
- [ ] Garder les routes et corps de commande start/continue existants, sans négociation de version. Préserver l’idempotence des nouvelles commandes : même clé et même corps retrouvent le même run, corps différent sous la même clé refusé. Les anciennes commandes auront été supprimées lors du nettoyage.
- [ ] Définir les cibles par ce nouvel ordre : cible C exécute A+C ; cible B exécute A+C+B ; après pause C, continuer vers B est une progression valide. Vérifier la première phase manquante plutôt qu’une comparaison alphabétique ou un préfixe A/B/C codé en dur.
- [ ] Publier chaque phase dans une transaction courte, avec révision et métadonnées. Garder paused/queued/running et le polling actuels ; le `process_status` peut passer de PENDING GAME SIMULATIONS en C à PENDING STATS en B, ce n’est pas une régression. La phase explicite fait foi.
- [ ] Déployer backend et frontend pendant le même arrêt des lancements ; exécuter le nettoyage de la tâche 1 avant de redémarrer les workers. Aucun ancien run ne doit être repris ou converti.
- [ ] Tester lancement jusqu’à C, continuation C→B puis D, lancement direct jusqu’à D, retry d’une nouvelle commande, changement de budgets entre deux phases, annulation et erreur B laissant AC consultable. Aucun calcul C ne doit être refait au retry de lecture frontend.

## Tâche 3 — Tour 1 moteur : fixer notre quatre et capturer les deux joueurs

**Fichiers :** modifier `engine/contracts.py`, `engine/vgc_bench_adapter.py`, le protocole/serveur existant et, dans `engine-runtime/src/pokecoach_vgc_bridge/`, `battle_runner.py`, `extract_turn_one.py`, les constructeurs de records et de joueurs identifiés par l’audit. Étendre `engine-runtime/tests/test_extract_turn_one.py`, ajouter `test_conditioned_openings.py` et `tests/integration/test_conditioned_first_turn.py`.

**Interface :** `SimulationRequest` transporte `our_selection`, `our_lead_slots`, `opponent_lead`. Étendre le record T1/protocole avec `ourFourSlots`, `ourLeadSlots`, `opponentLeadSlots`, `opponentBackPair`, `ourActions`, `opponentActions`, observations et preuve de provenance. Adapter ensemble le protocole interne et son consommateur ; les capacités doivent annoncer cette collecte bilatérale et les contraintes supportées.

- [ ] Envoyer notre quatre/lead depuis le backend et les imposer au preview dans le simulateur, pas seulement dans la réponse JSON. Le bridge actuel impose surtout les leads : compléter l’imposition du quatre et vérifier les sélections réellement acceptées pour les deux côtés.
- [ ] Laisser le back adverse échantillonné suivant la politique conditionnelle retenue en 04b. Notre propre back reste celui de C dans tous les échantillons. Enregistrer l’orientation réellement jouée du lead adverse, sans la confondre avec sa clé non ordonnée A.
- [ ] Capturer les décisions légales acceptées des deux joueurs avant résolution, puis jouer le T1 jusqu’à son terme. Ne pas fabriquer une seconde action lorsqu’un Pokémon a flinch ou été mis K.-O. : son choix initial est enregistré séparément de son exécution.
- [ ] Supprimer pour ce chemin les fallbacks `Unknown`, cible slot 0 et back déduit arbitrairement. Si les choix ne sont pas récupérables, produire une erreur technique bornée ; ne pas compter l’échantillon ni compléter une moitié de distribution avec des données fictives.
- [ ] Vérifier côté/slot des acteurs, cibles alliées/adverses, capacités de zone, switch et tera. Une action de notre côté ne doit jamais être reconstruite en supposant que p1 est toujours « nous » sans mapping réel.
- [ ] Tester des décisions simultanées avec un moteur instrumenté : la fonction de choix de notre joueur ne reçoit ni l’ordre du tour adverse ni son back caché. Contrôler indépendamment que notre sélection imposée est effectivement jouée.
- [ ] Exécuter les tests runtime puis un vrai appel `first_turn` répété sur une sélection fixe et deux leads adverses différents. Comparer demandes, traces et payloads ; un test sur le stub ne valide pas ce jalon.

## Tâche 4 — C sélectionne ; B calcule les ouvertures conditionnelles

**Fichiers :** modifier `workflow/phases/phase_c.py`, `phase_b.py`, `workflow/aggregation/selections.py` ; créer `workflow/aggregation/openings.py`, `tests/unit/test_conditioned_openings.py`. Adapter `tests/integration/test_phase_c_run.py`, `test_phase_b_run.py`.

**Interfaces :** `aggregate_selection(battles, leads_a) -> LeadPick` ; `aggregate_openings(records, selection, opponent_lead) -> OpeningStudy` ; garder les entrées `run_phase_c(context)` et `run_phase_b(context)` du registre.

- [ ] C exige désormais `[A]`, lit les fréquences A et joue ses combats complets contre le top configuré. Conserver la règle de choix du quatre/lead, ses comparaisons et limitations. Ne publier aucun premier tour recommandé à partir des taux de victoire C dans le nouveau contrat.
- [ ] B exige `[A,C]` et reprend exactement la sélection C. Pour chaque lead A, construire une requête T1 avec notre quatre et notre lead fixés, puis valider les choix réellement observés avant d’accepter l’échantillon.
- [ ] Agréger séparément `opponentActions` et `ourActions` sur le **même ensemble d’échantillons complets valides**. Trier par count décroissant puis clé canonique des actions (acteur, capacité, cibles, switch/tera). Ne pas conditionner notre distribution sur l’action adverse exécutée.
- [ ] Déduire la recommandation de la première paire de `ourActions`, stocker son effectif et le dénominateur. Garder toutes les autres paires comme alternatives observées. Tester une situation où ce mode diffère de l’ancien classement par victoire C et vérifier que le nouveau mode est retenu.
- [ ] Produire les backs par paire, marges de présence et observations de fin de tour à partir de ces mêmes simulations. Une action/mapping manquant invalide la simulation complète ; les erreurs/rejets sont comptés séparément du budget valide.
- [ ] Publier B atomiquement dans `openings`, avec `[A,C,B]` et révision 3. Un échec après certains leads conserve AC et ses choix ; ne pas présenter les leads non traités comme des zéros. A et C restent strictement égaux avant/après B.
- [ ] Tester permutations d’acteurs, cibles distinctes, ex æquo, deux leads adverses générant des distributions différentes pour notre même sélection, rejet d’un mauvais quatre, et un quatrième lead hors top C néanmoins étudié en B.

## Tâche 5 — Adapter l’affinage D

**Fichiers :** modifier `workflow/phases/phase_d.py`, `workflow/aggregation/refinement.py` et les tests D. Actualiser uniquement les sections A–D de la spec métier pour le nouveau contrat lors de l’implémentation.

- [ ] D exige `[A,C,B]`. Lire son lead adverse dans A, sa paire de back dans `openings.byOpponentLead`, et notre quatre/lead dans C. Vérifier que le contexte de B égale C avant de sélectionner ce back.
- [ ] Conserver l’affinage comme un résultat séparé ; ne pas remplacer la recommandation B par la distribution D, obtenue avec un back adverse désormais fixé.
- [ ] Conserver l’enregistrement des combats complets C/D et leur provenance moteur réelle. Publier D comme checkpoint partiel consultable, puis mettre le run en pause lorsque la cible D est atteinte.
- [ ] Vérifier par tests que l’ajout D ne modifie ni les choix de C ni les distributions/recommandations B.

## Tâche 6 — Livraison backend, exemples frontend et recette

**Fichiers :** compléter `docs/recettes/ouvertures-conditionnees.md`, les sections A–D de `docs/specs/2026-10-31-workflow-analyse-matchup.md`, `docs/README.md`, scripts de recette/benchmark et exemples JSON du contrat unique.

- [ ] Exporter le schéma JSON et les exemples validés que le plan frontend utilisera ; documenter noms exacts, nouvel ordre, nettoyage et invariants. Réserver les fixtures au test.
- [ ] Rejouer tests Python, runtime et SQL sur base jetable nettoyée ; vérifier qu’aucune seed de démonstration ou route de reset ne réintroduit les anciens rapports. Adapter ces fixtures au nouveau contrat partiel ou ne réinstaller que les équipes/matchups sans résultat. Aucun code du frontend n’est requis pour vérifier les réponses GraphQL à ce stade.
- [ ] Créer un nouveau run réel smoke jusqu’à C : voir `[A,C]`, sélection présente, `openings=null`. Continuer jusqu’à B : voir toutes les entrées A, notre même sélection, actions des deux côtés et recommandation égale au mode de notre distribution. Continuer jusqu’à D et vérifier la persistance.
- [ ] Faire un second run direct jusqu’à D ; contrôler les checkpoints et les effectifs des budgets actuels. Modifier uniquement la configuration de budget entre deux runs pour vérifier qu’un run en pause ne change pas de volume.
- [ ] Archiver runIds, paramètres, comptes, traces vérifiées et JSON GraphQL. Après réalisation du plan frontend, reprendre cette recette dans les deux onglets et après refresh.

## Fin et ordre de livraison

Backend prêt quand les réponses démontrent la sélection fixe, les deux distributions conditionnelles et le nouvel ordre ; la nouvelle interface est livrée par le plan Angular suivant. La bascule comprend le nettoyage des anciennes analyses et le redémarrage coordonné des services avec le contrat unique.

Hors périmètre : la phase E et son plan dédié, optimiser les ouvertures par des combats supplémentaires, augmenter les budgets, modifier le modèle BC ou ajouter une nouvelle phase métier.
