"""Étape E1 (plan, chapitre 9 ; décision A39) — associer d'un clic un test déjà écrit aux données de test du projet.

Ce que ces tests gardent (revues du 2026-10-15 : des faux verts reproduits sur les deux premières versions) :
1. TOUT OU RIEN par variable : une valeur associée ici et laissée en dur là — même autrement écrite (casse, espaces, un de
   ses mots) — n'est jamais possible ;
2. seulement les paramètres qui portent une DONNÉE dans une étape de la bibliothèque, reconnue comme Behave la reconnaît ;
   jamais un nom de champ, une étape écrite à la main, un bloc de texte (délimiteurs mêlés compris), une cellule de tableau
   ou d'exemples ; un nombre seulement s'il est le paramètre entier ;
3. joué avec le jeu « Par défaut », le test associé est EXACTEMENT le test d'origine — sinon rien n'est écrit ;
4. par l'API : le client ne choisit que des identifiants (liés à la valeur) ; nouvelle version À RELIRE ; un testeur associe,
   vérifications comprises (A40) ; un lecteur n'associe rien ; rien n'est écrasé.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.api.services import association_donnees as a
from testpilot.parametres import resolution
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, UserRepo, VersionRepo

MOTIFS = a.motifs_du_catalogue({"connector_type": "web"})
VALEURS = {"client": "Martin SARL", "ville": "Lyon"}
NOMS = ["client", "ville"]


def _feature(*etapes: str) -> str:
    return "\n".join(["# language: fr", "# Commande de Martin SARL", "Fonctionnalité: Commande pour Martin SARL",
                      "  Scénario: Passer une commande à Lyon", *[f"    {e}" for e in etapes], ""])


SAISIE = 'Quand je renseigne le champ "Client" avec la valeur "Martin SARL"'
VERIF = 'Alors la page affiche le texte "Commande de Martin SARL enregistrée"'


def _vu(feature, steps="", valeurs=VALEURS):
    trouve = a.propositions(feature, steps, valeurs, MOTIFS)
    return {p["variable"]: p for p in trouve["propositions"]}, {e["variable"]: e["raison"] for e in trouve["ecartees"]}


# ── 1-2. Ce qui est proposé ───────────────────────────────────────────────────────────────────────────────────────────────


def test_une_variable_est_proposee_avec_toutes_ses_lignes_et_dit_si_elle_touche_une_verification():
    proposees, _ = _vu(_feature(SAISIE, VERIF))

    p = proposees["client"]
    assert [l["ligne"] for l in p["lignes"]] == [5, 6] and p["verification"] is True
    assert p["lignes"][0]["apres"] == 'Quand je renseigne le champ "Client" avec la valeur "{{client}}"'
    assert p["lignes"][1]["apres"] == 'Alors la page affiche le texte "Commande de {{client}} enregistrée"'
    assert _vu(_feature(SAISIE))[0]["client"]["verification"] is False


def test_falsifiable_tout_ou_rien_une_valeur_ecrite_aussi_dans_un_bloc_de_texte_n_est_pas_proposee():
    """Faux vert reproduit : le bloc gardait « Martin SARL », le « n'affiche pas » passait à {{client}} — avec un autre jeu,
    le test vérifiait l'absence d'un client jamais touché."""
    feature = _feature("Quand je renseigne le champ \"Commentaire\" avec la valeur \"x\"", '  """', "  Martin SARL", '  """',
                       'Alors la page n\'affiche pas le texte "Martin SARL"')

    proposees, ecartees = _vu(feature)

    assert "client" not in proposees and "client" in ecartees


@pytest.mark.parametrize("etape", [
    'Quand je renseigne le champ "Martin SARL" avec la valeur "x"',      # un nom de champ, pas une valeur
    'Quand je fais quelque chose avec "Martin SARL"',                      # une étape écrite à la main : nature inconnue
    'Quand je clique sur "Martin SARL" dans la ligne contenant "x"',     # un libellé à cliquer
])
def test_falsifiable_une_valeur_ailleurs_que_dans_un_parametre_de_valeur_ecarte_la_variable(etape):
    proposees, ecartees = _vu(_feature(SAISIE, etape))

    assert "client" not in proposees and "client" in ecartees


@pytest.mark.parametrize("etape, proposee", [
    ('Quand je renseigne le champ "Quantité" avec la valeur "1"', True),       # le paramètre entier
    ('Alors la page affiche le texte "Commande 1"', False),                     # un morceau : « 1 » de quoi ?
    ('Alors la page affiche le texte "#ligne-1"', False),
])
def test_falsifiable_un_nombre_n_est_remplace_que_s_il_est_le_parametre_entier(etape, proposee):
    proposees, _ = _vu(_feature(etape), valeurs={"quantite": "1"})

    assert ("quantite" in proposees) is proposee


def test_les_titres_et_commentaires_ne_comptent_pas_et_ne_changent_pas():
    proposees, _ = _vu(_feature(SAISIE))

    assert [l["ligne"] for l in proposees["client"]["lignes"]] == [5], "le commentaire et les titres restent tels quels"


@pytest.mark.parametrize("etape, tableau", [
    ("Et le tableau contient :", ["| client | ville |", "| Martin SARL | Lyon |"]),          # étape écrite à la main
    ("Alors le tableau affiche :", ["| nom |", "| Martin SARL |"]),                          # une vérification déguisée
    ('Et j\'ajoute une ligne à "Lignes" avec :', ["| champ | valeur |", "| Martin SARL | 10 |"]),  # un nom de champ
])
def test_falsifiable_une_valeur_dans_un_tableau_ecarte_la_variable(etape, tableau):
    """Une colonne peut porter un nom de champ : avec un autre jeu, le test remplirait un autre champ (revue, reproduit)."""
    proposees, ecartees = _vu(_feature(SAISIE, etape, *[f"  {l}" for l in tableau]))

    assert "client" not in proposees and "client" in ecartees


def test_falsifiable_une_valeur_dans_les_exemples_d_un_plan_de_scenario_ecarte_la_variable():
    """Reproduit : la cellule alimentait un « Alors » via <attendu> ; une testeuse l'associait, puis changeait l'attendu par la
    valeur du jeu, sans le rôle dev."""
    feature = "\n".join(["# language: fr", "Fonctionnalité: F", "  Plan du Scénario: P", f"    {SAISIE}",
                         '    Alors la page affiche le texte "<attendu>"', "    Exemples:", "      | attendu |",
                         "      | Martin SARL |", ""])

    proposees, ecartees = _vu(feature)

    assert "client" not in proposees and "client" in ecartees


@pytest.mark.parametrize("verif", [
    'Alors la page n\'affiche pas le texte "Martin"',          # un de ses mots
    'Alors la page affiche le texte "MARTIN SARL"',            # une autre casse
    'Alors la page affiche le texte "Martin  SARL"',           # deux espaces
    'Alors la page affiche le texte "Martin SARLU"',           # un morceau
    'Alors la page n\'affiche pas le texte "SARL"',            # un sigle
])
def test_falsifiable_une_valeur_reprise_sous_une_autre_forme_ecarte_la_variable(verif):
    """Reproduit : la variable était proposée SANS vérification (le « Alors » restait en dur) — avec le jeu « Dupont SA », le
    test supprimait Dupont SA puis constatait l'absence de « Martin » : vert même si la suppression avait échoué."""
    feature = _feature(SAISIE, 'Et je clique sur "Supprimer" dans la ligne contenant "Martin SARL"', verif)

    proposees, ecartees = _vu(feature)

    assert "client" not in proposees and ecartees["client"] == "écrite aussi sous une autre forme"


