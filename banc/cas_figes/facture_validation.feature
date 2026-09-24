# language: fr
Fonctionnalité: Valider une facture la passe à l'état « Comptabilisé »

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "account" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Nominal] La facture validée est comptabilisée
    Soit une facture client brouillon de 50 euros est créée
    Quand je valide la facture
    Alors la facture est comptabilisée
