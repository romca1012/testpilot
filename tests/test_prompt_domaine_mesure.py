"""La génération reçoit enfin les FAITS mesurés — routes, onglets, valeurs de listes.

Ces faits étaient dans `data/domain/…json` depuis le 2026-07-17 (crawl déterministe, aucun LLM)
et **lus par personne** : seuls les champs requis en sortaient. L'agent redécouvrait donc par
exploration ce que le dépôt savait déjà — en payant, et en se trompant.

Deux des cinq causes d'échec du cas 1 étaient exactement là :
- `0020` — le test cliquait l'onglet « Ordinateurs » depuis `/my/home`, où il n'existe pas.
  L'annuaire sait qu'il vit sur `/myservices`.
- `0019` — l'agent inventait la valeur `"new"` d'un `<select>`. L'annuaire connaît les options
  réelles (`new_aquisition`, `remplacement`).

⚠️ Ces tests ne prouvent PAS que l'agent obéit — seulement qu'on lui dit. L'obéissance se mesure
en génération réelle (comme `0012` et `0007` A1 l'ont été), jamais par un test unitaire.
"""

import json
from pathlib import Path

import pytest

from testpilot.analysis.plan import TestPlan
from testpilot.generation import prompt as pm


def _plan(**kw):
    base = dict(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[],
                risks=[], connector_type="odoo", cost_usd=0.0, raw_spec="SPEC", entry_url="")
    base.update(kw)
    return TestPlan(**base)


def _modele(pages=None, onglets=None, transitions=None):
    return {
        "mesure_le": "2026-07-17",
        "pages": pages if pages is not None else {"/myservices": {"champs": []}},
        "onglets_internes": onglets or {},
        "transitions": transitions or {},
    }


# ── Les faits injectés ────────────────────────────────────────────────────────

def test_les_routes_reelles_sont_donnees(_=None):
    modele = _modele(pages={"/myservices": {"champs": []}, "/my/home": {"champs": []}})

    s = pm._section_domaine_mesure(_plan(), modele)

    assert "`/myservices`" in s and "`/my/home`" in s
    assert "n'en invente aucune autre" in s


def test_la_DATE_de_mesure_est_toujours_dite():
    """C'est une PHOTO, et elle vieillit. Une carto sans date est inexploitable — le lecteur ne
    peut pas savoir si elle vaut encore."""
    s = pm._section_domaine_mesure(_plan(), _modele())

    assert "2026-07-17" in s


def test_ou_vit_un_onglet_est_dit_explicitement():
    """⚠️ LE fait qui manquait à `0020`. Sans lui, l'agent clique un onglet depuis la page où le
    step d'auth l'a déposé — et l'onglet n'y est pas."""
    modele = _modele(
        pages={"/myservices": {"champs": []}, "/my/home": {"champs": []}},
        onglets={"/myservices": ["Ordinateurs", "Téléphonie"], "/my/home": ["Favoris"]})

    s = pm._section_domaine_mesure(_plan(), modele)

    assert "Ordinateurs" in s
    assert "`/myservices` : Ordinateurs" in s
    assert "il faut d'abord être sur la route qui le porte" in s


def test_les_valeurs_reelles_des_listes_sont_donnees():
    """⚠️ LE fait qui manquait à `0019` : l'agent inventait `"new"`."""
    modele = _modele(pages={"/formulaire/{id}": {"champs": [
        {"name": "types_demandes", "tag": "select",
         "options": [["nouvel_entrant", "Nouvel entrant"], ["remplacement_materiel", "Remp."]]},
    ]}})

    s = pm._section_domaine_mesure(_plan(), modele)

    assert "`nouvel_entrant`" in s and "`remplacement_materiel`" in s
    assert "n'invente jamais une valeur d'option" in s


# ── Le bruit qu'on refuse d'injecter ──────────────────────────────────────────

