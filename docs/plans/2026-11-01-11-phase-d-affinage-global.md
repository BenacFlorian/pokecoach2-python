# Plan 11 — Phase D : évaluation globale de notre sélection

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mesurer les résultats de notre quatre/lead recommandé sur N combats complets, avec des scénarios adverses échantillonnés selon les observations A/B, puis afficher cette évaluation dans le bloc D du frontend.

**Architecture:** Conserver A → C → B → D. C fournit notre sélection fixe ; A et B définissent la distribution des scénarios adverses. Préparer N scénarios reproductibles, jouer chacun avec des contraintes réellement appliquées dans Showdown, puis publier `refinement` sans modifier les sections A/C/B.

**Tech Stack:** Python/Pydantic, bridge VGC-Bench/Showdown, PostgreSQL/Flyway/PostGraphile, Angular/Transloco, pytest et Playwright existants.

**Spec:** Brief utilisateur « Refonte de la phase D (affinage global) », décisions explicites du 1er novembre 2026 ci-dessous, [workflow](../specs/2026-10-31-workflow-analyse-matchup.md) et [plan 10](2026-11-01-10-ouvertures-conditionnees-au-lead.md). Les décisions et corrections du présent document priment sur les passages des documents précédents décrivant D comme un scénario unique.

**Périmètre :** un plan coordonné backend, moteur, persistance et bloc Angular D. Aucun changement de la règle de sélection C ni des recommandations B. E viendra conclure le processus via son plan séparé ; son implémentation et ses recettes restent hors périmètre.

## 1. Décisions et corrections du brief

| Sujet | Décision retenue et raison |
| --- | --- |
| Population adverse | **Tous les leads de A de poids positif**, décision confirmée par l’utilisateur. Le top C n’intervient pas dans D. Une évaluation limitée au top C ne couvrirait que ce sous-ensemble. |
| Budget | Conserver **D=2 standard et D=2 smoke**, valeurs actuelles confirmées pour tester. N est le total de combats valides, jamais un multiplicateur par lead. Les valeurs restent configurables dans `simulation_budgets.py`. |
| Notre équipe | Quatre et lead identiques à `leadPick.selection` et `openings.selection`. D évalue cette sélection, ne l’optimise pas et ne remplace pas C. |
| Distribution adverse | Tirage avec remise d’un lead selon ses effectifs A, puis d’une paire de back selon ses effectifs B pour ce lead. Les données B sont déjà conditionnées à notre sélection C. |
| Données A/B invalides | Échec explicite avant les combats. Pas d’exclusion silencieuse, de prochain lead, de back inventé ou de renormalisation sur les seules données qui restent valides. |
| Échecs moteur | Rejouer le **même scénario** avec une autre seed de combat ; ne pas retirer un scénario pour remplacer celui qui échoue. Arrêter D si le budget ne peut être rempli. |
| Transparence | Histogramme des scénarios réellement joués dans le JSON et dans un détail repliable de l’UI. Un seul scénario répété N fois est un tirage possible, pas une anomalie. |
| Premiers tours D | Conserver les observations globales, séparées de B, avec un dénominateur propre si certains T1 ne sont pas exploitables. Elles ne constituent pas une nouvelle recommandation universelle. |
| Anciennes données | Décision de session maintenue : nettoyage des anciennes analyses, contrat remplacé directement, **aucune nouvelle version de résultat ni lecteur historique**. |

« Global » signifie ici : sur la distribution empirique du modèle observée en A/B, pour les équipes et réglages du run. Cela ne couvre ni les leads jamais observés en A, ni les backs jamais observés en B, ni la distribution réelle des joueurs humains. Le taux de victoire D est une observation sous cette distribution, pas une preuve que le quatre C est optimal. Avec N=2, la recette valide avant tout le fonctionnement technique.

## 2. Audit du code actuel et conséquences

Constats issus de la lecture du code, sans exécution de simulations pour rédiger ce plan :

