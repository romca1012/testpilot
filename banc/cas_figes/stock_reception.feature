# language: fr
Fonctionnalité: Un achat confirmé crée une réception

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "stock" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Nominal] L'achat confirmé crée une réception
    Soit une demande de prix de 3 unités est créée
    Quand je confirme la demande de prix
    Alors une réception est liée à la commande d'achat
