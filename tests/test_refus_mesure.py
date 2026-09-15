"""L'ÉMISSION d'un refus — le fait quitte le run au lieu d'être oublié (§5bis n°1).

Aujourd'hui, l'outil détecte parfaitement un refus (navigateur, filtre JavaScript, serveur) et
rend le bon verdict — puis **oublie tout**. Le run suivant réécrit la même valeur invalide,
indéfiniment. Ces tests vérifient que le refus est désormais **mesuré et consigné**.

⚠️ Chaque test marqué `GARDE` échoue sur le code d'avant : il n'y avait aucun payload, aucun
sidecar, et la sonde tronquait la valeur à 40 caractères — donc une valeur interdite sous une
forme qui n'a jamais été soumise, et jamais reconnue au run suivant.

Le transport passe par un FICHIER SIDECAR, jamais par le log : Behave ne recrache pas les logs
d'un scénario capturé, et un mécanisme dont le signal se perd selon la configuration de
journalisation n'est pas un mécanisme (leçon de `0007` B+).
"""

from __future__ import annotations

import json

import pytest

from behave_runtime.steps_library import _base_helpers as H
from behave_runtime.steps_library._base_helpers import (
    REGLES_REFUS_FILE_ENV,
    DonneeRefuseeError,
    RefusMesure,
)


class _FakePage:
    """Surface Playwright minimale : ce que rendent `evaluate` et `url`."""

    def __init__(self, resultats=None, url="https://portail.test/en/fournisseur/creation"):
        self.url = url
        self._resultats = list(resultats or [])
        self.appels = []

    def evaluate(self, script, arg=None):
        self.appels.append((script, arg))
        if not self._resultats:
            return None
        valeur = self._resultats.pop(0)
        return valeur(arg) if callable(valeur) else valeur


@pytest.fixture()
def sidecar(tmp_path, monkeypatch):
    """Désigne un sidecar jetable et remet à zéro le compteur de refus du run."""
    chemin = tmp_path / "regles_refus.jsonl"
    monkeypatch.setenv(REGLES_REFUS_FILE_ENV, str(chemin))
    monkeypatch.setattr(H, "_refus_consignes", 0)
    return chemin


def _lignes(chemin) -> list[dict]:
    if not chemin.exists():
        return []
    return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()]


# ── Le refus navigateur, après le clic ───────────────────────────────────────

def _champ_invalide(**kw) -> dict:
    base = {"nom": "tva_intracommunautaire", "valeur": "TestPilot", "manquant": False,
            "msg": "Le numéro de TVA doit contenir uniquement des chiffres.",
            "drapeaux": ["customError"], "pattern": "", "maxLength": "", "minLength": "",
            "max": "", "min": "", "step": "", "type": "text"}
    base.update(kw)
    return base


def test_GARDE_un_refus_du_navigateur_est_consigne_dans_le_sidecar(sidecar):
    page = _FakePage([[_champ_invalide()]])
    with pytest.raises(DonneeRefuseeError):
        H.verifier_soumission_non_bloquee(page)

    lignes = _lignes(sidecar)
    assert len(lignes) == 1
    assert lignes[0]["champ"] == "tva_intracommunautaire"
    assert lignes[0]["valeur_refusee"] == "TestPilot"
    assert lignes[0]["origine"] == "navigateur"


def test_GARDE_la_route_est_NORMALISEE_comme_l_annuaire(sidecar):
    """L'URL réelle porte une locale ; l'annuaire, non. Sans normalisation la règle est perdue."""
    page = _FakePage([[_champ_invalide()]], url="https://portail.test/en/fournisseur/creation")
    with pytest.raises(DonneeRefuseeError):
        H.verifier_soumission_non_bloquee(page)
    assert _lignes(sidecar)[0]["route"] == "/fournisseur/creation"


