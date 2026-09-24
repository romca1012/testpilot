# language: fr
Fonctionnalité: Créer une opportunité

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "crm" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Nominal] L'opportunité créée existe
    Quand je crée une opportunité de test
    Alors l'opportunité créée existe avec son nom
