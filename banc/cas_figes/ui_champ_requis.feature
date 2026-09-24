# language: fr
Fonctionnalité: Un champ requis vide affiche une erreur visible

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "sale_management" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Erreur] Confirmer un devis sans client affiche une erreur
    Soit je me connecte avec mes identifiants utilisateur
    Et je navigue vers l'URL du portail "/web#action=sale.action_quotations_with_onboarding"
    Quand je clique sur le bouton "Nouveau"
    Et je clique sur le bouton "Confirmer"
    Alors une notification d'erreur de validation est affichée dans l'interface Odoo
