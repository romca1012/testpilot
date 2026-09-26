"""Steps propres au connecteur `web` générique (Playwright + application web quelconque).

Un dossier par connecteur (audit DA du 2026-08-13) : ces steps ne sont copiés et proposés à l'agent
que pour un projet `web`. Le libellé « je me connecte avec mes identifiants utilisateur » existe
AUSSI côté `odoo/` avec un autre geste (connexion Odoo) : les deux dossiers ne sont jamais chargés
ensemble (`BehaveRunner._steps_library_files` : `generic/` + UN connecteur).
"""
from behave import given, when
from _base_helpers import connexion_web_utilisateur, se_connecter_en_tant_que


@given('je me connecte avec mes identifiants utilisateur')
@when('je me connecte avec mes identifiants utilisateur')
def step_login_web(context):
    """CONNECTE le navigateur avec l'identifiant et le mot de passe du projet — pour une connexion EN MILIEU de parcours (reconnexion après déconnexion) ; à l'ouverture, « j'accède à la page d'accueil de l'application » connecte déjà tout seul.

    ⚠️ Délègue à `_base_helpers.connexion_web_utilisateur`, qui délègue elle-même à la détection
    de l'exploration (`tenter_connexion_generique`) — NE RÉIMPLÉMENTE JAMAIS la connexion ici.
    Échec de connexion → prérequis non rempli (« bloqué »), jamais un défaut de l'application.
    """
    connexion_web_utilisateur(context, explicite=True)


@given('je me connecte en tant que "{libelle}"')
@when('je me connecte en tant que "{libelle}"')
def step_connect_as(context, libelle):
    """Change d'utilisateur : NOUVEAU contexte navigateur, page d'accueil du projet, puis connexion avec le compte `libelle`, déclaré sur le projet (« principal » = le compte de la connexion du projet). Compte inconnu ou connexion refusée → prérequis manquant (« bloqué »), jamais un défaut de l'application. N'écris JAMAIS un identifiant ni un mot de passe dans un scénario : seuls les libellés déclarés existent."""
    se_connecter_en_tant_que(context, libelle, connecteur="web")
