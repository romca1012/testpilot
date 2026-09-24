# language: fr
Fonctionnalité: Ouvrir un onglet d'un formulaire ne déclenche aucun faux refus

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "sale_management" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Nominal] L'onglet d'un formulaire s'ouvre sans faux refus
    Soit je me connecte avec mes identifiants utilisateur
    Et je navigue vers l'URL du portail "/web#action=sale.action_quotations_with_onboarding"
    Quand je clique sur le bouton "Nouveau"
    Et je clique sur le bouton "Autres informations"
    Alors l'onglet Autres informations est affiché
