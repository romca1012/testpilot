"""Lot 07b-1 (D8) — plusieurs comptes par projet : dépôt, API, transport au runtime, génération, step de connexion.

Les quatre précisions de D8, chacune prouvée ici :
1. le compte déjà configuré sur le projet est le compte « principal » (rien à migrer, libellé réservé) ;
2. l'agent de génération ne voit JAMAIS un secret, seulement les libellés — règle STRUCTURELLE (aucun chemin de code), pas une absence
   d'observation : tests de structure sur les sources + test sur ce que le projet remet à l'agent ;
3. seuls `admin` et `dev` créent ou modifient un compte ;
4. l'API ne renvoie jamais un secret en clair, même à un admin — le mot de passe cherché dans la RÉPONSE BRUTE, pas dans un champ.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.connectors.runtime_env import ENV_COMPTES, env_du_projet, project_env
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CompteInvalide,
    DuplicateName,
    ProjectAccountRepo,
    ProjectRepo,
    UserRepo,
)

RACINE = Path(__file__).resolve().parent.parent
SECRET = "S3cret-Commercial-9f2c"   # jamais affiché : cherché dans les réponses brutes


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "comptes.db")
    yield c
    c.close()


@pytest.fixture
def projet(conn):
    return ProjectRepo(conn).create(name="Portail", connector_type="web", base_url="https://app.example",
                                    username="admin", password="MdpPrincipal-77")


# ── 1. Le dépôt ─────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_un_compte_secondaire_se_cree_se_liste_et_se_supprime(conn, projet):
    repo = ProjectAccountRepo(conn)
    aid = repo.create(projet, label="Commercial", username="banc_commercial", password=SECRET, business_role="Vendeur")

    assert [(c["label"], c["username"], c["business_role"], c["has_secret"]) for c in repo.liste(projet)] == [
        ("Commercial", "banc_commercial", "Vendeur", 1)]
    assert repo.supprimer(projet, aid) is True
    assert repo.liste(projet) == []
    assert repo.supprimer(projet, aid) is False


def test_le_secret_est_chiffre_au_repos(conn, projet):
    ProjectAccountRepo(conn).create(projet, label="Commercial", username="u", password=SECRET)

    brut = conn.execute("SELECT password FROM project_account").fetchone()[0]

    assert brut.startswith("enc:v1:") and SECRET not in brut


@pytest.mark.parametrize("libelle", ["principal", "  Principal ", "PRINCIPAL"])
def test_le_libelle_principal_est_reserve_au_compte_du_projet(conn, projet, libelle):
    with pytest.raises(CompteInvalide, match="réservé"):
        ProjectAccountRepo(conn).create(projet, label=libelle, username="u")


@pytest.mark.parametrize("libelle", ["", "   ", 'Le "chef"', "a\x07b", "x" * 81, "“chef”"])
def test_un_libelle_qui_casserait_le_step_gherkin_est_refuse(conn, projet, libelle):
    """Le libellé s'écrit entre guillemets dans `je me connecte en tant que "<libellé>"` : un guillemet le couperait."""
    with pytest.raises(CompteInvalide):
        ProjectAccountRepo(conn).create(projet, label=libelle, username="u")


def test_les_espaces_et_retours_a_la_ligne_d_un_libelle_sont_normalises(conn, projet):
    aid = ProjectAccountRepo(conn).create(projet, label="  Chef \n  de   vente ", username="u")

    assert ProjectAccountRepo(conn).lire(projet, aid)["label"] == "Chef de vente"


def test_deux_libelles_qui_ne_different_que_par_la_casse_sont_un_doublon(conn, projet):
    repo = ProjectAccountRepo(conn)
    repo.create(projet, label="Responsable", username="a")

    with pytest.raises(DuplicateName):
        repo.create(projet, label="  responsable ", username="b")


def test_un_identifiant_vide_est_refuse(conn, projet):
    with pytest.raises(CompteInvalide, match="identifiant"):
        ProjectAccountRepo(conn).create(projet, label="Commercial", username="  ")


def test_modifier_sans_mot_de_passe_ne_vide_pas_le_secret(conn, projet):
    """L'API ne renvoie jamais le secret : un écran d'édition l'affiche vide — le réenvoyer tel quel ne doit pas l'effacer."""
    repo = ProjectAccountRepo(conn)
    aid = repo.create(projet, label="Commercial", username="u", password=SECRET)

    repo.modifier(projet, aid, label="Vendeur", password=None)
    assert repo.pour_runtime(projet)[0]["password"] == SECRET
    repo.modifier(projet, aid, password="")
    assert repo.pour_runtime(projet)[0]["password"] == ""


