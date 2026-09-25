"""Lot 05 (D5) — les libellés français de la confiance sont les MÊMES côté serveur et côté frontend.

Même garde que `test_lot02_revue.py` pour les causes : une valeur ajoutée d'un seul côté s'afficherait brute ou fausse
(CONTINUITE §4.7 — aucune valeur d'enum brute à l'écran).
"""

from __future__ import annotations

import re
from pathlib import Path

from testpilot.verdict import status as st

RACINE = Path(__file__).resolve().parents[1]


def _libelles_du_front() -> dict:
    source = (RACINE / "frontend" / "src" / "lib" / "status.ts").read_text(encoding="utf-8")
    bloc = re.search(r"const CONFIANCE_LABEL: Record<string, string> = \{(.*?)\n\}", source, re.S).group(1)
    return dict(re.findall(r"^\s*(\w+):\s*'([^']*)',?\s*$", bloc, re.M))


def test_le_front_libelle_exactement_les_memes_confiances_que_le_serveur():
    assert _libelles_du_front() == st.LIBELLES_CONFIANCE


def test_toute_confiance_a_un_libelle_francais():
    for confiance in st.CONFIANCES:
        assert st.LIBELLES_CONFIANCE.get(confiance), confiance


def test_le_libelle_a_confirmer_est_le_meme_des_deux_cotes():
    source = (RACINE / "frontend" / "src" / "lib" / "status.ts").read_text(encoding="utf-8")
    assert f"A_CONFIRMER_LABEL = '{st.LIBELLE_A_CONFIRMER}'" in source
