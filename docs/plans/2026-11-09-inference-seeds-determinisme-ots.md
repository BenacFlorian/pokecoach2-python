# Correction des seeds, du déterminisme et des open team sheets — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Exécuter les tâches dans l'ordre et appliquer une boucle TDD stricte : écrire le test, constater qu'il échoue pour la raison attendue, implémenter le minimum, puis obtenir le succès. Ne pas modifier le checkpoint, le dataset, les budgets d'analyse ou les résultats déjà enregistrés.

**But :** faire de chaque seed de simulation la source réelle des tirages de la policy, respecter le mode déterministe déclaré par le profil pour les décisions qui ne construisent pas une distribution, échantillonner les team previews et ouvertures que le pipeline doit comparer, et fournir au modèle les open team sheets comme pendant son entraînement.

**Architecture :** séparer le chargement des poids du contrôle de l'inférence. Le chargement ne modifie plus les RNG globaux. Chaque joueur reçoit un flux de seeds dérivé de la seed de requête, de son côté et de l'index de décision ; juste avant chaque appel synchrone à la policy, ce flux initialise Torch. Distinguer le déterminisme du team preview de celui des actions de combat : A et la découverte des candidats C échantillonnent le team preview, B échantillonne les ouvertures, tandis que les actions des combats complets gardent le réglage du profil.

**Stack :** Python 3.13, bridge JSONL, VGC-Bench, poke-env, PyTorch, Pydantic Settings, pytest, Ruff, serveur Pokémon Showdown local.

**Spécification :** demande utilisateur du 9 novembre 2026 et décisions détaillées dans la section 1 de ce document.

## Contraintes globales

- Le checkpoint `bc-mb-mc-80k-20261109T095752Z` et son hash ne changent pas.
- Le dataset et le trainer ne changent pas ; ce chantier concerne uniquement l'inférence dans `pokecoach2-python` et la configuration locale du modèle.
- Une même seed de requête doit produire le même flux de tirages de policy pour un même côté et la même séquence de décisions.
- Deux seeds différentes doivent produire deux flux RNG différents ; elles ne sont pas obligées de produire deux actions différentes si la policy choisit fortuitement la même action.
- Le flux `ours` et le flux `opponent` doivent être indépendants, même si les deux joueurs prennent leurs décisions dans un ordre différent.
- Ne pas promettre qu'un combat complet sera identique à seed égale : ce plan contrôle la policy PyTorch, pas tous les aléas internes du serveur Showdown.
- Le team preview de A et de C doit être stochastique même si le profil contient `deterministic: true` ; sinon C ne découvre qu'un seul candidat de quatre/lead à comparer.
- La phase B doit échantillonner le choix des backs et les actions du premier tour, puisqu'elle produit des distributions d'ouvertures.
- Les actions des combats complets C/D utilisent `inference.deterministic` du profil. En D, les quatre sont déjà imposés ; l'override stochastic du team preview n'a donc aucun effet sur leur composition.
- L'OTS du runtime doit être activée pour le profil M-C actuel, car le dataset d'entraînement exigeait `require_ots: true`.
- Une variable d'environnement explicitement définie doit pouvoir surcharger l'OTS du profil ; une valeur absente ne doit pas écraser le profil.
- Aucun test unitaire ne doit nécessiter un serveur Showdown, un GPU ou le checkpoint de production.
- Les tests réels restent conditionnels à `POKECOACH_VGC_REAL=1` et ne doivent pas être transformés en tests CI ordinaires.

## Points de contrôle prioritaires

1. Un profil absent ou ancien, sans `open_team_sheets`, conserve le comportement historique `false` au lieu d'activer silencieusement l'OTS pour tous les modèles.
2. `POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS=false` doit réellement désactiver l'OTS même si le profil vaut `true`; les chaînes invalides doivent être refusées au démarrage.
3. Le chargement répété d'un modèle ne doit plus appeler `set_global_seed(42)` ni remettre le flux d'échantillonnage à un état constant.
4. Les overrides propres à A/B/C doivent être appliqués seulement au segment concerné (team preview ou actions), sans écraser durablement la valeur du profil sur le joueur.
5. L'ordre d'appel de P1/P2 ne doit pas échanger leurs tirages : la dérivation inclut le côté et un compteur propre au joueur.

