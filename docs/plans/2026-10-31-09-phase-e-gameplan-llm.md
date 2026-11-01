# Phase E — Synthèse stratégique des combats D et rapport complet

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. **Pour le graphe, lire et appliquer obligatoirement [langgraph-generate-graph](../../../.agents/skills/langgraph-generate-graph/SKILL.md).** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Réutiliser les combats déjà simulés en D pour produire des conseils courts early/mid/endgame, une win condition, une ou deux menaces adverses et un ou deux Pokémon forts de notre équipe, puis publier le rapport complet.

**Architecture:** Après D : charger tous ses combats persistés → préparer statistiques globales et sélection de logs normalisés → conserver ces sources dans les métadonnées du run → graphe LangGraph séquentiel à deux nœuds → une génération LLM structurée → validation et publication atomique. **Aucune nouvelle simulation en E.**

**Tech Stack:** Python/Pydantic, LangGraph, client LLM isolé, PostgreSQL/PostGraphile, frontend Angular actuel sans onglets. Fournisseur **DeepInfra**, modèle **`deepseek-ai/DeepSeek-V4.1-Flash-1017`**, client **`langchain_openai.ChatOpenAI`** via l’API compatible Chat Completions. Charger la clé depuis **`DEEPINFRA_API_KEY`** dans le `.env` du backend ; aucune utilisation de modèle GPT ni de clé OpenAI.

**Spec et décisions :** demande et confirmations utilisateur du 1er novembre 2026. Ce plan remplace l’ancienne version E et prime sur les passages historiques du [workflow](../specs/2026-10-31-workflow-analyse-matchup.md) qui limitaient l’entrée du LLM aux seuls logs C/D. Il s’appuie sur [D global](2026-11-01-11-phase-d-affinage-global.md) et sur la page frontend déjà refondue. A–D sont validées fonctionnellement ; les adaptations de collecte ci-dessous fournissent uniquement les données supplémentaires nécessaires à E.

## 1. Décisions confirmées et périmètre

- **Combats D seulement**, du même run. Ne pas compléter la sélection avec C ni relancer `full_battle`, `first_turn` ou `preview` depuis E.
- Sélection souhaitée, sur le **nombre total N de combats D valides** : **15 % de victoires**, **15 % de défaites**, **20 % de parties serrées**. La catégorie atypique est supprimée : son quota initial de 10 % rejoint celui des parties serrées.
- Calculer les statistiques sur **tous les N combats D**, indépendamment de cette sélection. Les logs sélectionnés illustrent des cas ; leur distribution volontairement orientée ne sert pas à calculer le winrate.
- Conserver la **win condition**, en plus des cinq éléments de sortie demandés.
- Graphe validé : schéma **Pydantic dans le code**, deux nœuds **séquentiels**, un seul appel LLM nominal, stockage **réel** des sources dans les métadonnées du run, politique **fail_fast** si les sources indispensables ou la sortie sont invalides. Pas de parallélisme, d’outils agentiques, de boucle de réparation ni de `Annotated[..., add]`.
- Ne pas modifier la politique d’échantillonnage D, les budgets actuels, le bring C ni les recommandations B. Les sections `opponentLeads`, `leadPick`, `openings`, `refinement` restent identiques après E.
- Pas de nouvelle version de résultat ni de système de compatibilité. Adapter le contrat courant et ses lecteurs ; conserver la valeur technique `schemaVersion=2`. Ne pas nettoyer automatiquement les analyses : les runs D existants peuvent être réutilisés **si leurs traces contiennent les informations nécessaires**.

## 2. Écarts constatés dans le code actuel

Audit par lecture, sans exécuter de combat ni appeler un LLM :

| Constat | Conséquence pour l’implémentation |
| --- | --- |
| `normalization.build_battle_record` construit `turns` avec seulement le T1 ; `_run_full_battle` ajoute une preuve d’issue et `turnCount`, sans sérialiser toute la partie | Un combat effectivement terminé n’est pas forcément un historique complet enregistré. Compléter la capture lors des futurs combats D avant de déclarer E prête. |
| Les survivants finaux et les événements attribuables de dégâts ne sont pas dans le contrat normalisé actuel | Ajouter leur collecte déterministe ; ne pas déduire les survivants des seuls Pokémon révélés ni les dégâts des noms de capacités. |
| `assert_real_battles_eligible` vérifie provenance et preuve terminale, pas l’exhaustivité des tours | Le conserver et ajouter une validation spécifique des sources E. Rejeter stub/fixture avant toute requête payante. |
| `AnalysisRepository.list_battles` renvoie des records sans ID ni `sample_key` | Ajouter une lecture identifiée et filtrée `phase='D'`, nécessaire aux références, au tri et à l’audit. |
| Dans le runner, les callbacks de lecture des phases autres que C/D retombent actuellement sur C | Donner à E sa lecture explicite D ; ne pas réutiliser cette valeur par défaut. |
| `engine_supported_phases` et `get_capabilities` excluent explicitement `synthesis` | Raccorder l’éligibilité E et sa configuration, tout en conservant A–D sans secret LLM. |
| `publish_phase` ne finalise pas un succès ; les révisions suivent les publications, dont certaines sont regroupées | Ajouter une finalisation atomique ; utiliser `expected_revision + 1`, **jamais une révision 5 codée en dur**. |
| Le merge `execution_metadata || {'phases': ...}` remplace actuellement tout le sous-objet `phases` | Préserver les métadonnées précédentes et les sources E lors des écritures et de la finalisation. |
| Le frontend actuel a `matchup-left-column`, `gameplan.ts/html` et aucune navigation par onglets | Adapter ces composants, les modèles/mappers et les états de continuation ; ne pas restaurer l’ancienne UI. |
| L’ancien gameplan demande `preserve`, `eliminate`, `adaptations`, sans champ explicite pour nos Pokémon forts | Remplacer ces champs non demandés par `strengths` et adapter les validateurs/fixtures/front ensemble. |

