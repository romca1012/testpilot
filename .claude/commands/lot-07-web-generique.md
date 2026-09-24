---
description: Lot 07b-e — Application web authentifiée : session, contexte, vocabulaire, oracle (C2-C5) — la connexion à l'exécution (07a) est un lot à part
argument-hint: "[sous-lot : b | c | d | e — vide = tous, dans l'ordre]"
---

# Lot 07b-e — Connecteur web générique complet (hors connexion)

Lis `CLAUDE.md`, C2-C5 du plan. Décisions requises : **D7** (sous-lot e) et **D8** (sous-lot b).
Dépend des lots 02, 03 et **07a** (`/lot-07a-connexion-execution`, séparé le 2026-09-24). Sous-lot demandé : `$ARGUMENTS`. Une branche par sous-lot :
`lot-07<x>-…`.

## À lire d'abord

- `behave_runtime/environment.py` (`before_all`, `playwright_browser`, `before_scenario`).
- `src/testpilot/connectors/generic_web.py`, `_web_helpers.py` (`tenter_connexion_generique`,
  `ConnexionGeneriqueImpossibleError`), `connectors/odoo_login.py` (modèle de délégation),
  `connectors/runtime_env.py` (`_MAPPINGS`, `_MAPPINGS_OPTIONNEL`, `verifier_connexion`).
- `behave_runtime/steps_library/generic/_generic_steps.py`, `_base_helpers.py`.
- `tests/test_conformite_connecteur_web.py`, `tests/fixtures/torture_app/`.
- `src/testpilot/store/secrets.py`.

## 07b — Session réutilisée et stratégies d'authentification (C2)

1. Connexion une fois par run dans `before_all` quand le projet l'exige, `storage_state` écrit dans
   le dossier du run et passé à chaque `new_context`. Invalidation si une page redirige vers la
   connexion en cours de scénario (reconnexion une fois, puis `blocked`).
2. Réglage de projet `auth_strategie` ∈ {`formulaire` (défaut, détection actuelle), `totp`,
   `session_injectee`, `aucune`}. `totp` : secret chiffré, code généré par `pyotp` et saisi dans le
   champ détecté. `session_injectee` : cookies/jeton fournis, injectés dans le contexte. Le SSO
   d'entreprise passe par `session_injectee` (documenté, jamais deviné).
3. D8 : comptes multiples par projet (`project_account`) et step
   `je me connecte en tant que "<libellé du compte>"` (générique et Odoo) — nouveau contexte
   navigateur, session RPC réouverte pour Odoo.

## 07c — Contexte navigateur figé (C3)

`new_context(locale=…, timezone_id=…, viewport=…)` à partir des réglages du projet (défauts :
`fr-FR`, `Europe/Paris`, 1440×900), passés au sous-processus par `runtime_env`. Même contexte pour
l'exploration (`generic_web.py`, `odoo.py`) : l'agent doit voir ce que le test verra.

## 07d — Vocabulaire universel (C4)

Steps génériques, chacun avec test de conformité sur `torture_app` (ajoute les pages nécessaires à
la fixture) et, s'il affirme, via `constater_*` (lot 03) :

- `j'ouvre la page "<chemin>"` (relatif à l'URL du projet) ;
- `la page affiche le texte "<texte>"` / `n'affiche pas le texte "<texte>"` ;
- `l'URL courante contient "<fragment>"` ;
- `le tableau "<nom>" contient une ligne avec "<a>" et "<b>"` / `compte <n> lignes` ;
- `je clique sur "<libellé>" dans la ligne contenant "<texte>"` ;
- `j'accepte la boîte de dialogue` / `je refuse la boîte de dialogue` (natif + modale ARIA) ;
- `je télécharge le fichier via "<libellé>"` + `le fichier téléchargé se nomme "<motif>"` /
  `contient "<texte>"` (CSV, TXT, PDF via extraction texte) ;
- `dans le cadre "<nom>", …` : variante iframe des steps de saisie et de clic ;
- `un nouvel onglet s'ouvre sur "<fragment d'URL>"` ;
- `la requête "<méthode> <motif d'URL>" répond <code>` (attente de réponse réseau Playwright).

Les tableaux et lignes sont localisés par rôle ARIA d'abord (`table`, `row`, `cell`), puis par
structure HTML. Aucun sélecteur propre à une application.

## 07e — Oracle backend optionnel (C5, D7)

1. Réglage `oracle` : `{type: "http", base_url, auth}` ou `{type: "sql", dsn_lecture_seule}`.
   Secrets via `store/secrets.py`. `verifier_connexion` teste l'oracle et refuse s'il est
   configuré mais injoignable.
2. Steps : `l'oracle "<requête nommée>" renvoie <n> résultat(s)` et
   `le champ "<chemin JSON ou colonne>" de l'oracle "<requête nommée>" vaut "<valeur>"`. Les
   requêtes nommées sont déclarées dans les réglages du projet, jamais écrites par l'agent
   (la garde `_FORBIDDEN_IMPORTS` de `write.py` reste intacte).
3. SQL : connexion ouverte en lecture seule (`SET TRANSACTION READ ONLY` / rôle dédié), refus de
   toute requête non `SELECT`.
4. `ground_truth = backend_verified` si le scénario a exécuté au moins un constat d'oracle.

## Tests exigés

- Conformité (`-m conformance`) : connexion réelle sur the-internet (`/login`) et SauceDemo, avec
  et sans `storage_state` ; échec de connexion → `blocked`.
- Unitaires : stratégies d'auth (doublures), refus SQL non-SELECT, calcul `ground_truth`.
- Garde : aucun step générique ne référence `context.odoo`.

## Critères d'acceptation

- [ ] L'exploration et l'exécution utilisent le même code de connexion et le même contexte.
- [ ] Chaque nouveau step affirmatif a un test de falsifiabilité.

Rapport par sous-lot au format `CLAUDE.md` §10 ; lance `verdict-reviewer`.
