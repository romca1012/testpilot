"""Le store des règles apprises — le fait mesuré, et rien d'autre.

Ce que ces tests protègent, dans l'ordre d'importance :

1. **l'annuaire du crawl n'est JAMAIS réécrit** — c'est l'invariant fondateur ;
2. **la clé d'une règle ne dépend d'aucun texte** (principe 1) ;
3. la fusion **n'écrase jamais** ce que le crawl a mesuré, et **ne mute pas** son cache ;
4. un fichier abîmé n'empêche pas un run de tourner.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from testpilot.generation import domain_model
from testpilot.generation import regles_apprises as ra


def _regle(**kw) -> ra.RegleApprise:
    base = dict(route="/fournisseur/creation", champ="tva_intracommunautaire",
                type_contrainte="patternMismatch", valeur_contrainte=r"\d{9}",
                valeur_refusee="TestPilot", origine="navigateur", preuve="Format attendu.")
    base.update(kw)
    return ra.RegleApprise(**base)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Isole le store dans un dossier jetable et vide le cache entre deux tests."""
    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path / "regles-apprises")
    ra._lire.cache_clear()
    yield tmp_path
    ra._lire.cache_clear()


# ── Écriture et relecture ────────────────────────────────────────────────────

def test_un_refus_ecrit_une_regle_relisible(store):
    assert ra.enregistrer(1, [_regle()], execution_id=128) == 1
    regles = ra.charger(1)
    assert len(regles) == 1
    assert regles[0].champ == "tva_intracommunautaire"
    assert regles[0].valeur_refusee == "TestPilot"


def test_le_fichier_porte_execution_id_et_version_de_format(store):
    ra.enregistrer(1, [_regle()], execution_id=128)
    ligne = json.loads(ra.chemin(1).read_text(encoding="utf-8").splitlines()[0])
    assert ligne["execution_id"] == 128
    assert ligne["v"] == ra.FORMAT_VERSION
    assert ligne["mesure_le"]


def test_un_projet_sans_fichier_rend_une_liste_vide_sans_lever(store):
    """L'absence de refus est le cas NOMINAL, pas une erreur (doctrine read_field_fallbacks)."""
    assert ra.charger(999) == []


def test_un_fichier_illisible_ne_fait_PAS_tomber_le_resolveur(store):
    ra.enregistrer(1, [_regle()])
    with ra.chemin(1).open("a", encoding="utf-8") as flux:
        flux.write("{ceci n'est pas du JSON\n")
    ra._lire.cache_clear()
    regles = ra.charger(1)
    assert len(regles) == 1, "la ligne saine doit survivre à la ligne abîmée"


def test_une_regle_sans_route_ni_champ_est_refusee_a_l_ecriture(store):
    assert ra.enregistrer(1, [{"route": "", "champ": "x", "type_contrainte": "tooLong"}]) == 0
    assert ra.enregistrer(1, [{"route": "/a", "champ": "x", "type_contrainte": "inconnu"}]) == 0


def test_les_projets_ne_partagent_PAS_leurs_regles(store):
    """Deux projets sont deux APPLICATIONS (`0005`) : un refus de l'une n'apprend rien sur l'autre."""
    ra.enregistrer(1, [_regle()])
    assert ra.charger(2) == []


def test_le_cache_est_invalide_quand_le_fichier_change(store):
    ra.enregistrer(1, [_regle()])
    assert len(ra.charger(1)) == 1
    ra.enregistrer(1, [_regle(champ="autre_champ")])
    assert len(ra.charger(1)) == 2, "un cache non invalidé servirait la version d'avant"


# ── La clé : runtime seulement (principe 1) ──────────────────────────────────

