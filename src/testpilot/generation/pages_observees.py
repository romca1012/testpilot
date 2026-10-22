"""Étape 5 du plan unique (AV-2, interrupteur `TESTPILOT_IA_INFORMEE`) — les pages que le cas vise, telles que l'exploration
les a relevées : tous leurs champs (nom technique, libellé, type, obligatoire, contraintes), leurs boutons et leurs liens.

Pourquoi : la cartographie du projet connaissait ces noms exacts, mais ne servait qu'à REFUSER après coup ce que l'IA avait
inventé (`LITTERAL_NON_OBSERVE` : 8 à 12 refus par campagne, chacun un tour et un coût de plus). On les MONTRE avant qu'elle
écrive. Règle inchangée (D26, condition 4) : ce qui est OBSERVÉ sert à savoir OÙ aller et QUOI toucher ; ce qu'un test
VÉRIFIE vient du cas validé. La cartographie ne porte que des noms (champs, boutons, liens, titres, en-têtes de colonnes ;
les textes à chiffres sont écartés à l'exploration) ; un titre sans chiffre peut encore être une valeur (nom d'un produit en
tête de sa fiche) : même exposition que le texte des liens, déjà montré.

Module PUR : aucune I/O, aucun LLM. Choix des pages : celles que le plan vise (routes, adresse d'entrée — issues de l'analyse
de la spécification, un modèle de langage) ; à défaut, celles dont les noms rencontrent le TEXTE DU CAS validé par une
personne. Ce choix ne décide d'aucun verdict (il ne fait que montrer des pages). Jamais plus de `MAX_PAGES`, chacune
plafonnée — l'exploration n'a plus de limite de pages, le message ne doit pas grossir avec elle.
"""

from __future__ import annotations

import re
import unicodedata

MAX_PAGES = 4
MAX_CHAMPS = 30
MAX_BOUTONS = 20
MAX_LIENS = 20
MAX_CARACTERES = 6000
MAX_TITRES = 6
MAX_TABLEAUX = 4
_MOT_MIN = 4
# Un mot ou un lien présent sur plus de la moitié des pages est de la NAVIGATION COMMUNE (barre de menu, pied de page, suffixe
# du titre) : il ne dit rien de la page. Mesuré à sec sur le banc web (2026-10-22) : sans ce filtre, la barre de menu
# rattachait au cas « créer un client » les pages Contrôle d'accès et Panier.
_PART_COMMUNE = 0.5


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte or "") if unicodedata.category(c) != "Mn").lower()


def _mots(texte: str) -> set[str]:
    return {m for m in re.findall(r"[a-z0-9]+", _sans_accents(texte)) if len(m) >= _MOT_MIN}


def _noms_de_la_page(route: str, page: dict) -> set[str]:
    bouts = [route, page.get("titre") or ""]
    bouts += [c.get("label") or c.get("name") or "" for c in page.get("champs") or []]
    bouts += [a.get("label") or "" for a in page.get("actions") or []]
    bouts += [lien.get("text") or "" for lien in page.get("liens") or []]
    return _mots(" ".join(bouts))


def pages_visees(modele: dict | None, routes, texte_du_cas: str = "") -> list[str]:
    """Les routes de la cartographie à détailler : celles que le plan vise, sinon les mieux reliées au texte du cas."""
    from testpilot.generation.domain_model import _meme_route

    pages = (modele or {}).get("pages") or {}
    visees = [r for r in pages if any(_meme_route(r, str(u)) for u in routes or [] if u)]
    if visees:
        return visees[:MAX_PAGES]
    mots_du_cas = _mots(texte_du_cas)
    if not mots_du_cas:
        return []
    noms = {r: _noms_de_la_page(r, p) for r, p in pages.items()}
    communs = _communs(list(noms.values()))
    # Les mots de l'ADRESSE de la page ne sont jamais « communs » : « /panier » parle du panier, même si le lien « Panier » de la
    # barre de menu est sur toutes les pages (essai à sec : sans cela, le cas du panier ne recevait pas la page /panier).
    scores = sorted(((len(mots_du_cas & ((n - communs) | _mots(r))), r) for r, n in noms.items()),
                    key=lambda s: (-s[0], s[1]))
    meilleur = scores[0][0] if scores else 0
    # Seules les pages AUSSI liées au cas que la meilleure (au moins la moitié de son score) : un mot isolé partagé avec une
    # page sans rapport ne l'y ajoute pas (essai à sec du 2026-10-22 : la page de connexion revenait pour « créer un client »).
    return [r for score, r in scores if score > 0 and 2 * score >= meilleur][:MAX_PAGES]


def _communs(ensembles: list) -> set:
    """Ce qui revient sur plus de la moitié des pages (au moins trois pages : en deçà, rien n'est « commun »)."""
    if len(ensembles) < 3:
        return set()
    compte: dict = {}
    for ensemble in ensembles:
        for element in ensemble:
            compte[element] = compte.get(element, 0) + 1
    return {e for e, n in compte.items() if n > _PART_COMMUNE * len(ensembles)}