@pytest.mark.parametrize("valeur, verif", [
    ("BNP Paribas", 'Alors la page n\'affiche pas le texte "BNP"'),      # un mot court (revue, 3e passe, reproduit)
    ("Le Bon Coin", 'Alors la page n\'affiche pas le texte "Le Bon"'),
    ("Dupont SA", 'Alors la page n\'affiche pas le texte "SA"'),         # un sigle de deux lettres
    ("Martinez", 'Alors la page n\'affiche pas le texte "Martin"'),      # une troncature (revue, 4e passe)
])
def test_falsifiable_un_morceau_fait_de_mots_courts_ecarte_la_variable(valeur, verif):
    feature = _feature(f'Quand je renseigne le champ "Nom" avec la valeur "{valeur}"', verif)

    proposees, ecartees = _vu(feature, valeurs={"client": valeur})

    assert "client" not in proposees and ecartees["client"] == "écrite aussi sous une autre forme"


@pytest.mark.parametrize("valeur, ecrit", [
    ("1234.50", "1 234,50 €"), ("1234.50", "1234,5"), ("1234.50", "1'234.50"),
    ("1234.50 EUR", "1 234,50 €"),                    # la valeur porte son unité (A24) — revue, 4e passe, reproduit
])
def test_falsifiable_le_meme_nombre_autrement_ecrit_ecarte_la_variable(valeur, ecrit):
    """Une étape qui compare des NOMBRES lirait « 1 234,50 € » comme 1234.50 : laissé en dur, avec un autre jeu, l'attendu ne
    suivrait pas la valeur saisie (revue, 3e passe, reproduit)."""
    feature = _feature(f'Quand je renseigne le champ "Montant" avec la valeur "{valeur}"',
                       f'Alors le nombre affiché pour "Total" vaut "{ecrit}"')

    proposees, ecartees = _vu(feature, valeurs={"montant": valeur})

    assert "montant" not in proposees and "montant" in ecartees


