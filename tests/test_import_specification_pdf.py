"""Import d'une spécification : le PDF devient lisible, un plafond de taille apparaît, et
l'original téléversé est conservé (§6 point 9d de `docs/REPRISE-P3.md`, 2026-08-05).

⚠️ **Le défaut réel que ce fichier corrige.** Avant ce chantier, `spec_extract.py` refusait tout
PDF avec un message qui disait *« le PDF exige une bibliothèque non présente »* — **faux** :
`pdfplumber` est une dépendance du projet depuis le début, déjà utilisée côté CLI
(`spec_analyzer._read_spec`). Et la route `/cases/extract` lisait `await file.read()` sans aucune
limite, ni ne gardait jamais le fichier original — deux défauts documentés en commentaire dans
`config.py` avant d'être corrigés ici.

Chaque test redirige `config.DATA_DIR` (le garde-fou autouse de `conftest.py` l'exige : ces tests
ÉCRIVENT des fichiers) et `config.DB_PATH` vers un répertoire temporaire.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.analysis.spec_analyzer import spec_hash
from testpilot.api import app as app_mod
from testpilot.api import erreurs
from testpilot.api.services import spec_extract


# ── Construire un PDF minimal, SANS nouvelle dépendance ────────────────────────────────────────
# `pdfplumber` (lecture) est une dépendance déjà déclarée ; rien dans le projet ne sait ÉCRIRE un
# PDF. On en fabrique un à la main — un PDF valide est un format texte simple (objets numérotés +
# table `xref`) — plutôt que d'ajouter une bibliothèque juste pour les tests.
def _pdf(flux_texte: bytes) -> bytes:
    """Un PDF à une page, dont le contenu de la page est `flux_texte` (des opérateurs PDF bruts,
    p. ex. `BT ... Tj ET` pour du texte, ou vide pour une page blanche sans texte extractible)."""
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 200 200] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(flux_texte) + flux_texte + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, corps in enumerate(objets, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + corps + b"\nendobj\n")
    xref_offset = out.tell()
    n = len(objets) + 1
    out.write(b"xref\n0 %d\n" % n)
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\n" % n)
    out.write(b"startxref\n%d\n" % xref_offset)
    out.write(b"%%EOF")
    return out.getvalue()


PDF_AVEC_TEXTE = _pdf(b"BT /F1 12 Tf 20 100 Td (Bonjour spec de test) Tj ET")
PDF_SANS_TEXTE = _pdf(b"")  # page blanche : valide, mais aucun texte extractible (cas du scan)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    return TestClient(app_mod.app)


def _module(client) -> int:
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    return client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]


# ── Le PDF se lit ────────────────────────────────────────────────────────────────────────────

def test_un_pdf_AVEC_texte_se_lit(client):
    """Le cas nominal que l'ancien refus bloquait totalement."""
    mid = _module(client)

    r = client.post(f"/api/modules/{mid}/cases/extract",
                    files={"file": ("spec.pdf", io.BytesIO(PDF_AVEC_TEXTE), "application/pdf")})

    assert r.status_code == 200
    assert "Bonjour spec de test" in r.json()["text"]


def test_un_pdf_SANS_texte_extractible_leve_une_erreur_CLAIRE_pas_un_texte_vide(client):
    """⚠️ Un scan sans OCR est un PDF parfaitement valide, mais sans aucun texte dans son flux :
    le rendre comme une spec vide serait le motif « affiché ≠ réel » (§4.6) — l'utilisateur
    croirait avoir importé sa spec alors que rien n'a été lu."""
    mid = _module(client)

    r = client.post(f"/api/modules/{mid}/cases/extract",
                    files={"file": ("scan.pdf", io.BytesIO(PDF_SANS_TEXTE), "application/pdf")})

    assert r.status_code == 422
    assert "PDF" in r.json()["detail"]
    assert "texte" in r.json()["detail"]


def test_extract_text_pdf_directement_sans_passer_par_l_api():
    """L'unité la plus basse : `spec_extract` seul, sans FastAPI ni base."""
    assert spec_extract.extract_text("spec.pdf", PDF_AVEC_TEXTE) == "Bonjour spec de test"

    with pytest.raises(spec_extract.UnsupportedFormat):
        spec_extract.extract_text("scan.pdf", PDF_SANS_TEXTE)


def test_un_pdf_CORROMPU_leve_UnsupportedFormat_pas_une_exception_technique():
    """Des octets qui ne sont pas un PDF du tout (pas seulement « sans texte ») doivent produire
    la MÊME famille d'erreur que les autres formats illisibles — pas fuir une exception interne
    de `pdfplumber`/`pdfminer` que la route ne saurait pas traduire en 422."""
    with pytest.raises(spec_extract.UnsupportedFormat):
        spec_extract.extract_text("casse.pdf", b"ceci n'est pas un PDF")


# ── Le plafond de taille ─────────────────────────────────────────────────────────────────────

def test_un_fichier_au_dela_du_plafond_est_refuse_413(client, monkeypatch):
    monkeypatch.setattr(config, "SPEC_MAX_BYTES", 32)
    mid = _module(client)

    r = client.post(f"/api/modules/{mid}/cases/extract",
                    files={"file": ("gros.txt", io.BytesIO(b"x" * 5000), "text/plain")})

    assert r.status_code == 413
    assert r.json()["code"] == "specification_trop_grande"