def test_falsifiable_un_compte_d_un_autre_projet_n_est_ni_lu_ni_modifie_ni_supprime(conn, projet):
    autre = ProjectRepo(conn).create(name="Autre", connector_type="web", base_url="https://b.example")
    repo = ProjectAccountRepo(conn)
    aid = repo.create(projet, label="Commercial", username="u", password=SECRET)

    assert repo.lire(autre, aid) is None
    assert repo.modifier(autre, aid, username="pirate") is False
    assert repo.supprimer(autre, aid) is False
    assert repo.liste(autre) == []


# ── 2. Ce que l'API et la génération peuvent voir : jamais un secret ────────────────────────────────────────────────────────


@pytest.mark.parametrize("methode", ["liste", "lire", "libelles"])
def test_aucune_methode_de_lecture_du_depot_ne_rend_un_secret(conn, projet, methode):
    repo = ProjectAccountRepo(conn)
    aid = repo.create(projet, label="Commercial", username="banc_commercial", password=SECRET, business_role="Vendeur")

    rendu = getattr(repo, methode)(projet, aid) if methode == "lire" else getattr(repo, methode)(projet)

    texte = json.dumps(rendu, default=str)
    assert SECRET not in texte and "enc:v1:" not in texte and "password" not in texte


def test_le_projet_remis_a_la_generation_porte_les_libelles_et_aucun_identifiant_de_compte_secondaire(conn, projet):
    ProjectAccountRepo(conn).create(projet, label="Commercial", username="banc_commercial", password=SECRET, business_role="Vendeur")

    libelles = ProjectRepo(conn).get(projet)["comptes_libelles"]

    assert libelles == [{"label": "Commercial", "business_role": "Vendeur"}]
    assert "banc_commercial" not in json.dumps(libelles) and SECRET not in json.dumps(libelles)


def test_le_message_de_generation_liste_les_libelles_et_interdit_d_ecrire_un_identifiant():
    from testpilot.generation.prompt import _section_comptes

    section = _section_comptes([{"label": "Commercial", "business_role": "Vendeur"}, {"label": "Responsable", "business_role": ""}])

    assert 'je me connecte en tant que "<libellé>"' in section
    assert "« Commercial » — rôle : Vendeur" in section and "« Responsable »" in section and "« principal »" in section
    assert "JAMAIS d'identifiant ni de mot de passe" in section
    assert _section_comptes([]) == "" and _section_comptes(None) == ""


def _sources(*dossiers) -> list[Path]:
    fichiers: list[Path] = []
    for d in dossiers:
        p = RACINE / d
        fichiers += [p] if p.is_file() else sorted(p.rglob("*.py"))
    return [f for f in fichiers if "__pycache__" not in f.parts and "generated" not in f.parts]


def test_structure_la_generation_n_a_aucun_chemin_vers_un_secret_de_compte():
    """D8, précision 2 : règle STRUCTURELLE. Rien de `src/testpilot/generation/` ne touche `pour_runtime` (seule méthode qui rend un secret),
    ni la table des comptes, ni la variable d'environnement qui les transporte."""
    interdits = ("pour_runtime", "project_account", "ProjectAccountRepo", ENV_COMPTES, "env_du_projet")
    fautifs = [(f.relative_to(RACINE).as_posix(), mot) for f in _sources("src/testpilot/generation")
               for mot in interdits if mot in f.read_text(encoding="utf-8")]
    assert fautifs == []


def test_structure_pour_runtime_n_est_appele_que_par_le_transport_vers_le_runtime():
    autorises = {"src/testpilot/connectors/runtime_env.py", "src/testpilot/api/services/run_service.py",
                 "src/testpilot/store/repositories.py"}
    appelants = {f.relative_to(RACINE).as_posix() for f in _sources("src", "behave_runtime", "scripts")
                 if ".pour_runtime(" in f.read_text(encoding="utf-8")}
    assert appelants <= autorises, f"appelants inattendus de `pour_runtime` : {sorted(appelants - autorises)}"