- `workflow/phases/phase_d.py` sélectionne une unique `FixedBattleConfiguration`, puis joue tout le budget sur celle-ci. Sa limite actuelle vaut `max_attempts(N, multiplier=8)`.
- `workflow/aggregation/refinement.py` choisit le premier lead du top et le back B modal. Il canonicalise notre lead, ce qui peut perdre l’ordre de positions demandé ; conserver désormais le tuple de C lors de l’imposition.
- `_lead_weights` dans `selections.py` normalise sur les leads qu’on lui fournit. Son appel sur le top C ne convient pas à la nouvelle population D ; ne pas modifier C pour réutiliser ce helper privé.
- `simulation_budgets.py` contient bien 2/2 pour D. Le chiffre 10 du brief n’est pas l’état du code.
- **Contrainte moteur manquante :** `_run_full_battle` transmet seulement les leads à `create_policy_pair`. Le quatre de notre côté et le back adverse ne sont pas imposés au preview par ce chemin.
- **Preuve de back insuffisante :** `normalization.build_battle_record` remplit `participants.opponentBackPair` à partir du payload demandé. Cette valeur ne prouve pas que ce back a été joué. Un validateur comparant cette copie à la demande peut accepter un scénario erroné.
- Le paramètre `seed` est notamment utilisé dans les comptes joueurs. La lecture de `create_policy_pair` ne démontre pas un contrôle de tous les RNG de la politique et de Showdown : ne pas promettre des issues réelles identiques à seed égale.
- `aggregate_refinement` ignore les T1 dont la paire est absente mais conserve N comme dénominateur. L’extracteur peut aussi reconstruire une capacité depuis l’état final : les nouvelles statistiques D doivent distinguer un vrai T1 disponible d’une donnée absente.
- `tests/integration/test_phase_d_run.py` enchaîne les handlers avec un stub en mémoire ; ce test ne vérifie pas PostgreSQL. Ajouter une preuve de persistance réelle.
- Angular parse peu le contenu de `refinement`, puis affiche les limitations, les issues et les T1. Le contrat, son validateur et ce bloc doivent évoluer ensemble.

## 3. Distribution, seeds et erreurs

Pour chaque lead `l` de A de poids positif et chaque paire de back `b` de son entrée B :

```text
p(l)     = A.count(l) / somme_des_counts_A
p(b | l) = B.count(l, b) / somme_des_counts_B_pour_l
p(l, b)  = p(l) × p(b | l)
```

Exemple de test : A contient L1=60, L2=40. Les backs de L1 ont des counts 3 et 1 ; L2 a un seul back. Les poids des trois scénarios sont 0,45 ; 0,15 ; 0,40. Ne pas multiplier directement les counts A et B sans normaliser B par lead lorsque les effectifs B diffèrent.

Valider avant le tirage :

- A non vide, sampleSize positif, counts entiers non négatifs, somme des counts égale au sampleSize ; IDs et paires de leads uniques. Exclure uniquement les lignes de poids nul du support de tirage.
- Pour chaque lead A de poids positif, exactement une entrée B correspondante, même paire de slots, `sampleSize > 0`, backs distincts et disjoints du lead, slots entiers 0–5, counts positifs, dénominateurs cohérents et somme des counts égale au sampleSize B. Rejeter les doublons de paires après canonicalisation, les booléens et les nombres fractionnaires.
- `openings.selection == leadPick.selection`. Un lead sans back ou une ligne invalide est une erreur de checkpoint, même si le hasard n’aurait pas tiré ce lead sur les N parties.

Le constructeur de distribution trie les leads par clé canonique de slots/ID et les backs par paire canonique. Un ordre différent des listes JSON ne change pas les tirages. Ne pas dépendre de `hash()` Python, d’un RNG global ou de l’ordre de retour des requêtes SQL.

Pour chaque index `i` de 0 à N−1 :

1. Dériver une seed locale avec SHA256 de `run_seed:D:scenario:i` encodé en UTF-8, convertir ses huit premiers octets par `int.from_bytes(..., "big")`, créer un `random.Random` local, puis tirer le lead et son back via des seuils cumulés **entiers** et `randrange(total)`.
2. Figer ce scénario pour l’index. Les tirages des autres indices sont indépendants du nombre de retries.
3. Pour la tentative locale `a`, dériver la seed de combat avec SHA256 de `run_seed:D:battle:i:a`, avec la même conversion en entier. Séparer ainsi la sélection du scénario des aléas d’exécution.
4. Conserver au plus 8 tentatives par index, et au plus `8 × N` au total, cohérent avec le plafond actuel. Un index sans combat valide fait échouer D ; aucun rapport D partiellement rempli n’est publié.

