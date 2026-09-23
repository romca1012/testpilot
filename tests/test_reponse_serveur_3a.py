"""Étape 3a (§2bis) — lever les refus SILENCIEUX par la RÉPONSE SERVEUR.

⚠️ Le défaut fermé : 2 cas restaient `non_conforme` SILENCIEUX (rien créé, page muette) — on ne
pouvait pas distinguer « notre donnée refusée par une règle serveur » d'un « vrai défaut ». Odoo
poste vers `/website/form/…` et renvoie pourtant un JSON ; `environment.py` le capte sur
`context.reponse_formulaire`. Le comptage le consulte pour trancher :
  - `error_fields` → `DonneeRefuseeError` (notre donnée, l'app n'est pas en cause) ;
  - `error` générique → `non_conforme` EXPLIQUÉ (arbitrage porteur : refus silencieux d'une saisie
    valide = défaut de comportement) ;
  - `id` → l'enregistrement existe côté serveur ;
  - absente → silence inchangé.

Chaque branche est prouvée par sabotage — c'est ce qui en fait une garde, pas une description.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "behave_runtime" / "steps_library"))

import _base_helpers as H  # noqa: E402


class _Modele:
    def search_count(self, _):
        return 100  # inchangé après soumission → « rien créé »

    def with_context(self, **_kw):
        return self

    def search(self, domain=(), order=None, limit=None, **_kw):
        return []  # rien créé DEPUIS le relevé, quel que soit le domaine (§F1, 2026-09-23)


class _Env(dict):
    def __getitem__(self, k):
        return self.setdefault(k, _Modele())


class _Odoo:
    def __init__(self):
        self.env = _Env()


class _Page:
    """Page muette : aucune validation native invalide, aucun message d'erreur affiché."""

    def evaluate(self, *a, **k):
        return []  # aucun champ :invalid natif

    def locator(self, *a, **k):
        class _L:
            def count(self_inner):
                return 0

            def nth(self_inner, i):
                return None
        return _L()


class _Context:
    def __init__(self, reponse):
        self.page = _Page()
        self.odoo = _Odoo()
        self._initial_count_helpdesk_ticket = 100
        # Id maximal relevé (§F1, 2026-09-23) — sans lui, `_require_max_id` lève un `RuntimeError`
        # [code de test] avant même d'atteindre la réponse serveur que ces tests vérifient.
        self._initial_max_id_helpdesk_ticket = 100
        self.reponse_formulaire = reponse


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(H, "COUNT_SETTLE_TIMEOUT", 0.01, raising=False)


# ── Le helper de décision, isolé ──────────────────────────────────────────────

def test_refus_serveur_champs_nommes():
    ctx = _Context({"error_fields": ["numero_facture1", "date_avoir"]})
    assert H._refus_serveur(ctx) == ("champs", "numero_facture1, date_avoir")


def test_refus_serveur_generique():
    ctx = _Context({"error": "Enregistrement impossible"})
    assert H._refus_serveur(ctx)[0] == "generique"


def test_refus_serveur_cree():
    ctx = _Context({"id": 4242})
    assert H._refus_serveur(ctx) == ("cree", 4242)


def test_refus_serveur_absent():
    assert H._refus_serveur(_Context(None)) is None
    assert H._refus_serveur(_Context("pas un dict")) is None


# ── Bout en bout : le comptage tranche selon la réponse serveur ───────────────

def test_champs_nommes_donnent_donnee_invalide():
    """Le serveur nomme nos champs → c'est notre donnée, jamais l'app accusée."""
    ctx = _Context({"error_fields": ["code_client1"]})
    with pytest.raises(H.DonneeRefuseeError) as err:
        H.check_count_increased_by_one(ctx, "helpdesk.ticket")
    assert "LE SERVEUR A REFUSÉ" in str(err.value)
    assert "code_client1" in str(err.value)


def test_refus_generique_donne_non_conforme_EXPLIQUE():
    """Refus serveur sans champ, saisie valide côté navigateur → non_conforme (pas DonneeRefusee),
    mais EXPLIQUÉ (message serveur) — plus jamais un silence indécidable."""
    ctx = _Context({"error": "Contrainte métier violée"})
    with pytest.raises(AssertionError) as err:
        H.check_count_increased_by_one(ctx, "helpdesk.ticket")
    msg = str(err.value)
    assert not isinstance(err.value, H.DonneeRefuseeError), "un refus générique n'accuse pas NOTRE donnée"
    assert "LE SERVEUR A REFUSÉ" in msg
    assert "Contrainte métier violée" in msg


def test_sans_reponse_serveur_le_silence_reste_un_constat():
    """Aucune réponse captée → comportement d'avant : constat de comptage + « SILENCIEUX »."""
    ctx = _Context(None)
    with pytest.raises(AssertionError) as err:
        H.check_count_increased_by_one(ctx, "helpdesk.ticket")
    # §F1 (2026-09-23) : constat cloisonné au scénario (« depuis id > 100 »), plus « devrait
    # être N, obtenu M » (comptage global, abandonné par ce lot).
    assert "Aucune création détectée dans 'helpdesk.ticket' depuis id > 100" in str(err.value)
    assert "SILENCIEUX" in str(err.value)


def test_reponse_id_ne_masque_pas_un_compteur_a_zero():
    """Le serveur dit avoir créé (id) mais le compteur ne bouge pas (modèle différent / délai) :
    on ne prétend PAS que tout va bien — on retombe sur le constat de comptage."""
    ctx = _Context({"id": 999})
    with pytest.raises(AssertionError) as err:
        H.check_count_increased_by_one(ctx, "helpdesk.ticket")
    assert not isinstance(err.value, H.DonneeRefuseeError)
    assert "Aucune création détectée dans 'helpdesk.ticket' depuis id > 100" in str(err.value)
