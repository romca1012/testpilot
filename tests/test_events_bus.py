"""Diffusion en mémoire des changements d'un projet (SSE, audit 2026-09-07).

Ce module ne teste QUE le registre pub/sub lui-même (`events_bus.py`) — pas le flux HTTP, qui
est couvert par `test_events_sse.py`. Isoler les deux évite qu'un test lent (streaming réel)
masque une régression simple sur la logique de routage par projet.
"""

from __future__ import annotations

import queue

import pytest

from testpilot.api.services import events_bus


def test_un_evenement_publie_arrive_a_l_abonne_du_bon_projet():
    q = events_bus.abonner(1)
    try:
        events_bus.publier(1, {"kind": "case_created", "case_id": 42})
        assert q.get(timeout=1) == {"kind": "case_created", "case_id": 42}
    finally:
        events_bus.desabonner(1, q)


def test_un_evenement_ne_traverse_jamais_vers_un_AUTRE_projet():
    """L'isolation par projet doit s'appliquer ICI AUSSI — cohérent avec le reste de l'app
    (audit 2026-09-07, fermeture des projets par défaut)."""
    q_projet_1 = events_bus.abonner(1)
    q_projet_2 = events_bus.abonner(2)
    try:
        events_bus.publier(1, {"kind": "case_created", "case_id": 42})
        assert q_projet_1.get(timeout=1)["case_id"] == 42
        with pytest.raises(queue.Empty):
            q_projet_2.get_nowait()
    finally:
        events_bus.desabonner(1, q_projet_1)
        events_bus.desabonner(2, q_projet_2)


def test_publier_sans_aucun_abonne_ne_leve_jamais():
    """Un enregistrement réel ne doit jamais échouer parce que personne n'écoute — la
    notification est un confort, pas la source de vérité."""
    events_bus.publier(999999, {"kind": "case_created", "case_id": 1})  # pas d'exception


def test_desabonner_deux_fois_ne_leve_jamais():
    q = events_bus.abonner(1)
    events_bus.desabonner(1, q)
    events_bus.desabonner(1, q)   # idempotent


def test_un_abonne_qui_ne_consomme_plus_perd_le_plus_ancien_pas_le_plus_recent():
    """File pleine (onglet en arrière-plan, throttle navigateur) : `publier` ne doit jamais
    bloquer l'appelant — c'est une vraie requête utilisateur derrière — ni faire grossir la
    file indéfiniment. Le plus récent doit rester consultable."""
    q = events_bus.abonner(1)
    try:
        for i in range(events_bus._TAILLE_FILE_MAX + 10):
            events_bus.publier(1, {"kind": "case_updated", "case_id": i})
        assert q.qsize() <= events_bus._TAILLE_FILE_MAX
        derniers = []
        while True:
            try:
                derniers.append(q.get_nowait())
            except queue.Empty:
                break
        assert derniers[-1]["case_id"] == events_bus._TAILLE_FILE_MAX + 9
    finally:
        events_bus.desabonner(1, q)


def test_nombre_abonnes_reflete_les_abonnements_actifs():
    assert events_bus.nombre_abonnes(1) == 0
    q1 = events_bus.abonner(1)
    q2 = events_bus.abonner(1)
    assert events_bus.nombre_abonnes(1) == 2
    events_bus.desabonner(1, q1)
    assert events_bus.nombre_abonnes(1) == 1
    events_bus.desabonner(1, q2)
    assert events_bus.nombre_abonnes(1) == 0