---

## 1. Décisions de conception à respecter

### 1.1 Quatre réglages distincts

Ne plus utiliser une seule seed globale implicite pour représenter plusieurs intentions :

| Notion | Source | Rôle |
| --- | --- | --- |
| Seed de requête | `SimulationRequest.seed`, transportée dans le payload JSONL | Racine reproductible de tous les tirages de policy de cette simulation |
| Mode déterministe des actions | `profile.inference.deterministic` | Choix argmax ou échantillonnage des capacités/switchs pendant les combats complets |
| Override team preview | argument `teampreview_deterministic` de `create_policy_pair` | A et C doivent échantillonner les compositions |
| Override des actions B | argument `deterministic=False` de `_run_first_turn_battle` | B doit estimer une distribution de backs et d'ouvertures |

Le champ `deterministic` ne contrôle pas l'OTS. Le champ OTS ne contrôle pas le RNG. La seed ne doit pas modifier la configuration du profil. Ne pas utiliser un unique booléen mutable sans le restaurer : le team preview peut être stochastique alors que les actions du combat qui suit sont déterministes.

Matrice exigée :

| Chemin | Team preview | Actions après preview | Raison |
| --- | --- | --- | --- |
| A — `preview` | stochastique | aucune | distribution des leads adverses |
| C — `full_battle` sans quatre imposé | stochastique | profil | découvrir plusieurs quatre/leads candidats puis les évaluer |
| B — `first_turn` | stochastique pour les slots non imposés | stochastique | distribution des backs et ouvertures |
| D — `full_battle` avec quatre imposés | sans effet car composition imposée | profil | évaluation du choix C sur scénarios fixés |

### 1.2 Dérivation du flux de seeds

Créer un petit composant pur dans le runtime :

```text
PolicyDecisionSeedStream(request_seed: int, side: Literal["ours", "opponent"])
next_seed() -> int
```

Pour l'index de décision `i`, encoder en UTF-8 :

```text
pokecoach-policy-v1:{request_seed}:{side}:{i}
```

Calculer SHA-256, convertir les huit premiers octets avec `int.from_bytes(..., "big")`, puis borner à `0..2**63-1` pour une valeur portable vers `torch.manual_seed`. Incrémenter l'index après production de la seed.

Conséquences attendues :

- recréer un flux avec la même seed et le même côté redonne la même séquence ;
- changer la seed, le côté ou l'index change la seed dérivée ;
- chaque joueur possède son propre compteur ;
- aucun appel ne dépend de `hash()` Python, de l'ordre SQL, d'un UUID ou de l'ordonnancement P1/P2.

Le reseeding doit avoir lieu dans `RecordingPolicyPlayer.choose_move`, immédiatement avant `super().choose_move(battle)`. Cette méthode est synchrone : ne jamais ajouter de `await` entre le reseeding et l'appel de la policy. `PolicyPlayer.teampreview()` appelle déjà `self.choose_move()` pour ses deux choix ; le même mécanisme couvre donc le lead puis le back sans dupliquer de logique. Lorsque le team preview possède un override différent des actions, `RecordingPolicyPlayer.teampreview` applique temporairement `teampreview_deterministic`, appelle la méthode parente, puis restaure le mode d'action dans un bloc `finally`.

### 1.3 Priorité de configuration OTS

Résoudre `open_team_sheets` une seule fois lors de la création de la paire de joueurs :

1. variable `POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS` si elle est explicitement renseignée ;
2. sinon `profile.inference.open_team_sheets` ;
3. sinon `false` pour un checkpoint legacy sans profil.

Le profil actuel M-C doit déclarer `open_team_sheets: true`. Le défaut Python reste `false` pour ne pas changer silencieusement les anciens profils.

### 1.4 Limite de la reproductibilité

Ce plan contrôle les tirages de la policy. Il ne configure pas la seed interne du serveur Node Pokémon Showdown. La preview se termine avant le premier tour et doit être reproductible à seed égale. Pour un combat complet, seules les décisions de policy ont cette garantie ; les dégâts, critiques, speed ties et autres aléas Showdown peuvent encore varier.

### 1.5 Résultats historiques

Ne pas recalculer ni réécrire les analyses existantes. Après déploiement, créer de nouveaux runs depuis la phase A. Les pourcentages de leads produits avant ce correctif restent consultables, mais ne doivent pas servir de référence statistique.

