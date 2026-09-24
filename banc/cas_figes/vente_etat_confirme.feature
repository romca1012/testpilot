# language: fr
Fonctionnalité: Une commande confirmée passe à l'état « Bon de commande »

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "sale_management" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Nominal] La commande confirmée est à l'état Bon de commande
    Soit un devis de 2 unités est créé pour un client de test
    Quand je confirme le devis
    Et je désigne la commande de vente comme enregistrement courant
    Alors le champ "state" de cet enregistrement dans le modèle "sale.order" est égal à "sale"