def test_GARDE_la_cle_ne_depend_PAS_du_message_de_l_application(store):
    """Le même fait, deux formulations : UNE règle, pas deux.

    ⚠️ Échoue si `preuve` entre dans `cle()`. Un texte change de casse, de ponctuation ou de
    langue sans que le fait change — même raisonnement que `failure_signature`, qui refuse de se
    dériver du libellé écrit par l'agent.
    """
    a, b = _regle(preuve="Format attendu."), _regle(preuve="FORMAT ATTENDU !!")
    assert a.cle() == b.cle()

    ra.enregistrer(1, [a, b])
    regles = ra.charger(1)
    assert len(regles) == 1
    assert regles[0].occurrences == 2


def test_deux_refus_DIFFERENTS_restent_deux_regles(store):
    ra.enregistrer(1, [_regle(valeur_refusee="TestPilot"), _regle(valeur_refusee="ABC")])
    assert len(ra.charger(1)) == 2


def test_le_type_de_contrainte_appartient_a_une_enumeration_fermee():
    """Un drapeau hors `ValidityState` est un bug d'émission, pas une donnée."""
    assert "patternMismatch" in ra.TYPES_CONTRAINTE
    assert "customError" in ra.TYPES_CONTRAINTE
    assert "filtre_saisie" in ra.TYPES_CONTRAINTE
    assert "n_importe_quoi" not in ra.TYPES_CONTRAINTE


# ── L'invariant : l'annuaire du crawl est intouchable ────────────────────────

def test_INVARIANT_l_annuaire_du_crawl_n_est_JAMAIS_reecrit(store, tmp_path, monkeypatch):
    """Le cœur de l'arbitrage du 2026-08-03 — vérifié sur un cycle COMPLET.

    ⚠️ Si ce test tombe, c'est que l'apprentissage a contaminé la référence versionnée. Le brief
    dit « enrichir l'annuaire » ; l'invariant de `domain_model` dit qu'un modèle qui change tout
    seul n'est plus une référence, et n'attrape donc plus une régression de l'application. On
    enrichit **la connaissance**, jamais **le fichier**.
    """
    domaine = tmp_path / "domain"
    domaine.mkdir()
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", domaine)
    fichier = domain_model.chemin_du_modele(1)
    fichier.write_text(json.dumps({
        "project_id": 1,
        "pages": {"/fournisseur/creation": {"champs": [
            {"name": "tva_intracommunautaire", "tag": "input", "type": "text",
             "required": True, "visible": True, "contraintes": {}}]}},
    }, ensure_ascii=False), encoding="utf-8")
    avant = hashlib.sha256(fichier.read_bytes()).hexdigest()

    ra.enregistrer(1, [_regle()])
    regles = ra.charger(1)
    modele = domain_model.charger_modele({"id": 1, "connector_type": "odoo"})
    champ = modele["pages"]["/fournisseur/creation"]["champs"][0]
    ra.fusionner(champ, ra.pour_champ(regles, "/fournisseur/creation", champ["name"]))

    assert hashlib.sha256(fichier.read_bytes()).hexdigest() == avant


def test_GARDE_la_fusion_ne_MUTE_pas_le_modele_servi_par_le_cache(store):
    """`formulaires_requis` PARTAGE son sous-dictionnaire `contraintes` avec le modèle en cache.

    ⚠️ Échoue si `fusionner` fait `champ["contraintes"][...] = ...` au lieu de copier : le champ
    d'origine se retrouverait enrichi pour tout le processus — un modèle qui change tout seul.
    """
    contraintes_partagees = {}
    champ = {"name": "tva_intracommunautaire", "contraintes": contraintes_partagees}

    fusionne = ra.fusionner(champ, [_regle()])

    assert fusionne["contraintes"]["pattern"] == r"\d{9}"
    assert contraintes_partagees == {}, "le dictionnaire d'origine a été muté"
    assert champ.get("valeurs_interdites") is None
    assert fusionne["contraintes"] is not contraintes_partagees


# ── La fusion : remplir les blancs, jamais écraser ───────────────────────────

def test_la_fusion_n_ECRASE_JAMAIS_ce_que_le_crawl_a_mesure(store):
    """Le crawl a lu `\\d{7}` : un refus ne peut pas le contredire, seulement documenter un blanc."""
    champ = {"name": "code_client1", "contraintes": {"pattern": r"\d{7}"}}
    fusionne = ra.fusionner(champ, [_regle(champ="code_client1", valeur_contrainte=r"\d{9}")])
    assert fusionne["contraintes"]["pattern"] == r"\d{7}"