---

## Tâche 1 — Étendre le contrat de profil et propager l'override OTS

**Fichiers :**

- Modifier `engine-runtime/src/pokecoach_vgc_bridge/model_profile.py`.
- Modifier `engine-runtime/tests/test_model_profile.py`.
- Modifier `src/pokecoach_python/core/config.py`.
- Modifier `src/pokecoach_python/engine/subprocess_client.py`.
- Modifier `tests/unit/test_config.py`.
- Modifier `tests/unit/test_vgc_subprocess.py`.
- Modifier `.env.example`.
- Modifier `configs/vgc_model_mc.example.yaml`.
- Modifier `engine-runtime/config/vgc_model.example.yaml`.

**Interfaces produites :**

```text
InferenceConfig.open_team_sheets: bool = False
Settings.showdown_open_team_sheets: bool | None
```

`VgcSubprocessClient._default_env(settings)` ne doit écrire `POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS` que si `settings.showdown_open_team_sheets` n'est pas `None`. La valeur transportée est exactement `"1"` ou `"0"`.

- [ ] **Écrire les tests de profil en échec.** Ajouter `test_inference_options_loaded_from_profile` : charger un YAML contenant `device: cpu`, `deterministic: false`, `open_team_sheets: true` et vérifier les trois valeurs. Ajouter `test_legacy_profile_defaults_open_team_sheets_to_false` sans ce champ.
- [ ] **Constater RED.** Depuis `engine-runtime`, exécuter `uv run --group dev pytest tests/test_model_profile.py -q`. Le premier test doit échouer car `InferenceConfig` ne possède pas encore `open_team_sheets`.
- [ ] **Implémenter le parsing du profil.** Ajouter le champ typé avec défaut `False`; lire `inf_raw.get("open_team_sheets", False)`. Ne pas utiliser `bool("false")`, qui vaut `True` en Python : le YAML doit fournir un vrai booléen. Si la valeur n'est pas un booléen, lever `ModelProfileError` avec le nom du champ.
- [ ] **Obtenir GREEN sur le profil.** Relancer la commande ciblée.
- [ ] **Écrire les tests Settings/subprocess en échec.** Dans `test_config.py`, vérifier valeur absente → `None`, `true` → `True`, `false` → `False`, valeur invalide → erreur Pydantic. Construire le cas « absent » avec `_env_file=None` afin que le `.env` local réel ne rende pas le test dépendant de la machine. Dans `test_vgc_subprocess.py`, vérifier absent → clé non ajoutée par le code, vrai → `"1"`, faux → `"0"`. Nettoyer aussi la variable du processus avec `monkeypatch.delenv` avant d'appeler `_default_env`, car celui-ci commence par `os.environ.copy()`.
- [ ] **Constater RED** avec `uv run pytest tests/unit/test_config.py tests/unit/test_vgc_subprocess.py -q` depuis `pokecoach2-python`.
- [ ] **Ajouter le Setting et sa propagation.** Déclarer le champ optionnel avec alias exact `POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS`. Préserver `os.environ.copy()` puis appliquer la valeur normalisée du Setting lorsqu'elle existe.
- [ ] **Obtenir GREEN** sur les tests backend ciblés.
- [ ] **Mettre à jour les exemples.** Ajouter `open_team_sheets: true` dans les deux profils M-C/Trainer d'exemple. Documenter dans `.env.example` que l'env est un override facultatif du profil, pas une deuxième valeur obligatoire.
- [ ] **Ne pas encore modifier le profil local de production.** Cette modification arrive après que le runtime sache consommer le champ, en tâche 5.

**Critère de revue :** un ancien profil fonctionne encore avec OTS désactivée ; le nouveau profil peut activer l'OTS sans dépendre du chargement implicite du fichier `.env` par le subprocess.

---

## Tâche 2 — Créer des flux de seeds indépendants par joueur et décision

**Fichiers :**

- Créer `engine-runtime/src/pokecoach_vgc_bridge/inference_control.py`.
- Créer `engine-runtime/tests/test_inference_control.py`.
- Modifier ensuite `engine-runtime/src/pokecoach_vgc_bridge/battle_session.py` dans cette même tâche uniquement pour brancher le composant.