def test_GARDE_le_motif_lu_par_le_navigateur_devient_la_contrainte(sidecar):
    """`patternMismatch` → on relit `el.pattern`, jamais on ne devine dans le message."""
    page = _FakePage([[_champ_invalide(nom="code_client1", valeur="TEST_REMB_CLI001",
                                      drapeaux=["patternMismatch"], pattern=r"\d{7}",
                                      msg="Veuillez respecter le format demandé.")]])
    with pytest.raises(DonneeRefuseeError):
        H.verifier_soumission_non_bloquee(page)
    ligne = _lignes(sidecar)[0]
    assert ligne["type_contrainte"] == "patternMismatch"
    assert ligne["valeur_contrainte"] == r"\d{7}"


def test_une_valeur_longue_traverse_le_python_sans_etre_rognee(sidecar):
    """Le chemin PYTHON ne rogne pas la valeur.

    ⚠️ **Ce test ne prouve PAS que la sonde JavaScript ne tronque plus** : le faux `page` rend
    des dictionnaires tout faits et n'exécute aucun JavaScript. La troncature vit dans le
    `slice()` de la sonde, hors de portée d'un test sans navigateur — c'est
    `test_GARDE_la_sonde_JS_ne_tronque_plus_la_valeur` qui la tient, sur la source.
    """
    longue = "A" * 90
    page = _FakePage([[_champ_invalide(valeur=longue)]])
    with pytest.raises(DonneeRefuseeError):
        H.verifier_soumission_non_bloquee(page)
    assert _lignes(sidecar)[0]["valeur_refusee"] == longue


def test_GARDE_la_sonde_JS_ne_tronque_plus_la_valeur_a_40_caracteres():
    """⚠️ Échoue sur l'ancienne sonde (`slice(0, 40)`) — vérifié sur la SOURCE, faute de mieux.

    Une valeur tronquée serait interdite sous une forme **jamais soumise** : le résolveur
    régénérerait la vraie valeur au run suivant sans jamais la reconnaître. Mécanisme mort, et
    rien à l'écran pour le dire.

    Un test de source est faible — il vérifie une chaîne, pas un comportement. Il est ici parce
    que l'alternative honnête est **aucune couverture du tout** : seul un vrai navigateur
    exécuterait ce `slice`. Mieux vaut une garde faible et déclarée qu'une garde absente qu'on
    croit présente.
    """
    source = open(H.__file__, encoding="utf-8").read()
    assert "slice(0, 40)" not in source, "la sonde tronque encore la valeur apprise"
    assert source.count("slice(0, 120)") >= 2, "les deux sondes doivent relever la valeur entière"


def test_le_message_d_erreur_reste_INCHANGE(sidecar):
    """`str(exc)` ne bouge pas : la taxonomie classe sur le TYPE, Behave n'affiche que le texte."""
    page = _FakePage([[_champ_invalide()]])
    with pytest.raises(DonneeRefuseeError) as capture:
        H.verifier_soumission_non_bloquee(page)
    message = str(capture.value)
    assert "LE NAVIGATEUR A REFUSÉ D'ENVOYER" in message
    assert "L'APPLICATION N'EST PAS EN CAUSE" in message


def test_l_exception_porte_le_payload_structure(sidecar):
    page = _FakePage([[_champ_invalide()]])
    with pytest.raises(DonneeRefuseeError) as capture:
        H.verifier_soumission_non_bloquee(page)
    assert [r.champ for r in capture.value.refus] == ["tva_intracommunautaire"]


def test_un_champ_sans_name_n_apprend_RIEN(sidecar):
    """Un champ non ré-identifiable au run suivant ne produit pas de règle."""
    page = _FakePage([[_champ_invalide(nom="?")]])
    with pytest.raises(DonneeRefuseeError):
        H.verifier_soumission_non_bloquee(page)
    assert _lignes(sidecar) == []


def test_sans_sidecar_designe_rien_n_est_ecrit_et_rien_ne_casse(tmp_path, monkeypatch):
    """Hors run behave (test unitaire, appel direct) : aucune variable posée, aucun effet."""
    monkeypatch.delenv(REGLES_REFUS_FILE_ENV, raising=False)
    page = _FakePage([[_champ_invalide()]])
    with pytest.raises(DonneeRefuseeError):
        H.verifier_soumission_non_bloquee(page)