Si un ancien run ne possède que son T1, E ne peut pas recréer ses tours manquants. Importer/normaliser un log complet déjà conservé est possible **sans rejouer**, en créant une source dérivée avec provenance, sans modifier le combat immutable. Si aucun log complet n’existe, échouer avant l’appel LLM avec un message explicite ; proposer un nouveau run après correction de la capture, sans le lancer automatiquement.

## 3. Données de combat nécessaires

Préserver `BattleRecord`, ses participants, l’issue et les actions T1 utilisées par D. Enrichir le JSON existant avec :

- Historique ordonné depuis le preview jusqu’à l’événement terminal : tous les tours effectivement joués, actions observées/choix acceptés quand disponibles, cibles, changements, Tera, dégâts/soins, KO, statuts, boosts et effets de terrain pertinents. Distinguer choix et exécution ; conserver les événements sans attaque au lieu de supprimer ces tours.
- Mapping stable **côté + slot du snapshot**, y compris après switch, changement de position, forme ou surnom. Ne pas identifier un Pokémon uniquement par son nom ou par sa position active.
- État terminal des **quatre Pokémon sélectionnés de chaque côté**, incluant le back non envoyé : PV/maxPV ou précision disponible, état KO et nombre de survivants. Ne jamais compter les deux Pokémon non sélectionnés. Un Pokémon revenu au combat après un KO se traite selon son état final.
- Événements de dégâts avec source quand démontrable, cible, variation effective des PV, maximum de PV, tour et cause. Conserver la précision de mesure et les événements non attribuables. Ne pas confondre dégâts directs, recul, poison, météo, hazards, soins et variation de PV liée à un effet de forme.
- Preuve de fin, numéro du dernier tour, méthode de capture et empreinte du log/record. Les seuls booléens `finished=true` ou `terminalEvidence` ne prouvent pas la complétude de l’historique.

La capture reste passive : elle n’ajoute aucune simulation et ne révèle aucune information cachée à une politique pendant le combat. Pour les PV exacts, exploiter les observations autorisées de chaque joueur sur ses propres Pokémon, hors décision stratégique ; ne pas présenter les PV adverses arrondis d’un replay public comme une valeur exacte. Dédupliquer les messages des deux perspectives.

**Normalisation :** produire `NormalizedDBattle` avec `battleId`, `sampleKey`, participants/sets, outcome, terminalState, turns/events et qualité de capture. Enlever chat, usernames techniques, timestamps inutiles et messages de protocole redondants ; conserver la chronologie et les événements de jeu. Aucun résumé par LLM en amont et aucune reconstruction imaginaire d’un événement manquant.

## 4. Sélection déterministe des logs

La règle ci-dessous précise les arrondis et chevauchements laissés ouverts par les pourcentages. Elle reste indépendante de la sélection des équipes.

### Quotas

Pour N>0 : `q_win=ceil(15*N/100)`, `q_loss=ceil(15*N/100)`, `q_close=ceil(20*N/100)`. Calculer avec des entiers. Les arrondis vers le haut servent aux petits runs de test ; ils peuvent dépasser 50 % au total lorsque N est faible. Le nombre de combats **uniques** envoyés ne dépasse jamais N.

Construire trois listes exclusives en réservant les combats les plus contraints en premier :

1. **Serrées**, jusqu’à `q_close` : uniquement victoires/défaites ; d’abord les parties dont le gagnant conserve exactement **1 Pokémon**, puis celles où il en conserve **2** pour remplir le quota restant. Aucun élargissement aux gagnants à 3–4 Pokémon.
2. **Victoires**, jusqu’à `q_win`, parmi les parties non déjà retenues : nombre de survivants de notre côté décroissant.
3. **Défaites**, jusqu’à `q_loss`, parmi les parties non déjà retenues : nombre de survivants adverses décroissant.

À égalité, utiliser `sample_key` puis ID ; pas de RNG ni de durée de combat ajoutée arbitrairement au classement. Les catégories sont une allocation de l’échantillon, pas des classes disjointes de qualité : une victoire non réservée au quota serré peut encore être serrée.

- Chaque combat n’apparaît qu’une fois dans les logs transmis. Ne pas compter une même partie dans deux quotas.
- Une catégorie insuffisante reste incomplète : enregistrer quota demandé, nombre retenu et motif, sans transférer son quota vers une autre catégorie ni rejouer de partie.
- Les nuls entrent dans toutes les statistiques globales mais pas dans ces trois catégories, qui nécessitent un gagnant. Si aucune partie n’est sélectionnable, échouer explicitement `NO_SELECTABLE_D_BATTLE`, sans inventer un vainqueur ni appeler le fournisseur.
- Exemples obligatoires : N=100 donne des quotas 15/15/20 ; N=2 donne 1/1/1 mais au plus deux parties uniques ; un seul côté gagnant laisse l’autre catégorie vide ; un gagnant à deux survivants est utilisé après les gagnants à un survivant.
- Garder dans les métadonnées le manifeste complet : N, quotas, catégories, IDs/empreintes retenus et insuffisances. Signaler au LLM que les exemples ne sont pas représentatifs des fréquences globales.