def test_deux_valeurs_qui_se_chevauchent_ne_sont_pas_proposees_ensemble():
    feature = _feature('Quand je renseigne le champ "Nom" avec la valeur "Martin SARL Lyon"')

    proposees, ecartees = _vu(feature, valeurs={"client": "Martin SARL", "agence": "SARL Lyon"})

    assert set(proposees) == {"client"} and "chevauche" in ecartees["agence"]


def test_une_valeur_contenue_dans_une_autre_reste_proposee_si_l_autre_n_est_pas_dans_le_test():
    proposees, _ = _vu(_feature('Quand je renseigne le champ "Prénom" avec la valeur "Martin"'),
                       valeurs={"client": "Martin SARL", "prenom": "Martin"})

    assert set(proposees) == {"prenom"}


def test_falsifiable_un_bloc_ouvert_par_un_delimiteur_n_est_ferme_que_par_le_meme():
    """Reproduit : un « ``` » dans un bloc « \"\"\" » fermait le bloc pour l'analyseur, pas pour Behave."""
    feature = _feature('Quand je renseigne le champ "Message" avec la valeur "x"', '  """', "  ```", "  Bonjour Martin SARL",
                       "  ```", '  """', 'Alors la page n\'affiche pas le texte "Martin SARL"')

    proposees, ecartees = _vu(feature)

    assert "client" not in proposees and "client" in ecartees


def test_falsifiable_deux_valeurs_incluses_l_une_dans_l_autre_ne_sont_jamais_proposees_ensemble():
    proposees, ecartees = _vu(_feature(SAISIE), valeurs={"client": "Martin SARL", "prenom": "Martin"})

    assert set(proposees) == {"client"} and "prenom" in ecartees


@pytest.mark.parametrize("etapes, verification", [
    ([SAISIE, 'Et la page affiche le texte "Martin SARL"'], False),          # « Et » après un « Quand » : pas reconnu
    (['Alors la page affiche le texte "Bienvenue"', 'Et la page affiche le texte "Martin SARL"'], True),
    (['Alors la page affiche le texte "Bienvenue"', 'Mais la page n\'affiche pas le texte "Martin SARL"'], True),
])
def test_falsifiable_et_ou_mais_heritent_du_type_de_l_etape_precedente(etapes, verification):
    """Comme Behave : une étape « Alors » ne se trouve qu'après un « Alors » (ou en « Et » qui en hérite)."""
    proposees, _ = _vu(_feature(*etapes))

    assert ("client" in proposees) is verification
    if verification:
        assert proposees["client"]["verification"] is True


@pytest.mark.parametrize("etape, reconnue", [
    ('Quand je renseigne le champ "Client" avec la valeur "Martin SARL"', True),
    ('Quand je renseigne le champ "Client" avec la valeur "Martin SARL"'.replace("é", "e"), True),   # sans accents
    ('Quand Je renseigne le champ "Client" avec la valeur "Martin SARL"', False),                     # casse : Behave non plus
])
def test_une_etape_est_reconnue_comme_le_moteur_du_runtime_la_reconnait(etape, reconnue):
    assert ("client" in _vu(_feature(etape))[0]) is reconnue


def test_le_pliage_des_accents_est_celui_du_moteur_du_runtime():
    from behave_runtime.steps_library import _accent_matcher

    assert a.PLIAGE == _accent_matcher._FOLD


