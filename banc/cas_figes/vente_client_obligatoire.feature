# language: fr
Fonctionnalité: Une commande sans client est refusée

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "sale_management" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Erreur] La création d'une commande sans client est refusée
    Quand je tente de créer une commande de vente sans client
    Alors la création de la commande est refusée
