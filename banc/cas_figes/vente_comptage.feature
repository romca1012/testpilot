# language: fr
Fonctionnalité: Créer une commande augmente le nombre de commandes de 1

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "sale_management" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Nominal] Une commande créée augmente le nombre de commandes de 1
    Soit le nombre d'enregistrements dans le modèle "sale.order" est enregistré pour comparaison
    Quand je crée une commande de vente pour un client de test
    Alors le nombre total d'enregistrements dans le modèle "sale.order" augmente de 1