Garanties testables : mêmes checkpoints A/C/B, paramètres, seed et implémentation de tirage → même liste de scénarios ; mêmes records valides → mêmes agrégats. Les tests de scénario et d’agrégation sont déterministes. Les issues du moteur réel ne sont pas déclarées reproductibles tant que tous ses RNG ne le sont pas ; ce chantier ne dépend pas d’une telle garantie.

## 4. Contrat minimal de `refinement`

Conserver le modèle/enveloppe actuels (`SimulationResultV2`, valeur technique `schemaVersion=2`) sans nouveau format parallèle. Remplacer la définition de `RefinementSection` en ajoutant les champs nécessaires :

```text
{
  configuration: LeadSelection,       // strictement la sélection C
  samplingPolicy: "weighted-ab",      // identifie la méthode, pas une version de rapport
  samplingScope: "all-observed-leads",
  sampleSize: N,
  outcomes: { wins: W, losses: L, draws: T },
  scenarioCounts: [{
    opponentLeadId,
    opponentLeadSlots: [slot, slot],
    opponentBackPair: [slot, slot],
    count
  }],
  firstTurnSampleSize: M,
  firstTurns: [{ value: ActionPair, count, sampleSize: M }],
  battleIds: [id × N],
  limitations: [texte]
}
```

Invariants :

- `W + L + T = N > 0`, counts entiers non négatifs, battleIds uniques et exactement N.
- Les lignes de `scenarioCounts` regroupent seulement les scénarios réellement joués, sont uniques, ont un count positif et somment à N. Chaque scénario appartient au support A/B. Tri par count décroissant puis clé lead/back.
- Le scénario attendu d’un combat est comparé au preview/bring observé **avant** son acceptation ; l’histogramme est calculé à partir des records acceptés, pas du seul planning envoyé au moteur.
- Taux de victoire affiché = `W/N`. Les nuls restent au dénominateur ; ne pas afficher `(W + T/2)/N` comme taux de victoire ni exclure les nuls.
- `0 ≤ M ≤ N`. Les paires T1 exploitables somment à M ; chaque ligne porte M. Pour M=0 : liste vide et état « aucune observation T1 exploitable ». Une partie complète valide sans paire T1 fiable reste dans W/L/T et l’histogramme, sans actions inventées.
- Les T1 doivent provenir des choix acceptés au tour 1 ou d’une trace complète démontrant les deux actions initiales. Une capacité « dernière utilisée » en fin de combat ne convient pas. Documenter leur provenance. Un flinch/KO n’autorise pas à inventer une deuxième action exécutée.
- Ne pas comparer les fréquences T1 globales D à une recommandation B sans rappeler que les scénarios sont mélangés. B reste la source de recommandation par lead.
- A, C, B demeurent identiques dans le résultat JSON avant/après publication D, hors enveloppe `completedPhases` et révision. `gameplan` et `winCondition` restent nuls.

Stocker dans `BattleRecord.meta.refinementSampling` l’index, le scénario demandé, l’identifiant de politique, la seed de scénario, la seed de combat et le numéro de tentative. Les participants observés restent séparés de ces intentions. Utiliser les payloads JSON existants, sans nouvelle table. Enregistrer dans `execution_slice` N, attempts/rejects/errors, politique, histogramme et empreinte du planning ; retirer l’unique `opponentLeadId` global.

## 5. Risques à couvrir

| Risque | Vérification propriétaire |
| --- | --- |
| D reste limité au top C ou surpondère les leads avec davantage de backs | Tâche 1 : poids exacts et lead hors top |
| Back demandé recopié dans le résultat sans avoir été joué | Tâche 2 : preview effectif et scénario volontairement différent |
| Retry changeant de scénario ou avalant une perte de bail | Tâche 4 : moteur défaillant, erreur DB et progression |
| Mélange de dénominateurs T1/combats ou de nuls/victoires | Tâches 3 et 5 : contrat et rendu |
| Ancien rapport ciblé affiché comme une évaluation globale | Tâches 5–6 : nettoyage, fixtures et caches |

