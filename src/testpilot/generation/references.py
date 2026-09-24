"""Références inexistantes dans un `.feature` (lot 12, décision D11, 2026-09-24).

⚠️ **Le défaut mesuré** (campagne réelle du 23/09, cas 13) : un produit halluciné (« PC Portable HP »)
absent du catalogue réel gaspille un run entier. Un refus DÉTERMINISTE à l'écriture coûte moins.

⚠️ **Bloquant seulement quand la source FAIT AUTORITÉ, détectif sinon** (D11) :

- champ relationnel Odoo → `name_search` RPC : le serveur EST la source de vérité ;
- `<select>` dont TOUTES les options ont été relevées par `inspect_page_form` ;
- les listes de produits web et les autocomplétions non exhaustives (pagination, valeurs créées
  par le scénario) ne font autorité pour rien : avis détectif (`smoke_check.check_produits_observes`).

Jamais de refus pour une valeur **créée plus tôt dans le même scénario** (elle n'existe pas encore
dans la source) ni **marquée « rendue unique pour cette tentative »**. Une source injoignable
(RPC en échec) ne refuse rien : un contrôle qui ne peut pas juger ne condamne pas.

Le message de refus donne les 5 valeurs réelles les plus proches (`difflib`) : de quoi corriger
sans deviner à nouveau.
"""

from __future__ import annotations

import re

from testpilot.generation.smoke_check import _extraire_champ_valeur, _scenarios, plus_proches

_LIMITE_PROPOSITIONS = 200
# Paramètre de Scénario Plan (`<client>`) : une valeur de gabarit, pas une valeur saisie.
_PARAMETRE = re.compile(r"<[^<>]+>")


def _cree_plus_tot(valeur: str, lignes_avant: list[str]) -> bool:
    cite = f'"{valeur}"'
    return any(cite in ligne for ligne in lignes_avant)


def verifier_references(feature_content: str, options_select: dict, champs_relationnels: dict,
                        name_search) -> list[dict]:
    """Les références PROUVÉES inexistantes : `[{champ, valeur, ligne, source, proches}]`.

    `options_select` : `{champ: {valeurs et libellés}}` ; `champs_relationnels` : `{champ:
    {modèle lié, …}}` (ambigu si plusieurs → ignoré) ; `name_search(modèle, texte, limite)` →
    liste de `(id, nom affiché)` ou lève (source injoignable → aucun refus).
    """
    refus: list[dict] = []
    for _titre, ligne0, lignes in _scenarios(feature_content):
        for i, ligne in enumerate(lignes):
            trouve = _extraire_champ_valeur(ligne)
            if not trouve:
                continue
            champ, valeur = trouve
            if (not valeur.strip() or "rendue unique" in ligne or _PARAMETRE.search(valeur)
                    or _cree_plus_tot(valeur, lignes[:i])):
                continue
            numero = ligne0 + i + 1
            options = options_select.get(champ)
            if options:
                if valeur not in options:
                    refus.append({"champ": champ, "valeur": valeur, "ligne": numero,
                                  "source": "<select> dont toutes les options ont été relevées",
                                  "proches": plus_proches(valeur, options)})
                continue
            modeles = champs_relationnels.get(champ) or set()
            if len(modeles) != 1 or name_search is None:
                continue
            (modele,) = modeles
            try:
                if name_search(modele, valeur, 1):
                    continue
                proches = plus_proches(valeur, [nom for _id, nom in
                                                name_search(modele, "", _LIMITE_PROPOSITIONS)])
            except Exception:
                continue  # source injoignable : on ne condamne pas
            refus.append({"champ": champ, "valeur": valeur, "ligne": numero,
                          "source": f"name_search RPC sur « {modele} »", "proches": proches})
    return refus


def message_refus(refus: list[dict]) -> str:
    morceaux = []
    for r in refus[:4]:
        proches = ", ".join(f"« {p} »" for p in r["proches"]) or "aucune valeur réelle relevée"
        morceaux.append(f"ligne {r['ligne']} : « {r['valeur']} » n'existe pas pour le champ "
                        f"« {r['champ']} » (source : {r['source']}). Valeurs réelles les plus "
                        f"proches : {proches}.")
    return ("[write_feature_file] REFERENCE_INEXISTANTE : " + " ".join(morceaux)
            + " Corrige la valeur avec une valeur réelle, puis rappelle write_feature_file.")