**Budget de contexte :** supprimer l’ancien plafond arbitraire de 12 combats C/D. Compter les sources finales, instructions et schéma avec le tokenizer du modèle configuré, réserver la sortie et une marge. Les statistiques agrégées restent compactes ; les logs retenus sont normalisés intégralement. Si l’ensemble dépasse la limite, échouer avant l’appel avec les volumes mesurés et la configuration à ajuster. Ne pas couper des tours ou enlever silencieusement des sources promises par les quotas.

## 5. Statistiques calculées sur tous les combats D

N est le nombre de records D terminaux valides du run, égal à `refinement.sampleSize`. Vérifier l’ensemble des IDs contre `refinement.battleIds`, l’issue et le scénario de chaque record ; une ligne absente, étrangère au run ou technique n’est pas simplement retirée du dénominateur.

| Statistique | Définition et dénominateur |
| --- | --- |
| Winrate | W/N ; exposer séparément W, L, nuls et N. Les nuls restent au dénominateur. |
| Leads les plus fréquents | Lead adverse **effectivement joué en D**, par paire canonique de slots : count/N, tri décroissant puis clé stable. Ce ne sont pas les fréquences A ni les poids théoriques. |
| Résultats par lead | Pour chaque lead D : W/L/nuls, `sampleSize` du groupe et W/groupe. Inclure les petits effectifs ; aucune extrapolation aux leads non joués en D. |
| Menaces associées aux défaites | Pour chaque Pokémon adverse : nombre de défaites où il était sélectionné, où il est entré en jeu, où il a infligé des dégâts attribuables, KO directement attribuables et dégâts directs attribués sur nos Pokémon pendant ces défaites. Donner `lossSampleSize` et les effectifs de présence. Une présence dans une défaite n’est pas une preuve de causalité. |
| Dégâts moyens de nos Pokémon | Somme des dégâts **directs attribuables sur les PV adverses**, exprimés en points de pourcentage des PV maximum de chaque cible, divisée par le nombre de parties D où notre Pokémon est sélectionné. Notre quatre étant fixe, ce dénominateur doit valoir N. Un Pokémon resté dans le back inflige zéro si la trace le confirme. |

Précisions pour les dégâts :

- Compter les PV réellement perdus, pas les dégâts théoriques/overkill ; traiter chaque cible et chaque impact multi-hit une fois. Une somme supérieure à 100 % est possible sur plusieurs cibles ou après des soins.
- Ne pas attribuer le poison, la météo ou un dommage de cause inconnue au dernier attaquant. Conserver leurs volumes séparément lorsqu’ils sont mesurables. Les dégâts sur un substitut ne sont pas des PV du Pokémon et ne rentrent pas dans cette métrique.
- Cette mesure est explicitement une **moyenne de dégâts directs attribués**, pas le total de toute influence stratégique. Un Pokémon de soutien peut être proposé comme fort par le LLM sur la base des logs.
- Une attribution inconnue n’est pas un zéro. Inclure une section de qualité : événements non attribués, précision HP, parties exploitables pour chaque métrique et limites. Ne pas publier un classement « exact » lorsque les données ne le permettent pas ; ne pas compter une trace entièrement manquante comme une partie sans dégâts.
- Si L=0, les statistiques de menace **dans les défaites** sont vides avec dénominateur 0, pas un taux calculé par division par zéro. Le LLM peut proposer une menace observée ailleurs mais doit la présenter comme analyse, sans inventer des défaites.

Les stats sont calculées à partir des N records, jamais depuis les seuls logs sélectionnés, les textes LLM ou les tableaux A/B/C. Les snapshots des équipes sont admis comme contexte permettant d’identifier Pokémon, capacités et sets ; aucun agrégat A/B/C n’entre dans les sources.

## 6. Sortie structurée et contrat courant

Schéma Pydantic strict dans `graphs/matchup_gameplan/models.py` : `StrategyOutput` contient uniquement `gameplan` et `winCondition`.

```text
gameplan:
  opening: string                 # 1–2 phrases de conseil early game
  midgame: string                 # 1–2 phrases
  endgame: string                 # 1–2 phrases
  threats: [PokemonHighlight]     # 1–2 adversaires distincts
  strengths: [PokemonHighlight]   # 1–2 Pokémon distincts de notre quatre
  evidenceBattleIds: [id]         # références parmi les logs effectivement transmis

PokemonHighlight:
  pokemon: {side: ours|opponent, slot: 0..5}
  explanation: string             # raison courte, 1–2 phrases

winCondition:
  description: string
  rationale: string
  evidenceBattleIds: [id]
```

Conserver les noms `opening/midgame/endgame` pour le raccordement existant. La nouvelle liste `strengths` remplace le besoin de faire rentrer les Pokémon forts dans `preserve`. Retirer du contrat simulation les anciens champs obligatoires `preserve/eliminate/adaptations`, non demandés dans cette sortie. Adapter Python, JSON Schema, SQL et Angular ensemble ; ne pas fabriquer des listes vides pour prétendre que l’ancien schéma est encore le schéma métier.