def test_la_liste_des_etapes_qui_portent_une_donnee_est_tenue_a_jour_avec_la_bibliothèque():
    """Une étape nouvelle dont un paramètre ressemble à une valeur doit être CLASSÉE (ajoutée ici ou dans la liste du service)
    au lieu d'entrer d'office ; une étape retirée ne reste pas dans la liste."""
    import parse

    from testpilot.generation import steps_library

    exclus = {('l\'état technique de ce document est "{valeur}"', "valeur"),          # un code technique (« posted »)
              ('le document lié "{modele}" est à l\'état "{valeur}"', "valeur"),
              ('le champ "{champ}" de ce document vaut {nombre:g}', "nombre")}   # hors guillemets : pas de variable
    candidats = set()
    for connecteur in ("web", "odoo", None):
        for s in steps_library.catalogue(connector_type=connecteur):
            for nom in parse.compile(s.label).named_fields:
                if nom in {"value", "valeur", "texte", "text", "partial", "a", "b", "expected", "attendu", "nombre"}:
                    candidats.add((s.label, nom))

    assert candidats - exclus == a.VALEURS_D_ETAPES


def test_falsifiable_une_valeur_partagee_ou_ecrite_dans_le_code_n_est_pas_proposee():
    _, partagee = _vu(_feature(SAISIE), valeurs={**VALEURS, "ville_livraison": "Martin SARL"})
    proposees, dans_le_code = _vu(_feature(SAISIE), steps='constater("Martin SARL" in texte, "x")')

    assert set(partagee) >= {"client", "ville_livraison"}
    assert "client" not in proposees and dans_le_code["client"] == "aussi écrite dans le code des étapes"


@pytest.mark.parametrize("code, proposee", [
    ('nom = "Martin " + "SARL"', False),            # découpée dans deux chaînes
    ("assert 'martin sarl' in page.lower()", False),  # autre casse
    ("import martin\nfrom sarl import x", True),      # des instructions, pas une valeur
    ('ATTENDU = """\nBienvenue Martin\n"""', False),  # une chaîne sur plusieurs lignes (revue, 3e passe)
    ('texte = f"Bonjour {nom} Martin"', False),       # une f-string
])
def test_falsifiable_le_code_des_etapes_est_lu_sous_toutes_ses_formes_mais_seulement_dans_ses_chaines(code, proposee):
    assert ("client" in _vu(_feature(SAISIE), steps=code)[0]) is proposee


# ── 3. Appliquer ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_le_test_associe_rejoue_exactement_le_test_d_origine_sans_aucune_valeur_en_dur():
    feature = _feature(SAISIE, 'Et je renseigne le champ "Ville" avec la valeur "Lyon"', VERIF)
    proposees, _ = _vu(feature)

    associe, retenues = a.appliquer(feature, "", VALEURS, NOMS, MOTIFS, [proposees["client"]["id"]])

    assert [p["variable"] for p in retenues] == ["client"]
    executables = associe.split("\n")[4:]
    assert not any("Martin SARL" in l for l in executables), "tout ou rien"
    assert '"Lyon"' in associe, "une variable non choisie ne bouge pas"
    poses = {n: resolution.Valeur(v, "") for n, v in VALEURS.items()}
    assert resolution.remplacer(associe, poses, NOMS).texte == feature


def test_un_test_qui_ecrit_deja_une_variable_peut_etre_associe_davantage():
    feature = _feature('Quand je renseigne le champ "Ville" avec la valeur "{{ville}}"', SAISIE)
    proposees, _ = _vu(feature)

    associe, _ = a.appliquer(feature, "", VALEURS, NOMS, MOTIFS, [proposees["client"]["id"]])

    assert '"{{ville}}"' in associe and '"{{client}}"' in associe


def test_un_test_qui_ecrit_une_variable_sans_valeur_par_defaut_peut_etre_associe_et_la_garde():
    """Reproduit : proposé, puis toujours refusé (« ne rejouerait pas exactement »). La variable sans valeur reste écrite ; elle
    bloquera le lancement comme avant — rien d'autre ne change."""
    feature = _feature('Quand je renseigne le champ "Pays" avec la valeur "{{pays}}"', SAISIE)
    identifiant = _vu(feature)[0]["client"]["id"]

    associe, _ = a.appliquer(feature, "", VALEURS, [*NOMS, "pays"], MOTIFS, [identifiant])

    assert '"{{pays}}"' in associe and '"{{client}}"' in associe