def test_structure_aucune_route_ne_renvoie_pour_runtime_ni_ne_copie_une_ligne_de_compte_telle_quelle():
    routes = (RACINE / "src/testpilot/api/routes/projects.py").read_text(encoding="utf-8")
    assert "pour_runtime" not in routes
    schemas_src = (RACINE / "src/testpilot/api/schemas.py").read_text(encoding="utf-8")
    m = re.search(r"class AccountOut\(BaseModel\):.*?(?=\nclass |\ndef )", schemas_src, re.S)
    assert m and "password" not in m.group(0).replace("jamais un secret", "")


# ── 3. L'API : droits et absence de secret dans TOUTE réponse ──────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "comptes-api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _user(username: str, role: str) -> int:
    c = get_initialized_db(config.DB_PATH)
    try:
        return UserRepo(c).create(username=username, password_hash=access.hacher_mot_de_passe("mdp"), role=role)
    finally:
        c.close()


def _se_connecter(client, nom):
    assert client.post("/api/auth/login", json={"username": nom, "password": "mdp"}).status_code == 200


@pytest.fixture
def equipe(client):
    """Un projet créé par un admin, avec un `dev`, un `testeur` et un `lecture_seule` MEMBRES du projet."""
    _user("Root", access.ROLE_ADMIN)
    ids = {nom: _user(nom, role) for nom, role in (("Dev", access.ROLE_DEV), ("Testeuse", access.ROLE_TESTEUR),
                                                    ("Lecteur", access.ROLE_LECTURE_SEULE))}
    _se_connecter(client, "Root")
    pid = client.post("/api/projects", json={"name": "Portail", "connector_type": "web", "base_url": "https://app.example",
                                             "username": "admin", "password": "MdpPrincipal-77"}).json()["id"]
    for nom, role in (("Dev", "dev"), ("Testeuse", "testeur"), ("Lecteur", "lecture_seule")):
        assert client.post(f"/api/projects/{pid}/members", json={"user_id": ids[nom], "role": role}).status_code == 201
    return pid


CORPS = {"label": "Commercial", "username": "banc_commercial", "password": SECRET, "business_role": "Vendeur"}


def test_un_admin_cree_un_compte_et_ne_revoit_jamais_le_secret(client, equipe):
    """D8, précision 4 : le mot de passe est cherché dans la RÉPONSE BRUTE de chaque route, admin compris."""
    _se_connecter(client, "Root")

    cree = client.post(f"/api/projects/{equipe}/accounts", json=CORPS)
    assert cree.status_code == 201
    aid = cree.json()["id"]
    reponses = [cree, client.get(f"/api/projects/{equipe}/accounts"),
                client.patch(f"/api/projects/{equipe}/accounts/{aid}", json={"business_role": "Vendeur senior"}),
                client.patch(f"/api/projects/{equipe}/accounts/{aid}", json={"password": SECRET + "-bis"}),
                client.get("/api/projects")]

    for r in reponses:
        assert r.status_code == 200 or r.status_code == 201, r.text
        assert SECRET not in r.text and "MdpPrincipal-77" not in r.text and "enc:v1:" not in r.text, r.request.url
    assert cree.json()["has_secret"] is True and "password" not in cree.json()


def test_la_liste_montre_le_compte_principal_puis_les_secondaires(client, equipe):
    _se_connecter(client, "Root")
    client.post(f"/api/projects/{equipe}/accounts", json=CORPS)

    liste = client.get(f"/api/projects/{equipe}/accounts").json()

    assert [(c["label"], c["principal"], c["username"], c["has_secret"]) for c in liste] == [
        ("principal", True, "admin", True), ("Commercial", False, "banc_commercial", True)]
    assert liste[0]["id"] is None


@pytest.mark.parametrize("nom,attendu", [("Dev", 201), ("Testeuse", 403), ("Lecteur", 403)])
def test_seuls_admin_et_dev_creent_un_compte(client, equipe, nom, attendu):
    _se_connecter(client, nom)

    assert client.post(f"/api/projects/{equipe}/accounts", json=CORPS).status_code == attendu


@pytest.mark.parametrize("nom", ["Testeuse", "Lecteur"])
def test_falsifiable_un_testeur_ou_lecteur_ne_modifie_ni_ne_supprime_un_compte(client, equipe, nom):
    _se_connecter(client, "Root")
    aid = client.post(f"/api/projects/{equipe}/accounts", json=CORPS).json()["id"]
    _se_connecter(client, nom)

    assert client.patch(f"/api/projects/{equipe}/accounts/{aid}", json={"username": "pirate"}).status_code == 403
    assert client.delete(f"/api/projects/{equipe}/accounts/{aid}").status_code == 403
    _se_connecter(client, "Root")
    assert client.get(f"/api/projects/{equipe}/accounts").json()[1]["username"] == "banc_commercial"