def _lien(lien: dict) -> tuple[str, str]:
    return (lien.get("text") or "").strip(), str(lien.get("href") or "")


def _liens_internes(page: dict) -> list[tuple[str, str]]:
    return [_lien(lien) for lien in page.get("liens") or [] if _lien(lien)[0] and _lien(lien)[1].startswith("/")]


def _champ(champ: dict, contraintes) -> str:
    nom = champ.get("name") or ""
    libelle = champ.get("label") or ""
    bouts = [f"`{nom}`" if nom else "(sans nom)"]
    if libelle:
        bouts.append(f"« {libelle} »")
    details = [champ.get("type") or champ.get("tag") or ""]
    if champ.get("required"):
        details.append("obligatoire")
    # Revue : la cartographie range les options en paires [valeur, libellé] (comme `prompt._section_domaine_mesure`).
    options = [str(o[0] if isinstance(o, (list, tuple)) and o else o) for o in (champ.get("options") or [])][:6]
    if options:
        details.append("choix : " + ", ".join(f"« {o} »" for o in options))
    texte = " ".join(bouts) + f" ({', '.join(d for d in details if d)})"
    return texte + contraintes(champ)


def section(modele: dict | None, routes, texte_du_cas: str = "", contraintes=lambda c: "") -> str:
    """La section « Pages observées », ou "" (aucune page reconnue : rien n'est inventé)."""
    pages = (modele or {}).get("pages") or {}
    choisies = pages_visees(modele, routes, texte_du_cas)
    if not choisies:
        return ""
    lignes = ["## Pages observées par l'exploration" + (f" (relevé du {modele['mesure_le']})"
                                                       if (modele or {}).get("mesure_le") else ""), "",
              "Les noms EXACTS des champs, boutons et liens de l'application : emploie-les tels quels. Ce sont des repères "
              "pour agir, jamais des résultats attendus — ce que le test vérifie vient du cas. Ce relevé n'est pas une "
              "preuve à citer dans evidence_ids.", ""]
    if any((pages.get(r) or {}).get("titres") or (pages.get(r) or {}).get("tableaux") for r in choisies):
        lignes += ["Un tableau se désigne (« le tableau \"<nom>\" … ») par sa légende ou son nom, sinon par le titre qui le "
                   "précède, recopié À L'IDENTIQUE, casse comprise. Un tableau qui n'était pas affiché à l'exploration (aucune "
                   "donnée) n'y figure pas : désigne-le par le titre de sa page.", ""]
    titres_communs = _communs([set((p.get("titres") or [])) for p in pages.values()])
    liens_communs = _communs([set(_liens_internes(p)) for p in pages.values()])
    boutons_communs = _communs([{a.get("label") for a in p.get("actions") or [] if a.get("label")} for p in pages.values()])
    if liens_communs or boutons_communs:
        bouts = [f"« {t} » → {h}" for t, h in sorted(liens_communs, key=lambda x: x[1])] + [
            f"bouton « {b} »" for b in sorted(boutons_communs)]
        lignes += ["Sur presque toutes les pages : " + ", ".join(bouts[:MAX_LIENS]) + ".", ""]
    for route in choisies:
        page = pages.get(route) or {}
        titre = page.get("titre") or ""
        lignes.append(f"### {route}" + (f" — « {titre} »" if titre else ""))
        titres = [t for t in page.get("titres") or [] if t and t not in titres_communs][:MAX_TITRES]
        if titres:
            lignes.append("- Titres : " + ", ".join(f"« {t} »" for t in titres))
        tableaux = [t for t in page.get("tableaux") or [] if isinstance(t, dict)][:MAX_TABLEAUX]
        for tableau in tableaux:
            colonnes = ", ".join(f"« {c} »" for c in (tableau.get("colonnes") or [])[:12])
            nom = f"« {tableau['nom']} »" if tableau.get("nom") else "sans nom (désigne-le par le titre qui le précède)"
            lignes.append(f"- Tableau {nom}" + (f" — colonnes {colonnes}" if colonnes else ""))
        champs = [c for c in page.get("champs") or [] if c.get("visible", True)][:MAX_CHAMPS]
        if champs:
            lignes.append("- Champs :")
            lignes += [f"  - {_champ(c, contraintes)}" for c in champs]
        boutons = [a for a in page.get("actions") or [] if a.get("label") and a.get("visible", True)
                   and a["label"] not in boutons_communs][:MAX_BOUTONS]
        if boutons:
            lignes.append("- Boutons : " + ", ".join(
                f"« {a['label']} »" + (" (envoie le formulaire)" if a.get("soumet") else "") for a in boutons))
        liens = [lien for lien in _liens_internes(page) if lien not in liens_communs][:MAX_LIENS]
        if liens:
            lignes.append("- Liens : " + ", ".join(f"« {t} » → {h}" for t, h in liens))
        lignes.append("")
    texte = "\n".join(lignes).rstrip()
    if len(texte) > MAX_CARACTERES:
        texte = texte[:MAX_CARACTERES].rsplit("\n", 1)[0] + "\n(relevé tronqué)"
    return texte
