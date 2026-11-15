# Diagnostic du conditionnement de notre sélection de quatre — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prouver si le quatre proposé par la policy BC dépend réellement de l'équipe adverse, rendre visible la diversité des compositions échantillonnées en phase C et empêcher l'interface de présenter une sélection unique comme une comparaison riche.

**Architecture:** Le bridge expose les quatre complets choisis au team preview et une empreinte non sensible de l'observation réellement fournie à la policy. La phase C publie des diagnostics de fréquence calculés à partir de ses combats existants, sans augmenter son budget. Un script d'audit séparé rejoue les mêmes seeds contre plusieurs équipes adverses et compare les distributions. Angular affiche ces informations dans le détail de la sélection.

**Tech Stack:** Python 3.13, Pydantic, bridge JSONL VGC-Bench/poke-env, pytest, Angular 22 standalone, Signals, Vitest, Transloco, Tailwind/daisyUI.

**Spec:** [Workflow d'analyse d'un matchup](../specs/2026-10-31-workflow-analyse-matchup.md), complété par les décisions fonctionnelles de la section suivante.

## Global Constraints

- Le plan `2026-11-09-inference-seeds-determinisme-ots.md` est un prérequis déjà implémenté : ne pas réintroduire `set_global_seed(42)` et ne pas refaire sa gestion des seeds, de l'OTS ou de `deterministic`.
- Une requête et une seed identiques doivent produire le même team preview ; deux seeds différentes doivent piloter des tirages indépendants.
- Le modèle reçoit l'équipe adverse dans `PolicyPlayer.embed_battle`. L'audit doit vérifier que le chemin applicatif conserve cette information ; il ne doit pas se contenter de relire le code du vendor.
- Ne pas forcer artificiellement de la diversité, ne pas ajouter de température et ne pas remplacer le tirage de la policy par un choix aléatoire uniforme.
- Ne pas agrandir ni réentraîner le modèle dans ce plan. Les mesures produites serviront à décider si un plan d'entraînement est nécessaire.
- Ne pas modifier les budgets A/B/C/D. L'audit contrefactuel est une commande opérateur séparée et n'est pas exécuté pendant une analyse utilisateur.
- Les anciens résultats `schemaVersion: 2` sans diagnostics doivent rester lisibles. Aucun backfill SQL et aucune migration de base ne sont nécessaires.
- Le quatre final reste une sélection unique pour tout le matchup. Le joueur choisit ses quatre avant de connaître le lead adverse réel.
- Les fréquences affichées sont des fréquences de tirage de la policy dans PokeCoach. Elles ne doivent jamais être décrites comme la majorité des joueurs du dataset.
- Les changements Python et Angular vivent dans deux dépôts Git différents : faire des commits séparés dans chaque dépôt.

## Review Focus

- Même seed et mêmes snapshots : le team preview complet et son empreinte sont strictement reproductibles.
- Même seed et équipe adverse différente : l'empreinte de l'observation côté `ours` doit changer, même si la composition choisie reste identique.
- Un seul quatre observé sur tous les combats C : le résultat reste valide mais porte un avertissement explicite d'absence d'alternative comparée.
- Plusieurs leads pour le même quatre : `uniqueFours` vaut 1 tandis que `uniqueSelections` peut être supérieur à 1.
- Ancien résultat sans `samplingDiagnostics` : Python et Angular le valident et conservent l'affichage actuel.

---

## 1. Décisions fonctionnelles à ne pas réinterpréter

### 1.1 Ce que le modèle BC produit

La policy BC ne consulte pas une table du type « dans ce matchup, la majorité des joueurs a pris ces quatre Pokémon ». Elle reçoit une observation du combat, qui contient notre équipe et l'équipe adverse, puis produit une distribution d'actions. Au team preview, deux décisions successives construisent le lead puis les deux Pokémon de back.

En mode stochastique, répéter le team preview approche la distribution apprise par le modèle. En mode déterministe, on n'observe que son argmax. Ces deux sorties restent une généralisation du réseau à partir des replays d'entraînement ; elles ne sont pas une statistique directe des replays correspondant exactement au matchup.

