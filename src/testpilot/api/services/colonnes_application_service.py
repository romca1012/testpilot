"""Remplir, au lancement, les colonnes de données de test dont la source est l'application (étape 6, IT-4, A55).

La partie pure (validation, choix des valeurs, itérations) est dans `parametres/colonne_application.py` ; ici, la LECTURE de
l'application — l'oracle déclaré du projet (requête GET), ou Odoo par RPC — contre l'application de l'environnement de la
campagne, jamais une autre. Lecture seule : rien n'est écrit dans l'application.

Derrière l'interrupteur `TESTPILOT_COLONNE_DEPUIS_L_APPLICATION` (éteint) tant que le porteur n'a pas tranché combien
d'enregistrements et lesquels (A105) : éteint, une source déclarée est ignorée et la variable garde ses valeurs saisies.
"""

from __future__ import annotations

import logging

from testpilot.parametres import colonne_application as ca

logger = logging.getLogger(__name__)


def lire_les_valeurs(projet: dict, source: dict) -> list:
    """Les valeurs BRUTES de la source, dans l'ordre de l'application. Lève `ColonneImpossible` (application injoignable,
    réponse d'une autre forme) — jamais une liste vide inventée à la place d'une panne."""
    if source.get("type") == ca.TYPE_ORACLE:
        from testpilot.connectors.oracle_http import OracleHttp
        from testpilot.connectors.runtime_env import _config_oracle

        config = _config_oracle(projet or {})
        if config is None:
            raise ca.ColonneImpossible("le projet n'a plus d'oracle déclaré")
        requete = next((q for q in config["queries"] if isinstance(q, dict) and q.get("name") == source["requete"]), None)
        if requete is None or str(requete.get("method") or "GET").upper() != "GET":
            # Revue : seule une requête de LECTURE est jouée — sa méthode a pu changer depuis la saisie de la source.
            raise ca.ColonneImpossible(f"« {source['requete']} » n'est plus une requête de lecture (GET) de l'oracle")
        try:
            reponse = OracleHttp(config["base_url"], config["auth"], config["queries"]).executer(source["requete"])
        except Exception as exc:   # injoignable, requête retirée depuis, réponse illisible : la colonne n'est pas remplie
            raise ca.ColonneImpossible(f"l'oracle n'a pas répondu à « {source['requete']} » ({exc})") from exc
        return ca.valeurs_de_la_reponse(reponse, source.get("chemin") or "", source["cle"])
    if source.get("type") == ca.TYPE_ODOO:
        from testpilot.connectors.odoo import OdooConnector

        connecteur = OdooConnector.from_project(projet)
        try:
            connecteur.connect()
            ids = connecteur.search(source["modele"], [], limit=max(source.get("nombre") or 1, 1) * 3)
            lignes = connecteur.read(source["modele"], ids, [source["champ"]]) if ids else []
        except Exception as exc:
            raise ca.ColonneImpossible(f"Odoo n'a pas rendu « {source['modele']}.{source['champ']} » ({exc})") from exc
        finally:
            try:
                connecteur.disconnect()
            except Exception:
                logger.warning("[colonnes] déconnexion d'Odoo impossible", exc_info=True)
        par_id = {ligne.get("id"): ligne.get(source["champ"]) for ligne in lignes}
        return [par_id.get(i) for i in ids]
    raise ca.ColonneImpossible(f"source inconnue « {source.get('type')} »")


def relever_les_colonnes(conn, projet: dict | None, *, lecteur=None) -> dict[str, list[str]]:
    """Au LANCEMENT : `{nom: valeurs}` de chaque colonne à source, relevées sur `projet` (l'application de l'environnement de
    la campagne). Interrupteur éteint ou aucun projet : `{}`. Lève `ColonneImpossible` (colonne vide, source illisible,
    application injoignable : le lancement n'a pas lieu)."""
    from testpilot.generation import interrupteurs
    from testpilot.store.repositories import TestDataRepo

    if not projet or not interrupteurs.colonne_depuis_l_application_actif():
        return {}
    lecteur = lecteur or lire_les_valeurs   # lu à l'appel : remplaçable en test
    colonnes = {}
    for nom, texte in TestDataRepo(conn).sources_des_variables(projet["id"]).items():
        source = ca.lire_source(texte)
        if not source:
            continue
        valeurs = ca.valeurs_retenues(lecteur(projet, source), int(source.get("nombre") or ca.NOMBRE_PAR_DEFAUT))
        if not valeurs:
            raise ca.ColonneImpossible(f"la colonne « {nom} » n'a trouvé aucun enregistrement dans l'application")
        colonnes[nom] = valeurs
    return colonnes