def test_le_nombre_de_refus_consignes_est_PLAFONNE(sidecar, monkeypatch):
    monkeypatch.setattr(H, "_MAX_REFUS_PAR_RUN", 3)
    for _ in range(5):
        H._consigner_refus([RefusMesure(route="/a", champ="c", type_contrainte="tooLong")])
    assert len(_lignes(sidecar)) == 3


# ── Le filtre JavaScript — le signal que le crawl ne verra jamais ────────────

def test_GARDE_une_valeur_mutilee_apprend_la_classe_conservee(sidecar):
    """`FAC-TEST-001` retenu `001` ⇒ le filtre ne garde que les chiffres.

    C'est LE cas qui atteint les règles écrites en JavaScript : aucun attribut HTML ne les
    exprime, seule l'exécution les révèle.
    """
    page = _FakePage(["001"])
    with pytest.raises(DonneeRefuseeError):
        H._verifier_valeur_retenue(page, page, "numero_facture1", "FAC-TEST-001")

    ligne = _lignes(sidecar)[0]
    assert ligne["type_contrainte"] == "filtre_saisie"
    assert ligne["valeur_contrainte"] == r"\d"
    assert ligne["valeur_refusee"] == "FAC-TEST-001"
    assert ligne["origine"] == "filtre_saisie"


def test_une_classe_NON_prouvable_n_affirme_aucune_contrainte(sidecar):
    """Si aucune classe ne reconstruit le retenu, on noircit la valeur sans inventer de règle."""
    page = _FakePage(["totalement-autre-chose"])
    with pytest.raises(DonneeRefuseeError):
        H._verifier_valeur_retenue(page, page, "champ", "FAC-TEST-001")
    ligne = _lignes(sidecar)[0]
    assert ligne["valeur_contrainte"] == ""
    assert ligne["valeur_refusee"] == "FAC-TEST-001"


@pytest.mark.parametrize("ecrit, retenu, attendu", [
    ("FAC-TEST-001", "001", r"\d"),
    ("ABC123", "ABC", r"[A-Za-z]"),
    ("a_b-c", "a_bc", r"\w"),          # seul `\w` explique le souligné conservé
    ("a-b-c", "abc", r"[A-Za-z]"),     # la classe la PLUS STRICTE qui explique gagne
    ("FAC-TEST-001", "XYZ", ""),
    ("01/01/2024", "", ""),            # ⚠️ AUCUNE lettre dans « 01/01/2024 » : sans la garde, ce
    ("AAAAAAAA", "", ""),              #   cas « prouvait » [A-Za-z] à tort (cf. test dédié).
])
def test_la_classe_conservee_doit_etre_PROUVEE_par_reconstruction(ecrit, retenu, attendu):
    """L'ordre des classes va du plus strict au plus large, et c'est délibéré.

    `001` s'explique par `\\d` comme par `\\w` — mais `\\d` est ce qui INFORME le résolveur.
    Rendre la classe la plus large serait vrai et inutile.
    """
    assert H._classe_conservee(ecrit, retenu) == attendu


