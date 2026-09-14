"""Un scénario NÉGATIF ne doit plus jamais être accusé de « donnée fautive » sur le champ qu'IL
teste lui-même — bug réel mesuré le 2026-08-07 sur `/retenue_garantie` (cas 124 et 125, run 20).

Avant ce correctif, `verifier_soumission_non_bloquee` traitait TOUT champ invalide après un clic
comme une preuve que le jeu de données du test était fautif — y compris le champ que le scénario
laisse vide EXPRÈS (`je laisse le champ … vide`) pour vérifier que le formulaire le refuse. Aucun
scénario de ce type (une vingtaine dans `behave_runtime/generated/`) ne pouvait donc jamais
conclure « conforme » : le contrôle levait `DonneeRefuseeError` avant même que l'assertion
`Alors une erreur de validation est affichée` ait sa chance de se prononcer.

Deuxième défaut, sur le MÊME run : `copy_invoice_part` (un champ « ajouter des fichiers ») portait
un fichier valide juste avant le clic sur Envoyer — c'est le clic LUI-MÊME (JS du portail) qui l'a
vidé, mesuré en direct (`filesCount` passe de 1 à 0 entre l'attache et la lecture post-clic). Ce
n'est pas notre donnée qui est en cause : on l'avait bien remplie.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "behave_runtime" / "steps_library"))

import _base_helpers as H  # noqa: E402
from _base_helpers import DonneeRefuseeError, verifier_soumission_non_bloquee  # noqa: E402


class _Page:
    """`evaluate` rend la liste des champs invalides, comme le vrai script JS — même patron que
    `test_soumission_bloquee.py`. Les attributs de marquage sont posés directement, comme le
    ferait `attach_file`/`leave_field_empty` sur une vraie page Playwright."""

    def __init__(self, invalides): self.invalides = invalides

    def evaluate(self, script, *a): return self.invalides


def _champ(nom, msg, valeur="", manquant=False):
    return {"nom": nom, "valeur": valeur, "msg": msg, "manquant": manquant}


# ── Le champ que LE SCÉNARIO teste lui-même n'accuse plus le jeu de données ────

def test_le_champ_laisse_vide_par_le_scenario_lui_meme_ne_leve_RIEN():
    page = _Page([_champ("rib_original", "Please select a file.", manquant=True)])
    page._tp_champs_vides_intentionnels = {"rib_original"}

    verifier_soumission_non_bloquee(page)  # ne lève PAS


def test_un_AUTRE_champ_invalide_non_couvert_est_toujours_signale():
    """La protection ne doit couvrir QUE ce qu'on a explicitement marqué — un vrai souci de
    donnée ailleurs doit continuer à être signalé, sinon le contrôle perd tout son sens."""
    page = _Page([
        _champ("rib_original", "Please select a file.", manquant=True),
        _champ("code_client1", "format invalide", "abc"),
    ])
    page._tp_champs_vides_intentionnels = {"rib_original"}

    with pytest.raises(DonneeRefuseeError) as err:
        verifier_soumission_non_bloquee(page)

    message = str(err.value)
    assert "code_client1" in message
    assert "rib_original" not in message, "le champ testé ne doit plus apparaître dans le refus"


# ── Un champ fichier déjà rempli, vidé par le CLIC lui-même ────────────────────

def test_un_champ_fichier_deja_rempli_avant_le_clic_n_est_pas_accuse():
    """`copy_invoice_part` — 2026-08-07 : rempli avant le clic, vidé PAR le clic (JS du portail).
    Ce n'est pas notre jeu de données qui est en cause."""
    page = _Page([_champ("copy_invoice_part", "Please select one or more files.", manquant=True)])
    page._tp_champs_fichiers_remplis = {"copy_invoice_part"}

    verifier_soumission_non_bloquee(page)  # ne lève PAS


def test_combinaison_reelle_du_run_20_ne_leve_RIEN():
    """Rejoue EXACTEMENT ce qui a été mesuré sur le cas 125 : un champ testé (`rib_original`) +
    un champ fichier vidé par le clic (`copy_invoice_part`). Les deux couverts → aucun refus."""
    page = _Page([
        _champ("rib_original", "Please select a file.", manquant=True),
        _champ("copy_invoice_part", "Please select one or more files.", manquant=True),
    ])
    page._tp_champs_vides_intentionnels = {"rib_original"}
    page._tp_champs_fichiers_remplis = {"copy_invoice_part"}

    verifier_soumission_non_bloquee(page)  # ne lève PAS


