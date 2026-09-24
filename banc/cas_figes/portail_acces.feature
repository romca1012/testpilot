# language: fr
Fonctionnalité: L'espace personnel du portail est accessible

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "sale_management" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Nominal] L'espace personnel du portail s'affiche
    Quand je navigue vers l'URL du portail "/my"
    Alors l'espace personnel du portail est affiché
