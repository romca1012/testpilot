"""Extraction du texte d'un fichier de spécification téléversé, et conservation de l'original.

Le bouton « Générer » accepte une zone de texte OU un fichier (demande du porteur). Ce module
transforme un fichier en texte brut, que la génération traite ensuite comme n'importe quelle spec.

Formats gérés : `.txt`, `.md`, `.markdown` (texte brut), `.docx` (via `python-docx`) et `.pdf`
(via `pdfplumber`, déjà une dépendance du projet et déjà utilisée côté CLI dans
`spec_analyzer._read_spec` — même bibliothèque, mais depuis des octets déjà en mémoire plutôt
qu'un chemin sur disque, cf. `_pdf` ci-dessous).

Ce module fait aussi deux choses que la route seule ne peut pas garantir sans dupliquer leur
logique : borner la taille d'un envoi PENDANT la lecture (`lire_borne`, même patron que
`attachment_service`) et conserver l'ORIGINAL téléversé sur disque (`conserver_original`), pour
une version plus évoluée qui saura le relire — pas seulement le texte qu'on en a extrait.
"""

from __future__ import annotations

import io
from pathlib import Path

from testpilot import config
from testpilot.api import erreurs

_TAILLE_MORCEAU = 64 * 1024


class UnsupportedFormat(Exception):
    """Format de fichier non pris en charge — traduit en HTTP 422 par la route."""


_TEXTE = (".txt", ".md", ".markdown", ".text", ".feature")


async def lire_borne(fichier, max_bytes: int) -> bytes:
    """Lit `fichier` (un `UploadFile`, ou tout objet à `.read(n)` asynchrone) par morceaux, en
    refusant DÈS QUE le plafond est dépassé — jamais après avoir tout chargé en mémoire.

    ⚠️ Avant ce correctif, `/cases/extract` faisait `await file.read()` sans aucune limite : un
    envoi de plusieurs Go devenait autant de mémoire serveur avant d'être rejeté. Ici, une fois le
    morceau qui dépasse identifié, on lève tout de suite — `fichier.read()` n'est plus rappelé, et
    aucun morceau au-delà du plafond n'entre en mémoire.
    """
    morceaux: list[bytes] = []
    taille = 0
    while morceau := await fichier.read(_TAILLE_MORCEAU):
        taille += len(morceau)
        if taille > max_bytes:
            nom = getattr(fichier, "filename", "") or ""
            raise erreurs.ErreurMetier(
                "specification_trop_grande",
                f"« {nom} » dépasse la taille autorisée ({max_bytes // (1024 * 1024)} Mo). "
                "Réduisez le fichier, ou collez le texte directement dans la zone de saisie.")
        morceaux.append(morceau)
    return b"".join(morceaux)


def conserver_original(spec_hash: str, filename: str, data: bytes) -> Path:
    """Écrit les octets ORIGINAUX du fichier téléversé sous `DATA_DIR/specifications/<spec_hash>/`.

    Adressé par le hash du TEXTE EXTRAIT (`spec_analyzer.spec_hash`), pas par un nom aléatoire :
    deux téléversements qui produisent la même spec retombent sur le même dossier, sans doublon.
    Pas d'écran de consultation à construire maintenant (§6 point 9d de `REPRISE-P3.md`) — le
    porteur veut seulement ne pas perdre l'original « pour une version plus évoluée ».

    ⚠️ Le nom de fichier est réduit à son dernier segment (`Path(...).name`) : le dossier cible est
    déjà fixé par le hash (jamais par le client), mais `filename` reste une chaîne venue du
    client — `../../evil` ne doit pas pouvoir désigner un chemin hors de ce dossier.
    """
    dossier = Path(config.DATA_DIR) / "specifications" / spec_hash
    dossier.mkdir(parents=True, exist_ok=True)
    nom = Path(filename or "").name or "specification"
    chemin = dossier / nom
    chemin.write_bytes(data)
    return chemin


def extract_text(filename: str, data: bytes) -> str:
    """Rend le texte du fichier, ou lève `UnsupportedFormat`.

    On se fie à l'extension pour choisir le lecteur, mais un `.docx` illisible lève tout de même
    (on ne renvoie pas un texte tronqué en le faisant passer pour complet).
    """
    nom = (filename or "").lower()

    if nom.endswith(_TEXTE) or not _a_une_extension(nom):
        # Décodage tolérant : un fichier texte peut être en UTF-8 (le cas normal) ou en Latin-1.
        for enc in ("utf-8", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        raise UnsupportedFormat("fichier texte illisible (encodage non reconnu)")

    if nom.endswith(".docx"):
        return _docx(data)

    if nom.endswith(".pdf"):
        return _pdf(data)

    raise UnsupportedFormat(
        f"format non géré : {nom.rsplit('.', 1)[-1]} — utilisez .txt, .md ou .docx")


def _a_une_extension(nom: str) -> bool:
    return "." in nom.rsplit("/", 1)[-1]


def _docx(data: bytes) -> str:
    """Texte d'un .docx : paragraphes ET cellules de tableaux (les specs mettent souvent les
    champs dans un tableau — les omettre perdrait l'essentiel)."""
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover - la lib est installée dans cet environnement
        raise UnsupportedFormat("lecture .docx indisponible (python-docx manquant)") from exc

    document = docx.Document(io.BytesIO(data))
    morceaux = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cellules = [c.text.strip() for c in row.cells if c.text.strip()]
            if cellules:
                morceaux.append(" | ".join(cellules))
    return "\n".join(morceaux)


def _pdf(data: bytes) -> str:
    """Texte d'un PDF, page par page — même lecteur que le chemin CLI
    (`spec_analyzer._read_spec`), depuis des octets déjà en mémoire plutôt qu'un chemin sur disque.

    Un PDF protégé, corrompu, ou scanné sans OCR ne doit jamais rendre une chaîne vide qu'on
    ferait passer pour la spec complète (même discipline que `.docx` : un import silencieux qui
    perd le contenu est le motif « affiché ≠ réel » du §4.6) — on lève une erreur qui dit pourquoi.
    """
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - la lib est déclarée en dépendance du projet
        raise UnsupportedFormat("lecture PDF indisponible (pdfplumber manquant)") from exc

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            texte = "\n\n".join(page.extract_text() or "" for page in pdf.pages).strip()
    except UnsupportedFormat:
        raise
    except Exception as exc:
        raise UnsupportedFormat(f"PDF illisible (protégé ou corrompu) : {exc}") from exc

    if not texte:
        raise UnsupportedFormat(
            "le PDF ne contient aucun texte extractible (scan sans OCR, ou pages vides) — "
            "collez le texte, ou fournissez un .txt, .md ou .docx")
    return texte
