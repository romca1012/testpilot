"""Décision 0019 — une valeur de `<select>` inventée échoue TOUT DE SUITE et DIT pourquoi.

LE DÉFAUT MESURÉ (rejeu du cas 1, exec 27). Le `.feature` généré demandait
`types_demandes = "new"` ; les options réelles sont `nouvel_entrant` et `remplacement_materiel`.
`select_option(value="new")` a donc attendu **30 secondes**, puis levé :

    Locator.select_option: Timeout 30000ms exceeded.
    Call log: - waiting for locator("select[name='types_demandes']")

**Le message ne nomme que le locator du SELECT** — il donne à croire que le select est
introuvable. Il est là : sondé `count=1, visible=True, enabled=True`, et le step le vérifiait
lui-même (`if locator.count() > 0:`) **avant** l'appel. Playwright attendait l'**option**.

TOUTE LA CHAÎNE A CRU CE MESSAGE : `defect_taxonomy` a classé `ui_timeout → wrong_field_name →
« Champ/sélecteur introuvable »`, et l'agent de réparation a cherché un problème de **sélecteur**
— donc réparé à côté, et rebrûlé du budget à chaque tentative. C'est `0002` qui se rejoue : *le
message d'erreur ne porte pas la vraie cause, et tout ce qui le lit se trompe dans la même
direction.*

Ces tests ne touchent ni Playwright ni Odoo : ils injectent un faux locator. Ce qu'on garde, c'est
le **contrat** du helper, pas le navigateur.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

import _base_helpers as H  # noqa: E402

from testpilot.verdict import defect_origin as DO  # noqa: E402
from testpilot.verdict import defect_taxonomy as DT  # noqa: E402

# Les options RÉELLES du formulaire, sondées le 2026-07-17
# (`scripts/probe_select_options.py`). Ce ne sont pas des valeurs inventées pour le test.
OPTIONS_REELLES = [("nouvel_entrant", "Demande de nouvel entrant"),
                   ("remplacement_materiel", "Remplacement de matériel existant")]


class FauxSelect:
    """Un `<select>` qui note ce qu'on lui demande. Aucun navigateur."""

    def __init__(self, options=OPTIONS_REELLES):
        self.options = options
        self.selected = None

    def evaluate(self, _js):
        # Le helper lit les options par `el.options.map(...)` — on rend la même forme.
        return [list(o) for o in self.options]

    def select_option(self, value):
        self.selected = value


@pytest.fixture(autouse=True)
def _sidecar_isole(tmp_path, monkeypatch):
    """Le repli est TRACÉ (0007 B+) : on isole le sidecar pour ne pas polluer un vrai run."""
    monkeypatch.setenv(H.FIELD_FALLBACK_FILE_ENV, str(tmp_path / "fallbacks.txt"))


# ── Le contrat du helper ──────────────────────────────────────────────────────

def test_une_valeur_existante_est_selectionnee_sans_ceremonie():
    """Anti-faux-positif : le chemin normal ne doit rien coûter ni rien tracer."""
    sel = FauxSelect()
    H.select_option_strict(sel, "nouvel_entrant", field="types_demandes")
    assert sel.selected == "nouvel_entrant"


def test_une_valeur_INVENTEE_echoue_tout_de_suite_et_dit_les_options():
    """🔴 LE test de `0019` : la vraie cause, et de quoi corriger — pas un timeout de 30 s."""
    sel = FauxSelect()

    with pytest.raises(H.InvalidOptionValueError) as err:
        H.select_option_strict(sel, "new", field="types_demandes")

    message = str(err.value)
    assert "'new'" in message, "l'erreur doit nommer la valeur fautive"
    assert "n'existe pas" in message, "l'erreur doit dire la VRAIE cause"
    # De quoi corriger DU PREMIER COUP — c'est tout l'intérêt.
    assert "nouvel_entrant" in message and "remplacement_materiel" in message, (
        "l'erreur doit lister les options réelles : sinon l'agent devine une deuxième fois")
    assert sel.selected is None, "rien ne doit être sélectionné quand la valeur est fausse"


def test_le_LIBELLE_est_accepte_en_repli_et_le_repli_est_TRACE():
    """Tolérance de `0007` — mais un repli n'est JAMAIS silencieux (leçon de `0011`)."""
    sel = FauxSelect()

    H.select_option_strict(sel, "Demande de nouvel entrant", field="types_demandes")

    assert sel.selected == "nouvel_entrant", "le libellé doit être résolu vers sa valeur"
    trace = Path(__import__("os").environ[H.FIELD_FALLBACK_FILE_ENV]).read_text(encoding="utf-8")
    assert "types_demandes" in trace and "LIBELLÉ" in trace, (
        "le repli doit remonter jusqu'au rapport (0007 B+), jamais rester muet")