def test_les_transitions_BRUTES_ne_sont_PAS_injectees():
    """Mesuré : 36 des 38 routes pointent vers `/home`, `/contactus`, `/my/home`… c'est le menu
    global. Les déverser ajouterait des centaines de lignes qui ne discriminent rien et
    diluerait les faits utiles. On ne paie pas un prompt pour du bruit."""
    modele = _modele(
        pages={"/a": {"champs": []}, "/b": {"champs": []}},
        transitions={"/a": ["/home", "/contactus", "/b"], "/b": ["/home", "/contactus"]})

    s = pm._section_domaine_mesure(_plan(), modele)

    assert "/a` → " not in s
    assert "transition" not in s.lower(), "les transitions brutes ne doivent pas être déversées"


def test_un_libelle_UBIQUITAIRE_est_ecarte():
    """`Envoyer` (bouton de soumission) apparaît sur 17 routes sur 37 dans l'annuaire réel : il ne
    dit rien sur OÙ aller. Le garder ajoutait 17 lignes sans information."""
    pages = {f"/f{i}": {"champs": []} for i in range(10)}
    onglets = {f"/f{i}": ["Envoyer"] for i in range(10)}
    onglets["/f0"] = ["Envoyer", "Ordinateurs"]

    s = pm._section_domaine_mesure(_plan(), _modele(pages=pages, onglets=onglets))

    assert "Ordinateurs" in s, "le libellé DISTINCTIF est gardé"
    assert "Envoyer" not in s, "le libellé de gabarit est écarté"


# ── Ce qu'on n'invente jamais ─────────────────────────────────────────────────

def test_sans_annuaire_AUCUNE_section_n_est_produite():
    """Mieux vaut le silence qu'un fait inventé — la règle déjà appliquée aux champs requis."""
    assert pm._section_domaine_mesure(_plan(), None) == ""
    assert pm._section_domaine_mesure(_plan(), _modele(pages={})) == ""


def test_la_section_est_branchee_dans_le_message_initial():
    """Le test qui aurait manqué : la section peut être parfaite et n'être appelée par personne —
    c'est exactement ce qui est arrivé au graphe mesuré pendant trois jours."""
    modele = _modele(pages={"/myservices": {"champs": []}},
                     onglets={"/myservices": ["Ordinateurs"]})

    msg = pm.build_initial_message(_plan(), modele, None)

    assert "MESURÉE" in msg
    assert "Ordinateurs" in msg


def test_la_section_est_presente_AUSSI_avec_un_document_metier():
    """La passe 4b (`0022`) remplace les scénarios déduits par le métier validé — elle ne doit pas
    emporter les faits mesurés au passage. C'est la régression que j'ai commise une fois."""
    modele = _modele(pages={"/myservices": {"champs": []}},
                     onglets={"/myservices": ["Ordinateurs"]})
    metier = {"title": "T", "preconditions": "", "steps": ["E"], "expected_result": "R"}

    msg = pm.build_initial_message(_plan(), modele, metier)

    assert "Ordinateurs" in msg, "les faits mesurés doivent survivre au document métier"
    assert "LE CAS À AUTOMATISER" in msg


# ── Sur l'annuaire RÉEL du dépôt ──────────────────────────────────────────────

def test_sur_l_annuaire_REEL_le_fait_de_0020_est_present():
    """Contre le vrai fichier versionné, pas une fixture : c'est lui que la génération lira."""
    chemin = Path("data/domain/odoo.json")
    if not chemin.exists():
        pytest.skip("annuaire réel absent")
    modele = json.loads(chemin.read_text(encoding="utf-8"))

    s = pm._section_domaine_mesure(_plan(portal_routes=["/myservices"]), modele)

    assert "`/myservices` : Accessoires, Ordinateurs" in s, (
        "le fait qui a coûté le 5e rejeu du cas 1 doit atteindre le prompt")
    assert "Envoyer" not in s, "le gabarit doit rester écarté sur les données réelles"
    # Borne de coût : l'entrée est renvoyée à CHAQUE tour de la boucle ReAct.
    assert len(s) < 5000, f"section trop lourde ({len(s)} car.) — elle est payée à chaque tour"


