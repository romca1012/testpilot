"""La race de comptage post-soumission — refermée par une attente ACTIVE bornée.

LE DÉFAUT MESURÉ (run réel du cas 10, 2026-07-19, exec 32). Le ticket est créé par le NAVIGATEUR
(soumission web, création asynchrone) ; le comptage lit par RPC (`search_count`), une seule fois,
instantanément. Entre les deux, un délai → la lecture unique gagne la course et voit l'ancien
compte. Symptôme : +2 tickets réellement créés (26216 → 26218), mais chaque assertion comptait
avant que sa création soit visible → `success / non_conforme` 0/3, alors que l'application créait
correctement les tickets.

⚠️ Le sleep fixe d'avant « gagnait » la course à l'aveugle ; je l'avais retiré (lot robustesse),
d'où la régression. Le remède n'est pas un autre sleep : c'est un POLL borné, qui sort dès que la
condition est vraie et jamais au-delà de la fenêtre.

Tests à froid : faux `context.odoo.env[model]` dont `search_count` rend une SÉQUENCE (apparition
retardée). Horloge et sleep injectés → déterministe, sans vraie temporisation.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

import _base_helpers as H  # noqa: E402


class _FakeModel:
    """`search_count` rend les valeurs de `counts`, une par appel (la dernière ensuite)."""

    def __init__(self, counts):
        self.counts = list(counts)
        self.appels = 0

    def search_count(self, _domain):
        v = self.counts[min(self.appels, len(self.counts) - 1)]
        self.appels += 1
        return v

    def search(self, _domain, **_kw):
        """Le vrai modèle odoorpc en a un — `check_count_increased_by_one` s'en sert pour capturer
        l'enregistrement créé (2026-08-07). Sans lui ici, le faux serait moins capable que le vrai
        et le test passerait à côté de ce que la production fait vraiment."""
        return [4242]


class _FakeEnv:
    def __init__(self, model):
        self._model = model

    def __getitem__(self, _name):
        return self._model


class _Ctx:
    def __init__(self, counts, initial):
        self.odoo = type("O", (), {"env": _FakeEnv(_FakeModel(counts))})()
        setattr(self, H._count_attr("helpdesk.ticket"), initial)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Aucune attente réelle : on neutralise le sleep et on borne la fenêtre à peu de tours."""
    monkeypatch.setattr(H.time, "sleep", lambda *_: None)
    monkeypatch.setattr(H, "COUNT_SETTLE_TIMEOUT", 0.05)


# ── Le primitif d'attente, borné et déterministe ─────────────────────────────

def test_poll_sort_des_que_la_condition_est_vraie():
    lectures = iter([1, 1, 5])
    horloge = iter([0.0, 0.1, 0.2, 0.3])
    ok, val = H._poll_until(lambda: next(lectures), lambda v: v == 5,
                            timeout=10, _clock=lambda: next(horloge), _sleep=lambda *_: None)
    assert ok and val == 5


def test_poll_respecte_la_borne_et_ne_boucle_pas_a_l_infini():
    """Condition jamais vraie → sort au timeout (pas d'attente infinie), rend la dernière valeur."""
    horloge = iter([0.0, 3.0, 9.0])  # 9 ≥ timeout 8
    ok, val = H._poll_until(lambda: 1, lambda v: v == 2, timeout=8,
                            _clock=lambda: next(horloge), _sleep=lambda *_: None)
    assert ok is False and val == 1


# ── Le positif : la race est refermée, mais un vrai « non créé » échoue toujours ──

def test_positif_reussit_quand_le_ticket_apparait_en_RETARD():
    """La régression exacte : lecture unique aurait vu N et échoué ; le poll attend le ticket."""
    ctx = _Ctx(counts=[10, 10, 11], initial=10)  # ticket visible au 3ᵉ poll
    H.check_count_increased_by_one(ctx, "helpdesk.ticket")  # ne lève pas


def test_positif_echoue_si_le_ticket_n_est_JAMAIS_cree():
    """La correction ne masque pas un vrai défaut : rien créé → échec, message d'origine."""
    ctx = _Ctx(counts=[10], initial=10)  # reste à 10
    with pytest.raises(AssertionError, match="devrait être 11, obtenu 10"):
        H.check_count_increased_by_one(ctx, "helpdesk.ticket")


# ── Le négatif : même fenêtre 8 s — garde anti-faux-négatif ───────────────────

def test_negatif_passe_quand_rien_n_est_cree():
    ctx = _Ctx(counts=[10], initial=10)
    H.check_count_not_increased(ctx, "helpdesk.ticket")  # ne lève pas


def test_negatif_detecte_une_creation_TARDIVE_a_tort():
    """⚠️ Le point de la correction de plan : le négatif attend la MÊME fenêtre que le positif.
    Une création qui surgit en retard (à tort) doit être vue, pas ratée par une fenêtre trop
    courte. Ici le ticket apparaît au 3ᵉ poll — dans la fenêtre — et DOIT faire échouer."""
    ctx = _Ctx(counts=[10, 10, 11], initial=10)
    with pytest.raises(AssertionError, match="a augmenté"):
        H.check_count_not_increased(ctx, "helpdesk.ticket")


def test_les_deux_assertions_partagent_la_meme_fenetre():
    """Verrouille l'invariant : positif et négatif s'appuient sur la MÊME constante."""
    import inspect
    src_pos = inspect.getsource(H.check_count_increased_by_one)
    src_neg = inspect.getsource(H.check_count_not_increased)
    # Aucune des deux ne passe un `timeout=` explicite : elles héritent du défaut partagé.
    assert "timeout=" not in src_pos and "timeout=" not in src_neg
