"""Extraction du texte d'un fichier de spécification téléversé.

Le bouton « Générer » accepte une zone de texte OU un fichier (demande du porteur). Ce module
transforme un fichier en texte brut, que la génération traite ensuite comme n'importe quelle spec.

Formats gérés **sans nouvelle dépendance** : `.txt`, `.md`, `.markdown` (texte brut) et `.docx`
(via `python-docx`, déjà installé). Le PDF exige une bibliothèque non présente : on le REFUSE avec
un message clair plutôt que de rendre un texte vide — le motif « affiché ≠ réel » (§4.6) appliqué
à un import silencieux.
"""

from __future__ import annotations

import io


class UnsupportedFormat(Exception):
    """Format de fichier non pris en charge — traduit en HTTP 422 par la route."""


_TEXTE = (".txt", ".md", ".markdown", ".text", ".feature")


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
        raise UnsupportedFormat(
            "le PDF n'est pas encore géré — collez le texte, ou fournissez un .txt, .md ou .docx")

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
