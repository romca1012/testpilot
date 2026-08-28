"""Les PIÈCES JOINTES d'un résultat — la preuve visuelle, et la porte blindée qui la sert.

⚠️ **Ce que ce fichier protège, et le défaut réel qu'il empêche.**

Un résultat joué à la main n'a aucune trace machine : la capture d'écran est tout ce qui reste
pour attester que le test a réellement été joué. Mais téléverser un fichier dans un outil qui
pilote un ERP et garde des secrets chiffrés à côté de sa base, c'est ouvrir trois portes d'un
coup — et ce sont ces trois-là qui sont testées ici :

1. **Le XSS stocké.** Un `.svg` ou un `.html` servi depuis l'origine de TestPilot s'exécute avec
   l'autorité de l'application, cookie de session compris. La liste blanche les refuse, et le
   refus doit porter un CODE que l'écran sait lire (un client qui teste la phrase française casse
   à la première reformulation — le motif que la RFC 9457 est venue fermer ici).
2. **La traversée de chemin.** Un `filename` est une chaîne du client. S'il touche un jour un
   chemin, `../../.env` devient une adresse. Le test vérifie qu'il n'en touche jamais : le fichier
   sur disque porte un nom GÉNÉRÉ par le serveur, et le téléchargement passe par des identifiants
   numériques dont l'appartenance est vérifiée.
3. **Le disque plein.** La route d'import de spec existante lit tout en mémoire, sans plafond.
   Ici deux plafonds (taille, nombre) refusent, chacun avec son code.

Et surtout, l'invariant qui prime sur tous les autres : **la pièce jointe est OPTIONNELLE**. Un
résultat sans fichier s'enregistre exactement comme avant. Une preuve qu'on rend obligatoire n'est
plus une preuve, c'est un péage — et la saisie manuelle cesserait d'être utilisable.

⚠️ Chaque test redirige `config.DATA_DIR` vers un répertoire temporaire : le garde-fou autouse de
`conftest.py` échoue sinon, et il a raison — ces tests ÉCRIVENT des fichiers.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import app
from testpilot.api.deps import get_conn
from testpilot.api.services import attachment_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo, ResultRepo, RunRepo
from testpilot.verdict.status import MODE_MANUELLE

# Un PNG minuscule mais VALIDE — on ne teste pas le contenu, on teste le chemin qu'il emprunte.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    c = get_initialized_db(tmp_path / "pieces.db")
    yield c
    c.close()


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def campagne(conn):
    pid = ProjectRepo(conn).create(name="Portail")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    cid = CaseRepo(conn).create(title="Nominal", module_id=mid, feature_slug="nominal")
    autre = CaseRepo(conn).create(title="Autre", module_id=mid, feature_slug="autre")
    rid = RunRepo(conn).create(project_id=pid, name="Recette", case_ids=[cid, autre],
                               mode=MODE_MANUELLE)
    return {"run": rid, "cas": cid, "autre": autre}


def _resultat(client, campagne, cas: str = "cas", statut: str = "failed") -> int:
    r = client.post(f"/api/runs/{campagne['run']}/cases/{campagne[cas]}/results",
                    json={"statut": statut, "comment": "constaté à la main"})
    assert r.status_code == 201
    return r.json()["id"]


def _joindre(client, result_id: int, nom: str, contenu: bytes = PNG, type_mime: str = "image/png"):
    return client.post(f"/api/results/{result_id}/attachments",
                       files={"files": (nom, contenu, type_mime)})


# ── L'invariant qui prime : la pièce jointe est OPTIONNELLE ───────────────────

def test_un_resultat_SANS_fichier_s_enregistre_normalement(client, campagne):
    """⚠️ **Le test le plus important du fichier.** Ajouter les pièces jointes ne devait rien
    coûter à ceux qui n'en joignent pas : ni un champ obligatoire, ni un aller-retour de plus, ni
    une liste `null` que l'écran devrait deviner. Un résultat sans fichier reste un résultat
    entier."""
    r = client.post(f"/api/runs/{campagne['run']}/cases/{campagne['cas']}/results",
                    json={"statut": "passed"})

    assert r.status_code == 201
    assert r.json()["attachments"] == []
    historique = client.get(
        f"/api/runs/{campagne['run']}/cases/{campagne['cas']}/results").json()
    assert historique[0]["attachments"] == []


# ── Le geste nominal ─────────────────────────────────────────────────────────

def test_joindre_une_capture_puis_la_retrouver_et_la_telecharger(client, campagne):
    """Le parcours complet : je joins, l'historique le montre, et le fichier revient tel quel.

    Sans le téléchargement, la pièce jointe serait une ligne de base de données qui prétend être
    une preuve — exactement le genre d'« affiché ≠ réel » que ce produit refuse."""
    rid = _resultat(client, campagne)

    envoi = _joindre(client, rid, "capture-ecran.png")
    assert envoi.status_code == 201
    piece = envoi.json()[0]
    assert piece["filename"] == "capture-ecran.png"
    assert piece["content_type"] == "image/png"
    assert piece["size_bytes"] == len(PNG)

    historique = client.get(
        f"/api/runs/{campagne['run']}/cases/{campagne['cas']}/results").json()
    assert [p["filename"] for p in historique[0]["attachments"]] == ["capture-ecran.png"]

    fichier = client.get(f"/api/results/{rid}/attachments/{piece['id']}")
    assert fichier.status_code == 200
    assert fichier.content == PNG