**Interfaces produites :**

```text
PolicyDecisionSeedStream(request_seed: int, side: Literal["ours", "opponent"])
PolicyDecisionSeedStream.next_seed() -> int
seed_torch_for_policy_decision(torch_module, stream: PolicyDecisionSeedStream) -> int
```

`seed_torch_for_policy_decision` appelle `torch_module.manual_seed(seed)`. Si `torch_module.cuda.is_available()` vaut vrai, appeler aussi `torch_module.cuda.manual_seed_all(seed)`. Retourner la seed appliquée pour permettre l'audit et les tests, sans la logger à chaque décision en production.

- [ ] **Écrire les tests purs en échec.** Vérifier : séquences identiques pour deux flux recréés avec mêmes paramètres ; séquences différentes pour deux request seeds ; séquences différentes entre `ours` et `opponent` ; valeurs dans `0..2**63-1` ; compteur qui avance exactement une fois par `next_seed()`.
- [ ] **Tester le helper Torch sans importer le vrai Torch.** Utiliser un faux objet minimal qui enregistre `manual_seed` et `cuda.manual_seed_all`. Tester le chemin CUDA indisponible puis disponible.
- [ ] **Constater RED.** Depuis `engine-runtime`, exécuter `uv run --group dev pytest tests/test_inference_control.py -q`. L'import du module doit échouer avant l'implémentation.
- [ ] **Implémenter le composant pur** selon l'algorithme exact de la section 1.2. Refuser tout `side` autre que les deux littéraux prévus avec `ValueError`.
- [ ] **Obtenir GREEN** sur `test_inference_control.py`.
- [ ] **Écrire un test de branchement en échec.** Extraire ou exposer une petite factory testable pour `RecordingPolicyPlayer`, ou tester via de faux `deps`, afin de prouver que deux appels successifs à `choose_move` appliquent les indices 0 puis 1 avant d'appeler la méthode parente. Le test doit aussi vérifier qu'aucun reseeding n'est fait lorsque le joueur est déterministe, car aucun tirage Torch n'a lieu.
- [ ] **Brancher les flux dans `create_policy_pair`.** Affecter un flux `ours` à P1 et `opponent` à P2 avant le démarrage des listeners. Dans `RecordingPolicyPlayer.choose_move`, appeler le helper immédiatement avant `super().choose_move` seulement si `self.deterministic` est faux.
- [ ] **Obtenir GREEN** sur le test de branchement et l'ensemble `engine-runtime/tests/test_inference_control.py`.

**Interdictions :** ne pas utiliser un flux partagé P1/P2 ; ne pas dériver la seed depuis `session_id`; ne pas reseeder dans `teampreview` en plus de `choose_move`; ne pas utiliser `random.seed` ou `numpy.random.seed` si la décision est échantillonnée uniquement par Torch.

---

## Tâche 3 — Retirer la seed fixe du chargement et respecter le profil déterministe

**Fichiers :**

- Modifier `engine-runtime/src/pokecoach_vgc_bridge/policy_factory.py`.
- Compléter `engine-runtime/tests/test_policy_factory.py`.
- Modifier `engine-runtime/src/pokecoach_vgc_bridge/battle_session.py`.
- Créer ou compléter `engine-runtime/tests/test_policy_session_options.py`.

**Interfaces modifiées :**

```text
attach_policy_to_player(
    player,
    profile: VgcModelProfile,
    device_str: str | None = None,
    *,
    deterministic: bool | None = None,
    open_team_sheets: bool | None = None,
) -> None

create_policy_pair(
    ...,
    deterministic: bool | None = None,
    teampreview_deterministic: bool | None = None,
) -> tuple[Any, Any]
```

Règle de `attach_policy_to_player` :

```text
effective_deterministic = (
    profile.inference.deterministic
    if deterministic is None
    else deterministic
)
```

Après le chargement, affecter la policy puis `player.deterministic = effective_deterministic`.

