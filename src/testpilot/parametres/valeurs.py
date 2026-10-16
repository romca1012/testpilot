"""Ce qui reste des « valeurs attendues » déclarées par le projet (lot PT-03) après la décision A44 (porteur, 2026-10-16).

L'onglet « Valeurs attendues » (écriture des nombres du projet, unités ajoutées) est retiré : l'outil relève lui-même la
façon dont l'application écrit ses nombres, et la comparaison se comporte partout comme « Non déclarée » — deux écritures
reconnues, un nombre ambigu jamais tranché, l'unité toujours vérifiée (A24). Ce qui avait été enregistré reste en base,
inutilisé.

Reste ici le seul garde-fou encore utile : le sous-processus Behave hérite de l'environnement du serveur et relit `.env` ;
une variable du harnais laissée là y déciderait de l'écriture des nombres d'un projet sans que personne ne l'ait voulu
(revue du 2026-10-13). Le lanceur (`BehaveRunner._subprocess_env`) les pose donc toujours VIDES. Module pur : aucune I/O.
"""
from __future__ import annotations

# DUPLIQUÉES dans `behave_runtime/steps_library/_base_helpers.py` (le harnais ne dépend pas de ce paquet) — test d'accord :
# `tests/test_valeurs_du_projet.py`.
ENV_FORMAT_NOMBRE = "TESTPILOT_PROJET_FORMAT_NOMBRE"
ENV_UNITES = "TESTPILOT_PROJET_UNITES"
JAMAIS_HERITEES = (ENV_FORMAT_NOMBRE, ENV_UNITES)
