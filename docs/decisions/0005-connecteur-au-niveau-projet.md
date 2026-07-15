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

## Câblage du runtime (fait — suite de cette décision)

Le modèle seul ne suffisait pas : tant que le runtime tapait la config globale, l'interface
promettait un multi-projet que l'exécution ne tenait pas — le décalage « affiché ≠ réel » que
le produit est censé supprimer. Désormais :

- `connectors/runtime_env.py` : projet → variables d'environnement, **selon le
  `connector_type`** (multi-connecteurs, §8). Valeur vide ⇒ non propagée (repli config).
- `BehaveRunner(connection=…)` injecte ces variables dans le sous-processus behave. Le harnais
  appelle `load_dotenv()` **sans `override`** : les variables passées priment donc sur le `.env`.
- `run_service.resolve_connection(conn, case_id)` : cas → projet → connexion (chemin du run UI).
- `OdooConnector.from_project(…)` : l'exploration de génération observe l'app **du projet**.
- CLI : même règle que le rattachement automatique (le premier projet), source unique
  `ProjectRepo.first()` — sinon un cas serait rangé sous un projet et joué contre un autre.
- `ODOO_ENV` n'est jamais produit depuis un projet : le garde-fou anti-production reste intact.

## Portée / non couvert ici
- Édition de la connexion d'un projet existant (l'API `PATCH` ne gère que nom/description) :
  suivi. La création, elle, saisit toute la connexion.

Voir [[0004-hierarchie-projet-module-et-separation-feature-slug]].