- [ ] **Écrire les tests `attach_policy_to_player` en échec.** Monkeypatcher `load_policy_from_profile` pour éviter Torch/VGC-Bench. Vérifier que `deterministic=None` applique la valeur du profil, que `False` surcharge un profil `True`, et que la policy est toujours affectée.
- [ ] **Constater RED** avec `uv run --group dev pytest tests/test_policy_factory.py -q` depuis `engine-runtime`.
- [ ] **Supprimer la remise globale à 42.** Retirer l'import et l'appel `set_global_seed(42)` de `_load_policy_from_profile_cwd`. Ne pas le remplacer par une autre seed globale. Les poids sont intégralement rechargés depuis le checkpoint ; l'initialisation temporaire du PPO ne doit pas définir la séquence d'inférence.
- [ ] **Étendre `load_policy_from_profile` si nécessaire** pour transmettre `open_team_sheets` à la création de `ShowdownEnv`. La valeur effective fournie par la session prime ; sinon utiliser celle du profil. Cela garde cohérentes l'enveloppe de chargement et les joueurs réels.
- [ ] **Implémenter le mode déterministe effectif** dans `attach_policy_to_player`, puis obtenir GREEN sur `test_policy_factory.py`.
- [ ] **Écrire les tests de session en échec.** Avec de faux `PolicyPlayer`, profil et dépendances, vérifier que `create_policy_pair(... deterministic=None)` donne aux deux joueurs la valeur d'action du profil, tandis que `deterministic=False` donne faux aux deux joueurs. Vérifier séparément `teampreview_deterministic=False` : les deux appels de sélection de composition sont stochastiques, puis `player.deterministic` retrouve la valeur du profil avant la première action de combat. Vérifier aussi le chemin legacy sans profil : défaut faux, overrides explicites respectés.
- [ ] **Déplacer le chargement du profil au début de `create_policy_pair`.** Il doit être disponible avant de calculer OTS et déterminisme, puis être réutilisé pour attacher les deux policies. Ne pas charger le YAML trois fois.
- [ ] **Obtenir GREEN** sur les tests de session ciblés.

**Critère de revue :** après cette tâche, la valeur `deterministic: true` du YAML n'est plus décorative ; elle contrôle réellement P1/P2 hors override preview.

---

## Tâche 4 — Appliquer l'OTS et les modes stochastiques propres à A/B/C

**Fichiers :**

- Modifier `engine-runtime/src/pokecoach_vgc_bridge/battle_session.py`.
- Modifier `engine-runtime/src/pokecoach_vgc_bridge/battle_runner.py`.
- Modifier `engine-runtime/src/pokecoach_vgc_bridge/vgc_real.py`.
- Compléter `engine-runtime/tests/test_preview_lifecycle.py`.
- Compléter `engine-runtime/tests/test_policy_session_options.py`.
- Ajouter ou compléter un test de `RealRuntime.hello()` sans charger un vrai checkpoint si l'architecture des tests le permet.

**Helper attendu :**

```text
resolve_open_team_sheets(
    profile: VgcModelProfile | None,
    env_value: str | None,
) -> bool
```

Accepter comme vrais `1`, `true`, `yes`, `on` et comme faux `0`, `false`, `no`, `off`, sans distinction de casse ni espaces extérieurs. Refuser toute autre chaîne avec un message contenant `POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS`.

- [ ] **Écrire les tests de résolution OTS en échec.** Couvrir env absente + profil vrai/faux, env vraie qui surcharge profil faux, env fausse qui surcharge profil vrai, absence de profil, chaîne invalide.
- [ ] **Constater RED** sur `test_policy_session_options.py`.
- [ ] **Implémenter la résolution**, puis passer la même valeur `accept_open_team_sheet=effective_ots` aux deux `RecordingPolicyPlayer` et au chargement des policies. Ne pas conserver un `True` codé en dur dans `policy_factory.py` si la session a résolu `False`.
- [ ] **Écrire les tests de matrice en échec.** Monkeypatcher `create_policy_pair` dans chaque runner. Vérifier : A transmet `teampreview_deterministic=False`; C/full battle transmet également `teampreview_deterministic=False` tout en laissant `deterministic=None`; B/first turn transmet les deux overrides à `False`; un full battle D avec quatre imposés conserve les actions sous profil. Aucun test ne démarre Showdown.
- [ ] **Constater RED** sur `tests/test_preview_lifecycle.py`.
- [ ] **Implémenter la matrice de la section 1.1.** A et C passent `teampreview_deterministic=False`. B passe `teampreview_deterministic=False` et `deterministic=False`. Les actions C/D restent à `deterministic=None`, donc sous contrôle du profil. Ne pas déduire la phase depuis un hasard ou un nom de compte ; utiliser les arguments explicites du runner et le fait que les quatre D sont imposés.
- [ ] **Obtenir GREEN** sur les tests preview et session.
- [ ] **Rendre l'état observable.** Dans `hello()` et `preflight()`, conserver `stochastic: true` et ajouter un objet informatif stable décrivant `profileActionDeterministic`, les overrides A/B/C et `openTeamSheets`. Ne pas faire dépendre le protocole existant de ces champs supplémentaires ; les anciens clients doivent continuer à fonctionner.
- [ ] **Ajouter un test d'observabilité** vérifiant les valeurs avec le profil M-C simulé. Ne jamais inclure chemin sensible, contenu d'équipe ou seed courante dans `hello`.