def test_la_fusion_remplit_un_blanc_laisse_par_le_crawl(store):
    """Le cas `tva_intracommunautaire` : aucune contrainte HTML, une règle en JavaScript."""
    champ = {"name": "tva_intracommunautaire", "contraintes": {}}
    fusionne = ra.fusionner(champ, [_regle()])
    assert fusionne["contraintes"]["pattern"] == r"\d{9}"


def test_customError_range_la_phrase_de_l_application_en_regle_lisible(store):
    """Le navigateur n'expose AUCUNE contrainte machine — seulement son message."""
    champ = {"name": "tva_intracommunautaire", "contraintes": {}}
    regle = _regle(type_contrainte="customError", valeur_contrainte="",
                   preuve="Le numéro de TVA doit contenir uniquement des chiffres.")
    fusionne = ra.fusionner(champ, [regle])
    assert "uniquement des chiffres" in fusionne["contraintes"]["regle_lisible"]


def test_GARDE_valueMissing_n_AFFIRME_aucune_contrainte(store):
    """« refusé vide une fois » ne veut pas dire « toujours obligatoire ».

    ⚠️ Le code du navigateur documente déjà le piège : rendre 4 champs obligatoires parce qu'un
    choix fait plus haut les a rendus requis serait une INVENTION. Le fait est enregistré et
    remonté à l'agent ; il ne descend pas dans le résolveur.
    """
    champ = {"name": "motif_avoir", "contraintes": {}}
    regle = _regle(champ="motif_avoir", type_contrainte="valueMissing",
                   valeur_contrainte="", valeur_refusee="")
    fusionne = ra.fusionner(champ, [regle])
    assert fusionne["contraintes"] == {}
    assert fusionne.get("valeurs_interdites") is None


def test_refus_serveur_noircit_la_valeur_sans_affirmer_de_regle(store):
    champ = {"name": "code_client1", "contraintes": {}}
    regle = _regle(champ="code_client1", type_contrainte="refus_serveur",
                   valeur_contrainte="", valeur_refusee="ABC", origine="serveur")
    fusionne = ra.fusionner(champ, [regle])
    assert fusionne["contraintes"] == {}
    assert fusionne["valeurs_interdites"] == ["ABC"]


def test_un_champ_sans_regle_est_rendu_INCHANGE(store):
    champ = {"name": "libre", "contraintes": {"maxlength": "10"}}
    fusionne = ra.fusionner(champ, [])
    assert fusionne["contraintes"] == {"maxlength": "10"}
    assert "valeurs_interdites" not in fusionne


# ── Le rapprochement de route ────────────────────────────────────────────────

def test_pour_champ_ne_melange_pas_les_champs_ni_les_routes(store):
    regles = [_regle(), _regle(champ="autre"), _regle(route="/remboursement")]
    trouvees = ra.pour_champ(regles, "/fournisseur/creation", "tva_intracommunautaire")
    assert len(trouvees) == 1


def test_pour_champ_rapproche_une_route_a_identifiant(store):
    regles = [_regle(route="/mutation/{id}", champ="code_client1")]
    assert ra.pour_champ(regles, "/mutation/78", "code_client1")


def test_GARDE_une_route_sans_locale_retrouve_quand_meme_sa_regle(store):
    """Le piège `/my` — voir `test_normalisation_route`.

    ⚠️ Échoue si `pour_champ` compare les routes par égalité de chaînes. L'annuaire a stocké
    `/my/home` (mesuré depuis `/en/my/home`), alors qu'une URL sans locale se normalise en
    `/home` : la règle serait perdue **en silence**, et le mécanisme mort sans rien à l'écran
    pour le trahir.
    """
    regles = [_regle(route="/my/home", champ="code_client1")]
    assert ra.pour_champ(regles, "/home", "code_client1")