## Tâche 1 — Distribution A/B et planning déterministe

**Créer :** `src/pokecoach_python/workflow/refinement_sampling.py`, `tests/unit/test_refinement_sampling.py`.

**Interfaces :** `OpponentScenario(lead_id, lead_slots, back_pair)` ; `RefinementSamplingPlan(our_selection, scenarios)` ; `build_refinement_plan(result: SimulationResultV2, *, seed: int, budget: int) -> RefinementSamplingPlan`. Le plan possède exactement N scénarios ordonnés ; la sélection garde l’ordre C. Garder la distribution et le tirage dans ce module pur, distinct de l’agrégation des résultats.

- [ ] Écrire les tests de support et poids sur l’exemple 60/40 et 3/1, avec un lead hors top C qui reste éligible. Tester tous les seuils d’un tirage entier avec un RNG contrôlé : vérifier les intervalles de poids sans test probabiliste fragile sur un grand N.
- [ ] Tester une séquence de référence pour seed fixée, l’égalité après permutation des listes A/B et la stabilité du préfixe quand le budget augmente. Ne pas exiger que deux seeds distinctes donnent forcément deux scénarios distincts.
- [ ] Tester absence de backs, mauvais slots, doublons, count nul/négatif/fractionnaire, somme incohérente, entrée B manquante et sélection B≠C. Les échecs surviennent avant tout appel moteur.
- [ ] Implémenter la distribution de la section 3 sans appeler `studied_opponent_lead_count` et sans changer `selections.py`. Avec un support d’un seul scénario, accepter N répétitions.
- [ ] Exécuter `uv run pytest tests/unit/test_refinement_sampling.py -q` depuis le dépôt Python. Réussite : poids, validations et séquences attendus, sans dépendance réseau/DB.

## Tâche 2 — Imposer et prouver le scénario dans le moteur réel

**Modifier :** `engine-runtime/src/pokecoach_vgc_bridge/battle_session.py`, `battle_runner.py`, `normalization.py`, `fixture_sim.py` et leurs appelants ; `src/pokecoach_python/engine/vgc_bench_adapter.py` seulement si le transport le nécessite.

**Tests :** créer `engine-runtime/tests/test_fixed_full_battle.py` ; compléter `tests/integration/test_vgc_full_battle_real.py` et les tests de preview existants.

**Interfaces :** étendre `create_policy_pair` avec des quatre imposés optionnels des deux côtés, en plus des leads ; transmettre `SimulationRequest.our_selection`, `our_lead_slots` et `opponent_back_pair`. Faire recevoir à `build_battle_record` les participants observés explicitement, indépendamment du payload demandé.

- [ ] Écrire un test où le moteur annonce un back observé différent du back demandé : il doit être rejeté. Un simple écho du payload ne doit jamais suffire à valider ce test.
- [ ] Appliquer au preview notre quatre C et son lead, et le quatre adverse composé du lead tiré et du back tiré. Garder les six Pokémon dans les équipes du simulateur ; ne pas remplacer l’équipe de six par quatre pour contourner le preview.
- [ ] Garder l’ordre du lead C pour les positions actives ; utiliser un ordre de back stable. Les clés statistiques de paires peuvent être non ordonnées sans perdre le mapping positions/slots des actions.
- [ ] Lire les compositions réellement soumises et acceptées au preview, les comparer aux contraintes, puis stocker les participants observés. Supprimer pour ce chemin le fallback `_resolve_our_lineup` utilisé comme preuve et la copie du back depuis le payload. Une preuve manquante invalide le record.
- [ ] Vérifier qu’imposer les compositions dans le simulateur ne révèle pas le back caché de l’autre joueur à sa politique. Conserver les observations autorisées et le comportement BC durant le combat.
- [ ] Pour les T1 D, accepter uniquement une paire dont la provenance est démontrée. Rendre l’absence de T1 exploitable représentable sans invalider une issue terminale prouvée : aucune substitution depuis le dernier move utilisé. Adapter le validateur de record si nécessaire ; ne pas imposer de recalcul de B ou changer sa règle.
- [ ] Tester le chemin sans contraintes complètes utilisé par C : les nouveaux arguments optionnels ne doivent pas figer sa sélection. Les fixtures doivent représenter honnêtement leur mode, sans provenance moteur réel simulée.
- [ ] Exécuter `uv run --group dev pytest tests/test_fixed_full_battle.py tests/test_preview_lifecycle.py tests/test_extract_turn_one.py -q` depuis `engine-runtime`, puis la recette moteur réelle ciblée. Comparer demande, choix de preview et participants stockés sur au moins deux scénarios forcés dans le test moteur, sans imposer cette diversité au hasard d’un run N=2.

