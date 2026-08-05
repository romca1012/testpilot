"""Les PIÈCES JOINTES d'un résultat — la preuve visuelle qui accompagne un constat humain
(2026-08-05).

Un résultat joué à la main n'a pas de trace machine : personne ne peut rouvrir un journal
d'exécution pour vérifier ce qui s'est passé. La capture d'écran est ce qui reste — elle atteste
que le test a réellement été joué. Elle est **toujours optionnelle** : un résultat sans fichier
s'enregistre normalement, et rien ici ne doit rendre la saisie plus lourde qu'elle ne l'était.

⚠️ **Pourquoi ce module est écrit comme une porte blindée.** TestPilot pilote un ERP et garde des
secrets chiffrés à côté de sa base. Servir un fichier téléversé depuis sa propre origine, c'est
lui prêter l'autorité de l'application. Trois règles en découlent, et elles ne sont pas
négociables par configuration :

1. **Liste blanche fermée**, `svg` et `html` REFUSÉS. Ce ne sont pas des « images » et des
   « documents » : ce sont des porteurs de script. Servis ici, ils s'exécuteraient dans la
   session de l'utilisateur — du XSS stocké, avec le cookie de session à portée.
2. **Aucune chaîne venue du client ne touche un chemin.** Le nom d'origine est conservé pour
   l'affichage seulement ; le nom SUR LE DISQUE est généré (`uuid4`) et l'extension recopiée
   depuis la liste blanche — pas depuis ce que le client a écrit.
3. **Le contenu est écrit par morceaux**, avec le plafond vérifié à chaque morceau. La route
   d'import de spec (`/cases/extract`) lit tout d'un coup et sans limite : un fichier de 4 Go y
   devient 4 Go de mémoire. Ce défaut n'est pas recopié ici.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from testpilot import config
from testpilot.api import erreurs
from testpilot.store.repositories import ResultRepo

# ── La LISTE BLANCHE ─────────────────────────────────────────────────────────────────────────
# Extension → type servi. ⚠️ C'est CETTE table qui décide du `Content-Type` au téléchargement,
# jamais le `content_type` annoncé par le navigateur : celui-là est une déclaration du client,
# et une déclaration ne protège personne.
#
# Absents volontairement : `.svg` et `.html` (script exécutable, cf. l'en-tête du module), et
# tout ce qui s'exécute côté poste (`.exe`, `.js`, `.bat`…). Une extension inconnue est refusée —
# une liste NOIRE laisserait toujours passer celle qu'on n'a pas pensé à y mettre.
TYPES_ACCEPTES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".zip": "application/zip",
}

# Les seules à pouvoir s'afficher EN LIGNE (aperçu). Tout le reste part en téléchargement : une
# capture d'écran a besoin d'être vue, un `.zip` ou un `.pdf` n'a pas besoin d'être interprété
# par le navigateur dans le contexte de l'application.
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

_TAILLE_MORCEAU = 64 * 1024


def dossier(result_id: int) -> Path:
    """Où sont rangées les pièces jointes d'un résultat : `data/results/<id>/`.

    Même forme que `run_service.dossier_artefacts` — un dossier par entité, sous le répertoire
    de données configurable. Le chemin est ensuite STOCKÉ en base : c'est lui qui sera relu au
    téléchargement, jamais recalculé depuis une donnée du client.
    """
    return Path(config.DATA_DIR) / "results" / str(result_id)


def extension_acceptee(nom_client: str) -> str:
    """L'extension de la liste blanche correspondant à ce nom, ou un refus explicite.

    ⚠️ `Path(...).suffix` sur `../../.env` rend `.env` : le nom n'est jamais interprété comme un
    chemin, seulement comme une étiquette dont on lit la fin. Il n'y a donc rien à « nettoyer »
    — ce qui sort d'ici est une clé de la liste blanche, pas un morceau du nom du client.
    """
    ext = Path(nom_client or "").suffix.lower()
    if ext in TYPES_ACCEPTES:
        return ext
    if ext in (".svg", ".html", ".htm"):
        raise erreurs.ErreurMetier(
            "type_de_fichier_refuse",
            f"« {ext} » est refusé pour des raisons de sécurité : servi par TestPilot, ce format "
            "peut exécuter du script dans votre session. Joignez une capture d'écran (PNG, JPEG) "
            "à la place.")
    raise erreurs.ErreurMetier(
        "type_de_fichier_refuse",
        f"« {ext or nom_client} » n'est pas accepté. Formats possibles : "
        f"{', '.join(sorted(TYPES_ACCEPTES))}.")


def type_servi(stored_name: str) -> tuple[str, bool]:
    """Le `Content-Type` à servir pour ce fichier, et s'il peut s'afficher en ligne.

    Dérivé du nom SUR DISQUE (généré par nous, extension issue de la liste blanche) — donc d'une
    valeur que le client n'a jamais écrite.
    """
    ext = Path(stored_name).suffix.lower()
    return TYPES_ACCEPTES.get(ext, "application/octet-stream"), ext in IMAGES


async def enregistrer(conn, result_id: int, fichier: UploadFile) -> dict:
    """Écrit UN fichier sur le disque et l'inscrit en base. Rend la ligne créée.

    Refuse, dans cet ordre : type hors liste blanche, résultat déjà plein, fichier trop gros.
    Le plafond est vérifié **pendant** l'écriture : un fichier qui ment sur sa taille (ou qui n'en
    annonce aucune, ce que fait un envoi en flux) est coupé au premier morceau de trop, et le
    fragment déjà écrit est effacé — on ne laisse pas de moitié de fichier derrière un refus.
    """
    ext = extension_acceptee(fichier.filename or "")
    repo = ResultRepo(conn)

    deja = len(repo.pieces_jointes(result_id))
    if deja >= config.ATTACHMENT_MAX_PER_RESULT:
        raise erreurs.ErreurMetier(
            "trop_de_fichiers",
            f"ce résultat porte déjà {deja} pièces jointes (maximum "
            f"{config.ATTACHMENT_MAX_PER_RESULT}). Ajoutez un nouveau résultat si le constat a "
            "changé, ou retirez un fichier avant d'en joindre un autre.")

    cible = dossier(result_id)
    cible.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    chemin = cible / stored_name

    taille = 0
    try:
        with chemin.open("wb") as sortie:
            while morceau := await fichier.read(_TAILLE_MORCEAU):
                taille += len(morceau)
                if taille > config.ATTACHMENT_MAX_BYTES:
                    raise erreurs.ErreurMetier(
                        "fichier_trop_gros",
                        f"« {fichier.filename} » dépasse la taille autorisée "
                        f"({config.ATTACHMENT_MAX_BYTES // (1024 * 1024)} Mo). Une capture "
                        "d'écran recadrée, ou une image compressée, passera.")
                sortie.write(morceau)
    except BaseException:
        chemin.unlink(missing_ok=True)
        raise

    piece_id = repo.ajouter_piece_jointe(
        result_id, filename=(fichier.filename or "")[:255], stored_name=stored_name,
        dossier=str(cible), content_type=type_servi(stored_name)[0], size_bytes=taille)
    return {"id": piece_id, "filename": (fichier.filename or "")[:255],
            "content_type": type_servi(stored_name)[0], "size_bytes": taille}
