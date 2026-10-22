"""Garde de connexion à l'écriture (étape 5 du plan unique, AV-6 du registre des paramètres de test).

Pourquoi. La connexion est DÉJÀ faite : connexion enregistrée, rejouée par le harnais (« j'accède à la page d'accueil de
l'application » connecte avec le compte du projet). La consigne « n'écris jamais de step de connexion » existait dans le
prompt, mais une consigne ne suffit pas : mesuré en `base-4`, deux tests sortis « bloqués » sur un compte inventé. Cette
garde le refuse à l'écriture, sans IA :

- un compte cité par « je me connecte en tant que "<libellé>" » doit être DÉCLARÉ sur le projet (ou le principal) ;
- un test dont le cas ne porte pas sur la connexion ne rouvre pas la connexion : ni les deux steps de connexion explicite,
  ni la page de connexion relevée par l'exploration, ni la saisie d'un champ de mot de passe.

Ce que le cas « porte sur la connexion » se lit dans son intention DÉCLARÉE (titre, préconditions, étapes et résultat
attendu validés par le métier — `generation_service._intention_declaree`), jamais dans le texte écrit par l'agent
(décision 0015). La lecture est LARGE (le moindre mot de connexion, de session ou de mot de passe suffit) : dans le doute,
la garde se tait — elle ne doit jamais refuser un vrai test de connexion.

Module pur : aucune I/O, aucun LLM.
"""

from __future__ import annotations

import re
import unicodedata

_LIBELLE_PRINCIPAL = "principal"   # même libellé que `behave_runtime/steps_library/_base_helpers._LIBELLE_PRINCIPAL`

# Le moindre signe que le cas parle de connexion, de session ou d'identifiants (texte sans accents, en minuscules).
_PORTE_SUR_LA_CONNEXION = re.compile(
    r"connexion|connect|deconnex|deconnect|login|logout|log in|log out|sign in|sign out|signin|signout|authentif|"
    r"mot de passe|mots de passe|password|identifiant|credential|session|compte (?:verrouille|bloque|desactive|suspendu)|"
    r"locked out|2fa|double authentification|totp")

_CONNEXION_EXPLICITE = ("j'accède à la page de connexion sans me connecter",
                        "je me connecte avec mes identifiants utilisateur")
_EN_TANT_QUE = re.compile(r'^je me connecte en tant que "(?P<libelle>[^"]*)"$')
_PAGE = re.compile(r'^j\'ouvre la page "(?P<route>[^"]+)"$')
_CHAMP = re.compile(r'^je (?:renseigne|laisse) le champ "(?P<champ>[^"]+)"')


def _plat(texte: str) -> str:
    plat = unicodedata.normalize("NFD", (texte or "").replace("’", "'"))
    return "".join(c for c in plat if unicodedata.category(c) != "Mn").casefold()


def _cle(libelle: str) -> str:
    """La clé du harnais (`_cle_de_libelle`) : insensible à la casse et aux espaces multiples."""
    return " ".join((libelle or "").split()).casefold()


def porte_sur_la_connexion(intention: str) -> bool:
    """Le cas parle-t-il, même de loin, de connexion, de session ou d'identifiants ? Large par construction."""
    return bool(_PORTE_SUR_LA_CONNEXION.search(_plat(intention)))


def _route(route: str) -> str:
    return "/" + route.strip().lstrip("/").split("?")[0].split("#")[0].rstrip("/") if route.strip() else "/"


def _etapes(feature: str) -> list[str]:
    """Les libellés de toutes les étapes (contextes, règles, scénarios, plans développés), lus par le parseur de Behave."""
    from behave.parser import ParserError, parse_feature

    try:
        modele = parse_feature(feature or "", language="fr")
    except ParserError:
        return []
    if modele is None:
        return []
    etapes = []
    for conteneur in [modele, *(getattr(modele, "rules", None) or [])]:
        fond = getattr(conteneur, "background", None)
        etapes += [e.name for e in (fond.steps if fond else [])]
    etapes += [e.name for s in modele.walk_scenarios() for e in getattr(s, "steps", None) or []]
    return [str(e or "").strip() for e in etapes]


def refus(feature: str, *, porte_sur_la_connexion: bool | None, comptes: list[str] | None,
          page_connexion: str | None = None, champs_secrets: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """Ce qui empêche d'écrire ce test (vide : accepté).

    `porte_sur_la_connexion` : `None` (intention inconnue — banc, outil isolé) ne refuse rien sur ce point. `comptes` : les
    libellés DÉCLARÉS des comptes secondaires ; `None` (inconnus) ne contrôle pas les comptes. `page_connexion` et
    `champs_secrets` : la page de connexion et les champs de mot de passe relevés par l'exploration (connecteur web)."""
    fautes: list[str] = []
    connus = {_cle(c) for c in (comptes or ())} | {_LIBELLE_PRINCIPAL}
    secrets = {s.strip() for s in champs_secrets if s and s.strip()}
    for etape in dict.fromkeys(_etapes(feature)):
        compte = _EN_TANT_QUE.match(etape)
        if compte and comptes is not None and "<" not in compte.group("libelle") \
                and _cle(compte.group("libelle")) not in connus:
            fautes.append(f"« {etape} » : le compte « {compte.group('libelle')} » n'est pas déclaré sur ce projet "
                          f"(comptes : {', '.join([_LIBELLE_PRINCIPAL, *(comptes or [])])}) — n'invente jamais un "
                          "compte : sans compte précisé, le test joue avec le compte du cas")
        if porte_sur_la_connexion is not False:
            continue
        if etape in _CONNEXION_EXPLICITE:
            fautes.append(f"« {etape} » : ce cas ne porte pas sur la connexion — elle est DÉJÀ faite par « j'accède à la "
                          "page d'accueil de l'application » ; n'écris aucune étape de connexion")
            continue
        page = _PAGE.match(etape)
        # « / » jamais : sur beaucoup d'applications l'accueil EST la page de connexion tant qu'on n'est pas connecté.
        if page and page_connexion and _route(page_connexion) != "/" \
                and _route(page.group("route")) == _route(page_connexion):
            fautes.append(f"« {etape} » : la page de connexion ne s'ouvre pas dans un test qui ne porte pas sur la "
                          "connexion — la session du compte est déjà ouverte")
            continue
        champ = _CHAMP.match(etape)
        if champ and champ.group("champ").strip() in secrets:
            fautes.append(f"« {etape} » : aucun mot de passe ne se saisit dans un test qui ne porte pas sur la connexion")
    return fautes


def champs_secrets(annuaire) -> frozenset[str]:
    """Les noms et libellés des champs de mot de passe relevés par l'exploration (`litteraux_observes.Annuaire`)."""
    return frozenset(getattr(annuaire, "champs_mot_de_passe", None) or ())