# ── Modèles back-office (menus, 2026-09-18) — le trou « Parc IT » ─────────────────────────────
#
# Sans cette section, un module purement back-office (mesuré : « Parc IT ») restait invisible
# deux fois : hors périmètre du crawl (`crawl_exclusion_pattern` exclut `/web`/`/odoo`), et son
# nom de modèle technique impossible à deviner sans lui — mesuré : `company_id` au lieu du vrai
# `partner_id`, `equipment_type_id` au lieu du vrai `product_id`.

def test_les_modeles_backoffice_decouverts_sont_donnes():
    modele = _modele()
    modele["modeles_backoffice"] = [
        {"menu": "Générer des équipements", "model": "equipment.order"},
        {"menu": "Affectation d'équipements", "model": "equipment.assignation.order"},
    ]

    s = pm._section_modeles_backoffice(_plan(), modele)

    assert "`equipment.order`" in s and "Générer des équipements" in s
    assert "`equipment.assignation.order`" in s
    assert "inspect_schema" in s


def test_la_DATE_de_mesure_est_dite_aussi_pour_les_modeles_backoffice():
    modele = _modele()
    modele["modeles_backoffice"] = [{"menu": "Équipements", "model": "maintenance.equipment"}]

    s = pm._section_modeles_backoffice(_plan(), modele)

    assert "2026-07-17" in s


def test_sans_modele_backoffice_decouvert_AUCUNE_section_n_est_produite():
    """Mieux vaut le silence qu'un fait inventé — même règle que pour les champs requis."""
    assert pm._section_modeles_backoffice(_plan(), None) == ""
    assert pm._section_modeles_backoffice(_plan(), _modele()) == "", "modeles_backoffice absent"


def test_aucun_modele_n_est_jamais_omis_meme_sans_rapport_apparent():
    """Régression RÉELLE (Sapian, 2026-09-18) : `equipment.order`/`equipment.assignation.order`
    — les deux modèles que ce mécanisme existe pour révéler — n'ont JAMAIS matché le mot-clé du
    module (« Parc IT » ne recoupe pas « équipements » côté texte), et une troncature aux 30
    premiers les a fait disparaître, noyés derrière ~150 menus standard (Comptabilité, Mailing…).
    Une troncature qui peut cacher EXACTEMENT le fait que ce mécanisme sert à révéler est pire
    qu'un prompt plus long : plus AUCUN modèle découvert n'est omis, quel que soit son rang."""
    bruit = [{"menu": f"Menu générique {i}", "model": f"generic.model.{i}"} for i in range(150)]
    modele = _modele()
    modele["modeles_backoffice"] = bruit + [
        {"menu": "Générer des équipements", "model": "equipment.order"}]

    s = pm._section_modeles_backoffice(_plan(module_name="Parc IT"), modele)

    assert "`equipment.order`" in s, "aucun modèle découvert ne doit jamais être omis"
    assert s.count("generic.model") == 150, "le bruit n'est pas omis non plus — juste relégué"


def test_les_correspondances_lexicales_passent_en_tete_pour_la_lisibilite():
    bruit = [{"menu": f"Menu générique {i}", "model": f"generic.model.{i}"} for i in range(5)]
    modele = _modele()
    modele["modeles_backoffice"] = bruit + [
        {"menu": "Générer des équipements", "model": "equipment.order"}]

    s = pm._section_modeles_backoffice(_plan(module_name="équipements"), modele)

    assert s.index("equipment.order") < s.index("generic.model"), (
        "la correspondance lexicale doit apparaître avant le bruit, pas seulement survivre")


def test_la_section_backoffice_est_branchee_dans_le_message_initial():
    modele = _modele()
    modele["modeles_backoffice"] = [{"menu": "Générer des équipements", "model": "equipment.order"}]

    msg = pm.build_initial_message(_plan(), modele, None)

    assert "BACK-OFFICE" in msg
    assert "`equipment.order`" in msg
