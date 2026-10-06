"""Import Excel de bout en bout (preview puis confirm), via l'API réelle — même patron que
`test_import_specification_pdf.py` pour l'extraction de spécification.

⚠️ **La garde la plus importante de ce fichier** : un cas importé avec un Statut « Passed » doit
porter un résultat DÉCLARÉ (`last_statut_manuel`), jamais un verdict automatique
(`last_execution_status`/`last_functional_status` doivent rester vides) — c'est l'unique risque
réel de ce lot (§4 CLAUDE.md, faux PASSED), testé explicitement ci-dessous.
"""

from __future__ import annotations

import io

import openpyxl
import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    return TestClient(app_mod.app)


def _module(client) -> int:
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    return client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]


def _classeur(lignes: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Test Cases"
    ws.append(["Test Case ID", "Description", "Étapes du Test", "Résultat Attendu", "User Story",
              "Priorité", "Statut", "Testeur", "Date", "Type", "Commentaires"])
    for ligne in lignes:
        ws.append(ligne)
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


_CLASSEUR_SIMPLE = _classeur([
    ["TC-1", "Connexion valide", "1. Ouvrir /login\n2. Se connecter", "Accès au tableau de bord.",
     "AUTH", "P1 - Critique", "Passed"],
    ["TC-2", "Connexion invalide", "1. Ouvrir /login\n2. Mauvais mot de passe",
     "Message d'erreur affiché.", "AUTH", "P2 - Majeur", "Failed"],
])


def test_preview_ne_cree_rien_en_base(client):
    """L'aperçu seul ne doit écrire AUCUN cas — c'est tout le sens de l'écran de confirmation."""
    mid = _module(client)

    r = client.post(f"/api/modules/{mid}/cases/import-excel/preview",
                    files={"file": ("cahier.xlsx", io.BytesIO(_CLASSEUR_SIMPLE),
                                    "application/vnd.openxmlformats-officedocument"
                                    ".spreadsheetml.sheet")})

    assert r.status_code == 200
    body = r.json()
    assert body["feuille"] == "Test Cases"
    assert len(body["lignes"]) == 2
    assert body["lignes"][0]["titre"] == "Connexion valide"
    assert body["lignes"][0]["statut_manuel"] == "passed"

    pid = client.get(f"/api/modules/{mid}").json()["project"]["id"]
    cas = client.get(f"/api/cases?project_id={pid}").json()["items"]
    assert cas == [] or all(c.get("module_id") != mid for c in cas)


def test_confirm_cree_les_cas_et_le_resultat_declare_sans_toucher_au_verdict_automatique(client):
    """LE test qui compte le plus dans ce lot (§4 CLAUDE.md) : un statut Excel importé doit
    apparaître comme résultat MANUEL, et jamais comme si TestPilot avait lui-même exécuté quoi que
    ce soit."""
    mid = _module(client)
    preview = client.post(
        f"/api/modules/{mid}/cases/import-excel/preview",
        files={"file": ("cahier.xlsx", io.BytesIO(_CLASSEUR_SIMPLE),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    ).json()

    r = client.post(f"/api/modules/{mid}/cases/import-excel/confirm", json={
        "fichier_hash": preview["fichier_hash"], "feuille": preview["feuille"],
        "ligne_entete": preview["ligne_entete"], "mapping": preview["mapping"],
        "numeros_lignes_retenues": [l["numero_ligne"] for l in preview["lignes"]],
    })

    assert r.status_code == 200
    resume = r.json()
    assert resume["cree"] == 2
    assert resume["ignore"] == 0
    assert resume["run_id"] is not None  # les 2 lignes ont un statut reconnu

    pid = client.get(f"/api/modules/{mid}").json()["project"]["id"]
    cas = client.get(f"/api/cases?project_id={pid}").json()["items"]
    assert len(cas) == 2

    cas_passed = next(c for c in cas if c["title"] == "Connexion valide")
    # ⚠️ `cas_passed["statut"]` n'est PAS vérifié ici : `case_summary()` (schemas.py) appelle
    # `statut_de_test(execution, functional)` sans le 3e argument `manuel` — un bug PRÉ-EXISTANT,
    # hors périmètre de ce lot, qui fait que la liste des cas n'affiche jamais un statut déclaré
    # (manuel), quelle que soit sa source. Signalé séparément. La garde qui nous concerne ici est
    # vérifiée au niveau base, puisque `CaseSummary` n'expose pas `last_statut_manuel`/`origin`.
    conn = get_initialized_db(config.DB_PATH)
    try:
        ligne_db = CaseRepo(conn).get(cas_passed["id"])
        assert ligne_db["last_statut_manuel"] == "passed"
        assert ligne_db["last_execution_status"] is None
        assert ligne_db["last_functional_status"] is None
        assert ligne_db["origin"] == "manual_converted"
        assert ligne_db["etat"] == "new"  # pas de Gherkin : génération normale à suivre
        assert ligne_db["priority"] == "high"  # "P1 - Critique" dans le fichier
        # L'identifiant du cahier d'origine n'est pas perdu : il sert à rapprocher le cas
        # TestPilot de sa ligne Excel (champ « Références », comme TestRail).
        assert ligne_db["refs"] == "TC-1"

        cas_failed = next(c for c in cas if c["title"] == "Connexion invalide")
        ligne_db_failed = CaseRepo(conn).get(cas_failed["id"])
        assert ligne_db_failed["priority"] == "medium"  # "P2 - Majeur" dans le fichier
    finally:
        conn.close()


def test_testeur_date_commentaires_et_type_ne_sont_jamais_perdus_sans_statut_reconnu(client):
    """Relu en revue (`verdict-reviewer`) : avant ce correctif, une ligne SANS statut reconnu
    perdait silencieusement testeur/date/commentaires (repliés uniquement dans le commentaire du
    résultat manuel, donc jamais écrits s'il n'y avait pas de résultat) et `type` (aucun paramètre
    de création ne l'acceptait). Les deux sont maintenant conservés sur le cas lui-même."""
    mid = _module(client)
    classeur = _classeur([
        ["TC-3", "Export PDF", "1. Exporter", "Le PDF est généré.", "EXPORT", "P2 - Majeur", "",
         "Alice", "01/09/2026", "Fonctionnel", "Voir US-123"],
    ])
    preview = client.post(
        f"/api/modules/{mid}/cases/import-excel/preview",
        files={"file": ("cahier.xlsx", io.BytesIO(classeur),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    ).json()
    assert preview["lignes"][0]["statut_manuel"] is None  # pas de Statut dans ce fichier

    r = client.post(f"/api/modules/{mid}/cases/import-excel/confirm", json={
        "fichier_hash": preview["fichier_hash"], "feuille": preview["feuille"],
        "ligne_entete": preview["ligne_entete"], "mapping": preview["mapping"],
        "numeros_lignes_retenues": [preview["lignes"][0]["numero_ligne"]],
    })
    assert r.status_code == 200
    assert r.json()["run_id"] is None  # aucune ligne avec statut : pas de run manuel créé

    conn = get_initialized_db(config.DB_PATH)
    try:
        cid = r.json()["case_ids"][0]
        ligne_db = CaseRepo(conn).get(cid)
        assert "Alice" in ligne_db["description"]
        assert "01/09/2026" in ligne_db["description"]
        assert "Voir US-123" in ligne_db["description"]
        assert ligne_db["type"] == "fonctionnel"
    finally:
        conn.close()


def test_l_identifiant_importe_se_retrouve_par_la_recherche_de_la_liste(client):
    """L'identifiant du cahier (refs) est cherchable depuis la liste des cas, pas seulement
    visible sur la fiche — et une recherche qui ne correspond à rien ne renvoie rien."""
    mid = _module(client)
    preview = client.post(
        f"/api/modules/{mid}/cases/import-excel/preview",
        files={"file": ("cahier.xlsx", io.BytesIO(_CLASSEUR_SIMPLE),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    ).json()
    client.post(f"/api/modules/{mid}/cases/import-excel/confirm", json={
        "fichier_hash": preview["fichier_hash"], "feuille": preview["feuille"],
        "ligne_entete": preview["ligne_entete"], "mapping": preview["mapping"],
        "numeros_lignes_retenues": [l["numero_ligne"] for l in preview["lignes"]],
    })
    pid = client.get(f"/api/modules/{mid}").json()["project"]["id"]

    trouves = client.get(f"/api/cases?project_id={pid}&q=TC-2").json()["items"]
    assert [c["title"] for c in trouves] == ["Connexion invalide"]  # ligne TC-2 du fichier

    assert client.get(f"/api/cases?project_id={pid}&q=TC-999").json()["items"] == []


def test_confirm_cree_la_section_depuis_la_colonne_user_story(client):
    mid = _module(client)
    preview = client.post(
        f"/api/modules/{mid}/cases/import-excel/preview",
        files={"file": ("cahier.xlsx", io.BytesIO(_CLASSEUR_SIMPLE),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    ).json()

    client.post(f"/api/modules/{mid}/cases/import-excel/confirm", json={
        "fichier_hash": preview["fichier_hash"], "feuille": preview["feuille"],
        "ligne_entete": preview["ligne_entete"], "mapping": preview["mapping"],
        "numeros_lignes_retenues": [preview["lignes"][0]["numero_ligne"]],
    })

    pid = client.get(f"/api/modules/{mid}").json()["project"]["id"]
    cas = client.get(f"/api/cases?project_id={pid}").json()["items"]
    assert cas[0]["group_title"] == "AUTH"


def test_une_ligne_non_retenue_est_comptee_ignoree_et_n_est_pas_creee(client):
    mid = _module(client)
    preview = client.post(
        f"/api/modules/{mid}/cases/import-excel/preview",
        files={"file": ("cahier.xlsx", io.BytesIO(_CLASSEUR_SIMPLE),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    ).json()
    premiere_seulement = [preview["lignes"][0]["numero_ligne"]]

    r = client.post(f"/api/modules/{mid}/cases/import-excel/confirm", json={
        "fichier_hash": preview["fichier_hash"], "feuille": preview["feuille"],
        "ligne_entete": preview["ligne_entete"], "mapping": preview["mapping"],
        "numeros_lignes_retenues": premiere_seulement,
    })

    assert r.json()["cree"] == 1
    assert r.json()["ignore"] == 1


def test_un_fichier_non_xlsx_est_refuse_clairement(client):
    mid = _module(client)

    r = client.post(f"/api/modules/{mid}/cases/import-excel/preview",
                    files={"file": ("cahier.csv", io.BytesIO(b"a,b,c"), "text/csv")})

    assert r.status_code == 422
    assert "xlsx" in r.json()["detail"]


def test_une_colonne_non_reconnue_automatiquement_peut_etre_corrigee_a_la_main(client):
    """L'écran doit pouvoir rattacher une colonne qu'AUCUN synonyme n'a reconnue — pas seulement
    corriger une colonne déjà devinée (voir `entetes_brutes`, excel_import.py)."""
    mid = _module(client)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cas"
    ws.append(["Test Case ID", "Description", "Étapes du Test", "Résultat Attendu", "Env"])
    ws.append(["TC-1", "Titre", "1. Étape", "Résultat", "Préprod — voir ticket OPS-42"])
    tampon = io.BytesIO()
    wb.save(tampon)

    preview = client.post(
        f"/api/modules/{mid}/cases/import-excel/preview",
        files={"file": ("cahier.xlsx", io.BytesIO(tampon.getvalue()),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    ).json()
    assert "5" not in preview["mapping"]  # colonne "Env" non reconnue automatiquement
    assert preview["entetes_brutes"]["5"] == "Env"  # mais visible pour correction

    mapping_corrige = dict(preview["mapping"])
    mapping_corrige["5"] = "commentaires"  # l'utilisateur la rattache à la main

    client.post(f"/api/modules/{mid}/cases/import-excel/confirm", json={
        "fichier_hash": preview["fichier_hash"], "feuille": preview["feuille"],
        "ligne_entete": preview["ligne_entete"], "mapping": mapping_corrige,
        "numeros_lignes_retenues": [preview["lignes"][0]["numero_ligne"]],
    })

    pid = client.get(f"/api/modules/{mid}").json()["project"]["id"]
    cas = client.get(f"/api/cases?project_id={pid}").json()["items"]
    conn = get_initialized_db(config.DB_PATH)
    try:
        ligne_db = CaseRepo(conn).get(cas[0]["id"])
        assert "OPS-42" in ligne_db["description"]
    finally:
        conn.close()


def test_un_mapping_corrige_par_l_utilisateur_est_respecte_a_la_confirmation(client):
    """L'aperçu propose un mapping, mais c'est celui transmis par `confirm` qui fait foi — le
    filet de sécurité pour un Excel mal détecté automatiquement."""
    mid = _module(client)
    preview = client.post(
        f"/api/modules/{mid}/cases/import-excel/preview",
        files={"file": ("cahier.xlsx", io.BytesIO(_CLASSEUR_SIMPLE),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    ).json()
    # L'utilisateur décide que la colonne 2 (Description) est en fait le champ "section", pas
    # "titre" — un mapping délibérément différent de celui auto-détecté.
    mapping_corrige = dict(preview["mapping"])
    mapping_corrige["2"] = "section"

    r = client.post(f"/api/modules/{mid}/cases/import-excel/confirm", json={
        "fichier_hash": preview["fichier_hash"], "feuille": preview["feuille"],
        "ligne_entete": preview["ligne_entete"], "mapping": mapping_corrige,
        "numeros_lignes_retenues": [preview["lignes"][0]["numero_ligne"]],
    })

    assert r.status_code == 200
    pid = client.get(f"/api/modules/{mid}").json()["project"]["id"]
    cas = client.get(f"/api/cases?project_id={pid}").json()["items"]
    # Le titre n'a plus "Connexion valide" (devenu la section) : il retombe sur l'identifiant.
    assert cas[0]["title"] == "TC-1"