def test_un_admin_retire_la_preuve_sans_supprimer_le_resultat(client, campagne, conn):
    """La suppression porte sur la preuve ciblée ; le verdict et son historique restent intacts."""
    rid = _resultat(client, campagne)
    piece = _joindre(client, rid, "capture-ecran.png").json()[0]
    fichier = attachment_service.dossier(rid) / ResultRepo(conn).piece_jointe(
        rid, piece["id"])["stored_name"]

    retrait = client.delete(f"/api/results/{rid}/attachments/{piece['id']}")

    assert retrait.status_code == 204
    assert not fichier.exists()
    historique = client.get(
        f"/api/runs/{campagne['run']}/cases/{campagne['cas']}/results").json()
    assert historique[0]["id"] == rid
    assert historique[0]["attachments"] == []


def test_retirer_la_piece_d_un_AUTRE_resultat_est_introuvable(client, campagne):
    mien = _resultat(client, campagne)
    autre = _resultat(client, campagne, cas="autre")
    piece = _joindre(client, autre, "confidentiel.png").json()[0]

    retrait = client.delete(f"/api/results/{mien}/attachments/{piece['id']}")

    assert retrait.status_code == 404


def test_plusieurs_fichiers_en_UNE_fois(client, campagne):
    """Documenter un parcours demande souvent plusieurs captures : les envoyer une par une
    multiplierait les occasions d'échouer à moitié."""
    rid = _resultat(client, campagne)

    r = client.post(f"/api/results/{rid}/attachments", files=[
        ("files", ("etape-1.png", PNG, "image/png")),
        ("files", ("etape-2.png", PNG, "image/png")),
    ])

    assert r.status_code == 201
    assert [p["filename"] for p in r.json()] == ["etape-1.png", "etape-2.png"]


# ── Les en-têtes : ce que le navigateur a le droit de faire du fichier ────────

def test_une_image_s_affiche_en_ligne_et_le_reste_se_TELECHARGE(client, campagne):
    """⚠️ `nosniff` sur les DEUX, et `inline` réservé aux images de la liste blanche.

    Sans `nosniff`, un navigateur peut ré-interpréter un contenu à sa façon et exécuter ce que le
    serveur annonçait comme du texte. Et un document rendu `inline` s'ouvre dans l'origine de
    TestPilot — c'est précisément ce qu'on ne veut accorder qu'aux formats incapables de script."""
    rid = _resultat(client, campagne)
    image = _joindre(client, rid, "preuve.png").json()[0]
    doc = _joindre(client, rid, "journal.txt", b"trace", "text/plain").json()[0]

    rep_image = client.get(f"/api/results/{rid}/attachments/{image['id']}")
    rep_doc = client.get(f"/api/results/{rid}/attachments/{doc['id']}")

    assert rep_image.headers["x-content-type-options"] == "nosniff"
    assert rep_doc.headers["x-content-type-options"] == "nosniff"
    assert rep_image.headers["content-disposition"].startswith("inline")
    assert rep_doc.headers["content-disposition"].startswith("attachment")