def test_un_retenu_VIDE_ne_prouve_JAMAIS_de_classe(sidecar):
    """⚠️ Le défaut RÉEL, mesuré en production (campagne 18, 2026-08-06, champ `date_debut` de
    `/retenue_garantie`) — pas une hypothèse.

    Un champ dont le filtre de saisie vide TOUT (`retenu == ''`) rendait `[A-Za-z]` « prouvé » dès
    lors que l'écrit ne contenait aucune lettre (`01/01/2024` n'en a aucune : filtrer sur les
    lettres redonne bien `''`, trivialement — n'importe quelle classe absente de l'écrit passait
    ce test). Le résolveur déterministe apprenait donc une classe INVENTÉE, puis synthétisait sa
    valeur de rechange dans cette classe (`AAAAAAAA`) — qui, à son tour, sans le moindre chiffre,
    « prouvait » `\\d` au run suivant : la règle apprise ne convergeait jamais, elle tournait.

    Le champ `date_debut` était pourtant correctement typé `date` dans l'annuaire ; c'est cette
    classe apprise à tort qui écrasait la vraie date que `valeur_conforme.valeur_pour()` aurait
    autrement rendue (§7, `_valeur_pour_classe` prime sur `_premier_candidat` dès qu'une classe
    apprise existe).
    """
    page = _FakePage([""])   # le champ a tout perdu : c'est EXACTEMENT le cas réel mesuré
    with pytest.raises(DonneeRefuseeError):
        H._verifier_valeur_retenue(page, page, "date_debut", "01/01/2024")
    ligne = _lignes(sidecar)[0]
    assert ligne["valeur_contrainte"] == ""   # jamais `[A-Za-z]` — aucune classe n'est prouvée


def test_un_reformatage_cosmetique_n_apprend_RIEN(sidecar):
    """Un IBAN réaffiché avec des espaces reste valide — la soumission passe (mesuré 2026-07-23)."""
    page = _FakePage(["FR76 3000 4000 0512 3456 7890 189"])
    H._verifier_valeur_retenue(page, page, "iban", "FR7630004000051234567890189")
    assert _lignes(sidecar) == []


# ── Le refus serveur ─────────────────────────────────────────────────────────

def test_GARDE_le_refus_serveur_relit_la_VALEUR_des_champs_nommes(sidecar):
    """Le serveur nomme les champs, pas les valeurs — sans relecture, la règle est inutilisable.

    ⚠️ On saurait *quel* champ est refusé sans savoir *quoi* ne plus écrire : le résolveur
    n'aurait rien à en tirer.
    """
    page = _FakePage(["ABC", "999"])
    mesures = H._refus_serveur_mesures(page, "code_client1, numero_tva")

    assert [m.champ for m in mesures] == ["code_client1", "numero_tva"]
    assert [m.valeur_refusee for m in mesures] == ["ABC", "999"]
    assert all(m.origine == "serveur" for m in mesures)


def test_un_refus_serveur_n_AFFIRME_aucune_contrainte(sidecar):
    """La règle métier derrière n'est ni dans le HTML ni dans la réponse — la deviner serait une
    invention."""
    page = _FakePage(["ABC"])
    mesures = H._refus_serveur_mesures(page, "code_client1")
    assert mesures[0].valeur_contrainte == ""
    assert mesures[0].type_contrainte == "refus_serveur"


# ── Ce qui ne doit PAS apprendre ─────────────────────────────────────────────

def test_GARDE_le_mauvais_step_fichier_n_apprend_RIEN(sidecar):
    """`attach_file` sur un champ qui n'est pas un fichier : c'est NOTRE code de test qui est faux.

    ⚠️ L'application n'a rien refusé. En faire une règle apprise remplirait l'annuaire de faits
    sur notre propre outil, et le résolveur n'a rien à en tirer. Ce site lève donc un
    `DonneeRefuseeError` **sans passer par `lever_donnee_refusee`** — vérifié ici pour que
    personne ne « corrige » l'oubli apparent.
    """
    source = H.__file__
    with open(source, encoding="utf-8") as flux:
        lignes = flux.read().splitlines()
    bruts = [i for i, l in enumerate(lignes) if "raise DonneeRefuseeError(" in l]
    # Un seul `raise` brut subsiste : celui d'`attach_file`. Les autres passent par le
    # constructeur unique qui consigne.
    assert len(bruts) == 2, "attendu : la définition de lever_donnee_refusee + attach_file"
    contexte = "\n".join(lignes[max(0, bruts[-1] - 12):bruts[-1] + 3])
    assert "n'est PAS un champ fichier" in contexte or "champ fichier" in contexte
