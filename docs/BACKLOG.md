# Backlog — reports assumés

Point d'entrée unique des travaux **différés et documentés** (chaque entrée renvoie à sa
décision détaillée dans `docs/decisions/`). Ordonné par incrément cible.

## Incrément 2 (avant tout déploiement client réel)

- [ ] **Secret de connexion en clair** — le mot de passe de connexion d'un projet est stocké
  en clair dans SQLite. Acceptable en dev local (instance Odoo neutralisée), **inacceptable
  avant le premier déploiement client**. À traiter : chiffrement au repos ou gestionnaire de
  secrets. Atténuation déjà en place : l'API ne renvoie jamais le mot de passe (write-only).
  → voir `decisions/0005-connecteur-au-niveau-projet.md`.

## Incrément 1 (suite de l'interface / robustesse)

- [ ] **Parser d'exécution — steps « errored »** : capturer le message d'erreur des steps au
  statut `error` (aujourd'hui perdu → cause `unknown`). Priorité haute : sans ça, tout
  `technical_error` reste opaque. → `decisions/0002-parser-message-erreur-steps-errored-inc1.md`.
- [ ] **Fiabilité de la génération** : l'agent doit réutiliser les steps partagés au lieu d'en
  réinventer (cause racine du coût de génération, §brief). Priorité haute.
  → `decisions/0003-agent-reutiliser-steps-partages-inc1.md`.
- [ ] **Confirmations `pending_human`** : sous-commande / écran de traitement de la file de
  relecture des origines de défaut. → `decisions/0001-report-confirmations-pending-human-inc1.md`.
- [ ] **Runtime branché sur la connexion du projet** : l'exécution/génération utilise encore la
  connexion globale (config env) ; brancher sur la connexion propre à chaque projet (vraie
  multi-application). → `decisions/0005-connecteur-au-niveau-projet.md`.
- [ ] **Édition de la connexion d'un projet** : `PATCH /api/projects/{id}` ne gère que
  nom/description ; permettre d'éditer connecteur + connexion. → `decisions/0005-...`.

## Incrément 1+ (structure §7 non encore implémentée)

- [ ] **Exécution nommée transverse** (« Test Suite » ad hoc) : regroupement libre de cas de
  plusieurs modules, avec nom et but propres, et rapport attaché à l'exécution. Classé JTBD
  essentiel (régression transverse, §3 du brief). L'UI de l'onglet Exécution laisse la porte
  ouverte (badge mono/multi-module + nom d'exécution prévus dans les tuiles).
