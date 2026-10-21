"""Étape 4, morceau 6 (A69 révisée, porteur 2026-10-21) : UNE carte de l'application, qui dit quel compte voit quoi.

L'exploration passe par le compte principal puis par chaque compte déclaré. Ce module, PUR (aucune I/O, aucun LLM), réunit
leurs relevés en une seule carte : toutes les routes, et pour chacune — et pour chaque champ, bouton, menu — les comptes
qui la voient. Le porteur : « le but n'est pas de faire une séparation, mais d'en tirer toutes les routes nécessaires et
d'en distinguer par rapport au compte lors de l'exécution d'un cas ».

Deux garanties, testées (`tests/test_carte_des_comptes.py`) :
1. RIEN ne se perd ni ne s'altère : `vue_du_compte(carte, X)` rend EXACTEMENT le relevé de X (même forme qu'aujourd'hui).
   La carte n'invente pas un champ commun en mêlant les attributs de deux comptes (une liste aux options différentes
   reste propre à chaque relevé).
2. L'ABSENCE n'est un fait que pour un compte exploré EN ENTIER, dont la session a été revérifiée en fin de parcours
   (`absence_fiable` du relevé) : « Lecteur ne voit pas ce menu » n'est vrai qu'à ces conditions. Un compte en échec,
   arrêté, à la session perdue, explorée par un connecteur qui ne sait pas la revérifier, ou une page sautée par son propre
   regroupement (A82) : `voit` rend `None` (inconnu) — jamais `False`, qui ferait conclure à tort « ce compte n'a pas le
   droit ».

Les comptes ne sont connus ici que par leur LIBELLÉ (règle D8 : aucun identifiant de connexion, aucun secret).
"""

from __future__ import annotations

import copy

PRINCIPAL = "principal"


def _cle_du_champ(champ: dict) -> str:
    return f"{champ.get('name', '')}|{champ.get('identifie_par', '')}|{champ.get('tag', '')}"


def fusionner(releves: list[tuple[str, dict]], *, en_echec: list[dict] | None = None,
              incomplets: list[str] | None = None) -> dict:
    """`releves` : `[(libellé, relevé)]`, le principal d'abord, dans l'ordre d'exploration — seulement les comptes dont la
    connexion a été CONFIRMÉE. `en_echec` : `[{"libelle", "message"}]`. `incomplets` : les libellés dont l'exploration a été
    arrêtée en route (A83) — leur relevé compte pour « vu », jamais pour « pas vu »."""
    ordre = [libelle for libelle, _ in releves]
    rangs = {libelle: i for i, libelle in enumerate(ordre)}
    routes: dict[str, dict] = {}
    menus: dict[str, dict] = {}
    menus_inconnus: list[str] = []
    fiables: list[str] = []
    familles: dict[str, list[str]] = {}

    def noter(dico: dict, cle: str, libelle: str, **autres) -> dict:
        entree = dico.setdefault(cle, {"vu_par": [], **{k: [] for k in autres}})
        if libelle not in entree["vu_par"]:
            entree["vu_par"].append(libelle)
        for k, vrai in autres.items():
            if vrai and libelle not in entree[k]:
                entree[k].append(libelle)
        return entree

    for libelle, releve in releves:
        for route, page in ((releve or {}).get("pages") or {}).items():
            entree = routes.setdefault(route, {"vu_par": [], "champs": {}, "actions": {}})
            if libelle not in entree["vu_par"]:
                entree["vu_par"].append(libelle)
            for champ in page.get("champs") or []:
                noter(entree["champs"], _cle_du_champ(champ), libelle, visible_pour=bool(champ.get("visible")))
            for action in page.get("actions") or []:
                noter(entree["actions"], str(action.get("label") or ""), libelle, visible_pour=bool(action.get("visible")))
        # Les menus que CE compte voit (`menus_visibles` : clé stable + chemin) ; `None` = non lus : inconnus.
        if (releve or {}).get("menus_visibles") is None:
            menus_inconnus.append(libelle)
        for menu in (releve or {}).get("menus_visibles") or []:
            noter(menus, str(menu.get("cle") or ""), libelle).setdefault("chemin", menu.get("chemin") or "")
        if (releve or {}).get("absence_fiable"):
            fiables.append(libelle)
        familles[libelle] = [k[: -len("/…")] for k in ((releve or {}).get("familles") or {})]

    def tri(libelles: list[str]) -> list[str]:
        # Le principal d'abord, puis l'ordre d'exploration — un affichage stable, quel que soit l'ordre des relevés.
        return sorted(libelles, key=lambda x: (x != PRINCIPAL, rangs.get(x, len(rangs)), x))

    for entree in routes.values():
        entree["vu_par"] = tri(entree["vu_par"])
        for sous in (entree["champs"], entree["actions"]):
            for e in sous.values():
                e["vu_par"], e["visible_pour"] = tri(e["vu_par"]), tri(e["visible_pour"])
    for e in menus.values():
        e["vu_par"] = tri(e["vu_par"])

    incomplets = [x for x in (incomplets or []) if x in rangs]
    return {
        "comptes_explores": ordre,
        "comptes_complets": [x for x in ordre if x not in incomplets and x in fiables],
        "familles_par_compte": familles,
        "comptes_incomplets": incomplets,
        "comptes_en_echec": list(en_echec or []),
        "menus_inconnus": menus_inconnus,
        "routes": dict(sorted(routes.items())),
        "menus": dict(sorted(menus.items())),
        "releves": {libelle: copy.deepcopy(releve) for libelle, releve in releves},
    }


