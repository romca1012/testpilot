"""Pourquoi rien n'a été créé — **lire la page au lieu d'accuser** (2026-07-22, composant A).

⚠️ **Le défaut.** Quand le compteur d'enregistrements n'augmentait pas, le test concluait
« l'application est non conforme », point. Or **trois causes très différentes** produisent ce même
symptôme :

1. **le navigateur a refusé d'envoyer** — une valeur viole la validation HTML native : c'est la
   donnée DU TEST qui est invalide, l'application n'y est pour rien *(c'est la 9ᵉ cause, et elle a
   faussé toute une campagne de mesure)* ;
2. **le serveur a refusé** pour une raison métier (SIRET incohérent, doublon…) : l'application fait
   exactement son travail ;
3. **l'application est réellement en défaut** — le seul cas où le verdict est mérité.

Les confondre, c'est accuser à tort deux fois sur trois.

⚠️ **Ce composant ne change AUCUN statut.** Il explique. Distinguer ces trois cas en verdicts
séparés (le « 4ᵉ verdict ») est une décision de modèle qui appartient au porteur — mais on ne
pouvait pas la lui poser sans savoir d'abord *si la page parle*. C'est ce que ceci mesure.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "behave_runtime" / "steps_library"))

from _base_helpers import diagnostic_soumission  # noqa: E402


class _Element:
    def __init__(self, texte, visible=True):
        self._texte, self._visible = texte, visible

    def is_visible(self): return self._visible
    def inner_text(self): return self._texte


class _Locator:
    def __init__(self, elements): self._elements = elements

    def count(self): return len(self._elements)
    def nth(self, i): return self._elements[i]


class _Page:
    """Page simulée : `invalides` = ce que rend la validation native, `erreurs` = par sélecteur."""

    def __init__(self, invalides=None, erreurs=None):
        self.invalides = invalides or []
        self.erreurs = erreurs or {}

    def evaluate(self, script): return self.invalides
    def locator(self, selecteur): return _Locator(self.erreurs.get(selecteur, []))


# ── Cause 1 : le navigateur a bloqué (notre donnée est invalide) ─────────────

def test_un_champ_INVALIDE_disculpe_l_application():
    """⚠️ LE cas qui a faussé la mesure : `code_client1` attend `\\d{7}`, le test écrivait
    « TEST_REMB_CLI001 ». Il faut que le rapport dise que l'application n'y est pour rien."""
    page = _Page(invalides=[{"nom": "code_client1",
                             "msg": "Veuillez respecter le format demandé."}])

    d = diagnostic_soumission(page)

    assert "LE NAVIGATEUR A REFUSÉ" in d
    assert "code_client1" in d
    assert "Veuillez respecter le format demandé." in d
    assert "L'application n'est PAS en cause" in d


def test_plusieurs_champs_invalides_sont_tous_nommes():
    page = _Page(invalides=[{"nom": "a", "msg": "m1"}, {"nom": "b", "msg": "m2"}])

    d = diagnostic_soumission(page)

    assert "2 champ(s)" in d and "a : m1" in d and "b : m2" in d


def test_la_validation_native_PRIME_sur_le_message_serveur():
    """Si un champ est `:invalid`, l'envoi n'a jamais eu lieu : un bandeau résiduel affiché par la
    page précédente induirait en erreur. Le signal le plus décisif gagne."""
    page = _Page(invalides=[{"nom": "x", "msg": "invalide"}],
                 erreurs={".alert-danger": [_Element("Erreur serveur quelconque")]})

    assert "LE NAVIGATEUR A REFUSÉ" in diagnostic_soumission(page)


# ── Cause 2 : le serveur a répondu, et il le dit ─────────────────────────────

@pytest.mark.parametrize("selecteur", [
    ".o_notification.border-danger", ".alert-danger", "[role='alert']",
    ".invalid-feedback", ".o_has_error .text-danger",
])
def test_un_refus_AFFICHE_est_rapporte_quel_que_soit_son_habillage(selecteur):
    """Odoo, Bootstrap et l'accessibilité n'annoncent pas une erreur de la même façon. En manquer
    une, c'est retomber dans « refus silencieux » alors que la page parlait."""
    page = _Page(erreurs={selecteur: [_Element("Le numéro SIREN est incohérent.")]})

    d = diagnostic_soumission(page)

    assert "L'APPLICATION A REFUSÉ" in d
    assert "Le numéro SIREN est incohérent." in d


def test_le_refus_serveur_appelle_a_la_PRUDENCE_pas_a_la_condamnation():
    """Un refus métier légitime ressemble à un défaut. Le rapport doit le dire au lecteur."""
    page = _Page(erreurs={".alert-danger": [_Element("Ce fournisseur existe déjà.")]})

    assert "légitime avant de conclure" in diagnostic_soumission(page)


