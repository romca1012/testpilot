"""Couche 1 — empêcher l'erreur au lieu de la constater (2026-07-22).

Deux mécanismes complémentaires, tous deux **déterministes** et sans LLM :

**A. La règle en français (`title`)** — mesuré : `numero_facture1` n'a **aucun** `pattern`, mais son
attribut `title` dit *« Veuillez saisir des groupes de sept chiffres. »* La règle était écrite dans
la page, lisible, en clair — **et le crawl la jetait**. L'agent devinait donc, et devinait mal.

**B. Le contrôle de mutilation** — après chaque saisie, comparer ce qu'on a écrit à ce que le champ
a **retenu**. Le champ `numero_facture1` porte un filtre JavaScript qui supprime les caractères non
numériques : `FAC-TEST-001` y devient `001`. Trois chiffres au lieu de sept → soumission bloquée →
rien créé → verdict `non_conforme`. **L'application avait raison.**

⚠️ **Ce qui rend B décisif : il ne connaît RIEN.** Ni `pattern`, ni `title`, ni cartographie. Il
compare, c'est tout. Il attrape donc les filtres JavaScript, masques de saisie et normalisations —
**tout ce qu'un crawl statique ne verra jamais**. C'est le complément exact du plafond de
l'annuaire, et la raison pour laquelle « tout savoir à l'avance » n'est pas la bonne stratégie.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "behave_runtime" / "steps_library"))

from testpilot.analysis.plan import TestPlan  # noqa: E402
from testpilot.generation import prompt as pm  # noqa: E402


def _plan(routes):
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"],
                    portal_routes=routes, risks=[], connector_type="odoo", cost_usd=0.0,
                    raw_spec="SPEC", entry_url=routes[0] if routes else "")


def _modele(champs):
    return {"mesure_le": "2026-07-22", "pages": {"/form/{id}": {"champs": champs}},
            "transitions": {}, "onglets_internes": {}}


def _champ(name, **kw):
    base = {"name": name, "required": True, "tag": "input", "type": "text", "visible": True}
    return {**base, **kw}


# ── A. La règle en français atteint le prompt ────────────────────────────────

def test_la_regle_LISIBLE_est_transmise_a_l_agent():
    """⚠️ LE cas mesuré : aucun `pattern`, mais une phrase qui dit tout."""
    modele = _modele([_champ("numero_facture1", contraintes={
        "regle_lisible": "Veuillez saisir des groupes de sept chiffres."})])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "Veuillez saisir des groupes de sept chiffres." in s
    assert "CONTRAINTE" in s


def test_la_regle_lisible_et_le_motif_COEXISTENT():
    """Un motif est exact, une phrase est compréhensible. Aucun ne remplace l'autre."""
    modele = _modele([_champ("siret", contraintes={
        "regle_lisible": "Le SIRET doit contenir 14 chiffres.", "pattern": r"\d{9} \d{5}"})])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "Le SIRET doit contenir 14 chiffres." in s
    assert r"`\d{9} \d{5}`" in s


def test_le_crawl_CAPTURE_le_title():
    """La couche 1 ne vaut que si la mesure ramène la donnée. On lit le code du crawl : le test
    d'intégration réel exige un navigateur, mais l'oubli de capture, lui, se voit ici."""
    source = Path("scripts/crawl_domaine.py").read_text(encoding="utf-8")

    assert "regle_lisible" in source
    assert "getAttribute('title')" in source


# ── B. Le contrôle de mutilation ─────────────────────────────────────────────

class _Page:
    """Simule un ÉLÉMENT qui RETIENT autre chose que ce qu'on lui a écrit.

    ⚠️ Depuis l'étape 2.1 du plan de consolidation (2026-09-15), `_verifier_valeur_retenue` relit
    l'ÉLÉMENT déjà résolu par `locate_field` (`el.evaluate(...)`), plus jamais une reconstruction
    `[name="..."]` côté page — cette fausse valeur sert donc à la fois de `page` (jamais lue ici,
    `_route_courante` s'en contente via `getattr`) et d'`el` dans les appels ci-dessous."""

    def __init__(self, retenu):
        self.retenu = retenu
        self.ecrit = None

    def evaluate(self, script, *a):
        return self.retenu


def test_une_valeur_MUTILEE_est_detectee_immediatement():
    """⚠️ LE cas mesuré : `FAC-TEST-001` filtré en `001` par un masque de saisie JavaScript."""
    from _base_helpers import _verifier_valeur_retenue, DonneeRefuseeError

    champ = _Page("001")
    with pytest.raises(DonneeRefuseeError, match="MODIFIÉ la valeur saisie"):
        _verifier_valeur_retenue(champ, champ, "numero_facture1", "FAC-TEST-001")