### 1.2 Ce que PokeCoach affiche après la phase C

La phase C laisse la policy choisir notre quatre et notre lead dans chaque combat complet, puis `aggregate_selections` classe les couples `(ourFourSlots, ourLeadSlots)` observés selon la couverture des leads adverses et le taux de victoire simulé. La sélection affichée est donc le gagnant de cette règle. Ce n'est ni le quatre humain majoritaire du dataset, ni nécessairement le quatre le plus souvent tiré par la policy.

### 1.3 Résultat attendu de ce plan

Après implémentation, il doit être possible de répondre séparément à quatre questions :

1. La policy reçoit-elle une observation différente lorsque l'équipe adverse change ?
2. Pour un matchup donné, combien de quatre et de couples quatre/lead la phase C a-t-elle réellement observés ?
3. La distribution des quatre change-t-elle lorsque seule l'équipe adverse change et que les mêmes seeds sont réutilisées ?
4. La sélection finale est-elle issue d'une vraie comparaison ou était-elle le seul candidat disponible ?

Le plan ne définit aucun seuil universel de « bonne diversité ». Un quatre dominant peut être correct pour une équipe très rigide. Il fournit les données nécessaires pour distinguer cette situation d'un effondrement comportemental du modèle.

## 2. Cartographie des fichiers

### Dépôt `pokecoach2-python`

- `engine-runtime/src/pokecoach_vgc_bridge/battle_session.py` : capturer l'empreinte de la première observation de team preview pour chaque joueur.
- `engine-runtime/src/pokecoach_vgc_bridge/battle_runner.py` : retourner les quatre complets du preview et leurs empreintes.
- `engine-runtime/src/pokecoach_vgc_bridge/normalization.py` : normaliser le contrat de réponse preview.
- `src/pokecoach_python/engine/contracts.py` : étendre `PreviewRecord` avec les quatre complets optionnels.
- `src/pokecoach_python/engine/vgc_bench_adapter.py` : parser les nouveaux champs du bridge.
- `src/pokecoach_python/schemas/analysis_result.py` : typer les diagnostics publiés avec `leadPick`.
- `src/pokecoach_python/workflow/aggregation/selections.py` : calculer les distributions observées et les limitations.
- `src/pokecoach_python/diagnostics/teampreview_conditioning.py` : calcul pur des distributions et comparaisons contrefactuelles.
- `scripts/audit-teampreview-conditioning.py` : commande opérateur utilisant le vrai adapter.
- `docs/recettes/audit-conditionnement-selection-quatre.md` : exécution et interprétation de l'audit réel.

### Dépôt `pokecoach2-angular/pokecoach-angular`

- `src/app/core/models/simulation-result.model.ts` : types des diagnostics.
- `src/app/core/graphql/simulation-result-validator.ts` : validation stricte avec compatibilité des anciens résultats.
- `src/app/core/matchup/selection-details-display.ts` : modèle de présentation.
- `src/app/features/matchup/selection-detail-modal.ts` et `.html` : affichage des fréquences et de leur provenance.
- `src/app/features/matchup/matchup-left-column.ts` et `.html` : transmettre notre équipe à la modale.
- `public/i18n/fr.json` et `public/i18n/en.json` : textes explicites et non ambigus.

---

### Task 1: Publier la diversité réellement observée en phase C

**Files:**
- Modify: `src/pokecoach_python/schemas/analysis_result.py`
- Modify: `src/pokecoach_python/workflow/aggregation/selections.py`
- Modify: `tests/unit/test_phase_c.py`
- Modify: `tests/unit/test_analysis_result.py`
- Modify: `contracts/examples/openings/ac.json`

**Interfaces:**
- Produces: `LeadPickSamplingDiagnostics`, ajouté sous `LeadPickSection.samplingDiagnostics`.
- Consumes: les `BattleRecord` déjà fournis à `aggregate_selections`; aucun combat supplémentaire.

