# language: fr
Fonctionnalité: Confirmer un devis crée un bon de livraison

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "sale_management" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Nominal] La confirmation du devis crée le bon de livraison
    Soit un devis de 2 unités est créé pour un client de test
    Quand je confirme le devis
    Alors un bon de livraison est lié à la commande de vente