def test_le_message_DISCULPE_l_application():
    """La confusion qu'on traque depuis le début : ce n'est pas un défaut applicatif."""
    from _base_helpers import _verifier_valeur_retenue, DonneeRefuseeError

    champ = _Page("001")
    with pytest.raises(DonneeRefuseeError) as err:
        _verifier_valeur_retenue(champ, champ, "numero_facture1", "FAC-TEST-001")

    message = str(err.value)
    assert "ce n'est pas un défaut de l'application" in message
    assert "'FAC-TEST-001'" in message and "'001'" in message, "les deux valeurs sont montrées"


def test_une_valeur_INTACTE_passe():
    from _base_helpers import _verifier_valeur_retenue, DonneeRefuseeError

    champ = _Page("1234567")
    _verifier_valeur_retenue(champ, champ, "numero_facture1", "1234567")


@pytest.mark.parametrize("retenu, ecrit", [
    ("  1234567  ", "1234567"),      # espaces de bordure ajoutés
    ("1234567", "  1234567  "),      # espaces de bordure écrits
    ("DUPONT", "Dupont"),            # champ qui majusculise
])
def test_les_normalisations_ANODINES_ne_declenchent_rien(retenu, ecrit):
    """Signaler une majusculisation produirait du bruit sans défaut réel — et le bruit finit par
    faire ignorer les vraies alertes."""
    from _base_helpers import _verifier_valeur_retenue, DonneeRefuseeError

    champ = _Page(retenu)
    _verifier_valeur_retenue(champ, champ, "nom", ecrit)


def test_un_champ_ABSENT_ne_declenche_rien():
    """Le champ introuvable a déjà son propre diagnostic ailleurs — ne pas le doubler d'un
    message trompeur sur la valeur."""
    from _base_helpers import _verifier_valeur_retenue, DonneeRefuseeError

    champ = _Page(None)
    _verifier_valeur_retenue(champ, champ, "inexistant", "x")


def test_un_REFORMATAGE_par_espaces_internes_est_tolere():
    """Correctif C (rejeu 2026-07-23, IBAN). Un champ qui réaffiche un IBAN par groupes de 4
    (`FR76…189` → `FR76 3000 …189`) ne l'a PAS mutilé : la valeur reste valide, la soumission
    passe. Le crier serait un faux positif."""
    from _base_helpers import _verifier_valeur_retenue

    champ = _Page("FR76 3000 6000 0112 3456 7890 189")
    _verifier_valeur_retenue(champ, champ, "iban_client", "FR7630006000011234567890189")


def test_une_vraie_MUTILATION_reste_detectee_malgre_la_tolerance_espaces():
    """Garde négative : tolérer les espaces ne doit pas laisser passer une suppression de
    caractères. `FAC-TEST-001` → `001` diffère encore une fois les espaces retirés."""
    from _base_helpers import _verifier_valeur_retenue, DonneeRefuseeError

    champ = _Page("0 0 1")
    with pytest.raises(DonneeRefuseeError):
        _verifier_valeur_retenue(champ, champ, "numero_facture1", "FAC-TEST-001")


class _PageQuiPlante:
    def evaluate(self, *a, **kw): raise RuntimeError("navigateur mort")


def test_un_controle_qui_plante_ne_fait_pas_tomber_le_scenario():
    """Même invariant que le diagnostic de soumission : un mécanisme de sûreté ne doit jamais
    devenir lui-même une cause d'échec technique."""
    from _base_helpers import _verifier_valeur_retenue, DonneeRefuseeError

    champ = _PageQuiPlante()
    _verifier_valeur_retenue(champ, champ, "nom", "valeur")


# ── Sur l'annuaire RÉEL, après re-mesure ────────────────────────────────────

def test_l_annuaire_REEL_porte_la_regle_de_numero_facture1():
    """Se déclenchera après la prochaine exploration — d'ici là, il documente l'attente."""
    chemin = Path("data/domain/projet-1.json")
    if not chemin.exists():
        pytest.skip("annuaire réel absent")
    modele = json.loads(chemin.read_text(encoding="utf-8"))

    regles = [c for i in modele["pages"].values() for c in (i.get("champs") or [])
              if (c.get("contraintes") or {}).get("regle_lisible")]
    if not regles:
        pytest.skip("annuaire antérieur à la capture de `title` — ré-explorer le projet")

    assert regles, "au moins une règle lisible doit être capturée"