- [ ] **Step 1: Ajouter les tests de contrat en échec.** Construire un résultat AC avec `samplingDiagnostics` et vérifier les règles suivantes : les comptes de `fourFrequencies` et `selectionFrequencies` somment chacun à `sampleSize`; les slots sont valides; les comptes sont strictement positifs; `uniqueFours` et `uniqueSelections` correspondent aux tailles des listes. Ajouter un test qui valide encore un ancien AC sans ce champ.

- [ ] **Step 2: Définir les modèles Pydantic exacts.** Ajouter :

```python
class FourFrequency(StrictModel):
    ourFourSlots: tuple[int, int, int, int]
    count: int = Field(ge=1)

class SelectionFrequency(StrictModel):
    selection: LeadSelection
    count: int = Field(ge=1)

class LeadPickSamplingDiagnostics(StrictModel):
    source: Literal["policy-samples"]
    samplingPolicy: Literal["stochastic-team-preview-v1"]
    sampleSize: int = Field(ge=1)
    uniqueFours: int = Field(ge=1, le=15)
    uniqueSelections: int = Field(ge=1)
    fourFrequencies: list[FourFrequency]
    selectionFrequencies: list[SelectionFrequency]
```

Ajouter `samplingDiagnostics: LeadPickSamplingDiagnostics | None = None` à `LeadPickSection`. Canonicaliser `ourFourSlots` dans `FourFrequency` par ordre croissant. Dans `SelectionFrequency`, conserver le lead dans `ourLeadSlots` et présenter `ourFourSlots` avec le lead en premier via `four_slots_leads_first`.

- [ ] **Step 3: Exécuter les tests ciblés et constater l'échec attendu.** Run: `uv run pytest tests/unit/test_analysis_result.py tests/unit/test_phase_c.py -q`. Expected: FAIL car l'agrégateur ne renseigne pas encore `samplingDiagnostics`.

- [ ] **Step 4: Implémenter `_build_sampling_diagnostics(battles, studied_ids, leads_by_slots) -> LeadPickSamplingDiagnostics`.** Ne compter que les combats des leads adverses effectivement étudiés. Agréger séparément le quatre canonique et le couple quatre/lead. Trier chaque distribution par `count` décroissant puis par slots croissants pour garantir un JSON stable.

- [ ] **Step 5: Brancher les diagnostics dans `aggregate_selections`.** Le `sampleSize` doit être exactement le nombre de combats ayant alimenté le classement. Ne pas utiliser `section_a.sampleSize`, qui correspond à la phase A. Ne pas changer `_rank_candidates` ni `selectionRuleVersion` dans cette tâche.

- [ ] **Step 6: Ajouter les limitations explicites.** Si `uniqueFours == 1`, ajouter : « La policy n'a échantillonné qu'un seul quatre sur N combats de phase C ; aucune composition alternative n'a pu être comparée. » Si plusieurs quatre existent mais que chacun n'a qu'un très faible effectif, conserver la limitation d'effectifs faibles existante sans inventer un seuil supplémentaire.

- [ ] **Step 7: Couvrir les cas importants dans `test_phase_c.py`.** Ajouter les tests `test_sampling_diagnostics_distinguish_four_from_four_lead`, `test_sampling_diagnostics_are_stably_sorted`, `test_single_four_adds_explicit_limitation` et `test_diagnostics_ignore_unstudied_opponent_leads`.

- [ ] **Step 8: Mettre à jour l'exemple AC puis exécuter la suite.** Run: `uv run pytest tests/unit/test_phase_c.py tests/unit/test_analysis_result.py -q`. Expected: PASS.

- [ ] **Step 9: Commit Python.**

```bash
git add src/pokecoach_python/schemas/analysis_result.py \
  src/pokecoach_python/workflow/aggregation/selections.py \
  tests/unit/test_phase_c.py tests/unit/test_analysis_result.py \
  contracts/examples/openings/ac.json
git commit -m "feat: expose phase C selection diversity"
```