def test_falsifiable_un_resultat_qui_ne_rejoue_pas_l_origine_n_est_jamais_ecrit(monkeypatch):
    feature = _feature(SAISIE)
    identifiant = _vu(feature)[0]["client"]["id"]
    monkeypatch.setattr(a, "_poser", lambda texte, places, nom: texte.replace("Martin SARL", "{{client}} !"))

    with pytest.raises(a.AssociationImpossible):
        a.appliquer(feature, "", VALEURS, NOMS, MOTIFS, [identifiant])


def test_falsifiable_un_identifiant_lie_a_une_ancienne_valeur_est_refuse():
    """La valeur « Par défaut » a changé entre l'affichage et le clic : le choix portait sur l'ancienne."""
    feature = _feature(SAISIE, 'Et je renseigne le champ "Nom" avec la valeur "Dupont SA"')
    ancien = _vu(feature)[0]["client"]["id"]

    with pytest.raises(a.AssociationImpossible):
        a.appliquer(feature, "", {**VALEURS, "client": "Dupont SA"}, NOMS, MOTIFS, [ancien])


@pytest.mark.parametrize("choix", [[], ["client:0000000000"]])
def test_un_choix_qui_n_est_pas_une_proposition_est_refuse(choix):
    with pytest.raises(a.AssociationImpossible):
        a.appliquer(_feature(SAISIE), "", VALEURS, NOMS, MOTIFS, choix)


# ── 3 bis. Le texte du cas aussi (décision A41) ────────────────────────────────────────────────────────────────────────

METIER = {"preconditions": "Le client Martin SARL existe", "steps": ["Ouvrir les commandes", "Choisir Martin SARL",
                                                                     "Saisir 1 article"],
          "expected_result": "La commande de Martin SARL est enregistrée"}


def test_la_proposition_montre_aussi_le_texte_du_cas_qui_change():
    p = a.propositions(_feature(SAISIE), "", VALEURS, MOTIFS, METIER)["propositions"][0]

    assert [l["champ"] for l in p["lignes_du_cas"]] == ["Préconditions", "Étape 2", "Résultat attendu"]
    assert p["lignes_du_cas"][1]["apres"] == "Choisir {{client}}"


def test_le_texte_du_cas_associe_cite_la_variable_et_garde_le_reste():
    retenues = a.propositions(_feature(SAISIE), "", VALEURS, MOTIFS, METIER)["propositions"]

    nouveau = a.cas_associe(METIER, retenues, VALEURS)

    assert nouveau["steps"] == ["Ouvrir les commandes", "Choisir {{client}}", "Saisir 1 article"]
    assert nouveau["preconditions"] == "Le client {{client}} existe"
    assert nouveau["expected_result"] == "La commande de {{client}} est enregistrée"
    assert METIER["steps"][1] == "Choisir Martin SARL", "l'original n'est pas modifié"


def test_une_valeur_courte_ou_absente_du_cas_ne_le_change_pas():
    """« 1 » dans « Saisir 1 article » n'est pas touché (A41 : la régénération garde alors les variables du test)."""
    feature = _feature('Quand je renseigne le champ "Quantité" avec la valeur "1"')
    retenues = a.propositions(feature, "", {"quantite": "1"}, MOTIFS, METIER)["propositions"]

    assert retenues and retenues[0]["lignes_du_cas"] == []
    assert a.cas_associe(METIER, retenues) is None


@pytest.mark.parametrize("test_steps", ["Ouvrir les commandes\nChoisir Martin SARL", "", '[{"action": "Martin SARL"}]'])
def test_falsifiable_des_etapes_illisibles_ne_sont_jamais_reecrites(test_steps):
    """Revue A41, reproduit : des étapes en texte simple (l'écran les découpe par lignes) devenaient « [] » dès que la valeur
    était dans le résultat attendu — le cas perdait toutes ses étapes."""
    metier = a.metier_de_la_version({"test_steps": test_steps, "expected_result": "Commande de Martin SARL"})
    retenues = a.propositions(_feature(SAISIE), "", VALEURS, MOTIFS, metier)["propositions"]

    assert a.cas_associe(metier, retenues, VALEURS) == {"expected_result": "Commande de {{client}}"}