def test_un_membre_en_lecture_voit_les_libelles_mais_jamais_un_secret(client, equipe):
    _se_connecter(client, "Root")
    client.post(f"/api/projects/{equipe}/accounts", json=CORPS)
    _se_connecter(client, "Lecteur")

    r = client.get(f"/api/projects/{equipe}/accounts")

    assert r.status_code == 200 and SECRET not in r.text and r.json()[1]["label"] == "Commercial"


def test_l_api_refuse_un_libelle_reserve_ou_en_double_avec_un_message_clair(client, equipe):
    _se_connecter(client, "Root")
    assert client.post(f"/api/projects/{equipe}/accounts", json={**CORPS, "label": "principal"}).status_code == 422
    assert client.post(f"/api/projects/{equipe}/accounts", json=CORPS).status_code == 201
    doublon = client.post(f"/api/projects/{equipe}/accounts", json={**CORPS, "label": "commercial"})
    assert doublon.status_code == 409 and doublon.json()["code"] == "nom_deja_pris"
    assert client.patch(f"/api/projects/{equipe}/accounts/9999", json={"username": "x"}).status_code == 404


# ── 4. Le transport vers le runtime ─────────────────────────────────────────────────────────────────────────────────────────


def test_les_comptes_secondaires_arrivent_au_sous_processus_par_l_environnement(conn, projet):
    ProjectAccountRepo(conn).create(projet, label="Commercial", username="banc_commercial", password=SECRET, business_role="Vendeur")

    env = env_du_projet(conn, ProjectRepo(conn).get(projet))

    assert json.loads(env[ENV_COMPTES]) == [{"label": "Commercial", "username": "banc_commercial", "password": SECRET}]
    assert env["WEB_USER"] == "admin" and env["WEB_PASSWORD"] == "MdpPrincipal-77"   # le principal reste `WEB_*`


def test_sans_compte_secondaire_la_variable_n_est_pas_posee(conn, projet):
    assert ENV_COMPTES not in env_du_projet(conn, ProjectRepo(conn).get(projet))
    assert ENV_COMPTES not in project_env(ProjectRepo(conn).get(projet))


def test_falsifiable_le_secret_est_dechiffre_pour_le_runtime_pas_transmis_chiffre(conn, projet):
    """Un jeton `enc:v1:…` transmis tel quel ferait échouer la connexion avec un « mot de passe invalide » incompréhensible."""
    ProjectAccountRepo(conn).create(projet, label="Commercial", username="u", password=SECRET)

    charge = json.loads(env_du_projet(conn, ProjectRepo(conn).get(projet))[ENV_COMPTES])

    assert charge[0]["password"] == SECRET and "enc:v1:" not in json.dumps(charge)


# ── 5. Le rôle métier ne décide de RIEN (décision 0015) ────────────────────────────────────────────────────────────────────


_JETONS_ROLE_METIER = ("business_role", "role_metier", "comptes_libelles", "project_account", "ProjectAccountRepo")


def _lecteurs_du_role_metier(fichiers) -> list[tuple[str, str]]:
    return [(f.name, j) for f in fichiers for j in _JETONS_ROLE_METIER if j in f.read_text(encoding="utf-8")]


def test_aucun_code_de_verdict_ne_lit_le_role_metier_d_un_compte():
    """`business_role` est un libellé d'affichage saisi par un humain. Il ne doit jamais classer une cause ni décider d'un statut : ni le
    verdict (`verdict/`, qui contient la taxonomie des causes), ni l'exécution (`execution/`), ni le harnais Behave et la bibliothèque de
    steps (`behave_runtime/`), ni les services de run ne le mentionnent. Vérifié à l'introduction du champ (décision 0015)."""
    fichiers = _sources("src/testpilot/verdict", "src/testpilot/execution", "behave_runtime")
    assert len(fichiers) > 20, "le scan doit couvrir de vrais fichiers"
    assert _lecteurs_du_role_metier(fichiers) == []
    # Les services de run TRANSPORTENT les comptes (donc nomment la table) mais ne lisent ni le rôle métier ni les libellés d'affichage.
    services = _sources("src/testpilot/api/services/run_service.py", "src/testpilot/api/services/campaign_service.py")
    assert [(n, j) for n, j in _lecteurs_du_role_metier(services) if j in ("business_role", "role_metier", "comptes_libelles")] == []


