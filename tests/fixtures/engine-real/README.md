# Traces moteur réel (expurgées)

Placer ici des exports JSON de combats **sans pseudos utilisateur** pour tests de normalisation (`engine-runtime/tests` et `tests/integration/test_vgc_*_real.py` lorsque activés).

Les tests CI utilisent le bridge `POKECOACH_BRIDGE_FIXTURE=1` avec des snapshots contenant de vrais noms de capacités dans `moves`.
