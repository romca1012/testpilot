# language: fr
Fonctionnalité: Confirmer une demande de prix crée un bon de commande

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "purchase" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Nominal] La demande de prix confirmée devient un bon de commande
    Soit une demande de prix de 3 unités est créée
    Quand je confirme la demande de prix
    Et je désigne la commande d'achat comme enregistrement courant
    Alors le champ "state" de cet enregistrement dans le modèle "purchase.order" est égal à "purchase"
