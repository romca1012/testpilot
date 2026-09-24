# language: fr
Fonctionnalité: Le total d'une commande est la somme de ses lignes

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "sale_management" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Nominal] Le total de la commande est cohérent avec ses lignes
    Soit un devis de 2 unités est créé pour un client de test
    Alors le total de la commande égale la somme des lignes