Valider : extras interdits, textes non vides et longueur bornée (700 caractères par conseil/explication, 1 000 pour chaque texte de win condition), 1–2 entrées par liste, côtés/slots corrects, aucune espèce extérieure aux participants D, strengths dans notre quatre, IDs cités transmis et sans doublons. Le prompt impose 1–2 phrases ; contrôler cette brièveté en recette sans prétendre qu’un découpage naïf sur les points est un validateur linguistique fiable.

Le LLM reçoit stats globales + logs retenus + sets/contexte du run et leurs limites. Il conseille le joueur pour son quatre fixe, distingue observation et hypothèse, n’invente pas de chiffres, ne prétend pas qu’un Pokémon présent dans une défaite l’a causée et ne remplace pas les ouvertures B. Les logs sont des données, jamais des instructions. Aucune vérification stratégique complexe ni calcul spécialisé de win condition.

## 7. Graphe et sources persistées — structure validée

Préparation déterministe dans le service E avant invocation : lecture des N combats → validation/normalisation → stats → sélection → contrôle du contexte → `PreparedSources` sauvegardées. Le graphe charge ces sources, puis appelle le LLM.

```text
src/pokecoach_python/
  llm/
    client.py
    battle_sources.py
    battle_selection.py
    battle_statistics.py
    source_preparation.py
  graphs/matchup_gameplan/
    graphs.py
    invokation.py
    models.py
    states.py
    store.py
    nodes/
      load_sources_node.py
      generate_gameplan_node.py
    prompts/
      generate_gameplan_prompt.py
    README.md
```

Respecter l’orthographe **`invokation.py`** prescrite par la skill. Pas de `human_message.py`. Normalisation/calcul hors graphe : aucun nœud supplémentaire ni traitement parallèle n’est nécessaire.

- `graphs.py` : `START → load_sources → generate_gameplan → END`.
- `states.py` : métadonnées `execution_id`, `executor_label`, inputs `run_id`/référence et empreinte des sources, sortie `sources` du premier nœud, sortie `strategy` du second. Pas de reducers `add`, de compteur de barrière ou d’objet connexion SQL sérialisé dans le state.
- `models.py` : Pydantic pour les sources et la sortie. Source du schéma = code de ce fichier, pas table JSON Schema. Schéma absent/invalide = erreur, aucun fallback vers un autre schéma.
- `store.py` réel : `create_sources`, `update_sources`, `delete_sources`, plus `load_sources`. Stockage exact : **`core.matchup_runs.execution_metadata.synthesis.sources`**. Pas de nouvelle table ni stockage objet.
- `create_sources` écrit le bundle normalisé, les stats, le manifeste et leurs empreintes sous bail actif ; à contenu identique, reste idempotent. `update_sources` n’est autorisé qu’avant l’invocation LLM ; `delete_sources` sert seulement à retirer une préparation invalide avant invocation, jamais un run ou un combat. Les métadonnées et preuves des runs terminaux restent immuables.
- `load_sources_node` relit ce bundle du même run et vérifie son empreinte. `generate_gameplan_node` construit localement `HumanMessage`, appelle `StrategyClient.generate(sources)`, puis valide la sortie. Aucun accès libre à la DB ou outil à disposition du modèle.
- Un appel nominal ; au plus **deux tentatives HTTP au total** pour erreur fournisseur transitoire, sans multiplier retries SDK et graphe. Une sortie structurellement invalide échoue, sans appel autonome de réparation.
- `prompts/generate_gameplan_prompt.py` contient les sections `ROLE`, `CONTEXT`, `OBJECTIVE`, `CONSTRAINTS`, `SOURCES` (stats globales, logs sélectionnés, sets/qualité), `OUTPUT FORMAT`, `QUALITY CRITERIA` ; aucune logique DB.
- README du graphe : `Description`, `Operation / Flow`, `Input`, `Output`, reprenant l’objectif utilisateur et les décisions validées. Logs de début/fin par nœud avec execution_id, sans secrets ni dump intégral des prompts.

Les données préparées sont conservées pour inspection même si le fournisseur échoue. La finalisation ne doit ni effacer `synthesis.sources`, ni écraser les métadonnées A–D.

### Configuration DeepInfra imposée

- Client conservé : `ChatOpenAI` de `langchain-openai`, même si l’inférence est exécutée par DeepInfra.
- `model="deepseek-ai/DeepSeek-V4.1-Flash-1017"` ; renseigner cette valeur exacte dans `LLM_MODEL`/son défaut explicite dans Settings et `.env.example`.
- `base_url="https://api.deepinfra.com/v1/openai"` ; utiliser Chat Completions, avec `use_responses_api=False`. Ne pas laisser le SDK choisir l’endpoint OpenAI par défaut.
- `api_key=settings.deepinfra_api_key.get_secret_value()` : champ Settings `SecretStr` lié à `DEEPINFRA_API_KEY`, chargé via le mécanisme `.env` existant. Ne pas dépendre de `OPENAI_API_KEY`. Dans `.env.example`, seule une valeur vide/documentée est permise ; ne jamais recopier la clé réelle.
- Sortie : `client.with_structured_output(StrategyOutput, method="json_schema", strict=True)` puis validation Pydantic/métier. Confirmer l’acceptation du schéma exact par ce modèle lors de la recette ; une incompatibilité est une erreur explicite, sans remplacement silencieux du modèle, du fournisseur ou par du texte libre.
- Conserver timeout/budget de sortie configurés et `max_retries=0` sur le client si les deux tentatives maximum sont gérées par `StrategyClient`, pour éviter les retries imbriqués.
- Le comptage des tokens doit être adapté à ce modèle DeepSeek : ne pas utiliser implicitement un tokenizer GPT ou supposer que le comptage intégré de `ChatOpenAI` reconnaît cet identifiant. Vérifier le tokenizer et la sérialisation utilisés, puis confronter l’estimation aux usages renvoyés par DeepInfra en recette.