def test_le_type_servi_vient_de_la_LISTE_BLANCHE_pas_du_client(client, campagne):
    """Le navigateur DÉCLARE un type ; une déclaration ne protège personne. Un fichier annoncé
    `text/html` mais nommé `.png` doit être servi comme une image — sinon la liste blanche se
    contourne avec un en-tête de requête."""
    rid = _resultat(client, campagne)
    piece = _joindre(client, rid, "piege.png", PNG, "text/html").json()[0]

    rep = client.get(f"/api/results/{rid}/attachments/{piece['id']}")
    assert rep.headers["content-type"].startswith("image/png")


# ── Les refus : la liste blanche ─────────────────────────────────────────────

@pytest.mark.parametrize("nom", ["exploit.svg", "page.html", "page.htm"])
def test_svg_et_html_sont_REFUSES_c_est_du_script_execute_chez_l_utilisateur(client, campagne,
                                                                            nom):
    """⚠️ **Le refus le plus important.** Ces formats sont servis depuis l'origine de TestPilot :
    les afficher exécuterait leur script dans la session de l'utilisateur, avec son cookie — du
    XSS stocké, sur un outil qui pilote un ERP. Le message doit dire « sécurité », sinon quelqu'un
    ajoutera l'extension un jour en croyant réparer un oubli."""
    rid = _resultat(client, campagne)

    r = _joindre(client, rid, nom, b"<svg onload=alert(1)>", "image/svg+xml")

    assert r.status_code == 415
    assert r.json()["code"] == "type_de_fichier_refuse"
    assert "sécurité" in r.json()["detail"]


def test_un_type_inconnu_est_refuse_et_la_liste_des_formats_possibles_est_DITE(client, campagne):
    """Un refus qui ne dit pas ce qui est accepté oblige à deviner par essais successifs."""
    rid = _resultat(client, campagne)

    r = _joindre(client, rid, "script.exe", b"MZ", "application/octet-stream")

    assert r.status_code == 415
    assert r.json()["code"] == "type_de_fichier_refuse"
    assert ".png" in r.json()["detail"]


def test_un_chemin_tordu_en_guise_de_NOM_ne_mene_nulle_part(client, campagne, tmp_path):
    """⚠️ `../../.env` est un nom de fichier valide côté client. Il ne devient dangereux que s'il
    touche un chemin ; ici il ne le touche jamais — il est lu comme une étiquette, son extension
    n'est pas dans la liste blanche, et il est refusé avant toute écriture. Rien n'apparaît hors
    du répertoire de données."""
    rid = _resultat(client, campagne)

    r = _joindre(client, rid, "../../.env", b"SECRET=1", "text/plain")

    assert r.status_code == 415
    assert not (tmp_path / ".env").exists()
    assert not (tmp_path.parent / ".env").exists()


def test_le_fichier_sur_disque_porte_le_nom_GENERE_par_le_serveur(client, campagne, conn):
    """⚠️ **La garde qui rend les autres inutiles à contourner.** Même un nom parfaitement
    ordinaire ne doit pas devenir un nom de fichier : c'est le serveur qui nomme (`uuid4` +
    extension issue de la liste blanche). Le nom du client ne survit que comme étiquette
    d'affichage — deux utilisateurs peuvent d'ailleurs envoyer « capture.png » sans s'écraser."""
    rid = _resultat(client, campagne)
    _joindre(client, rid, "../../evil.png")

    piece = ResultRepo(conn).pieces_jointes(rid)[0]
    assert piece["filename"] == "../../evil.png"          # l'étiquette, conservée telle quelle
    assert piece["stored_name"] != piece["filename"]
    assert piece["stored_name"].endswith(".png")
    assert "/" not in piece["stored_name"] and "\\" not in piece["stored_name"]
    fichiers = list(attachment_service.dossier(rid).iterdir())
    assert [f.name for f in fichiers] == [piece["stored_name"]]


