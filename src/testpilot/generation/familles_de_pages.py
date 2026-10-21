"""Étape 4, morceau 6 (A81, A82 — porteur 2026-10-21) : une exploration COMPLÈTE, sans limite de pages, qui finit quand même.

Il n'y a plus de plafond (les 60 pages tronquaient : projet 18 arrêté à exactement 60). L'exploration visite chaque MODÈLE de
page une fois. Les numéros étaient déjà regroupés (`/commande/12` et `/commande/57` → `/commande/{id}`) ; une boutique dont les
fiches s'appellent `/produit/chaussure-rouge`, `/produit/sac-noir`… faisait pourtant visiter ses 5 000 produits un par un.

A82 : des pages SŒURS (même adresse parente) dont la STRUCTURE est identique — mêmes champs, mêmes formulaires, mêmes boutons,
mêmes destinations de liens — forment un seul modèle une fois 3 exemples vus ; les sœurs suivantes ne sont plus visitées, mais
comptées, et le détail de l'exploration le dit (« /produit/… : 1 modèle, 3 exemples visités, 4 997 pages du même modèle »).

Dans le doute, on NE regroupe PAS (le coût est du temps, jamais un trou silencieux dans la carte). Une sœur n'est sautée que
si TOUT ceci est vrai — sinon elle est visitée :
- les sœurs déjà visitées (au moins 3) ont TOUTES la même structure (deux structures = famille hétérogène) ;
- la sœur a été trouvée sur une vraie LISTE : la page qui y mène renvoie vers au moins 10 sœurs de la même adresse parente
  (un menu d'administration — `/admin/utilisateurs`, `/admin/groupes`, `/admin/parametres` — n'est pas une liste) ;
- son nom ET celui des exemples ressemblent à des identifiants — un chiffre, ou au moins deux séparateurs
  (`article-12`, `p42`, `chaussure-rouge-cuir`) : des noms de rubriques (`parametres`, `email-templates`) sont des pages
  distinctes (seconde revue : un seul tiret est la norme des adresses, il ne dit rien) (revue du 2026-10-21 : décider sans avoir visité la page
  pouvait sauter un formulaire de paramètres rangé parmi des listes) ;
- la racine du site n'est jamais une famille (`/contact`, `/tarifs`, `/connexion`) ;
- un libellé de bouton ou une destination de lien qui change d'une page à l'autre suffit à distinguer deux structures.

Module PUR : aucune I/O, aucun navigateur, aucun LLM.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

SEUIL_EXEMPLES = 3
SEUIL_LISTE = 10   # une page qui renvoie vers au moins 10 sœurs est une liste ; en dessous, un menu : tout est visité
def _ressemble_a_un_identifiant(route: str) -> bool:
    nom = route.rstrip("/").rsplit("/", 1)[-1]
    return bool(re.search(r"\d", nom)) or len(re.findall(r"[-_]", nom)) >= 2


def adresse_parente(route: str) -> str | None:
    """`/produit/sac-noir` → `/produit`. `None` pour une page à la racine (`/contact`) ou la racine elle-même : jamais une
    famille. Une route dont le dernier segment est déjà un numéro (`/commande/{id}`) est déjà un modèle : `None`."""
    morceaux = [m for m in (route or "").split("/") if m]
    if len(morceaux) < 2 or morceaux[-1] == "{id}":
        return None
    return "/" + "/".join(morceaux[:-1])


def _prefixe(href: str, route: str) -> str | None:
    href = (href or "").strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    cible = urlparse(urljoin(route, href))   # résolu comme le navigateur le ferait depuis cette page
    morceaux = [m for m in (cible.path or "/").split("/") if m]
    return cible.netloc + ("/" + "/".join(morceaux[:-1]) if morceaux else "/")


def structure(infos: dict, route: str) -> str:
    """L'empreinte de ce que la page PERMET de faire, sans son contenu : champs (identifiant, balise, type), formulaires
    (méthode, nombre de champs), boutons (libellé), et l'adresse parente de chaque lien interne."""
    champs = sorted({(c.get("name", ""), c.get("tag", ""), c.get("type", "")) for c in infos.get("champs") or []})
    formulaires = sorted({(f.get("method", ""), int(f.get("champs") or 0)) for f in infos.get("formulaires") or []})
    boutons = sorted({str(a.get("label") or "") for a in infos.get("actions") or []})
    liens = sorted({p for p in (_prefixe(lien.get("href"), route) for lien in infos.get("liens") or []) if p})
    return json.dumps([champs, formulaires, boutons, liens], ensure_ascii=False)


class Regroupement:
    """Suit, pendant un crawl, les pages sœurs déjà vues ; dit quelles sœurs ne sont plus à visiter."""

    def __init__(self, seuil: int = SEUIL_EXEMPLES) -> None:
        self.seuil = seuil
        self._vues: dict[str, dict[str, list[str]]] = {}   # adresse parente → structure → routes visitées
        self._ignorees: dict[str, set[str]] = {}           # adresse parente → routes sœurs non visitées

    def noter(self, route: str, infos: dict) -> None:
        parente = adresse_parente(route)
        if parente is None:
            return
        routes = self._vues.setdefault(parente, {}).setdefault(structure(infos, route), [])
        if route not in routes:
            routes.append(route)

    def _famille(self, parente: str) -> list[str] | None:
        structures = self._vues.get(parente) or {}
        if len(structures) != 1:
            return None   # aucune page vue, ou une famille hétérogène : on visite tout
        exemples = next(iter(structures.values()))
        return exemples if len(exemples) >= self.seuil else None

    def a_ignorer(self, route: str, soeurs_liees: int = 0) -> bool:
        """`True` si `route` est une sœur d'une famille déjà regroupée, jamais visitée : elle est comptée, pas visitée.
        `soeurs_liees` : combien de sœurs de cette adresse parente la page qui a mené à `route` liste (voir `SEUIL_LISTE`)."""
        parente = adresse_parente(route)
        exemples = self._famille(parente) if parente is not None else None
        if exemples is None or route in exemples or soeurs_liees < SEUIL_LISTE:
            return False
        if not _ressemble_a_un_identifiant(route) or not all(_ressemble_a_un_identifiant(e) for e in exemples):
            return False
        self._ignorees.setdefault(parente, set()).add(route)
        return True

    def bilan(self) -> dict:
        """`{"/produit/…": {"exemples": [...], "pages_du_meme_modele": N}}` — pour le détail de l'exploration."""
        return {f"{parente}/…": {"exemples": list(self._famille(parente) or []), "pages_du_meme_modele": len(ignorees)}
                for parente, ignorees in sorted(self._ignorees.items()) if self._famille(parente)}
