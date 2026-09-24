---
description: Lot 07a — Connexion à l'exécution du connecteur web générique ; un échec de connexion donne « bloqué » (C1)
---

# Lot 07a — Connexion à l'exécution (C1)

Lis `CLAUDE.md`, C1 du plan. Décision requise : aucune. **Dépend du lot 02 uniquement**
(`PreconditionNonRemplieError` → `blocked`). Branche : `lot-07a-connexion-execution`.
Séparé du lot 07 le 2026-09-24 : c'est le manque qui bloque l'objectif « tester toute application
web », et il est petit.

## À lire d'abord

- `behave_runtime/environment.py` (`before_all` : `WEB_USER`/`WEB_PASSWORD` posés, jamais lus).
- `src/testpilot/connectors/generic_web.py`, `_web_helpers.py` (`tenter_connexion_generique`,
  `ConnexionGeneriqueImpossibleError`), `connectors/odoo_login.py` (modèle de délégation),
  `connectors/runtime_env.py` (`_MAPPINGS`, `_MAPPINGS_OPTIONNEL`, `verifier_connexion`).
- `behave_runtime/steps_library/generic/_generic_steps.py`, `_base_helpers.py`.
- `tests/test_conformite_connecteur_web.py`, `tests/fixtures/torture_app/`.

## Travail — le manque bloquant

Aujourd'hui l'exploration se connecte mais les tests tournent en **anonyme** : `WEB_USER` /
`WEB_PASSWORD` ne sont lus par aucun step.

1. Step générique `je me connecte avec mes identifiants utilisateur` pour le connecteur `web`,
   qui **délègue** à `tenter_connexion_generique` (même fonction que l'exploration — jamais une
   seconde implémentation, cf. l'incident du 2026-09-18 documenté dans `odoo/_odoo_steps.py`).
   Attention au conflit de libellé avec le step Odoo : les deux vivent dans des dossiers
   distincts copiés selon le connecteur ; vérifie qu'aucun projet ne charge les deux.
2. Échec de connexion → `PreconditionNonRemplieError` (→ `blocked`, lot 02), avec l'URL et le
   schéma tenté. Identifiants vides sur une application qui exige une connexion → idem.
3. Critère de connexion réussie **vérifié** : l'URL a quitté la page de connexion **et** aucun
   champ mot de passe visible, ou un sélecteur « connecté » déclaré dans les réglages du projet.

## Tests exigés

- Conformité (`-m conformance`) : connexion réelle sur the-internet (`/login`) et SauceDemo ;
  échec de connexion (mauvais mot de passe) → `blocked`, jamais `failed` ni `technical_error`.
- Unitaires : le step délègue à `tenter_connexion_generique` (aucune seconde implémentation) ;
  identifiants vides sur une application qui exige une connexion → `PreconditionNonRemplieError`.
- Garde : aucun step générique ne référence `context.odoo`.

## Critères d'acceptation

- [ ] Un cas généré sur **the-internet (`/login`)** et sur **SauceDemo** s'exécute connecté, sans
      step de connexion écrit par l'agent.
- [ ] Un échec de connexion donne « bloqué » (jamais `failed`).
- [ ] L'exploration et l'exécution utilisent le même code de connexion.
- [ ] `python -m pytest -q` et ruff critique verts.

Rapport au format `CLAUDE.md` §10 ; lance `verdict-reviewer`.
