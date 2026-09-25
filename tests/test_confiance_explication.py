"""Lot 05 (D5) — « Réussi — à confirmer » dit POURQUOI : quel élément a été retrouvé par repli, ou le second essai.

La note est déterministe (jamais confiée au LLM) et survit à l'indisponibilité du modèle : sans elle, un vert à confirmer
n'aurait qu'une étiquette et aucune raison.
"""

from __future__ import annotations

from testpilot.verdict import explication
from testpilot.verdict import status as st


def _verdict(confiance, *, idents=(), execution=st.EXEC_SUCCESS, fonctionnel=st.FUNC_CONFORME):
    scenario = st.ScenarioVerdict("S1", execution, fonctionnel, confiance=confiance,
                                  resolutions_adaptatives=list(idents))
    return st.CaseVerdict(execution, fonctionnel, scenarios=[scenario], confiance=confiance)


def test_la_note_nomme_l_element_retrouve_par_repli():
    note = explication.note_confiance(_verdict(st.CONFIANCE_AUTO_RESOLUE, idents=["sujet_renomme"]))

    assert "à confirmer" in note and "sujet_renomme" in note


def test_la_note_du_retry_parle_du_second_essai():
    assert "second essai" in explication.note_confiance(_verdict(st.CONFIANCE_APRES_RETRY))


def test_un_vert_nominal_n_a_aucune_note():
    assert explication.note_confiance(_verdict(st.CONFIANCE_NOMINALE)) == ""


def test_falsifiable_un_echec_n_est_jamais_qualifie_a_confirmer():
    """Un `non_conforme` obtenu après repli reste un échec : pas de « Réussi — à confirmer » sur un non-vert."""
    echec = _verdict(st.CONFIANCE_AUTO_RESOLUE, idents=["x"], fonctionnel=st.FUNC_NON_CONFORME)
    technique = _verdict(st.CONFIANCE_APRES_RETRY, execution=st.EXEC_TECHNICAL_ERROR, fonctionnel=st.FUNC_INDETERMINE)

    assert explication.note_confiance(echec) == "" and explication.note_confiance(technique) == ""


def test_la_note_survit_a_l_indisponibilite_du_modele(monkeypatch):
    def en_panne(*args, **kwargs):
        raise RuntimeError("LLM indisponible")

    monkeypatch.setattr(explication, "_data_explication", en_panne)

    texte, cout = explication.propose_explication(
        _verdict(st.CONFIANCE_AUTO_RESOLUE, idents=["sujet_renomme"]), llm=object())

    assert cout == 0.0 and "sujet_renomme" in texte and "à confirmer" in texte


def test_sans_note_l_indisponibilite_du_modele_laisse_le_commentaire_vide(monkeypatch):
    """Comportement d'avant inchangé pour un vert nominal."""
    def en_panne(*args, **kwargs):
        raise RuntimeError("LLM indisponible")

    monkeypatch.setattr(explication, "_data_explication", en_panne)

    assert explication.propose_explication(_verdict(st.CONFIANCE_NOMINALE), llm=object()) == ("", 0.0)