---

### Task 2: Exposer le team preview complet et l'empreinte de l'observation

**Files:**
- Modify: `engine-runtime/src/pokecoach_vgc_bridge/battle_session.py`
- Modify: `engine-runtime/src/pokecoach_vgc_bridge/battle_runner.py`
- Modify: `engine-runtime/src/pokecoach_vgc_bridge/normalization.py`
- Modify: `engine-runtime/src/pokecoach_vgc_bridge/fixture_sim.py`
- Modify: `src/pokecoach_python/engine/contracts.py`
- Modify: `src/pokecoach_python/engine/vgc_bench_adapter.py`
- Modify: `engine-runtime/tests/test_preview_lifecycle.py`
- Create: `engine-runtime/tests/test_preview_observation_fingerprint.py`
- Modify: `tests/integration/test_vgc_preview_real.py`
- Modify: `tests/unit/test_vgc_subprocess.py`

**Interfaces:**
- Produces: `PreviewRecord.our_four_slots`, `PreviewRecord.opponent_four_slots` et `meta["ourObservationFingerprint"]`.
- Consumes: le flux de seed et le mode stochastique mis en place par le plan d'inférence précédent.

- [ ] **Step 1: Écrire les tests du nouveau contrat en échec.** Une réponse preview complète contient `ourFourSlots` et `opponentFourSlots`, chacun avec quatre slots distincts entre 0 et 5. L'adapter les convertit en tuples. Si un ancien bridge omet ces champs, l'adapter retourne `None` afin de préserver la compatibilité pendant un déploiement progressif.

- [ ] **Step 2: Tester l'empreinte sans charger le checkpoint.** Extraire un helper pur :

```python
def fingerprint_policy_observation(observation: npt.NDArray[np.float32], action_mask: npt.NDArray) -> str:
    ...
```

L'empreinte est `sha256-v1:<hex>`, calculée sur la forme, les octets C-contigus de l'observation float32 et le masque converti en booléens. Tester : mêmes tableaux = même empreinte; un changement adversaire simulé dans l'observation = empreinte différente; aucun tableau brut n'apparaît dans la sortie.

- [ ] **Step 3: Capturer uniquement la première observation de team preview.** Dans `RecordingPolicyPlayer.choose_move`, avant l'appel parent, si `battle.in_team_preview` et si `pokecoach_preview_observation_fingerprint` n'existe pas encore, calculer l'observation avec `self.embed_battle(battle, fake_rating=2000)`, le masque avec `DoublesEnv.get_action_mask(battle)`, puis mémoriser l'empreinte. Ne pas recalculer au second choix du team preview et ne pas modifier la seed.

- [ ] **Step 4: Retourner les quatre complets depuis le runner.** Remplacer le retour limité aux leads de `_await_preview_selection` par une structure privée contenant les quatre slots P1 et P2. `_run_policy_preview_battle` dérive les leads depuis les deux premiers slots et transmet aussi les quatre complets à `build_preview`.

- [ ] **Step 5: Étendre la normalisation sans casser le fixture.** La réponse JSONL preview expose au niveau racine `ourFourSlots` et `opponentFourSlots`; `meta` contient `ourObservationFingerprint` et `opponentObservationFingerprint` lorsqu'ils existent. Mettre le fixture au même format avec des valeurs stables.

- [ ] **Step 6: Étendre `PreviewRecord`.** Ajouter après les champs existants :

```python
our_four_slots: tuple[int, int, int, int] | None = None
opponent_four_slots: tuple[int, int, int, int] | None = None
```

Le workflow A continue de lire uniquement `opponent_lead_slots`; aucune donnée de diagnostic ne doit entrer dans `OpponentLeadsSection`.

- [ ] **Step 7: Renforcer le test réel opt-in.** Dans `test_preview_real_checkpoint`, vérifier pour deux appels identiques : quatre complets identiques, empreinte côté `ours` identique et format `sha256-v1:`. Ajouter un appel avec une copie de l'adversaire dont un Pokémon est remplacé; l'empreinte côté `ours` doit changer. Le test reste protégé par `require_vgc_real`.

