# 0005 — Le connecteur remonte au niveau Projet (§7/§8)

Date : 2026-07-15
Statut : acté — implémenté (Interface 1.1)
Priorité : structurel

## Contexte

La décision 0004 a introduit la hiérarchie Projet → Module → Cas, mais avec deux défauts
révélés à l'usage par le porteur :

1. Le projet par défaut de la migration s'appelait **« Odoo »** — or Odoo est l'**ERP/
   application testée**, atteint via un **connecteur** (§8 « architecture multi-connecteurs »).
   « Odoo » est une valeur de connecteur, **jamais** un nom de projet.
2. Le **connecteur** (`connector_type`) était porté par le **cas de test** (§7 littéral),
   incohérent avec « un projet = une application » : une app a un connecteur + une connexion.

## Décision (tranchée par le porteur)

1. **Projet = l'application/ERP sous test** (ex. « Portail Sapian »). Pas de niveau *Client*
   au-dessus : « client externe » est un **rôle utilisateur** (§2), pas une entité de la
   hiérarchie.
2. Le **connecteur remonte au Projet** : `connector_type` + paramètres de connexion
   (`base_url`, `database`, `username`, `password`) vivent sur `project`. Ils **quittent**
   `test_case` (colonne `connector_type` supprimée).
3. Migration : le projet par défaut « Odoo » est **renommé « Portail Sapian »**, connecteur
   `odoo`, connexion reprise de la config existante (`ODOO_URL`/`ODOO_DB`/`ODOO_USER`/
   `ODOO_PASSWORD` — `localhost:10017`, etc.).
4. Le formulaire de création de projet demande désormais **le connecteur + sa connexion**.
5. Le rattachement automatique (génération/CLI) ne recrée **jamais** un projet « Odoo » :
   il rattache au premier projet existant, ou en crée un depuis la config si aucun.

## Mécanisme

Migration 2 (`_migrate_2_project_connector`, `PRAGMA user_version` → 2), idempotente et
gardée par introspection. Vérifiée sur une copie de la base réelle (renommage + connexion +
suppression de `test_case.connector_type`) et par test unitaire.

## Sécurité — dette assumée et documentée

Le **mot de passe** de connexion est stocké **en clair** dans SQLite. Mesures prises :
l'API ne le renvoie **jamais** (write-only : accepté en entrée, absent de toute réponse).
**À traiter avant déploiement client réel** : chiffrement au repos ou gestionnaire de
secrets (hors périmètre Inc. 1.1). La base locale est de toute façon gitignorée.

## Portée / non couvert ici

- L'exécution/génération **runtime** utilise encore la connexion globale (config env) pour
  l'unique instance locale ; **brancher le runtime sur la connexion du projet** (multi-app
  réelle) est un suivi. Le modèle de données est en place, le câblage runtime non.
- Édition de la connexion d'un projet existant (l'API `PATCH` ne gère que nom/description) :
  suivi. La création, elle, saisit toute la connexion.

Voir [[0004-hierarchie-projet-module-et-separation-feature-slug]].