# ── Isolation par page (jamais de fuite d'un scénario à l'autre) ──────────────

def test_le_marquage_est_isole_PAR_PAGE():
    """Chaque scénario a sa PROPRE page Playwright (`environment.py`) — un ensemble module-level
    aurait fait fuiter l'intention d'un scénario vers le suivant si un champ porte le même nom."""
    page_a = _Page([_champ("piece_jointe_facture", "Please select a file.", manquant=True)])
    page_a._tp_champs_vides_intentionnels = {"piece_jointe_facture"}
    page_b = _Page([_champ("piece_jointe_facture", "Please select a file.", manquant=True)])
    # page_b ne marque RIEN — un scénario différent, sans lien avec l'intention de page_a.

    verifier_soumission_non_bloquee(page_a)  # ne lève PAS (couvert)
    with pytest.raises(DonneeRefuseeError):
        verifier_soumission_non_bloquee(page_b)  # lève (non couvert sur CETTE page)


# ── `attach_file` / `leave_field_empty` posent bien le marquage ───────────────

class _FauxLocatorFichier:
    def __init__(self): self.first = self
    def set_input_files(self, chemin): pass
    def evaluate(self, script, *a): return "file" if "type" in script else "input"
    def count(self): return 1  # `locate_field` : le champ existe par son attribut `name`
    def wait_for(self, **kw): pass


class _FauxPageFichier:
    def __init__(self): self._marques = {}
    def wait_for_selector(self, *a, **kw): pass
    def locator(self, sel): return _FauxLocatorFichier()


def test_attach_file_MARQUE_le_champ_comme_rempli():
    page = _FauxPageFichier()

    H.attach_file(page, "copy_invoice_part")

    assert page._tp_champs_fichiers_remplis == {"copy_invoice_part"}


class _FauxLocatorTexte:
    def __init__(self, nom="rib_original"): self.first = self; self.nom = nom
    def evaluate(self, script, *a):
        if "tagName" in script:
            return "input"
        if ".type" in script or "el.type" in script:
            return "text"
        return self.nom  # `el.name || el.id || ''`, lu par `leave_field_empty`

    def fill(self, *a, **kw): pass
    def count(self): return 1  # `locate_field` : le champ existe par son attribut `name`
    def wait_for(self, **kw): pass


class _FauxPageTexte:
    def __init__(self): self.url = "https://exemple.test/formulaire"
    def wait_for_selector(self, *a, **kw): pass
    def locator(self, sel): return _FauxLocatorTexte()


def test_leave_field_empty_MARQUE_le_champ_comme_intentionnellement_vide():
    page = _FauxPageTexte()
    original = H.resolve_field_name
    H.resolve_field_name = lambda p, n: n
    try:
        H.leave_field_empty(page, "rib_original")
    finally:
        H.resolve_field_name = original

    assert page._tp_champs_vides_intentionnels == {"rib_original"}


# ── 2ᵉ passe (2026-08-07) : le scénario ENTIER est marqué, pas seulement des champs ────
#
# ⚠️ Les deux exemptions ci-dessus ne couvrent que deux MÉCANISMES précis (`je laisse le champ …
# vide`, `je joins un fichier …`). Mesuré le MÊME jour sur `/retenue_garantie` (cas 121 et 122,
# run 21) : un scénario qui écrit une valeur VOLONTAIREMENT invalide en toutes lettres
# (`code_client1` = "123456", 6 chiffres au lieu de 7) tombait dans le même piège — aucun
# marquage PAR CHAMP ne peut couvrir une valeur invalide passée par `je renseigne le champ …`.
#
# Le signal retenu est structurel et mesuré : sur les 85 scénarios de `behave_runtime/generated/`,
# les 35 négatifs portent TOUS l'assertion « … n'a pas augmenté », aucun des 43 nominaux ne la
# porte, et AUCUN ne porte les deux. `environment.py` la lit avant le premier step.

