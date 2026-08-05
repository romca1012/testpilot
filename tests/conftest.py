"""Garde-fou anti-pollution : aucun test ne doit toucher le VRAI `data/` du poste.

⚠️ **Pourquoi ce fichier existe.** Un test réel (`test_transport_refus.py`, avant correctif)
lançait un vrai `BehaveRunner(project_id=7)` sans isoler `regles_apprises.REGLES_DIR` — chaque
exécution de la suite écrivait une vraie ligne dans le vrai `data/regles-apprises/projet-7.jsonl`
du poste de développement, sur un projet qui n'existe même pas en base. Trouvé en observant le
fichier grossir pendant une suite de tests, pas par relecture.

Le correctif ponctuel (isoler CE test) ne protège pas contre le PROCHAIN oubli du même genre —
aucun `conftest.py` n'existait pour l'empêcher structurellement. Celui-ci ne connaît aucun
mécanisme précis (règles apprises, artefacts d'exécution, base…) : il fingerprint le vrai
`data/` avant/après CHAQUE test et fait échouer le test qui l'a changé, quel que soit le chemin
par lequel il l'a fait. Zéro faux positif attendu : les 30 fichiers de tests qui touchent déjà
`DATA_DIR`/`DB_PATH`/`DOMAIN_DIR`/`REGLES_DIR` isolent tous correctement (vérifié).

Échappatoire explicite pour un futur test qui aurait une vraie raison de toucher le disque réel :
`@pytest.mark.donnees_reelles` (déclaré dans `pyproject.toml`). Aucun test actuel n'en a besoin.

⚠️ **Limite assumée, découverte en construisant ce garde-fou** : il fingerprint le `data/` réel,
pas « ce que les tests ont fait ». Si l'application tourne en parallèle (un utilisateur réel sur
`localhost:8000` pendant que la suite passe) et écrit dans ce même `data/`, le test qui se trouve
être en cours à ce moment-là sera accusé à tort. Ne pas faire tourner la suite en même temps qu'on
utilise l'application sur ce poste.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from testpilot import config

# Résolu UNE FOIS, avant qu'un test ne monkeypatch `config.DATA_DIR` — c'est le vrai chemin sur
# le disque du poste qu'on protège, pas le symbole (qui peut être redirigé légitimement vers
# `tmp_path` par le test lui-même).
_VRAI_DATA_DIR = Path(config.DATA_DIR).resolve()


def _empreinte() -> dict[str, int]:
    """Taille de chaque fichier sous le vrai `data/` — la TAILLE seule, pas la date.

    ⚠️ **La date de modification a été essayée et abandonnée.** Mesuré sur ce poste (Windows) :
    des faux positifs apparaissent et disparaissent d'un lancement à l'autre de la MÊME suite,
    sans aucun changement de code — l'indexeur/antivirus du système touche des `mtime` sous
    `data/` sans toucher leur contenu. La taille est un signal plus grossier mais STABLE : chaque
    fuite réellement trouvée jusqu'ici (une ligne JSONL ajoutée, un fichier créé) change une
    taille ou une existence. Limite assumée, pas cachée : une écriture qui remplacerait un
    contenu par un autre de MÊME taille resterait invisible — borne acceptée plutôt qu'un
    mécanisme plus cher (hash de contenu) sur 23 Mo de données à chaque test.

    Ne lève jamais : un fichier qui disparaît entre le `stat` et la lecture (verrou Windows,
    course avec un autre processus) doit faire échouer le TEST fautif, pas le garde-fou lui-même.
    """
    empreinte: dict[str, int] = {}
    if not _VRAI_DATA_DIR.exists():
        return empreinte
    for chemin in _VRAI_DATA_DIR.rglob("*"):
        if not chemin.is_file():
            continue
        try:
            empreinte[str(chemin)] = chemin.stat().st_size
        except OSError:
            continue
    return empreinte


@pytest.fixture(autouse=True)
def _garde_donnees_reelles(request):
    """Échoue si un test a écrit dans le vrai `data/` du poste — voir le docstring du module."""
    if request.node.get_closest_marker("donnees_reelles"):
        yield
        return

    avant = _empreinte()
    yield
    apres = _empreinte()

    if avant == apres:
        return

    crees = sorted(set(apres) - set(avant))
    supprimes = sorted(set(avant) - set(apres))
    modifies = sorted(p for p in avant.keys() & apres.keys() if avant[p] != apres[p])
    detail = "; ".join(
        f"{libelle}: {chemins}"
        for libelle, chemins in (("créés", crees), ("modifiés", modifies), ("supprimés", supprimes))
        if chemins
    )
    pytest.fail(
        f"[garde données réelles] {request.node.nodeid!r} a modifié le VRAI {_VRAI_DATA_DIR} "
        f"({detail}). Isoler avec monkeypatch (config.DATA_DIR/DB_PATH ou le module dérivé — "
        f"REGLES_DIR, DOMAIN_DIR…) ou marquer @pytest.mark.donnees_reelles si c'est délibéré.",
        pytrace=False,
    )