**Résultat attendu :** A échantillonne les leads, C découvre plusieurs compositions candidates si la policy leur donne une probabilité non nulle, B échantillonne les backs/ouvertures, les actions des combats complets respectent le profil et les deux joueurs voient le même niveau d'information OTS.

---

## Tâche 5 — Activer la configuration M-C actuelle et documenter l'exploitation

**Fichiers :**

- Modifier `/home/webinage/Documents/perso/pokecoach2/model/MC/vgc_model_bc_mb_to_mc_80k.yaml`.
- Modifier localement `pokecoach2-python/.env` sans afficher ni réécrire les secrets existants.
- Modifier `docs/recettes/moteur-reel.md`.
- Compléter `tests/integration/test_vgc_preview_real.py`.

**Configuration finale attendue :**

```yaml
inference:
  device: auto
  deterministic: true
  open_team_sheets: true
```

Et dans l'environnement local :

```dotenv
POKECOACH_SHOWDOWN_OPEN_TEAM_SHEETS=true
```

La valeur `.env` est volontairement identique au profil pour rendre l'intention visible dans l'installation locale. Documenter qu'elle a priorité et peut être supprimée si l'on souhaite laisser le profil seul décider.

- [ ] **Modifier le profil M-C actuel** en ajoutant seulement `open_team_sheets: true`. Ne pas changer `model_id`, `trainer_package_dir`, `device` ou `deterministic`.
- [ ] **Ajouter la variable dans `.env`** sans imprimer le fichier complet dans les logs et sans committer ce fichier ignoré.
- [ ] **Mettre à jour la recette.** Remplacer le texte « OTS optionnelle, défaut 0 » par la hiérarchie env → profil → défaut legacy. Expliquer que le checkpoint M-C actuel exige l'OTS parce que son dataset avait `require_ots: true`.
- [ ] **Compléter le test réel reproductible.** Dans `test_vgc_preview_real.py`, appeler deux fois `engine.preview` avec exactement la même requête et vérifier les deux paires de leads. Ce test prouve la reproductibilité de preview à seed égale.
- [ ] **Ne pas ajouter de faux test de diversité.** Un test exigeant `len(unique) > 1` serait probabiliste et pourrait échouer avec une policy légitimement concentrée ; un test sans assertion n'apporterait aucune garantie. La diversité multi-seeds est examinée dans la recette métier de la tâche 6, tandis que les tests unitaires prouvent que les flux RNG dérivés sont distincts.
- [ ] **Vérifier `hello`/preflight** : checkpoint chargé, matrice A/B/C annoncée, actions des combats complets sous le profil et OTS vraie.

---

## Tâche 6 — Vérifications automatisées et recette de non-régression réelle

### 6.1 Tests automatisés sans Showdown

- [ ] Depuis `engine-runtime`, exécuter :

```bash
uv run --group dev pytest \
  tests/test_inference_control.py \
  tests/test_model_profile.py \
  tests/test_policy_factory.py \
  tests/test_policy_session_options.py \
  tests/test_preview_lifecycle.py -q
```

- [ ] Toujours depuis `engine-runtime`, exécuter toute la suite :

```bash
uv run --group dev pytest -q
```

- [ ] Depuis `pokecoach2-python`, exécuter :

```bash
uv run pytest tests/unit -q
uv run ruff check .
```

- [ ] Exécuter Ruff dans le runtime si le projet le fournit via l'environnement ; sinon lancer au minimum le formateur/linter configuré à la racine sans modifier `engine-runtime/vendor/`.