def test_falsifiable_une_valeur_dans_celle_d_une_autre_variable_n_est_pas_remplacee_dans_le_cas():
    """Revue A41, reproduit : « Choisir Martin SARL » devenait « Choisir {{prenom}} SARL »."""
    valeurs = {"prenom": "Martin", "client": "Martin SARL"}
    metier = {**METIER, "steps": ["Choisir Martin SARL", "Saluer Martin"]}
    retenues = a.propositions(_feature('Quand je renseigne le champ "Prénom" avec la valeur "Martin"'), "", valeurs, MOTIFS,
                              metier)["propositions"]

    assert a.cas_associe(metier, retenues, valeurs)["steps"] == ["Choisir Martin SARL", "Saluer {{prenom}}"]


def test_falsifiable_un_nombre_n_est_pas_remplace_dans_le_cas():
    """Revue A41, reproduit : « Saisir 100 articles à 100 EUR » — la quantité ou le prix ? Jamais deviné."""
    metier = {**METIER, "steps": ["Saisir 100 articles à 100 EUR"]}
    feature = _feature('Quand je renseigne le champ "Quantité" avec la valeur "100"')
    retenues = a.propositions(feature, "", {"quantite": "100"}, MOTIFS, metier)["propositions"]

    assert retenues and a.cas_associe(metier, retenues, {"quantite": "100"}) is None


def test_une_proposition_non_choisie_laisse_le_cas_intact():
    feature = _feature(SAISIE, 'Et je renseigne le champ "Ville" avec la valeur "Lyon"')
    metier = {**METIER, "steps": ["Choisir Martin SARL", "Livrer à Lyon"]}
    propositions = {p["variable"]: p for p in a.propositions(feature, "", VALEURS, MOTIFS, metier)["propositions"]}

    assert a.cas_associe(metier, [propositions["ville"]], VALEURS) == {"steps": ["Choisir Martin SARL", "Livrer à {{ville}}"]}


# ── 4. Par l'API ──────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _se_connecter(client, nom):
    assert client.post("/api/auth/login", json={"username": nom, "password": "mdp"}).status_code == 200


