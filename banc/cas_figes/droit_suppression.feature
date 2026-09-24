# language: fr
Fonctionnalité: Un commercial ne supprime pas une commande confirmée

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "sale_management" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Erreur] La suppression d'une commande confirmée est refusée au commercial
    Soit une commande confirmée appartient au compte commercial
    Quand le compte commercial tente de supprimer la commande confirmée
    Alors la suppression est refusée et la commande existe toujours