## Tâche 3 — Agrégats, contrat et validations de stockage

**Modifier :** `src/pokecoach_python/workflow/aggregation/refinement.py`, `schemas/analysis_result.py`, `contracts/simulation-result-v2.schema.json`, les exemples `contracts/examples/simulation-abcd.json` et `contracts/examples/openings/acbd.json`, ainsi que les fixtures qui réutilisent une section D.

**Tests :** `tests/unit/test_phase_d.py`, `tests/unit/test_analysis_result.py`, `tests/unit/test_conditioned_result.py`. Dans conception, ajouter `tests/sql/090_global_refinement.sql` et une nouvelle migration `V<prochaine_version>__validate_global_refinement.sql` avec son profil `_repoindex.md`, si nécessaire pour compléter les contrôles SQL ; ne pas modifier les migrations appliquées.

**Interfaces :** `validate_refinement_battle(record, *, our_selection, scenario)` puis `aggregate_refinement(battles, *, selection, plan, battle_ids) -> RefinementSection` ; modèles typés pour `scenarioCounts` et `outcomes`, champs définis en section 4. Le modèle d’enveloppe vérifie aussi les références A/B et la sélection C.

- [ ] Ajouter un test de trois parties W/L/T, dont deux T1 exploitables : N=3, M=2, issues 1/1/1, histogramme total 3 et fréquences T1 total 2. Ajouter M=0, un seul scénario répété et deux scénarios aux mêmes quatre mais leads différents.
- [ ] Calculer W/L/T et l’histogramme sans pondération supplémentaire : l’échantillonnage a déjà appliqué les poids A/B. Trier les résultats et actions de façon stable. Ne pas fusionner les combats C avec D.
- [ ] Copier `configuration` depuis C sans la réordonner silencieusement. Générer les limites sur la distribution empirique A/B, l’effectif et les éventuelles observations T1 manquantes. Aucun ancien texte « configuration ciblée lead #1/back #1 ».
- [ ] Valider strictement les invariants de la section 4 côté Python et le schéma JSON exporté. Renforcer les contrôles SQL sur présence/types/sommes/sélection de D et conserver les triggers d’immutabilité A/C/B. Utiliser les mêmes exemples dans les tests contractuels.
- [ ] Remplacer l’exécution metadata `opponentLeadId` unique par politique/histogramme/empreinte du planning et compteurs. Une publication réussie ajoute uniquement D à ACB et met le run en pause si D est la cible.
- [ ] Vérifier qu’ajouter D ne change aucun octet de la sérialisation canonique des sections A/C/B. Les exemples de rapports déjà utilisés par d’autres tests peuvent recevoir le nouveau sous-objet D, sans ajouter de tâches fonctionnelles pour E.
- [ ] Exécuter les tests Python ciblés puis `./scripts/test-db.sh` dans conception. Les migrations/profils et commentaires SQL suivent les règles locales, en anglais.

## Tâche 4 — Exécution D et persistance par scénario

**Modifier :** `src/pokecoach_python/workflow/phases/phase_d.py`, `workflow/aggregation/refinement.py`, `workflow/battle_records.py` ; adapter `workflow/runner.py`/`db/analysis_repository.py` uniquement pour transmettre ou vérifier les métadonnées nécessaires. Mettre à jour le commentaire D de `simulation_budgets.py`, pas ses valeurs.

**Tests :** compléter `tests/unit/test_phase_d.py` et `tests/integration/test_phase_d_run.py`.

