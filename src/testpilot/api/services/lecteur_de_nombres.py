"""Le lecteur de nombres du HARNAIS, chargé par son chemin — pour valider ce qu'un projet déclare avec les règles exactes
de celui qui lira l'écran (lot PT-03).

`behave_runtime/steps_library/_lecture_nombre.py` est un module pur, sans autre dépendance que la bibliothèque standard,
copié tel quel dans le dossier de chaque exécution. Le harnais ne dépend pas de ce paquet ; l'inverse est permis (la
génération lit déjà la bibliothèque de steps). Charger le vrai module évite de recopier ici la table des unités : une
copie divergerait, et une unité acceptée par l'écran de réglage serait refusée par le test.
"""
from __future__ import annotations

import functools
import importlib.util

from testpilot import config


@functools.lru_cache(maxsize=1)
def lecteur():
    chemin = config.BEHAVE_RUNTIME_DIR / "steps_library" / "_lecture_nombre.py"
    spec = importlib.util.spec_from_file_location("_tp_lecture_nombre", chemin)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module          # exigé par `dataclasses` pendant l'exécution du module
    spec.loader.exec_module(module)
    return module