- [ ] **Step 8: Exécuter les tests bridge et adapter.** Run: `uv run pytest engine-runtime/tests/test_preview_lifecycle.py engine-runtime/tests/test_preview_observation_fingerprint.py tests/unit/test_vgc_subprocess.py tests/integration/test_vgc_preview_real.py -q`. Expected: PASS, avec le test réel skip si le profil VGC réel n'est pas configuré.

- [ ] **Step 9: Commit Python.**

```bash
git add engine-runtime/src engine-runtime/tests \
  src/pokecoach_python/engine/contracts.py \
  src/pokecoach_python/engine/vgc_bench_adapter.py \
  tests/integration/test_vgc_preview_real.py tests/unit/test_vgc_subprocess.py
git commit -m "feat: expose complete policy team previews"
```

---

### Task 3: Créer l'audit contrefactuel de conditionnement

**Files:**
- Create: `src/pokecoach_python/diagnostics/__init__.py`
- Create: `src/pokecoach_python/diagnostics/teampreview_conditioning.py`
- Create: `scripts/audit-teampreview-conditioning.py`
- Create: `tests/unit/test_teampreview_conditioning.py`
- Create: `tests/integration/test_teampreview_conditioning_cli.py`

**Interfaces:**
- Consumes: `EngineAdapter.preview(SimulationRequest) -> PreviewRecord` enrichi en tâche 2.
- Produces: un rapport JSON autonome, versionné `auditVersion: 1`.

- [ ] **Step 1: Écrire les tests de calcul pur en échec.** Couvrir la canonicalisation d'un quatre, le comptage des quatre et des couples quatre/lead, la reproductibilité par seed, et la distance de variation totale entre deux distributions.

- [ ] **Step 2: Définir les types du rapport.** Utiliser des dataclasses gelées ou des modèles Pydantic avec ces informations minimales : identité de l'équipe adverse, nombre d'échantillons, distribution des quatre, distribution des couples quatre/lead, empreintes d'observation uniques, et pour chaque paire d'adversaires `pairedSelectionChanges`, `pairedSelectionChangeRate` et `totalVariationDistance`.

- [ ] **Step 3: Implémenter les calculs purs.** Pour deux distributions de quatre `p` et `q`, calculer `0.5 * sum(abs(p[k] - q[k]))` sur l'union des clés. Les fréquences utilisent le même dénominateur `samples`. Les changements appariés comparent les quatre obtenus avec exactement la même seed face aux deux adversaires.

- [ ] **Step 4: Implémenter `run_conditioning_audit`.** Signature :

```python
def run_conditioning_audit(
    engine: EngineAdapter,
    *,
    our_snapshot: dict[str, Any],
    opponents: Sequence[NamedSnapshot],
    regulation: str,
    checkpoint_id: str,
    base_seed: int,
    samples: int,
    timeout_seconds: float,
) -> ConditioningAuditReport:
    ...
```

Exiger au moins deux adversaires et `samples >= 2`. Pour chaque index `i`, utiliser la seed `base_seed + i` pour tous les adversaires. Refuser une réponse sans quatre complet ou sans empreinte : l'audit ne doit pas conclure à partir de données partielles.

- [ ] **Step 5: Classer le constat sans prétendre mesurer l'intelligence.** Pour chaque paire, produire exactement l'un de ces statuts :

  - `observation-and-selection-differ` : empreintes différentes et au moins un quatre apparié différent;
  - `observation-differs-selection-stable` : empreintes différentes mais aucun quatre apparié différent;
  - `observation-not-different` : empreinte identique malgré des snapshots adverses différents; considérer ce statut comme une erreur du pipeline.

Ne pas ajouter de statut `healthy`, `smart` ou `good-diversity`.