def test_le_role_metier_n_est_meme_pas_transmis_au_runtime(conn, projet):
    """Structurel : ce que le sous-processus ne reçoit pas, aucun verdict ne peut le lire."""
    ProjectAccountRepo(conn).create(projet, label="Commercial", username="u", password=SECRET, business_role="Administrateur système")

    env = env_du_projet(conn, ProjectRepo(conn).get(projet))

    assert "business_role" not in env[ENV_COMPTES] and "Administrateur" not in json.dumps(env)
    assert set(ProjectAccountRepo(conn).pour_runtime(projet)[0]) == {"label", "username", "password"}


def test_falsifiable_le_garde_du_role_metier_mord(tmp_path):
    """Le scan ne serait pas une preuve s'il ne voyait rien : une source de verdict qui LIT le champ est trouvée."""
    fautive = tmp_path / "verdict_fautif.py"
    fautive.write_text("def statut(compte):\n    return 'conforme' if compte['business_role'] == 'Admin' else 'non_conforme'\n",
                       encoding="utf-8")
    saine = tmp_path / "verdict_sain.py"
    saine.write_text("def statut(constats):\n    return 'conforme' if constats else 'indetermine'\n", encoding="utf-8")

    assert _lecteurs_du_role_metier([fautive, saine]) == [("verdict_fautif.py", "business_role")]


# ── 6. Le step de connexion (harnais, avec doublures) ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def H():
    chemin = str(RACINE / "behave_runtime" / "steps_library")
    if chemin not in sys.path:
        sys.path.insert(0, chemin)
    import _base_helpers

    return _base_helpers


def _contexte(H, *, connecteur="odoo", journal=None, secondaires=None, echec_rpc=False):
    journal = journal if journal is not None else []
    environ = {"ODOO_USER": "admin", "ODOO_PASSWORD": "pw-admin", "WEB_USER": "admin", "WEB_PASSWORD": "pw-admin",
               ENV_COMPTES: json.dumps(secondaires if secondaires is not None else
                                       [{"label": "Commercial", "username": "banc_commercial", "password": SECRET}])}
    comptes, erreur = H.construire_comptes(connecteur, environ)

    class Odoo:
        def login(self, db, user, password):
            journal.append(("rpc", user, password))
            if echec_rpc:
                raise RuntimeError("Wrong login ID or password")

    page = SimpleNamespace(goto=lambda url, **k: journal.append(("goto", url)))
    ctx = SimpleNamespace(comptes=comptes, comptes_erreur=erreur, compte_courant="principal", odoo=Odoo(), odoo_db="bd",
                          odoo_url="https://odoo.example", odoo_user="admin", odoo_password="pw-admin", page=page,
                          web_url="https://app.example", web_user="admin", web_password="pw-admin",
                          _reouvrir_contexte=lambda: journal.append(("nouveau_contexte",)))
    return ctx, journal


def test_construire_comptes_le_principal_vient_de_la_connexion_du_projet(H):
    comptes, erreur = H.construire_comptes("odoo", {"ODOO_USER": "admin", "ODOO_PASSWORD": "x"})
    assert erreur == "" and comptes == {"principal": {"label": "principal", "user": "admin", "password": "x"}}
    web, _ = H.construire_comptes("web", {"WEB_USER": "w", "WEB_PASSWORD": "y", "ODOO_USER": "pas-lui"})
    assert web["principal"]["user"] == "w"


@pytest.mark.parametrize("brut", ["pas du json", '{"label": "x"}', '[{"label": "A"}]', '[{"label": "principal", "username": "u"}]',
                                  '[{"label": "A", "username": "u"}, {"label": "a", "username": "v"}]'])
def test_construire_comptes_ne_taise_jamais_une_liste_illisible_ni_incoherente(H, brut):
    _, erreur = H.construire_comptes("odoo", {ENV_COMPTES: brut})
    assert erreur, "une liste de comptes illisible doit produire une erreur, pas être ignorée"
    assert "pas du json" not in erreur   # jamais le contenu : il porte des secrets