def vue_du_compte(carte: dict, libelle: str) -> dict | None:
    """Le relevé d'UN compte, dans la forme lue aujourd'hui par la génération (`pages`, `transitions`, `modeles_backoffice`…).
    `None` si ce compte n'a pas été exploré — jamais la vue d'un autre compte à sa place (ce serait lui prêter des écrans)."""
    releve = ((carte or {}).get("releves") or {}).get(libelle)
    return copy.deepcopy(releve) if releve is not None else None


def voit(carte: dict, libelle: str, route: str, *, champ: dict | None = None, menu: str | None = None) -> bool | None:
    """Ce compte voit-il cette route (ou ce champ de cette route, ou ce menu — sa clé stable ou son chemin) ? `True` :
    observé. `False` : PAS observé alors que ce compte a été exploré EN ENTIER (et, pour un menu, que ses menus ont été lus).
    `None` : on ne sait pas (compte non exploré, en échec, arrêté en route, ou menus illisibles)."""
    carte = carte or {}
    if libelle not in (carte.get("comptes_explores") or []):
        return None
    if menu is not None:
        if libelle in (carte.get("menus_inconnus") or []):
            return None
        menus = carte.get("menus") or {}
        entree = menus.get(menu) or next((e for e in menus.values() if e.get("chemin") == menu), None)
        if entree is None:
            return None   # ni cette clé ni ce chemin (peut-être dans une autre langue) : on ne sait pas, jamais « ne voit pas »
        vu = libelle in entree.get("vu_par", [])
    else:
        entree = (carte.get("routes") or {}).get(route) or {}
        if champ is not None:
            vu = libelle in ((entree.get("champs") or {}).get(_cle_du_champ(champ)) or {}).get("vu_par", [])
        else:
            vu = libelle in entree.get("vu_par", [])
    if vu:
        return True
    if menu is None:
        from testpilot.generation.familles_de_pages import adresse_parente
        if adresse_parente(route) in ((carte.get("familles_par_compte") or {}).get(libelle) or []):
            return None   # une sœur que le regroupement de CE compte n'a pas visitée : pas vue, pas pour autant absente
    return False if libelle in (carte.get("comptes_complets") or []) else None
