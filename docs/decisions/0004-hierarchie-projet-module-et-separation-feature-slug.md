# 0004 — Hiérarchie Projet → Module → Cas (§7) + séparation `feature_slug` / `module_id`

Date : 2026-07-15
Statut : acté — implémenté (Interface 1.1)
Priorité : structurel

## Contexte

Le brief §7 pose la hiérarchie **Projet → Module/Fonctionnalité → Cas de test**. Le socle
Inc. 0 ne l'avait pas implémentée : `test_case` portait un simple champ texte `module`,
sans notion de projet — impossible de distinguer deux projets sans rapport dans l'UI.

Audit préalable : le champ `module` avait un **double rôle conflaté** —
1. **métier** : le module propriétaire affiché ;
2. **technique** : `run_service` faisait `case["module"]` → `Executor.execute(module_name)`
   → le runner Behave cherche `{module}.feature`. La valeur `demande_materiel` servait donc
   AUSSI de nom de fichier `.feature`.

## Décision

1. Introduire les tables `project` et `module` (relations réelles).
2. Sur `test_case` : **séparer les deux rôles** —
   - `module_id` (FK `module`) : rangement **métier** ;
   - `feature_slug` (TEXT) : nom du `.feature`, rôle **technique**, propre au cas.
3. **Supprimer** la colonne texte `module` une fois le backfill vérifié (pas de colonne
   inerte laissée derrière — choix explicite du porteur).
4. Migration des données existantes : projet par défaut **« Odoo »**, module nommé d'après
   le slug (`demande_materiel` → **« Demande matériel »**), `feature_slug` = ancien `module`.

## Mécanisme de migration

`PRAGMA user_version` dans `store/db.py` : `schema.sql` (cible, `CREATE IF NOT EXISTS`) puis
migrations versionnées idempotentes gardées par introspection. Migration 1 :
ajoute `module_id` + `feature_slug` si absents, backfille, **DROP** `module`, `user_version=1`.
Vérifiée sur une copie de la base réelle (cas `demande_materiel`) et par test unitaire
(`test_projects.py::test_migration_depuis_ancien_schema`).

## Invariant préservé (vérifié)

Le **gate de relecture humaine obligatoire avant la première exécution** (§4/§5) ne dépend
que de l'approbation de la VERSION, pas du module. Confirmé sans régression après
rattachement `module_id` : un cas généré+rattaché reste bloqué tant qu'aucune relecture
n'est approuvée (`test_review_gate.py`, `test_api.py::test_run_refuse_si_non_approuve`, plus
une vérification end-to-end dédiée).

## Portée

- **Non couvert ici** (reste §7 / incréments suivants) : l'« Exécution nommée » (Test Suite
  ad hoc transverse aux modules), et la création de cas depuis l'UI. La création de cas
  passe encore par la génération CLI, qui rattache automatiquement au projet « Odoo ».
- Portable PostgreSQL : `DROP COLUMN` et `ADD COLUMN` sont standard ; le runner
  `user_version` est spécifique SQLite mais isolé dans `db.py` (à remplacer par une table
  `schema_migrations` lors de la bascule PostgreSQL).