def test_odoo_le_step_ouvre_un_nouveau_contexte_se_connecte_et_rouvre_la_session_rpc(H, monkeypatch):
    ctx, journal = _contexte(H)
    monkeypatch.setattr(H, "playwright_login",
                        lambda c: journal.append(("ui", c.odoo_user, c.odoo_password)))

    H.se_connecter_en_tant_que(ctx, "  commercial ", connecteur="odoo")

    assert journal == [("nouveau_contexte",), ("ui", "banc_commercial", SECRET), ("rpc", "banc_commercial", SECRET),
                       ("goto", "https://odoo.example")]
    assert ctx.compte_courant == "Commercial" and ctx.odoo_user == "banc_commercial"


def test_falsifiable_un_compte_inconnu_est_un_prerequis_manquant_sans_toucher_au_navigateur(H, monkeypatch):
    ctx, journal = _contexte(H)
    monkeypatch.setattr(H, "playwright_login", lambda c: journal.append(("ui",)))

    with pytest.raises(H.PreconditionNonRemplieError, match=r"« Inconnu ».*comptes connus : principal, Commercial"):
        H.se_connecter_en_tant_que(ctx, "Inconnu", connecteur="odoo")

    assert journal == [], "aucun navigateur rouvert, aucune connexion tentée pour un libellé inexistant"
    assert ctx.compte_courant == "principal"


def test_falsifiable_un_mot_de_passe_refuse_par_le_serveur_bloque_au_lieu_de_juger_l_application(H, monkeypatch):
    ctx, _ = _contexte(H, echec_rpc=True)
    monkeypatch.setattr(H, "playwright_login", lambda c: None)

    with pytest.raises(H.PreconditionNonRemplieError, match="connexion impossible avec le compte « Commercial »") as exc:
        H.se_connecter_en_tant_que(ctx, "Commercial", connecteur="odoo")

    assert SECRET not in str(exc.value), "un message d'erreur ne porte jamais le secret"
    assert ctx.compte_courant == "principal", "le compte courant n'est mémorisé qu'une fois la connexion réussie"


def test_falsifiable_un_compte_sans_mot_de_passe_est_refuse(H):
    ctx, _ = _contexte(H, secondaires=[{"label": "Vide", "username": "u", "password": ""}])
    with pytest.raises(H.PreconditionNonRemplieError, match="pas d'identifiant ou de mot de passe"):
        H.se_connecter_en_tant_que(ctx, "Vide", connecteur="odoo")


def test_falsifiable_une_liste_de_comptes_illisible_bloque_meme_pour_le_principal(H):
    ctx, _ = _contexte(H)
    ctx.comptes_erreur = "la liste des comptes du projet est illisible"
    with pytest.raises(H.PreconditionNonRemplieError, match="illisible"):
        H.se_connecter_en_tant_que(ctx, "principal", connecteur="odoo")


def test_web_le_step_ouvre_l_application_puis_se_connecte_avec_le_compte(H, monkeypatch):
    ctx, journal = _contexte(H, connecteur="web")
    monkeypatch.setattr(H, "connexion_web_utilisateur",
                        lambda c, explicite: journal.append(("connexion", c.web_user, c.web_password, explicite)))

    H.se_connecter_en_tant_que(ctx, "Commercial", connecteur="web")

    assert journal == [("nouveau_contexte",), ("goto", "https://app.example"), ("connexion", "banc_commercial", SECRET, True)]


def test_le_teardown_retablit_la_session_du_compte_principal(H):
    ctx, journal = _contexte(H)
    ctx.compte_courant, ctx.odoo_user = "Commercial", "banc_commercial"

    H.retablir_le_compte_principal(ctx)

    assert journal == [("rpc", "admin", "pw-admin")] and ctx.compte_courant == "principal" and ctx.odoo_user == "admin"


def test_le_teardown_ne_fait_rien_quand_le_compte_principal_est_deja_actif(H):
    ctx, journal = _contexte(H)
    H.retablir_le_compte_principal(ctx)
    assert journal == []


def test_le_step_est_declare_pour_odoo_et_pour_web_seulement():
    """Un step de connexion par connecteur : `generic/` ne doit pas le porter (il n'a pas de session RPC à rouvrir)."""
    def _porte(chemin):
        return 'je me connecte en tant que "{libelle}"' in (RACINE / chemin).read_text(encoding="utf-8")

    assert _porte("behave_runtime/steps_library/odoo/_odoo_steps.py") and _porte("behave_runtime/steps_library/web/_web_steps.py")
    assert not _porte("behave_runtime/steps_library/generic/_generic_steps.py")