### 6.2 Test réel avec le checkpoint M-C

Préconditions : serveur Showdown local actif, `VGC_MODEL_PROFILE` pointant vers le profil M-C, runtime VGC-Bench installé, `POKECOACH_VGC_REAL=1`.

- [ ] Lancer le test réel preview ciblé :

```bash
export POKECOACH_VGC_REAL=1
uv run pytest tests/integration/test_vgc_preview_real.py -q -s
```

- [ ] Lancer ensuite les tests réels existants `first_turn` et `full_battle` pour vérifier que le respect de `deterministic: true` n'a pas cassé les contraintes de lead/bring-4 :

```bash
uv run pytest \
  tests/integration/test_vgc_first_turn_real.py \
  tests/integration/test_vgc_full_battle_real.py \
  tests/integration/test_vgc_constraints_real.py -q
```

### 6.3 Vérification métier sur les analyses

- [ ] Redémarrer le backend et le worker afin que le subprocess bridge recharge le code, le profil et l'environnement. Un bridge déjà lancé conserve son ancien état.
- [ ] Créer un **nouveau** run d'analyse depuis la phase A sur le matchup Trick Room problématique. Ne pas reprendre un run partiel antérieur.
- [ ] Conserver pour ce premier contrôle le budget standard A=300.
- [ ] Noter l'histogramme complet des leads, pas uniquement le top 2. Comparer le nombre de paires distinctes et la masse des leads contenant le poseur de Trick Room.
- [ ] Relancer le même matchup avec la même seed de run : l'histogramme doit être identique si les 300 previews sont rejouées dans le même ordre.
- [ ] Relancer avec une autre seed de run : l'histogramme peut différer. Ne pas exiger que chaque simulation individuelle diffère.
- [ ] Contrôler un deuxième matchup non Trick Room pour détecter une correction spécialisée accidentelle.
- [ ] Archiver les deux histogrammes et les champs `hello`/preflight avec le commit testé. Ne pas conclure à la qualité stratégique du modèle à partir de ce seul test ; il valide d'abord l'indépendance des tirages.

## Résultats attendus après implémentation

1. La seed différente calculée par `phase_a._attempt_seed` influence réellement les tirages Torch.
2. Les 300 previews ne redémarrent plus toutes depuis la seed fixe 42.
3. Une preview rejouée avec la même seed reste reproductible.
4. Le profil `deterministic: true` est réellement appliqué à `first_turn` et `full_battle`.
5. A et le team preview de C sont stochastiques ; B échantillonne ses ouvertures ; les overrides ne réécrivent pas le profil.
6. Le runtime M-C utilise les open team sheets comme le dataset d'entraînement.
7. Les anciennes configurations sans nouveau champ restent compatibles.

## Hors périmètre

- Calcul direct des 15 probabilités de leads à partir des logits ; ce sera une optimisation distincte après validation du sampling.
- Changement du nombre de simulations A/B/C/D.
- Réentraînement, agrandissement du modèle ou modification de l'architecture.
- Filtrage supplémentaire du dataset, pondération des gagnants ou surpondération du team preview.
- Seed complète du serveur Pokémon Showdown et reproductibilité bit à bit des combats complets.
- Migration ou suppression des analyses historiques.

## Checklist de livraison pour Composer

- [ ] Chaque comportement a d'abord été observé en échec dans un test ciblé.
- [ ] Aucun `set_global_seed(42)` ne subsiste dans le chemin de chargement/inférence du bridge.
- [ ] `rg -n "set_global_seed\(42\)" engine-runtime/src` ne retourne rien.
- [ ] Aucun fichier sous `engine-runtime/vendor/` n'a été modifié.
- [ ] `.env` n'est pas ajouté à Git et aucun secret n'apparaît dans le diff ou les logs.
- [ ] Le diff du profil M-C ne change que l'activation OTS.
- [ ] Les suites unitaires du runtime et du backend passent.
- [ ] Les tests réels sont exécutés ou explicitement signalés comme non exécutés avec la précondition manquante.
- [ ] Un nouveau run A=300 du matchup Trick Room est produit après redémarrage complet des processus.
- [ ] Le rapport final distingue clairement validation technique du sampling et validation stratégique du modèle.
