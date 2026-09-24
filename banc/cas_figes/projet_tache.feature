# language: fr
Fonctionnalité: Créer une tâche dans un projet

  Contexte:
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Et la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le module Odoo "project" est installé et actif sur la base définie dans "ODOO_DB"

  Scénario: [Nominal] La tâche créée est rattachée au projet
    Soit un projet de test existe
    Quand je crée une tâche dans ce projet
    Alors la tâche est rattachée au projet
