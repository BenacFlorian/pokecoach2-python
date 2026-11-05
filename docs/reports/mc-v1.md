# Rapport M-C V1 (template)

> **Statut global :** `EN ATTENTE` — à compléter après la campagne réelle (tâche 16).

## Checklist spec / lot E

- [ ] Dataset `natural` publié (cible ~300 replays exploitables ou écart documenté)
- [ ] Fine-tuning BC depuis parent M-B (architecture héritée, lr effectif tracé)
- [ ] Job HTTP d'entraînement terminé en `completed` **après** export + reload CPU
- [ ] Package téléchargé, hash SHA-256 enregistré, reload dans un processus isolé
- [ ] Profil PokeCoach pointant vers le package (sans complétion Tiny implicite)
- [ ] Deux combats M-C réels persistés, séparés par redémarrage des processus
- [ ] Zéro ordre Showdown rejeté ; aucun repli silencieux sur erreur de contrat
- [ ] Traces consultables dans l'UI existante

## Identifiants de la campagne

| Artefact | ID / hash |
| --- | --- |
| Snapshot archive | _à remplir_ |
| Dataset | _à remplir_ |
| Job entraînement | _à remplir_ |
| Modèle publié | _à remplir_ |
| Checkpoint SHA-256 | _à remplir_ |
| Match 1 / Match 2 | _à remplir_ |

## Commandes exécutées

```bash
# Trainer (exemples — remplacer par les commandes réelles et codes de sortie)
devbox run start
devbox run cli -- train --config configs/...
curl http://127.0.0.1:8010/training/jobs/...
```

## Verdicts par critère

| Critère | Résultat (`PASSED` / `FAILED` / `BLOCKED`) | Preuve |
| --- | --- | --- |
| Export + reload CPU | _à remplir_ | _logs / JSON_ |
| Contrat bridge | _à remplir_ | _tests parité_ |
| Combat 1 | _à remplir_ | _trace ID_ |
| Combat 2 (post-restart) | _à remplir_ | _trace ID_ |

## Limites connues

- _Reprise collecte, séries BO3 inconnues, tests ignorés, etc._

## Validation humaine (pause E)

- **Résultat technique :** _PASSED / FAILED / BLOCKED_
- **Validation humaine :** _en attente_