L’URL, l’authentification et l’identifiant demandé figurent dans la [documentation du modèle DeepInfra](https://deepinfra.com/deepseek-ai/DeepSeek-V4.1-Flash-1017/api). Le mode `json_schema` est décrit dans la [documentation des sorties structurées DeepInfra](https://docs.deepinfra.com/chat/structured-outputs) ; la recette doit valider son usage avec notre schéma et la version verrouillée de `langchain-openai`.

## 8. Points de revue

| Risque | Test propriétaire |
| --- | --- |
| Combat terminé mais historique limité au T1 | Tâche 1 : preuve de collecte complète et ancien record refusé |
| Quotas petits N/chevauchements et stats calculées sur le sous-échantillon | Tâche 2 : exemples de sélection + stats sur N |
| Attribution fausse de dégâts ou mauvais survivants | Tâches 1–2 : états terminaux, sources d’événements et précision |
| Graphe ignorant la skill, schéma non borné ou sources mutées | Tâche 3 : architecture, empreinte et tests de sortie |
| E lisant C, relançant le moteur ou publiant après perte de bail | Tâche 4 : runner/repository et doubles d’interdiction |
| Frontend encore calé sur les anciens champs/onglets | Tâche 5 : contrat et page actuelle |

## Tâche 1 — Rendre les combats D exploitables sans partie supplémentaire

**Modifier :** `engine-runtime/src/pokecoach_vgc_bridge/battle_session.py`, `battle_runner.py`, `recorder.py`, `normalization.py` ; `src/pokecoach_python/engine/contracts.py`, `engine/provenance.py`, `workflow/battle_records.py`, `contracts/battle-trace-v1.schema.json` selon les champs ajoutés. Créer `engine-runtime/src/pokecoach_vgc_bridge/full_battle_trace.py` et `engine-runtime/tests/test_full_battle_trace.py`.

**Interfaces :** capture passive `FullBattleTrace` et `normalize_complete_battle(trace, snapshots) -> BattleRecord` ; `validate_d_synthesis_source(record)` complète, sans remplacer, le contrôle d’éligibilité moteur existant.

- [ ] Écrire une fixture de plusieurs tours incluant switch, KO, soins, dégâts multi-cibles, Tera et événement terminal ; vérifier que la normalisation ne produit pas seulement T1 et conserve les participants réellement joués.
- [ ] Capturer les événements à leur réception via les hooks disponibles dans la version locale de poke-env/VGC-Bench ; inspecter les appels réels avant de surcharger le joueur. Conserver le comportement du joueur et l’absence d’information cachée dans ses décisions.
- [ ] Enregistrer états terminaux des quatre de chaque côté et provenance HP. Tester back jamais envoyé, double KO, nul, changement de position, soin, résurrection si représentée, et fin anticipée avec raison terminale : ne pas reconstruire un nombre de survivants depuis le seul compteur de KO.
- [ ] Vérifier couverture preview→fin et cohérence entre événements/tours/terminalState. Un log tronqué, un mapping impossible ou des données terminales absentes bloquent l’éligibilité E ; un événement de dégâts non attribuable est conservé comme tel, pas inventé.
- [ ] Préserver les champs T1 consommés par D, sa sélection, sa distribution et ses budgets. Cette instrumentation peut être partagée avec C mais E ne lira que D.
- [ ] Tester qu’un ancien `BattleRecord` avec seulement T1 et `terminalEvidence.turnCount > 1` échoue. Tester qu’un véritable combat d’un tour reste admissible si sa trace est complète.
- [ ] Exécuter depuis `engine-runtime` `uv run --group dev pytest tests/test_full_battle_trace.py tests/test_fixed_full_battle.py -q`, puis les tests de records/provenance côté Python. Faire une preuve de capture sur un nouveau combat D réel au budget existant avant de valider ce jalon.

## Tâche 2 — Sélection, statistiques globales et préparation des sources

**Créer :** `src/pokecoach_python/llm/battle_sources.py`, `battle_selection.py`, `battle_statistics.py`, `source_preparation.py`, les modèles de sources dans `graphs/matchup_gameplan/models.py`, et `tests/unit/test_battle_sources.py`, `test_battle_selection.py`, `test_battle_statistics.py`. Compléter `db/analysis_repository.py` pour lire IDs/sample_key/SHA/payload des seuls combats D du run. La tâche 3 complètera le même fichier de modèles avec la sortie structurée.

**Interfaces :** `StoredDBattle(id, sample_key, sha256, record)` ; `select_d_battles(records) -> SelectionManifest` ; `compute_d_statistics(records) -> DStatistics` ; `prepare_sources(records, snapshots, token_budget, token_counter) -> PreparedSources`. Tous les tris et calculs sont purs et déterministes ; les types sources résident dans les modèles du graphe, sans import circulaire vers le runner.

- [ ] Lire tous les D, vérifier nombre, IDs, provenance et empreintes ; normaliser les sources complètes. Aucune requête de lecture C ni agrégat A/B/C transmis. Vérifier le contenu avec des marqueurs dans les fixtures des sections interdites.
- [ ] Implémenter la sélection de la section 4 et ses tests : N=2/100, catégories insuffisantes, ex æquo, logs uniques, gagnant à un puis deux survivants, nuls et absence totale de partie sélectionnable.
- [ ] Implémenter stats W/L/nuls, fréquences et résultats par lead, menace dans les défaites et dégâts moyens selon la section 5. Tester explicitement un combat non retenu dans les logs qui change les stats globales.
- [ ] Couvrir HP arrondis/exacts, dégâts indirects, multi-hit, overkill, cible alliée, substitut, source inconnue, Pokémon resté dans le back et aucune défaite. Vérifier unité, dénominateurs et qualité ; ne pas produire de division par zéro ni de faux zéros.
- [ ] Construire le bundle compact avec stats de N, logs sélectionnés complets, sets, contexte et manifeste. Comparer chaque log normalisé à sa source et tracer les transformations ; jamais une génération LLM intermédiaire.
- [ ] Compter le contexte complet avec le tokenizer adapté, instructions/schéma/sortie réservés. Tester dépassement avant appel et absence de troncature d’une bataille. Configurer les limites sans imposer arbitrairement douze logs.
- [ ] Exécuter `uv run pytest tests/unit/test_battle_sources.py tests/unit/test_battle_selection.py tests/unit/test_battle_statistics.py -q`.

## Tâche 3 — Graphe LangGraph, stockage des sources et sortie structurée

**Créer :** toute l’arborescence `graphs/matchup_gameplan/` de la section 7, `llm/client.py`, `tests/unit/test_strategy_graph.py`, `tests/integration/test_synthesis_sources_store.py`.

**Modifier :** `pyproject.toml`, `uv.lock`, `core/config.py`, `.env.example`, `db/analysis_repository.py`. **Ne pas lire, modifier ou afficher le secret du `.env` pendant la rédaction ou les tests unitaires.**

**Interfaces :** `StrategyClient.generate(sources: PreparedSources) -> StrategyOutput` ; `create_matchup_gameplan_graph(store, client)` ; `invoke_matchup_gameplan(run_id, sources_hash, execution_id) -> StrategyOutput`. Le bridge moteur garde son environnement isolé ; LangGraph s’installe dans l’application Python.

- [ ] Appliquer obligatoirement la skill et ses choix déjà validés (§7), sans redemander ces validations. Créer les modèles Pydantic stricts, les deux nœuds, le prompt structuré, le README et les trois opérations obligatoires du store avec leur portée limitée aux sources préparatoires.
- [ ] Configurer `LLM_MODEL=deepseek-ai/DeepSeek-V4.1-Flash-1017`, `DEEPINFRA_API_KEY` (SecretStr depuis le `.env` existant), l’URL DeepInfra de la section 7, `LLM_INPUT_TOKEN_BUDGET`, `LLM_OUTPUT_TOKEN_BUDGET`, timeout et limite de tentatives. Une clé absente laisse A–D disponibles et E indisponible. Ne pas modifier la clé existante ni demander `OPENAI_API_KEY`.
- [ ] Stocker sous `execution_metadata.synthesis.sources` avec contrôle run/bail/révision et mise à jour JSON ciblée. Tester create/load identiques, refus de modification après invocation, delete sans toucher aux combats et refus d’écriture terminale.
- [ ] Compiler le graphe deux nœuds, injecter le client/store dans son contexte et construire `HumanMessage` dans le nœud de génération. Construire `ChatOpenAI` avec le modèle, `base_url` et `api_key` DeepInfra explicites ; demander `with_structured_output(StrategyOutput, method="json_schema", strict=True)` puis revalider les références métier. Vérifier ce schéma sur `deepseek-ai/DeepSeek-V4.1-Flash-1017` lors de la recette.
- [ ] Écrire le prompt pour les six éléments demandés, leurs longueurs et leur provenance. Mentionner sélection orientée des exemples, stats sur N et qualité des données, sans assimiler dégâts directs et utilité globale ni annoncer une certitude stratégique.
- [ ] Avec une clé factice et un transport HTTP contrôlé, vérifier le modèle exact, l’URL DeepInfra, le header d’authentification et le format `json_schema`, sans lire de vraie clé ni appeler le réseau. Vérifier qu’aucun client ne vise l’API OpenAI et que l’absence de `OPENAI_API_KEY` ne bloque pas DeepInfra. Tester ensuite doubles de fournisseur, ordre des nœuds, un appel nominal, source manquante, empreinte différente, champs supplémentaires `leadPick`, sorties vides, références inconnues, mauvais côté et plus de deux menaces/strengths. Tester retries transitoires bornés, timeout et sortie invalide sans réparation automatique.
- [ ] Exécuter `uv run pytest tests/unit/test_strategy_graph.py tests/integration/test_synthesis_sources_store.py -q`. Aucun appel payant dans ces tests.

## Tâche 4 — Handler E, capacités et finalisation atomique

**Créer :** `src/pokecoach_python/workflow/phases/phase_e.py`, `tests/integration/test_phase_e_run.py`.

**Modifier :** `workflow/registry.py`, `workflow/types.py`, `workflow/runner.py`, `engine/capabilities.py`, `services/analysis_commands.py`, `schemas/analysis_commands.py`, `db/analysis_repository.py`, `schemas/analysis_result.py`, `contracts/simulation-result-v2.schema.json` et fixtures. Dans conception : nouvelle migration de finalisation/contrat à la prochaine version libre, profil repoindex, et `tests/sql/100_synthesis_finalization.sql` ; migrations appliquées immuables.

**Interfaces :** `run_phase_e(context) -> PhaseOutput` ; contexte E avec lecture D identifiée et service de synthèse injectés ; `assemble_complete_result(previous, strategy)` ; `publish_complete(..., expected_revision, result, execution_metadata_patch)`.

- [ ] Exiger un checkpoint publié `['A','C','B','D']`. Sur exécution complète, garder la publication D avant E : ne pas étendre `_defer_publish_after_phase` au couple D→E. Les résultats D restent visibles si le LLM échoue.
- [ ] Enregistrer `synthesis` dans le registre et les capacités seulement lorsque le déploiement et la configuration LLM le permettent. Ne pas laisser la logique qui filtre systématiquement `synthesis`. Ne pas vérifier une configuration payante par un appel de génération au chargement des capacités.
- [ ] Séparer disponibilité des simulations et disponibilité de la synthèse déjà alimentée : ajouter `synthesisAvailable: boolean` à la réponse de capacités, indicateur de configuration E indépendant du moteur et consommé par le bouton dédié. Le lancement d’un nouveau run reste conditionné à A–D disponibles. Si le bridge est indisponible, renvoyer `phases=[]` pour les lancements nécessitant des simulations et conserver `synthesisAvailable=true` lorsque E est configurée, plutôt qu’un 503 global ; les préconditions du run sont revérifiées côté serveur. Dans le mapping Angular, `defaultTargetPhase` peut alors être nul et le bouton de nouveau run désactivé, sans bloquer Continuer vers E.
- [ ] Pour une continuation D→E seule, ne pas construire/préflight un moteur de simulation dans le runner, y compris via `_initial_provenance` en début d’exécution. Conserver le contrôle de provenance enregistrée et des empreintes des sources ; ne pas exiger un serveur Showdown ou le checkpoint courant chargés pour lire des combats déjà valides. Fournir explicitement la lecture D, sans callback par défaut sur C. Pour les phases qui simulent encore, préserver le contrôle de compatibilité du moteur courant.
- [ ] Préparer/persister les sources, lancer le graphe hors transaction SQL puis assembler `gameplan` et `winCondition`. E n’a pas d’accès aux méthodes de simulation. Ajouter un double moteur qui échoue si l’une de ces méthodes est appelée pendant E.
- [ ] Comparer les empreintes A/C/B/D avant/après. Ajouter `synthesis` aux phases terminées ; seule la partie E du résultat change. Adapter les contrats stricts à `strengths`/threats référencées ; conserver les deux sections de sortie existantes au niveau enveloppe.
- [ ] Finaliser dans une seule transaction : vérifier status running, token, **bail non expiré**, expected_revision ; écrire `report=partial_result`, révision courante+1, `status=succeeded`, `process_status=SUCCESS`, `finished_at`, progression terminée et libération du bail. Fusionner les sous-objets metadata sans effacer A–D ni les sources.
- [ ] Conserver le heartbeat existant pendant l’appel et vérifier annulation/bail avant publication. Un timeout fournisseur, une validation invalide, une annulation ou un échec de commit n’est pas un succès ; garder A–D consultables, report nul et sources d’audit conservées.
- [ ] Enregistrer prompt/empreinte, modèle, paramètres non secrets, tokens si disponibles, durée, références des sources et sortie validée dans les métadonnées appropriées. Aucun log de secret. Un retry de commande ne doit pas lancer une nouvelle simulation ni modifier un run terminal.
- [ ] Tester continuation depuis un run dont D a été publié à révision 1, et run où chaque phase a sa révision : E incrémente une seule fois dans les deux cas. Tester C jamais lu, absence de moteur, perte de bail pendant génération, succès atomique et refus de modification terminale.
- [ ] Exécuter `uv run pytest tests/integration/test_phase_e_run.py -q` et `./scripts/test-db.sh` dans conception, sur base jetable. Ne pas supprimer les données de travail pour cette recette.

## Tâche 5 — Brancher la sortie sur la page Angular actuelle

**Fichiers Angular**, sous `pokecoach2-angular/pokecoach-angular/` : `src/app/features/matchup/gameplan.ts/html`, `matchup-left-column.ts/html`, `matchup.ts/html`, `analysis-controls.ts/html`, `core/python/analysis-api.models.ts`, `core/models/simulation-result.model.ts`, `core/models/matchup.model.ts`, `core/graphql/simulation-result-validator.ts`, `core/matchup/simulation-display.ts` (chemins core sous `src/app/`), tests correspondants, `public/i18n/fr.json` et `en.json`.

- [ ] Adapter les types, validateur et mapper aux références `{side,slot}` et au champ `strengths`. Résoudre les noms/portraits depuis les snapshots du run, sans demander au LLM de produire des noms à parser. Ne pas confondre nos Pokémon forts avec la sélection de quatre, qui reste celle de C.
- [ ] Afficher dans la colonne gauche : conseils courts early/mid/endgame, win condition, 1–2 menaces et 1–2 Pokémon forts avec leur explication. Retirer les sections historiques preserve/eliminate/adaptations devenues sans source, sans rétablir des onglets. Texte rendu comme texte, aucun HTML libre du modèle.
- [ ] Conserver l’origine IA et les références aux combats quand présentes. Le détail des statistiques/sources peut rester dans les métadonnées de recette ; ne pas ajouter une nouvelle page d’analyse pour ce chantier.
- [ ] Pendant E, afficher un état de génération avec A–D accessibles ; après échec, conserver les données partielles et l’erreur ; après succès, lire le rapport complet et arrêter le polling. Distinguer l’absence de configuration LLM d’un résultat non encore calculé.
- [ ] Ajouter une action de **continuation vers synthesis** pour un run D éligible en pause : utiliser l’endpoint continue existant, pas `launch()` qui crée aujourd’hui un nouveau run. Conserver idempotence, runId et sélection du run ; le lancement d’un nouveau run reste une action distincte.
- [ ] Tester snapshots avec mêmes noms de Pokémon, sortie invalide, absence de strengths, succès après polling et refresh, continuation D→E sans appel start ni changement de runId. Appliquer les skills Angular et design-system du projet.
- [ ] Exécuter `devbox run test`, `devbox run lint`, `devbox run build` depuis Angular ; ajouter un E2E ciblé `e2e/synthesis.spec.ts` et adapter les parcours live existants.

## Tâche 6 — Recette réelle, documentation et critères de clôture

**Fichiers :** créer `docs/recettes/phase-e.md` ; actualiser les sections E/contrat du workflow, `docs/README.md`, `.env.example` et le README du graphe ; adapter `scripts/analysis-smoke.py` si nécessaire. Ne pas réécrire les choix A–D validés.

- [ ] D’abord auditer un run D existant : nombre de combats, traces disponibles, terminaux/survivants et qualité HP. S’il est incomplet, constater l’inéligibilité sans LLM et sans simulation automatique. S’il est complet, préparer les sources et continuer directement ce run.
- [ ] Si une nouvelle capture est nécessaire, réaliser un nouveau run D au budget existant après la tâche 1, puis utiliser **ses mêmes combats** pour E. Documenter que cette collecte initiale corrige l’absence d’historique ; E n’ajoute aucune partie.
- [ ] Utiliser `deepseek-ai/DeepSeek-V4.1-Flash-1017` sur DeepInfra avec `DEEPINFRA_API_KEY` déjà présente dans le `.env`, sans afficher sa valeur ; lancer le worker et continuer via l’UI ou `uv run python scripts/analysis-smoke.py --run-id UUID --target synthesis`. Vérifier le même runId, un appel LLM nominal et aucun appel simulation pendant E ; la recette de continuation doit fonctionner avec Showdown arrêté lorsque D est déjà enregistré et éligible.
- [ ] Contrôler le bundle conservé : stats sur N, quotas 15/15/20, combats uniques et tous les tours, limites des catégories/mesures, aucun C ni agrégat A/B/C. Vérifier les six éléments de sortie, citations valides et brièveté après affichage et refresh.
- [ ] Tester une exécution neuve jusqu’à synthesis : D est publié avant l’appel LLM, puis finalisation au succès. Vérifier que nombre et empreintes des combats D restent identiques avant/après E.
- [ ] Archiver runIds, corpus/empreintes, quotas obtenus, qualité des stats, modèle/prompt, durées de préparation et génération, tokens/coût **seulement si mesurés**, résultats des tests et lecture humaine. Aucun benchmark chiffré inventé et aucune promesse de qualité stratégique sur N=2.
- [ ] Exécuter les tests ciblés Python, runtime, SQL et Angular, puis les parcours navigateur. Ne pas déclarer l’intégration LLM réelle validée sur un client mock.

## Critère de fin

Le même run fournit un rapport complet dont A–D sont inchangées et dont E conseille le joueur à partir des **statistiques de tous ses combats D** et des **logs normalisés de la sélection 15/15/20**. La win condition, les menaces et nos Pokémon forts sont structurés et affichés dans la page actuelle. Les sources sont inspectables, les erreurs explicites, et **E ne simule aucune partie supplémentaire**.

## Références techniques pour l’implémentation

- [Skill locale langgraph-generate-graph](../../../.agents/skills/langgraph-generate-graph/SKILL.md) : structure des fichiers, nœuds, state, store et prompts obligatoire.
- [API de graphe LangGraph](https://docs.langchain.com/oss/python/langgraph/graph-api) : construction/compilation du `StateGraph` et transitions séquentielles.
- [Intégration ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai) : bibliothèque cliente conservée avec `base_url` DeepInfra explicite ; verrouiller la version réellement testée.
- [DeepInfra — Chat Completions](https://docs.deepinfra.com/chat/overview), [modèle DeepSeek-V4.1-Flash-1017](https://deepinfra.com/deepseek-ai/DeepSeek-V4.1-Flash-1017/api) et [sorties structurées](https://docs.deepinfra.com/chat/structured-outputs) : endpoint, authentification et format de réponse côté fournisseur.
- [Protocole de simulation Showdown](https://github.com/smogon/pokemon-showdown/blob/master/sim/SIM-PROTOCOL.md) : références des messages de bataille, à confronter à la version locale utilisée pour la capture ; la présence d’un message ne suffit pas à prouver une attribution de dégâts.