def test_un_scenario_qui_ATTEND_un_refus_ne_leve_RIEN_quel_que_soit_le_champ():
    """Le cas 121 : `code_client1` invalide EXPRÈS, écrit en toutes lettres — aucun marquage par
    champ ne peut le couvrir, seul le marquage du SCÉNARIO le peut."""
    page = _Page([_champ("code_client1", "Le Code Client doit contenir exactement 7 chiffres.",
                         "123456")])
    H.marquer_scenario_attend_un_refus(page)

    verifier_soumission_non_bloquee(page)  # ne lève PAS


def test_un_scenario_NOMINAL_est_toujours_protege_par_le_controle():
    """La borne : SANS ce marquage, un refus reste signalé exactement comme avant. C'est ce qui
    empêche l'exemption de devenir un trou — un scénario nominal dont la donnée est refusée doit
    toujours dire « c'est notre donnée », jamais accuser l'application."""
    page = _Page([_champ("code_client1", "format invalide", "123456")])

    with pytest.raises(DonneeRefuseeError, match="LE NAVIGATEUR A REFUSÉ"):
        verifier_soumission_non_bloquee(page)


def test_le_marquage_de_scenario_est_isole_PAR_PAGE():
    """Un scénario = une page (`environment.py`) : le marquage ne doit jamais fuir vers le
    scénario suivant, sinon un nominal hériterait de l'exemption d'un négatif précédent."""
    negatif = _Page([_champ("code_client1", "format invalide", "123456")])
    H.marquer_scenario_attend_un_refus(negatif)
    nominal = _Page([_champ("code_client1", "format invalide", "123456")])

    verifier_soumission_non_bloquee(negatif)      # exempté
    with pytest.raises(DonneeRefuseeError):
        verifier_soumission_non_bloquee(nominal)  # toujours protégé


def test_environment_MARQUE_bien_les_scenarios_negatifs():
    """Le câblage : `environment.py` doit lire les steps AVANT le premier clic. Sans lui, la
    fonction de marquage existerait sans que rien ne l'appelle — exactement le genre d'oubli que
    `test_soumission_bloquee.py::test_click_button_APPELLE_le_controle` attrape déjà ailleurs."""
    source = Path("behave_runtime/environment.py").read_text(encoding="utf-8")

    assert "marquer_scenario_attend_un_refus" in source
    assert "n'a pas augmenté" in source
    bloc = source.split("def before_scenario(")[1].split("\ndef ")[0]
    assert "_marquer_si_scenario_negatif" in bloc, (
        "le marquage doit être appelé depuis before_scenario, avant tout step")


# ── Le contexte d'enregistrement après un comptage réussi (cas 120) ───────────

class _FauxModeleCree:
    def __init__(self, ids=None, boom=False): self.ids, self.boom = ids or [777], boom
    def search_count(self, _d): return 11
    def search(self, _d, **_kw):
        if self.boom:
            raise RuntimeError("RPC perdu")
        return self.ids


class _CtxCree:
    def __init__(self, boom=False):
        modele = _FauxModeleCree(boom=boom)
        self.odoo = type("O", (), {"env": type("E", (), {
            "__getitem__": lambda s, n: modele})()})()
        setattr(self, H._count_attr("helpdesk.ticket"), 10)


def test_un_comptage_reussi_POSE_l_enregistrement_pour_les_steps_suivants():
    """⚠️ Le bug du cas 120 (2026-08-07) : « le nombre … augmente de 1 » PROUVE qu'un
    enregistrement a été créé, mais ne le posait pas en contexte — le step suivant (« le champ …
    de CET enregistrement … ») plantait en `AttributeError`, verdict « erreur technique » sur un
    scénario où l'application avait parfaitement fonctionné."""
    ctx = _CtxCree()

    H.check_count_increased_by_one(ctx, "helpdesk.ticket")

    assert ctx.last_record_ids == [777]
    assert ctx.last_record_model == "helpdesk.ticket"


def test_une_capture_IMPOSSIBLE_ne_fait_PAS_echouer_le_comptage():
    """Best-effort : le contrat de ce step est le COMPTAGE, déjà rempli. Une commodité pour les
    steps suivants ne doit jamais faire tomber une assertion qui a réussi — le step suivant le
    signalera clairement de lui-même."""
    ctx = _CtxCree(boom=True)

    H.check_count_increased_by_one(ctx, "helpdesk.ticket")  # ne lève PAS

    assert not hasattr(ctx, "last_record_ids"), "rien posé, mais rien de silencieux non plus"