- [ ] **Step 6: Écrire la CLI.** Arguments exacts : `--our-snapshot PATH`, au moins deux `--opponent NAME=PATH`, `--regulation`, `--checkpoint-id`, `--samples` (défaut 300), `--base-seed` (défaut 1), `--timeout-seconds` et `--output PATH`. Charger `Settings`, créer `VgcBenchEngineAdapter`, appeler `preflight`, exécuter l'audit, écrire le JSON avec indentation et fermer l'adapter dans `finally`.

- [ ] **Step 7: Définir les codes de sortie.** `0` si l'audit est complet, même lorsque les sélections restent identiques; `1` si un couple reçoit `observation-not-different`; `2` pour arguments, snapshots ou réponses invalides. Toujours écrire le rapport lorsque suffisamment de données existent pour expliquer le résultat.

- [ ] **Step 8: Tester la CLI avec un faux adapter.** Le test ne démarre ni Showdown ni Torch. Vérifier les seeds appariées, le JSON stable, les trois statuts et les codes de sortie.

- [ ] **Step 9: Exécuter les tests.** Run: `uv run pytest tests/unit/test_teampreview_conditioning.py tests/integration/test_teampreview_conditioning_cli.py -q`. Expected: PASS.

- [ ] **Step 10: Commit Python.**

```bash
git add src/pokecoach_python/diagnostics scripts/audit-teampreview-conditioning.py \
  tests/unit/test_teampreview_conditioning.py \
  tests/integration/test_teampreview_conditioning_cli.py
git commit -m "feat: audit team preview conditioning"
```

---

### Task 4: Afficher les fréquences de la policy dans Angular

**Files:**
- Modify: `../pokecoach2-angular/pokecoach-angular/src/app/core/models/simulation-result.model.ts`
- Modify: `../pokecoach2-angular/pokecoach-angular/src/app/core/graphql/simulation-result-validator.ts`
- Modify: `../pokecoach2-angular/pokecoach-angular/src/app/core/graphql/simulation-result-validator.spec.ts`
- Modify: `../pokecoach2-angular/pokecoach-angular/src/app/core/matchup/selection-details-display.ts`
- Modify: `../pokecoach2-angular/pokecoach-angular/src/app/core/matchup/selection-details-display.spec.ts`
- Modify: `../pokecoach2-angular/pokecoach-angular/src/app/features/matchup/selection-detail-modal.ts`
- Modify: `../pokecoach2-angular/pokecoach-angular/src/app/features/matchup/selection-detail-modal.html`
- Create: `../pokecoach2-angular/pokecoach-angular/src/app/features/matchup/selection-detail-modal.spec.ts`
- Modify: `../pokecoach2-angular/pokecoach-angular/src/app/features/matchup/matchup-left-column.ts`
- Modify: `../pokecoach2-angular/pokecoach-angular/src/app/features/matchup/matchup-left-column.html`
- Modify: `../pokecoach2-angular/pokecoach-angular/public/i18n/fr.json`
- Modify: `../pokecoach2-angular/pokecoach-angular/public/i18n/en.json`

**Interfaces:**
- Consumes: `LeadPickSection.samplingDiagnostics` optionnel produit en tâche 1.
- Produces: une section de diagnostic dans la modale « Détail de la sélection ».

- [ ] **Step 1: Ajouter les types TypeScript.** Reproduire exactement `FourFrequencyV2`, `SelectionFrequencyV2` et `LeadPickSamplingDiagnosticsV2`, puis ajouter `samplingDiagnostics?: LeadPickSamplingDiagnosticsV2 | null` à `LeadPickSectionV2`. Ne pas utiliser `unknown` pour ces nouveaux champs.

- [ ] **Step 2: Écrire les tests du validateur en échec.** Accepter un ancien `leadPick` sans diagnostics. Pour un diagnostic présent, vérifier source, policy, bornes des slots, quatre distincts, lead inclus dans le quatre, comptes positifs, sommes et valeurs de `uniqueFours`/`uniqueSelections`. Rejeter une somme incohérente au lieu de corriger silencieusement.