**Interfaces :** conserver `run_phase_d(context)` ; consommer le validateur par scénario et l’agrégateur de la tâche 3 à la place de la configuration unique. Utiliser `sample_key_for_refinement(i)` pour l’index planifié, jamais le numéro de tentative.

- [ ] Charger et valider le checkpoint ACB ; résoudre une seule fois N via `phase_d_valid_budget(context.profile)` ; construire le planning avant la première simulation. Pour N=2, lancer exactement deux combats valides au total.
- [ ] Jouer chaque scénario avec les seeds et plafonds de la section 3. Une issue terminale perdante ou nulle est un échantillon valide ; ni victoire ni richesse du T1 ne servent à accepter/rejeter une partie.
- [ ] Séparer les erreurs moteur récupérables des erreurs de persistance, de bail, d’annulation ou de progression. Ne pas envelopper `insert_battle`/`report_progress` dans un `except Exception` qui relancerait un combat après une erreur DB. Une perte de bail stoppe le traitement.
- [ ] Enregistrer un combat validé avec son scénario, index et seeds dans `meta.refinementSampling`. Vérifier le quatre, le lead, le back adverse et l’issue depuis les données observées. Conserver `report_progress('D', done, N)`.
- [ ] À la fin, relire les N combats D persistés ; vérifier indices uniques 0…N−1, correspondance avec les scénarios attendus, participants et battleIds. Ne pas confondre ordre SQL, ordre d’insertion et index métier. Une incohérence empêche la publication.
- [ ] Conserver les garanties d’idempotence existantes de `sample_key`/empreinte. Ne pas ajouter une reprise automatique au milieu d’un D interrompu : le cycle actuel marque les baux expirés en échec. Si des records D préexistent dans une exécution qui devrait commencer vide, arrêter explicitement plutôt que les écraser ou les mélanger. Relancer un nouveau run via le mécanisme existant.
- [ ] Tester un timeout puis succès au même index : même scénario, autre seed de combat, scénario suivant inchangé. Tester aussi rejet de composition, épuisement des tentatives, erreur DB et annulation. En échec, ACB reste consultable et `refinement` reste nul.
- [ ] Exécuter `uv run pytest tests/unit/test_phase_d.py tests/integration/test_phase_d_run.py -q`.

## Tâche 5 — Afficher l’évaluation globale dans Angular

**Fichiers**, relatifs à `pokecoach2-angular/pokecoach-angular/` : `src/app/core/models/simulation-result.model.ts`, `core/graphql/simulation-result-validator.ts` et son test (sous `src/app/`), `src/app/features/matchup/lead-pick.ts`, `lead-pick.html`, `public/i18n/fr.json`, `en.json`. Créer/compléter `src/app/features/matchup/lead-pick.spec.ts` et `e2e/global-refinement.spec.ts`.

Appliquer les skills [angular-developer](../../../.agents/skills/angular-developer/SKILL.md) et [design-system](../../../.agents/skills/design-system/SKILL.md). Adapter le bloc existant sous « Nos quatre », sans refonte de l’onglet ni modification de la colonne B.

- [ ] Étendre le type et le parseur `refinement` avec politique, périmètre, histogramme et M. Valider entiers, sommes, slots, configuration C et références A/B avant rendu ; ne pas utiliser de cast non vérifié pour faire accepter un ancien JSON.
- [ ] Titre FR « Évaluation globale de notre sélection » / EN « Overall evaluation of our selection ». Afficher notre sélection fixe et « Sur {{sample}} combats complets : {{wins}} victoires, {{losses}} défaites, {{draws}} nuls », puis le taux `wins/sampleSize`. Ne pas présenter N=2 comme une validation stratégique.
- [ ] Ajouter un texte traduit indiquant que les scénarios sont tirés à partir des fréquences observées des leads et backs adverses. Garder la limite sur le petit échantillon visible à côté des chiffres.
- [ ] Ajouter un `<details>` accessible « Répartition des scénarios simulés » : pour chaque ligne, Pokémon du lead, Pokémon du back, `count/N` et pourcentage observé. Résoudre les slots à partir du snapshot adverse du run. Ne pas confondre cette fréquence réalisée avec la probabilité théorique A/B.
- [ ] Conserver un détail « Premiers tours observés dans ces simulations », avec M/N exploitable si M<N. Pour M=0, ne pas afficher une distribution à zéro comme preuve d’absence d’action. Les recommandations à droite restent exclusivement celles de B.
- [ ] Tester issues avec nuls, histogramme multiscénario et uniscénario, M<N/M=0, slots invalides et sélection incohérente. Tester N=2 sans exiger au moins deux scénarios distincts. Vérifier traductions FR/EN, mobile, clavier et les deux thèmes.
- [ ] Mettre à jour les fixtures E2E et tester le passage du checkpoint ACB au checkpoint ACBD après polling, puis refresh. Vérifier que les cartes d’ouvertures B n’ont pas changé.
- [ ] Exécuter `devbox run test`, `devbox run lint`, `devbox run build`, puis l’E2E ciblé depuis le dépôt Angular.

