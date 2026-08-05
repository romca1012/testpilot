"""Le CONTRAT D'ERREUR de l'API — RFC 9457 (lot B, 2026-07-24).

**Le défaut qu'on corrige.** L'API répondait `{"detail": "La connexion du projet « X » est
incomplète : le mot de passe…"}`. Un client qui veut *réagir* — proposer d'ouvrir l'écran des
projets, réessayer, ignorer — n'a alors qu'une **phrase française** à interpréter. Une correction
de faute de frappe dans le message casse le client, en silence.

Le comble : **les codes existaient déjà** (`no_connection`, `duplicate`, `needs_review`…), portés
par les exceptions des services. Ce sont les routes qui les jetaient en ne gardant que le texte.
Ce module les fait traverser la frontière HTTP.

**La forme rendue** (RFC 9457, `application/problem+json`) :

```json
{
  "type": "https://testpilot.local/erreurs/connexion_incomplete",
  "title": "La connexion du projet est incomplète",
  "status": 409,
  "detail": "La connexion du projet « Recette » est incomplète : le mot de passe. …",
  "instance": "/api/v1/modules/3/cases",
  "code": "connexion_incomplete"
}
```

- `code` est **l'API stable** : c'est lui qu'un client teste, jamais `detail`.
- `detail` reste la phrase destinée à l'humain — libre d'évoluer sans casser personne.
- ⚠️ **`detail` est conservé tel quel** : le frontend actuel l'affiche déjà, et le passage à
  RFC 9457 ne devait rien casser au moment où on le pose.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

# Base d'URI des types de problème. Purement identifiante — rien n'est servi à cette adresse.
BASE_TYPE = "https://testpilot.local/erreurs/"

# ── Le catalogue des codes ───────────────────────────────────────────────────────────────────
# UN SEUL endroit. Un code qui n'est pas ici n'existe pas : c'est ce qui empêche d'en inventer
# un par route, et ce qui permet de dire à un client ce sur quoi il peut compter.
#
# ⚠️ Un code est un CONTRAT : on peut en ajouter, jamais en renommer sans le déprécier d'abord.
CATALOGUE: dict[str, tuple[int, str]] = {
    # ── Ressource absente ou état incompatible ──
    "introuvable":            (404, "Ressource introuvable"),
    "nom_deja_pris":          (409, "Ce nom est déjà utilisé"),
    "conteneur_non_vide":     (409, "Cet élément porte encore des enfants"),
    # ── Connexion à l'application testée ──
    "connexion_incomplete":   (409, "La connexion du projet est incomplète"),
    # ── Cycle de vie d'un cas ──
    "aucune_version":         (409, "Ce cas n'a pas encore de test technique"),
    "relecture_requise":      (409, "Ce cas attend une relecture"),
    "specification_vide":     (422, "La spécification est vide"),
    "metier_incomplet":       (422, "Le document métier est incomplet"),
    "etat_incompatible":      (409, "L'action ne s'applique pas dans cet état"),
    # ── Campagnes ──
    "campagne_vide":          (422, "Cette campagne ne contient aucun cas"),
    "campagne_en_cours":      (409, "Cette campagne est déjà en cours"),
    "campagne_archivee":      (409, "Cette campagne est archivée (lecture seule)"),
    # ── Exécution MANUELLE d'un cas : la saisie de son résultat (2026-08-04) ──
    # `untested` n'est PAS saisissable : c'est l'absence de résultat, jamais un choix. Le refus
    # doit le DIRE, sinon l'utilisateur cherche l'option manquante dans une liste déroulante.
    "statut_invalide":        (422, "Ce statut ne peut pas être saisi"),
    "cas_hors_campagne":      (409, "Ce cas ne fait pas partie de cette campagne"),
    # Le mode se choisit à la CRÉATION de la campagne : une campagne automatique se lance, elle
    # ne se saisit pas. Sans ce code, le refus remonterait en erreur d'intégrité SQLite (le
    # trigger du mode) — illisible pour un client, et impossible à distinguer d'une panne.
    "campagne_automatique":   (409, "Cette campagne est automatique (résultats non saisissables)"),
    "campagne_manuelle":      (409, "Cette campagne est manuelle (elle ne se lance pas)"),
    # ── Pièces jointes d'un résultat (2026-08-05) ──
    # Trois refus DISTINCTS, parce que l'écran doit dire lequel : « trop gros », « type refusé »
    # et « trop de fichiers » appellent trois gestes différents de l'utilisateur. Un code unique
    # le forcerait à lire une phrase française pour deviner lequel — le défaut que la RFC 9457
    # est venue fermer ici.
    "fichier_trop_gros":      (413, "Ce fichier dépasse la taille autorisée"),
    "type_de_fichier_refuse": (415, "Ce type de fichier n'est pas accepté"),
    "trop_de_fichiers":       (409, "Ce résultat porte déjà trop de pièces jointes"),
    # ── Import d'une spécification (2026-08-05) ──
    "specification_trop_grande": (413, "Cette spécification dépasse la taille autorisée"),
    # ── Exploration ──
    "exploration_en_cours":   (409, "Une exploration est déjà en cours sur ce projet"),
    # ── Requête mal formée / non géré ──
    "requete_invalide":       (422, "Requête invalide"),
    "non_gere":               (400, "Requête non prise en charge"),
}

# Les services parlent leur propre langue (héritée) ; on la traduit ici, en un seul endroit,
# plutôt que d'aller renommer des codes internes dans quatre services et leurs tests.
_DEPUIS_SERVICE = {
    "not_found": "introuvable",
    "duplicate": "nom_deja_pris",
    "no_connection": "connexion_incomplete",
    "no_version": "aucune_version",
    "needs_review": "relecture_requise",
    "invalid_spec": "specification_vide",
    "invalid_metier": "metier_incomplet",
    "invalid_state": "etat_incompatible",
    "empty": "campagne_vide",
    "already_running": "campagne_en_cours",
    "archived": "campagne_archivee",
    "manual": "campagne_manuelle",
}


class ErreurMetier(Exception):
    """Une erreur que le CLIENT doit pouvoir reconnaître sans lire de français.

    `code` doit exister au `CATALOGUE` — sinon on lève à la construction. C'est délibérément
    brutal : un code inventé passerait autrement en production, et un client construirait sa
    logique sur une valeur que personne ne s'est engagé à maintenir.
    """

    def __init__(self, code: str, detail: str = "", *, status: int | None = None):
        if code not in CATALOGUE:
            raise ValueError(f"code d'erreur inconnu : {code!r} — ajoutez-le au CATALOGUE")
        defaut_status, titre = CATALOGUE[code]
        self.code = code
        self.titre = titre
        self.status = status or defaut_status
        self.detail = detail or titre
        super().__init__(self.detail)


def depuis_service(code_service: str, detail: str, *, defaut: str = "non_gere") -> ErreurMetier:
    """Traduit le code d'une exception de service (`RunError`, `CampaignError`…) en erreur HTTP.

    Les services portaient déjà ces codes ; les routes les jetaient pour ne garder que le texte.
    """
    return ErreurMetier(_DEPUIS_SERVICE.get(code_service, defaut), detail)


def _probleme(*, code: str, titre: str, status: int, detail: str, chemin: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"{BASE_TYPE}{code}",
            "title": titre,
            "status": status,
            "detail": detail,
            "instance": chemin,
            "code": code,
        },
    )


async def gerer_erreur_metier(request: Request, exc: ErreurMetier) -> JSONResponse:
    return _probleme(code=exc.code, titre=exc.titre, status=exc.status,
                     detail=exc.detail, chemin=request.url.path)


# Statut HTTP → code de repli, pour les `HTTPException` pas encore converties. Elles rendent ainsi
# la MÊME forme : un client n'a jamais à gérer deux formats d'erreur selon la route qu'il appelle.
_REPLI_PAR_STATUT = {404: "introuvable", 409: "etat_incompatible", 422: "requete_invalide"}


async def gerer_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    code = _REPLI_PAR_STATUT.get(exc.status_code, "non_gere")
    titre = CATALOGUE[code][1]
    detail = exc.detail if isinstance(exc.detail, str) else titre
    return _probleme(code=code, titre=titre, status=exc.status_code,
                     detail=detail, chemin=request.url.path)