# ── Les refus : les plafonds ─────────────────────────────────────────────────

def test_un_fichier_TROP_GROS_est_refuse_avec_son_propre_code(client, campagne, monkeypatch):
    """Le plafond se lit dans `config`, et le refus porte un code DISTINCT de « type refusé » :
    l'écran doit pouvoir dire « recadrez votre capture » plutôt que « fichier refusé »."""
    monkeypatch.setattr(config, "ATTACHMENT_MAX_BYTES", 32)
    rid = _resultat(client, campagne)

    r = _joindre(client, rid, "enorme.png", b"\x89PNG" + b"\x00" * 5000)

    assert r.status_code == 413
    assert r.json()["code"] == "fichier_trop_gros"


def test_un_refus_de_taille_ne_laisse_AUCUN_fragment_sur_le_disque(client, campagne, monkeypatch):
    """⚠️ Le contenu est écrit par morceaux : le refus tombe donc APRÈS un début d'écriture. Un
    fragment laissé là remplirait le disque, refus après refus, sans jamais apparaître nulle
    part."""
    monkeypatch.setattr(config, "ATTACHMENT_MAX_BYTES", 32)
    rid = _resultat(client, campagne)

    _joindre(client, rid, "enorme.png", b"\x89PNG" + b"\x00" * 5000)

    dossier = attachment_service.dossier(rid)
    assert not dossier.exists() or list(dossier.iterdir()) == []


def test_le_NOMBRE_de_pieces_par_resultat_est_plafonne(client, campagne, monkeypatch):
    """Un plafond de taille seul se contourne avec mille petits fichiers."""
    monkeypatch.setattr(config, "ATTACHMENT_MAX_PER_RESULT", 2)
    rid = _resultat(client, campagne)
    _joindre(client, rid, "un.png")
    _joindre(client, rid, "deux.png")

    r = _joindre(client, rid, "trois.png")

    assert r.status_code == 409
    assert r.json()["code"] == "trop_de_fichiers"


# ── Les refus : l'accès ──────────────────────────────────────────────────────

def test_la_piece_jointe_d_un_AUTRE_resultat_n_est_pas_atteignable(client, campagne):
    """⚠️ **Le défaut classique d'une route de téléchargement** : l'identifiant du fichier suffit,
    et l'appartenance n'est pas vérifiée. On demande alors n'importe quelle pièce jointe depuis
    n'importe quelle URL. Ici la requête exige que la pièce soit CELLE de ce résultat — clause
    SQL, pas convention de nommage."""
    mien = _resultat(client, campagne)
    autre = _resultat(client, campagne, cas="autre")
    piece_de_l_autre = _joindre(client, autre, "confidentiel.png").json()[0]

    r = client.get(f"/api/results/{mien}/attachments/{piece_de_l_autre['id']}")

    assert r.status_code == 404


def test_un_resultat_inconnu_refuse_le_televersement(client, campagne):
    rid = _resultat(client, campagne)
    r = _joindre(client, rid + 9999, "capture.png")
    assert r.status_code == 404
    assert r.json()["code"] == "introuvable"


def test_une_campagne_ARCHIVEE_refuse_qu_on_y_joigne_un_fichier(client, campagne, conn):
    """Archivée = lecture seule, la même règle que pour la saisie. Enrichir après coup la preuve
    d'une campagne clôturée reviendrait à modifier ce qu'un rapport déjà transmis donne à lire."""
    rid = _resultat(client, campagne)
    RunRepo(conn).archive(campagne["run"], True)

    r = _joindre(client, rid, "tardif.png")

    assert r.status_code == 409
    assert r.json()["code"] == "campagne_archivee"