def test_un_message_INVISIBLE_est_ignore():
    """Un bandeau présent dans le DOM mais masqué n'a pas été montré à l'utilisateur : le citer
    inventerait une explication (« affiché ≠ réel », §4.6)."""
    page = _Page(erreurs={".alert-danger": [_Element("Résidu masqué", visible=False)]})

    assert "SILENCIEUX" in diagnostic_soumission(page)


def test_un_message_vide_ne_compte_pas():
    page = _Page(erreurs={".alert-danger": [_Element("   \n  ")]})

    assert "SILENCIEUX" in diagnostic_soumission(page)


# ── Cause 3 : la page ne dit rien — et on le dit aussi ───────────────────────

def test_un_refus_SILENCIEUX_est_nomme_comme_tel():
    """⚠️ Le résultat le plus utile pour la suite. Si les formulaires ne disent rien, aucun
    raffinement du verdict n'y changera quoi que ce soit — il faudra une autre approche. Mieux
    vaut le savoir maintenant que l'apprendre après avoir construit dessus."""
    d = diagnostic_soumission(_Page())

    assert "SILENCIEUX" in d
    assert "distinguer un rejet métier d'un défaut applicatif" in d


# ── L'invariant non négociable : ne JAMAIS casser le scénario ────────────────

class _PageQuiPlante:
    def evaluate(self, script): raise RuntimeError("navigateur mort")
    def locator(self, s): raise RuntimeError("navigateur mort")


def test_un_diagnostic_qui_plante_ne_casse_PAS_le_scenario():
    """⚠️ L'invariant décisif. Un diagnostic qui lève transformerait un échec fonctionnel lisible
    en erreur technique — il détruirait exactement l'information qu'il est censé apporter."""
    d = diagnostic_soumission(_PageQuiPlante())

    assert "indisponible" in d
    assert "RuntimeError" in d


def test_le_diagnostic_reste_BORNE():
    """`error_summary` est coupé à 500 caractères : un diagnostic bavard serait amputé par la
    queue, donc amputé de sa CONCLUSION — la partie qui porte le sens."""
    page = _Page(invalides=[{"nom": f"champ_{i}", "msg": "x" * 200} for i in range(5)])

    d = diagnostic_soumission(page)

    assert len(d) <= 380
    assert d.endswith("…")


# ── Bout en bout : le message d'assertion PORTE le diagnostic ────────────────

class _Env(dict):
    def __getitem__(self, k): return self.setdefault(k, _Modele())


class _Modele:
    def search_count(self, _): return 26222


class _Odoo:
    def __init__(self): self.env = _Env()


class _Context:
    def __init__(self, page):
        self.page = page
        self.odoo = _Odoo()
        # Le snapshot pris par « …est enregistré pour comparaison » (cf. `_count_attr`).
        self._initial_count_helpdesk_ticket = 26222


def test_donnee_refusee_nativement_leve_le_4e_verdict_au_comptage(monkeypatch):
    """§2bis 4ᵉ verdict. Quand rien n'est créé PARCE QUE le navigateur a refusé notre donnée, le
    comptage lève `DonneeRefuseeError` (→ `donnee_invalide`), pas une `AssertionError` (→
    `non_conforme`). C'est ICI que passaient 4 des 6 faux `non_conforme` de la re-mesure."""
    import _base_helpers as H

    monkeypatch.setattr(H, "COUNT_SETTLE_TIMEOUT", 0.01, raising=False)
    ctx = _Context(_Page(invalides=[{"nom": "code_client1", "msg": "format attendu"}]))

    with pytest.raises(H.DonneeRefuseeError) as err:
        H.check_count_increased_by_one(ctx, "helpdesk.ticket")

    message = str(err.value)
    assert "LE NAVIGATEUR A REFUSÉ" in message
    assert "code_client1" in message, "le champ fautif est nommé"


def test_un_refus_SILENCIEUX_reste_un_constat_de_comptage(monkeypatch):
    """Sans champ invalide natif (refus serveur silencieux), on ne peut pas disculper la donnée :
    ça reste une `AssertionError` (constat + « SILENCIEUX »). L'indécidable est levé par la
    vérification par l'état (3a), pas ici."""
    import _base_helpers as H

    monkeypatch.setattr(H, "COUNT_SETTLE_TIMEOUT", 0.01, raising=False)
    ctx = _Context(_Page(invalides=[]))  # aucun champ :invalid → refus silencieux

    with pytest.raises(AssertionError) as err:
        H.check_count_increased_by_one(ctx, "helpdesk.ticket")

    message = str(err.value)
    assert "devrait être 26223, obtenu 26222" in message, "le constat de comptage est préservé"
    assert "SILENCIEUX" in message