def _cas(client, feature: str, metier: dict | None = None):
    """Projet (créé par l'administrateur), dev, testeuse, lecteur ; `client` = Martin SARL, `ville` = Lyon ; un cas."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        ids = {nom: UserRepo(conn).create(username=nom, password_hash=access.hacher_mot_de_passe("mdp"), role=role)
               for nom, role in (("Root", access.ROLE_ADMIN), ("Dev", access.ROLE_DEV), ("Testeuse", access.ROLE_TESTEUR),
                                 ("Lecteur", access.ROLE_LECTURE_SEULE))}
    finally:
        conn.close()
    _se_connecter(client, "Root")
    pid = client.post("/api/projects", json={"name": "Boutique", "connector_type": "web", "base_url": "https://a.test",
                                              "username": "u", "password": "p"}).json()["id"]
    for nom, role in (("Dev", "dev"), ("Testeuse", "testeur"), ("Lecteur", "lecture_seule")):
        client.post(f"/api/projects/{pid}/members", json={"user_id": ids[nom], "role": role})
    base = f"/api/projects/{pid}/donnees-de-test"
    for nom in NOMS:
        client.post(f"{base}/variables", json={"nom": nom})
    tableau = client.get(base).json()
    client.put(f"{base}/jeux/{tableau['jeux'][0]['id']}/valeurs",
               json={"valeurs": {str(v["id"]): VALEURS[v["nom"]] for v in tableau["variables"]}})
    conn = get_initialized_db(config.DB_PATH)
    try:
        cid = CaseRepo(conn).create(title="Commande", module_id=ModuleRepo(conn).create(project_id=pid, name="Ventes"),
                                    feature_slug="commande")
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature,
                                       steps_content="# steps\n", **(metier or {}))
        CaseRepo(conn).set_current_version(cid, vid)
        conn.commit()
    finally:
        conn.close()
    return cid, vid


def _proposition(client, cid, variable):
    vu = client.get(f"/api/cases/{cid}/associations").json()
    return vu["version_id"], next(p for p in vu["propositions"] if p["variable"] == variable)


def test_falsifiable_une_testeuse_associe_une_action_et_la_nouvelle_version_est_a_relire(client):
    cid, vid = _cas(client, _feature(SAISIE, 'Et je renseigne le champ "Ville" avec la valeur "Lyon"'))
    _se_connecter(client, "Testeuse")
    version, p = _proposition(client, cid, "client")

    r = client.post(f"/api/cases/{cid}/associations", json={"version_id": version, "choix": [p["id"]]})

    assert r.status_code == 200, r.text
    detail = client.get(f"/api/cases/{cid}").json()
    nouvelle = next(v for v in detail["versions"] if v["id"] == detail["current_version_id"])
    assert detail["current_version_id"] != vid and '"{{client}}"' in nouvelle["feature_content"]
    assert nouvelle["steps_content"] == "# steps\n", "le code des étapes n'est jamais touché"
    assert detail["gate"]["allowed"] is False, "à relire avant toute exécution, comme toute modification"
    assert "Association aux données de test" in (nouvelle.get("change_summary") or "")


def test_une_testeuse_associe_aussi_une_verification_et_la_nouvelle_version_est_a_relire(client):
    """Décision A40 (porteur, 2026-10-15) : ouvert à tous, sans condition de rôle ; la relecture reste obligatoire."""
    cid, vid = _cas(client, _feature(SAISIE, VERIF))
    _se_connecter(client, "Testeuse")
    version, p = _proposition(client, cid, "client")
    assert p["verification"] is True

    r = client.post(f"/api/cases/{cid}/associations", json={"version_id": version, "choix": [p["id"]]})

    assert r.status_code == 200, r.text
    detail = client.get(f"/api/cases/{cid}").json()
    assert detail["current_version_id"] != vid and detail["gate"]["allowed"] is False


def test_l_association_change_le_test_et_le_texte_du_cas_dans_la_meme_version(client):
    import json

    cid, vid = _cas(client, _feature(SAISIE), {"preconditions": "Rien", "expected_result": "Commande de Martin SARL",
                                               "test_steps": json.dumps(["Choisir Martin SARL"], ensure_ascii=False)})
    version, p = _proposition(client, cid, "client")
    assert p["lignes_du_cas"][0]["champ"] == "Étape 1"

    assert client.post(f"/api/cases/{cid}/associations", json={"version_id": version, "choix": [p["id"]]}).status_code == 200

    detail = client.get(f"/api/cases/{cid}").json()
    nouvelle = next(v for v in detail["versions"] if v["id"] == detail["current_version_id"])
    assert json.loads(nouvelle["test_steps"]) == ["Choisir {{client}}"]
    assert nouvelle["expected_result"] == "Commande de {{client}}" and nouvelle["preconditions"] == "Rien"
    assert '"{{client}}"' in nouvelle["feature_content"]


def test_falsifiable_des_etapes_en_texte_simple_sont_recopiees_a_l_identique(client):
    """Revue A41 : de bout en bout — la nouvelle version garde ses étapes telles quelles, seul le résultat attendu change."""
    etapes = "Ouvrir les commandes\nChoisir Martin SARL"
    cid, _ = _cas(client, _feature(SAISIE), {"expected_result": "Commande de Martin SARL", "test_steps": etapes})
    version, p = _proposition(client, cid, "client")

    assert client.post(f"/api/cases/{cid}/associations", json={"version_id": version, "choix": [p["id"]]}).status_code == 200

    detail = client.get(f"/api/cases/{cid}").json()
    nouvelle = next(v for v in detail["versions"] if v["id"] == detail["current_version_id"])
    assert nouvelle["test_steps"] == etapes and nouvelle["expected_result"] == "Commande de {{client}}"


def test_falsifiable_un_lecteur_ne_peut_pas_associer(client):
    cid, vid = _cas(client, _feature(SAISIE))
    _se_connecter(client, "Lecteur")
    version, p = _proposition(client, cid, "client")

    assert client.post(f"/api/cases/{cid}/associations", json={"version_id": version, "choix": [p["id"]]}).status_code == 403


def test_falsifiable_un_test_modifie_entre_temps_n_est_pas_ecrase(client):
    cid, vid = _cas(client, _feature(SAISIE))
    _, p = _proposition(client, cid, "client")

    r = client.post(f"/api/cases/{cid}/associations", json={"version_id": vid + 1000, "choix": [p["id"]]})

    assert r.status_code == 409 and client.get(f"/api/cases/{cid}").json()["current_version_id"] == vid