- [ ] **Step 3: Étendre `SelectionDetailsDisplay`.** Fournir à la vue une liste ordonnée de quatre avec `count`, `sampleSize` et les Pokémon résolus depuis notre équipe. Le mapper ne recalcule pas les fréquences depuis `comparisons`, car les diagnostics backend sont la source de vérité.

- [ ] **Step 4: Transmettre `ourTeam` à la modale.** Ajouter un input requis à `SelectionDetailModal`, le relayer depuis `MatchupLeftColumn`, et utiliser les slots pour afficher les noms des quatre Pokémon. Ne pas dupliquer une copie de l'équipe dans le modèle de résultat.

- [ ] **Step 5: Ajouter le rendu accessible.** Dans la modale existante, ajouter sous la justification une section avec un `<h3>` nu, la phrase de provenance, un badge neutre « X quatre distincts sur N simulations », puis une liste des quatre par fréquence décroissante. Chaque ligne contient les quatre noms, `count / sampleSize` et le pourcentage calculé pour l'affichage.

- [ ] **Step 6: Afficher l'absence de diversité comme une information persistante.** Lorsque `uniqueFours === 1`, rendre une alerte douce de niveau `warning` : « Le modèle n'a tiré qu'une seule composition sur {{count}} simulations. Cette recommandation n'a pas été comparée à d'autres compositions. » Ne pas qualifier la composition de mauvaise.

- [ ] **Step 7: Expliquer la provenance sans ambiguïté.** Ajouter les clés FR/EN correspondant à : « Ces fréquences proviennent des simulations du modèle pour ce matchup. Elles ne représentent pas directement les choix majoritaires des joueurs du dataset. » Aucun texte utilisateur ne doit employer « confiance du modèle » car ce plan ne calcule pas une calibration.

- [ ] **Step 8: Tester le composant.** Vérifier l'affichage multi-quatre, l'alerte mono-quatre, les noms résolus par slots, le pourcentage et l'absence totale de la zone pour un ancien résultat sans diagnostics.

- [ ] **Step 9: Exécuter les contrôles Angular.** Depuis `pokecoach2-angular/pokecoach-angular`, run: `npm test -- --run`, puis `npm run build`. Expected: PASS.

- [ ] **Step 10: Exécuter les greps du design system sur les templates modifiés.** Vérifier qu'aucun radius, shadow, couleur sémantique d'emphase ou style de titre interdit n'a été ajouté. Expected: aucune sortie pour les motifs interdits documentés dans `.agents/skills/design-system/SKILL.md`.

- [ ] **Step 11: Commit Angular.**

```bash
git add src/app/core src/app/features/matchup public/i18n
git commit -m "feat: explain model selection diversity"
```

---

### Task 5: Documenter et exécuter la recette de décision

**Files:**
- Create: `docs/recettes/audit-conditionnement-selection-quatre.md`
- Modify: `docs/recettes/phase-c.md`

**Interfaces:**
- Consumes: la CLI de la tâche 3 et les diagnostics phase C de la tâche 1.
- Produces: un rapport JSON conservable et une décision reproductible sur la prochaine action.

- [ ] **Step 1: Documenter les prérequis.** Profil du modèle réel chargé, OTS aligné avec l'entraînement, team preview C stochastique, deux dépôts aux commits attendus, Showdown disponible et snapshots JSON complets de notre équipe plus au moins trois équipes adverses réellement différentes.

- [ ] **Step 2: Donner la commande réelle.** Exemple avec 300 seeds appariées et trois adversaires :

```bash
uv run python scripts/audit-teampreview-conditioning.py \
  --our-snapshot /chemin/our-team.json \
  --opponent balance=/chemin/opponent-balance.json \
  --opponent trick-room=/chemin/opponent-trick-room.json \
  --opponent offense=/chemin/opponent-offense.json \
  --regulation M-C \
  --checkpoint-id vgcbench-mc-bc \
  --samples 300 \
  --base-seed 1 \
  --output artifacts/teampreview-conditioning.json
```