def test_un_select_vide_le_dit_au_lieu_de_planter_obscurement():
    sel = FauxSelect(options=[])
    with pytest.raises(H.InvalidOptionValueError, match="aucune option"):
        H.select_option_strict(sel, "quoi que ce soit", field="vide")


# ── Point 3 de l'arbitrage : la taxonomie classe-t-elle CORRECTEMENT ? ────────

class _Failure:
    """Miroir d'un échec réel : la taxonomie classe sur le TYPE d'exception (`0015`)."""

    def __init__(self, raw):
        self.raw = raw
        self.scenario_name = "[NOMINAL] Demande avec PC Portable HP"
        self.step_text = 'Et le champ demande "types_demandes" est rempli avec "new"'
        self.failure_type = "unknown"
        self.traceback_summary = ""


def test_l_InvalidOptionValue_de_0019_est_classe_broken_test_code():
    """🔴 LA vérification demandée — et elle a trouvé un trou, elle ne l'a pas confirmé.

    Consigne : *« Vérifiez par un test si l'exception levée par A est déjà correctement classée en
    broken_test_code par la taxonomie actuelle. Si oui, n'ajoutez rien. Si le test montre une
    mauvaise classification (répétant le trou de 0015 sur un TypeError nu), alors seulement
    ajoutez la distinction nécessaire. »*

    **Mesuré : rien ne classait cette erreur** → `unknown` → `indetermine` → **confirmation
    humaine exigée**. Or c'est le cas le plus évidemment réparable qui soit : *notre* code passe
    une valeur que l'application n'offre pas. L'application va très bien. C'est le trou que `0015`
    avait retiré pour `TypeError`, jamais rejoué ici.

    ⚠️ **Et la correction évidente était fausse.** Mon premier jet mappait `ValueError` →
    `broken_test_code` : `tests/test_taxonomy_signal.py` l'a refusé, et il avait raison — `0015` a
    **délibérément** laissé `ValueError` hors du signal parce qu'**odoorpc le lève légitimement**
    (« aucun enregistrement » = contexte serveur manquant → jugement humain). Le type seul ne
    distingue pas les deux ; mapper `ValueError` aurait fait réparer un test contre un vrai
    problème de données — le faux négatif que §4.4 déclare inacceptable.
    D'où une **classe dédiée** : un signal non ambigu **par construction**, que personne d'autre
    ne lève.
    """
    raw = ("_base_helpers.InvalidOptionValueError: select 'types_demandes' : la valeur 'new' n'existe pas. "
           "Options réelles : 'nouvel_entrant' (Demande de nouvel entrant), "
           "'remplacement_materiel' (Remplacement de matériel existant).")

    assert DT.classify_failure(_Failure(raw)) == DT.BROKEN_TEST_CODE, (
        "une InvalidOptionValueError est levée par NOTRE helper et par personne d'autre : c'est un "
        "défaut de NOTRE code, réparable sans confirmation humaine")
    assert DO._ORIGIN_BY_CAUSE[DT.BROKEN_TEST_CODE] == DO.TEST_A_REPARER


def test_le_classement_ne_depend_PAS_du_libelle_du_step():
    """Principe 1 / `0015` : le `step_text` est écrit par l'agent — il ne classe rien.

    Le libellé contient « champ », mot qui pousserait vers `wrong_field_name` par mots-clés. Le
    signal (`ValueError`) doit primer, quel que soit le nom du step.
    """
    f = _Failure("_base_helpers.InvalidOptionValueError: select 'x' : la valeur 'y' n'existe pas.")
    f.step_text = 'Et le champ "types_demandes" est rempli'
    assert DT.classify_failure(f) == DT.BROKEN_TEST_CODE

    f.step_text = "Et n'importe quoi d'autre écrit par l'agent"
    assert DT.classify_failure(f) == DT.BROKEN_TEST_CODE


def test_un_vrai_bug_applicatif_ne_devient_pas_reparable_au_passage():
    """Garde-fou §4.4 : élargir le barème ne doit pas ouvrir la porte au faux négatif.

    Une assertion en échec (rendue `ASSERT FAILED:` par Behave — un signal, pas du texte d'agent)
    reste un jugement HUMAIN, même si le message contient le mot « valeur ».
    """
    f = _Failure("ASSERT FAILED: la valeur affichée ne correspond pas au montant attendu")
    assert DT.classify_failure(f) != DT.BROKEN_TEST_CODE