class _FluxFactice:
    """Simule un `UploadFile` : sert `contenu` par morceaux, et compte les octets réellement
    SERVIS — pour distinguer « la lecture s'est arrêtée tôt » de « la réponse finale est un
    rejet », qui ne prouve pas la même chose (un `await file.read()` intégral suivi d'un refus
    APRÈS coup donnerait la même réponse finale, mais aurait déjà tout chargé en mémoire)."""

    def __init__(self, contenu: bytes, taille_morceau: int = 64 * 1024):
        self._donnees = contenu
        self._position = 0
        self._taille_morceau = taille_morceau
        self.octets_servis = 0

    async def read(self, n: int = -1) -> bytes:
        taille = n if n and n > 0 else self._taille_morceau
        bloc = self._donnees[self._position:self._position + taille]
        self._position += len(bloc)
        self.octets_servis += len(bloc)
        return bloc


def test_la_lecture_S_ARRETE_avant_la_fin_du_fichier_pas_apres(monkeypatch):
    """⚠️ Le test qui distingue « borné » de « borné en apparence ». Sans lecture par morceaux,
    un fichier de plusieurs Go serait entièrement chargé en mémoire avant que quiconque ne songe
    à en mesurer la taille — c'était le défaut réel de `/cases/extract` avant ce correctif. Ici on
    vérifie directement que `lire_borne` n'a jamais demandé plus que le strict nécessaire pour
    détecter le dépassement."""
    un_megaoctet = b"x" * (1024 * 1024)
    flux = _FluxFactice(un_megaoctet, taille_morceau=64 * 1024)

    with pytest.raises(erreurs.ErreurMetier) as exc:
        asyncio.run(spec_extract.lire_borne(flux, max_bytes=100))

    assert exc.value.code == "specification_trop_grande"
    # Le plafond (100 octets) tient dans le PREMIER morceau (64 Ko) : la lecture s'est arrêtée là,
    # jamais près du mégaoctet total disponible.
    assert flux.octets_servis <= 64 * 1024
    assert flux.octets_servis < len(un_megaoctet)


def test_un_fichier_SOUS_le_plafond_est_lu_en_entier():
    """Le pendant positif : `lire_borne` ne coupe rien quand il n'y a pas lieu de couper."""
    contenu = b"une spec parfaitement raisonnable"
    flux = _FluxFactice(contenu)

    lu = asyncio.run(spec_extract.lire_borne(flux, max_bytes=config.SPEC_MAX_BYTES))

    assert lu == contenu


# ── La conservation de l'original ────────────────────────────────────────────────────────────

def test_l_original_atterrit_sous_DATA_DIR_specifications_hash_et_s_y_retrouve(client, tmp_path):
    """Le porteur veut le FICHIER, pas seulement son texte — pour une version plus évoluée qui
    saura le relire. Le dossier est adressé par le hash du TEXTE EXTRAIT (`spec_hash`), pas par un
    nom aléatoire : c'est ce hash qui doit pouvoir retrouver le fichier plus tard."""
    mid = _module(client)

    r = client.post(f"/api/modules/{mid}/cases/extract",
                    files={"file": ("ma_spec.md", io.BytesIO(b"# Ma spec\ncontenu"),
                                    "text/markdown")})
    assert r.status_code == 200
    texte = r.json()["text"]

    dossier = tmp_path / "data" / "specifications" / spec_hash(texte)
    assert (dossier / "ma_spec.md").exists()
    assert (dossier / "ma_spec.md").read_bytes() == b"# Ma spec\ncontenu"


def test_un_nom_de_fichier_tordu_ne_sort_pas_du_dossier_du_hash(tmp_path, monkeypatch):
    """⚠️ `filename` est une chaîne venue du client. `conserver_original` doit la traiter comme
    une étiquette, jamais comme un chemin — même discipline que `attachment_service` pour les
    pièces jointes d'un résultat."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")

    chemin = spec_extract.conserver_original("abc123", "../../evil.md", b"contenu")

    assert chemin.parent == tmp_path / "data" / "specifications" / "abc123"
    assert not (tmp_path / "evil.md").exists()
    assert not (tmp_path / "data" / "evil.md").exists()


def test_deux_televersements_de_la_MEME_spec_retombent_sur_le_MEME_dossier(client, tmp_path):
    """Adressé par le hash du texte, pas par un nom aléatoire : pas de doublon quand la même spec
    est importée deux fois (deux noms de fichier différents, même contenu extrait)."""
    mid = _module(client)
    contenu = b"# Spec identique\ndetails"

    client.post(f"/api/modules/{mid}/cases/extract",
               files={"file": ("premier-envoi.md", io.BytesIO(contenu), "text/markdown")})
    r2 = client.post(f"/api/modules/{mid}/cases/extract",
                     files={"file": ("second-envoi.md", io.BytesIO(contenu), "text/markdown")})

    dossier = tmp_path / "data" / "specifications" / spec_hash(r2.json()["text"])
    assert sorted(p.name for p in dossier.iterdir()) == ["premier-envoi.md", "second-envoi.md"]


# ── Pas de régression sur les formats déjà gérés ────────────────────────────────────────────

def test_txt_md_et_docx_ne_regressent_pas():
    """Le branchement du PDF touche `extract_text` : vérifier que les formats déjà en place n'ont
    pas bougé — même fonction, même dispatch par extension."""
    import docx  # python-docx, déjà une dépendance (utilisée par `spec_extract._docx`)

    assert spec_extract.extract_text("spec.txt", "bonjour".encode()) == "bonjour"
    assert "titre" in spec_extract.extract_text("spec.md", "# titre\ncorps".encode())

    document = docx.Document()
    document.add_paragraph("Paragraphe de spec")
    tampon = io.BytesIO()
    document.save(tampon)

    assert spec_extract.extract_text("spec.docx", tampon.getvalue()) == "Paragraphe de spec"