- [ ] **Step 3: Documenter la matrice de décision.** Appliquer dans cet ordre :

  1. `observation-not-different` : bug du pipeline d'observation/OTS/snapshot; ne pas juger le modèle et ne pas relancer un entraînement.
  2. Empreintes différentes et plusieurs changements appariés : la sélection est comportementalement conditionnée par l'adversaire; un même quatre final peut être un cœur dominant ou le résultat de l'agrégation.
  3. Empreintes différentes mais zéro changement apparié sur les trois adversaires : le moteur transmet bien l'adversaire mais la policy se comporte comme si son quatre était invariant; préparer ensuite un plan dataset/modèle.
  4. Plusieurs quatre sont observés, mais le même gagnant sort de tous les matchups : examiner les lignes `comparisons`, la couverture et les taux de victoire avant de modifier le modèle; un futur plan pourra séparer découverte des candidats et évaluation à budget égal.

- [ ] **Step 4: Relancer au moins trois analyses standard.** Utiliser la même équipe à nous contre les trois adversaires de l'audit. Dans chaque détail de sélection, relever `sampleSize`, `uniqueFours`, `uniqueSelections`, le quatre dominant et le quatre finalement recommandé.

- [ ] **Step 5: Vérifier le sens du résultat affiché.** La modale doit dire « simulations du modèle », jamais « majorité des joueurs ». Une sélection mono-quatre doit afficher l'avertissement, même si son taux de victoire simulé est élevé.

- [ ] **Step 6: Enregistrer les preuves.** Conserver le JSON d'audit, les trois run IDs, le fingerprint du checkpoint, le commit Python, le commit Angular et une courte conclusion dans la recette. Ne pas conclure « modèle trop petit » à partir du seul nombre de quatre uniques.

- [ ] **Step 7: Exécuter les suites finales.** Python : `uv run pytest -q` et `uv run ruff check .`. Bridge : `uv run pytest engine-runtime/tests -q`. Angular : `npm test -- --run` et `npm run build`. Expected: PASS; les tests réels opt-in peuvent être skip uniquement si la recette réelle a été exécutée séparément avec le checkpoint.

- [ ] **Step 8: Commit documentation Python.**

```bash
git add docs/recettes/audit-conditionnement-selection-quatre.md docs/recettes/phase-c.md
git commit -m "docs: add bring-four conditioning audit"
```

## 3. Critères d'acceptation finaux

1. Le détail d'une analyse indique combien de quatre distincts ont été réellement tirés en phase C et avec quels effectifs.
2. Une analyse où la policy n'a produit qu'un seul quatre ne prétend plus avoir comparé plusieurs compositions.
3. Un ancien résultat sans diagnostics reste valide et s'affiche comme avant.
4. L'audit reproduit exactement les sélections pour une même seed et un même adversaire.
5. L'audit prouve par empreinte que changer l'équipe adverse change l'observation reçue par notre policy.
6. Le rapport sépare la sensibilité de l'observation de la sensibilité de la décision.
7. Aucun texte ne présente la recommandation comme le choix majoritaire des joueurs du dataset.
8. Aucun changement de modèle, de dataset, de budget ou de règle de classement n'est caché dans cette implémentation.

## 4. Suite éventuelle, hors périmètre

Si l'audit obtient `observation-differs-selection-stable` contre plusieurs archétypes, écrire un nouveau plan dédié au modèle et au dataset. Ce futur travail devra mesurer les labels de team preview dans train/validation, comparer le checkpoint parent et le checkpoint fine-tuné, calculer les probabilités/entropies de la policy et tester un modèle plus grand seulement après avoir établi que la capacité est le facteur limitant.

Si plusieurs candidats existent mais sont mal comparés, écrire plutôt un plan de phase C en deux étages : découverte de candidats par previews peu coûteux, puis combats imposés à budget égal par candidat et par lead adverse. Ne pas mélanger ce changement coûteux avec le présent plan de diagnostic.