## Tâche 6 — Nettoyage, recette réelle et documentation

**Fichiers :** adapter `docs/recettes/phase-d.md`, la section D de `docs/specs/2026-10-31-workflow-analyse-matchup.md`, `docs/README.md` ; annoter le [plan D historique](2026-10-31-08-phase-d-affinage.md) et la tâche D du plan 10 comme remplacés. Dans conception, vérifier/adapter `scripts/reset-analysis-data.sql`. Ajouter `tests/integration/test_phase_d_persistence.py` et `e2e/global-refinement-live.spec.ts` côté Angular.

- [ ] À l’implémentation, arrêter les workers/lancements et nettoyer les anciennes analyses selon la décision déjà prise. Conserver équipes/matchups, purger commandes/runs/combats, vérifier les références et rapports résiduels éventuels ; vider les caches/commandes navigateur avant redémarrage. Ne pas utiliser Flyway `clean`, ni toucher à son historique. Aucun nettoyage pendant la rédaction de ce plan.
- [ ] Vérifier les seeds de démonstration et fixtures pour qu’elles ne réintroduisent pas de D à scénario unique avec l’ancien contrat. Déployer le contrat backend et son lecteur Angular ensemble ; aucun lecteur de compatibilité ni incrément de `schemaVersion`.
- [ ] Le test de persistance utilise une DB jetable et le vrai repository/runner : publier ACB puis D, relire via SQL/PostGraphile, vérifier N lignes D, indices/scénarios/seeds, histogramme, W/L/T, et identité de A/C/B. Tester échec D sans publication et immutabilité d’un D déjà publié.
- [ ] Recette réelle : nouveau run smoke jusqu’à B, relever la sélection C et la distribution A/B ; continuer vers D avec le vrai checkpoint et Showdown. Vérifier les demandes, compositions observées et les deux issues ; comparer les JSON persistés au bloc Angular après refresh.
- [ ] Rejouer avec le profil standard **actuellement à 2**. Un test moteur contrôlé couvre plusieurs scénarios ; ne pas relancer jusqu’à obtenir un histogramme jugé plus joli, ni augmenter automatiquement N. L’utilisateur augmentera le budget lorsqu’il voudra étudier la qualité stratégique.
- [ ] Archiver runId, checkpoint, versions moteur/Showdown, seed, budget, planning/empreinte, scénarios effectivement joués, retries et résultats. La reproductibilité demandée porte sur le planning ; ne pas déclarer les issues moteur reproductibles sans mesure dédiée.
- [ ] Actualiser les explications et recettes D, ainsi que le commentaire du budget. Conserver E dans son plan séparé, sans élargir cette livraison.

## Critères de fin

- D joue N combats complets au total avec notre sélection C réellement imposée et des scénarios tirés sur tous les leads A selon les backs B.
- Les participants observés prouvent chaque scénario ; un payload recopié ne suffit pas.
- Les retries conservent le scénario, les limites sont bornées et un échec ne publie pas un résultat biaisé ou incomplet.
- W/L/T, histogramme, effectif T1 et dénominateurs sont cohérents ; A/C/B restent identiques.
- Le frontend explique l’évaluation globale sous la distribution observée, présente les scénarios réalisés et conserve B comme source de recommandation T1.
- Les anciennes analyses sont nettoyées lors de la bascule. Aucun nouveau versionnement de résultat, aucune modification de sélection C et aucune implémentation de E.
