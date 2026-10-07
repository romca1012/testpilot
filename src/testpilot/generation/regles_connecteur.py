"""Règles du connecteur injectées dans le prompt de génération (lot Q3, décision D20).

⚠️ **Derrière un interrupteur ÉTEINT** (`TESTPILOT_REGLES_CONNECTEUR`), comme le reste de Q3-a : ce que l'API reçoit
ne change pas tant qu'une mesure du banc (Q2) n'a pas montré que ça améliore sans régresser.

⚠️ **Par connecteur, jamais par client** (D20, CLAUDE.md §6) : rien ici ne nomme Sapian, SauceDemo ni l'application du
banc. Chaque règle vient d'un défaut MESURÉ, daté, et vaut pour toute application servie par ce connecteur.

Module PUR : aucune I/O hors lecture de `os.environ` (via `interrupteurs`).
"""

from __future__ import annotations

from collections.abc import Mapping

from testpilot.generation import interrupteurs

# Défaut mesuré le 2026-10-07 (banc d'agents, campagne base-1) : sur un projet à UN seul compte, l'agent ne reçoit aucune
# consigne sur les comptes ; il a écrit un mot de passe de sa tête (« testeur »), l'application l'a refusé à juste titre, et le
# verdict sortait `non_conforme` sur une application saine (faux rouge). Le step « je me connecte en tant que "principal" »
# existe pour les connecteurs `web` et `odoo` : il n'était simplement pas annoncé.
REGLE_COMPTE_PRINCIPAL = (
    "Pour te connecter dans un scénario (test de connexion, ou retour à l'écran de connexion), écris "
    "`Quand je me connecte en tant que \"principal\"` : c'est le compte du projet. N'écris JAMAIS d'identifiant "
    "ni de mot de passe, même d'exemple : tu ne les connais pas et une valeur inventée fait échouer la connexion."
)

# Défauts mesurés le 2026-10-07 (campagne base-1) : (1) un test a écrit `context.base_url` dans du code de step — un attribut
# qui n'existe pas (AttributeError, technical_error) ; (2) un test a cliqué sur « Ajouter … au panier » une seconde fois en
# supposant rester sur la même page, alors que l'application avait navigué (ElementIntrouvableError).
REGLES_WEB = (
    "- Ne fais AUCUN appel HTTP direct dans le code d'un step (pas de `requests`, pas de `context.base_url`, pas de "
    "`page.request`) : la vérification côté serveur passe par les steps d'oracle, avec les NOMS de requêtes listés "
    "dans le prompt. Sans oracle déclaré, ne promets pas de vérification serveur.\n"
    "- Une action qui envoie un formulaire ou ajoute un élément peut changer de page. Avant d'enchaîner une seconde "
    "action, regarde la page d'ARRIVÉE (`inspect_page_snapshot`), pas celle de départ."
)


def regles_actives(env: Mapping[str, str] | None = None) -> bool:
    return interrupteurs.regles_connecteur_actif(env)


def regles_web(env: Mapping[str, str] | None = None) -> str:
    """Le texte de `GenericWebConnector.rules()` ; vide tant que l'interrupteur est éteint."""
    if not regles_actives(env):
        return ""
    return REGLE_COMPTE_PRINCIPAL + "\n" + REGLES_WEB
