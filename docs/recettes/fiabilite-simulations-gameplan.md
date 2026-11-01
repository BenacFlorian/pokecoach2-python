# Recette — Fiabilité simulations et gameplan (plan 13)

Cette recette valide la bascule **quatre imposé en B**, **traces D complètes pour E**, **sources limitées au bring-4** et **contrôles de prose**.

## Prérequis

- Plan 12 (cibles Showdown) déployé.
- Workers arrêtés avant tout nettoyage de runs historiques invalides.
- `DEEPINFRA_API_KEY` configurée pour un smoke E optionnel.

## Vérifications automatisées

```bash
cd pokecoach2-python
pytest tests/unit/test_battle_sources.py tests/unit/test_source_selection.py \
  tests/unit/test_strategy_references.py tests/unit/test_phase_e_run.py \
  tests/unit/test_phase_b.py -q
cd engine-runtime && pytest tests/test_conditioned_first_turn.py -q 2>/dev/null || true
```

Attendu :

- E refuse une trace D avec `turnCount=12` et tours 2–12 sans événements.
- E accepte un tour « switch only » avec événements explicites.
- `prepare_sources(..., our_four=...)` n’expose que quatre Pokémon côté nous.
- Phase B rejette un `first_turn` dont le quatre confirmé diffère de C.

## Run manuel recommandé

1. Lancer une analyse jusqu’à **C**, noter `ourFourSlots` / `ourLeadSlots`.
2. Phase **B** : vérifier dans les échantillons `ourFourSlots`, `previewAccepted` et l’égalité avec C.
3. Phase **D** : ouvrir une bataille persistée ; chaque tour > 1 doit avoir des `events` non vides ; `terminalEvidence.turnCount` = `len(turns)`.
4. Phase **synthesis** : échec explicite si trace creuse ; succès uniquement avec historiques complets. Payload sources : quatre slots d’origine, pas les six de l’équipe.
5. Front : recommandations T1 = décision avant résolution ; détails `resolutions` lorsque la capture le prouve (tâche 4).

## Nettoyage des runs invalides

Ne pas réparer rétroactivement les rapports terminés sur traces vides. Préparer une commande SQL/API ciblée (aperçu des `run_id` concernés), sauvegarder si besoin, exécuter **workers arrêtés**. Les analyses A–D restent consultables ; seul E reste bloqué ou en erreur jusqu’à un nouveau D fiable.

## Archivage

Conserver pour au moins un run neuf : `runId`, sélection C, extrait JSON d’un `first_turn` B, extrait d’un combat D (tours 1–3 + terminal), hash sources E, capture UI des ouvertures avec résolutions.

## Limites connues (nov. 2026)

- **Tâche 2** (capture `BattleCapture`, identités, retrait des fallbacks `Unknown`) et **tâche 4** (agrégation `resolutions` + Angular) peuvent être partiellement livrées ; suivre le plan `docs/plans/2026-11-01-13-fiabilite-simulations-traces-gameplan.md`.
- Jetons `{{ours:N}}` dans la prose LLM : garde-fou actuel = détection des noms hors bring-4 ; rendu tokenisé complet prévu dans une itération suivante.
