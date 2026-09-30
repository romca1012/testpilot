# Extension — capture guidée du formulaire de connexion, essai sur Odoo — terminé

Ce n'est pas un lot numéroté de `docs/PLAN-FIABILITE-VERDICT-2026-09.md` : c'est une extension du
chantier « Enregistrement assisté du chemin de connexion » (sous-lots A à E déjà clos, voir
`docs/RAPPORT-LOT-ENREGISTREMENT-CHEMIN-CONNEXION-CLOTURE-2026-09-30.md`), demandée explicitement
par le porteur en cours de session, à la suite d'un bug réel trouvé sur staging (identifiants
valides, connexion qui n'aboutit toujours pas après le correctif WebSocket).

Décisions utilisées : aucune décision `D#` du registre du plan — hors périmètre de ce plan. Deux
décisions structurantes ont été prises directement avec le porteur, dans la conversation :
1. Étendre la capture à 3 clics guidés (identifiant, mot de passe, bouton) après l'écran de
   pré-connexion, plutôt que de corriger seulement les heuristiques de `tenter_connexion_generique`
   — accepté explicitement (« oui vas y » après proposition courte).
2. Ouvrir le MÊME mécanisme, à la demande, au connecteur Odoo — demandé explicitement par le
   porteur (« je te propose qu'on le câble au connecteur odoo qu'on essaye aussi sans supprimer
   odoo connector »), contre ma recommandation initiale (Odoo n'a historiquement pas ce problème :
   formulaire fixe, base par paramètre d'URL).

## Ce que ça change, en une phrase

Un formulaire de connexion (identifiant, mot de passe, bouton) peut désormais être identifié une
fois, par 3 clics guidés dans la session live, puis rejoué par rôle/nom AccName (jamais deviné) à
la place de la détection générique par balayage du DOM — pour le connecteur `web`, et, à l'essai,
pour Odoo si un déploiement personnalisé met en défaut sa détection codée en dur.

## Changements

- `src/testpilot/store/db.py` — migration 56 : colonne `login_form_json` (`TEXT NOT NULL
  DEFAULT ''`) sur `project_login_recording`, idempotente.
- `alembic/versions/a2d47f9c8e15_login_form_capture.py` — révision équivalente, chaînée sur
  `e1c6a9f2b830`.
- `src/testpilot/store/schema_sa.py` — colonne portable + `ALIGNED_WITH_SCHEMA_VERSION = 56`.
- `src/testpilot/store/portable_connection.py` — `ALEMBIC_HEAD = "a2d47f9c8e15"`.
- `src/testpilot/store/project_login_recordings.py` — `LoginForm`, `enregistrer(..., login_form=
  None)` (une reconfirmation sans formulaire efface tout formulaire antérieur, jamais un mélange),
  `lire_formulaire`.
- `src/testpilot/api/services/live_session_service.py` — `SessionLive` gagne un mode
  `_mode_formulaire` : après `capture_arretee` (mot de passe visible), 3 clics guidés résolus par
  `accname.calculer` (même mécanisme que le reste de la capture) alimentent `login_form`, jamais un
  descripteur partiel.
- `src/testpilot/api/routes/live_session.py` — `_confirmer` écrit aussi `login_form`, l'accusé
  `confirme` porte `formulaire_connexion: bool`.
- `src/testpilot/api/services/exploration_service.py` — `login_form` lu et transmis au connecteur,
  même motif que `sequence_connexion`.
- `src/testpilot/connectors/_web_helpers.py` — `FormulaireConnexionObsoleteError`,
  `remplir_et_soumettre_formulaire_connexion` (get_by_role exact=True, arrêt net sans repli à
  mi-chemin) ; `rejouer_sequence_connexion`/cette nouvelle fonction gagnent `attendre_reseau`
  (contourner le bus de long-polling d'Odoo, qui ne stabilise jamais `networkidle`) ;
  `tenter_connexion_et_lire_resultat` préfère `login_form` quand fourni.
- `src/testpilot/connectors/generic_web.py` — `login_form` transmis depuis le projet, préféré à
  `tenter_connexion_generique` partout où celle-ci était appelée (`_ensure_page`,
  `crawl_relogin_hook`).
- `src/testpilot/connectors/odoo.py` / `odoo_login.py` — essai : `OdooConnector` transmet
  `sequence_connexion`/`login_form` à `playwright_login`, qui les consulte AVANT sa détection codée
  en dur (fixe si absents, comportement 100 % inchangé).
- `src/testpilot/connectors/runtime_env.py` — `ENV_LOGIN_RECORDING`/`ENV_LOGIN_FORM` ouverts à
  `connector in ("web", "odoo")`, `ENV_STRATEGIE`/`ENV_TOTP_SECRET`/`ENV_INJECTED_SESSION` restent
  réservés à `web` (concepts propres à sa stratégie de connexion, pas génériques).
- `src/testpilot/api/services/run_service.py` — `resolve_connection` lit aussi `login_form`.
- `behave_runtime/environment.py` — lecture des 2 variables d'environnement déplacée dans
  `before_all` (commune aux deux connecteurs UI), au lieu de rester locale à
  `_tenter_connexion_initiale` (web uniquement).
- `behave_runtime/steps_library/_base_helpers.py` — `authentifier_selon_la_strategie` et
  `connexion_web_utilisateur` préfèrent `login_form` quand fourni sur `context`.
- `frontend/src/lib/useLiveSession.ts` / `pages/LiveSession.vue` — nouveaux messages serveur, pas-à-
  pas visuel des 3 clics guidés, `formulaireConnexionEnregistre` affiché à la confirmation.

## Tests ajoutés

- `tests/test_migration_login_form_capture.py` — migration 56 : colonne neuve, idempotente, valeur
  réelle qui survit à une re-migration.
- `tests/test_project_login_recordings.py` — `lire_formulaire`, et surtout
  `test_falsifiable_une_reconfirmation_sans_formulaire_efface_l_ancien_jamais_un_melange`.
- `tests/test_live_session_service_formulaire.py` — 8 tests purs (sans navigateur) de la machine à
  états : ordre des 3 clics, clic ambigu qui n'avance pas, 4ᵉ clic qui n'écrase rien, `recommencer`
  qui vide sans repasser en mode séquence.
- `tests/test_live_session_ws.py` — preuve bout en bout (vrai Chromium, marqueur `conformance`) des
  3 clics guidés et de leur écriture en base.
- `tests/test_remplir_formulaire_connexion.py` — `FormulaireConnexionObsoleteError` : arrêt net
  jamais un repli à mi-chemin, jamais de secret dans le message d'erreur.
- `tests/test_odoo_login_formulaire_enregistre.py` — délégation Odoo, ordre séquence puis
  formulaire, régression du chemin par défaut (aucune délégation si rien n'est enregistré).
- `tests/test_runtime_connection.py` — remplace `test_project_env_ignore_la_sequence_pour_odoo`
  (assertion INVERSÉE, voir « Écarts ») par `test_project_env_transmet_aussi_la_sequence_pour_odoo`
  + `test_project_env_reserve_bien_la_strategie_d_auth_au_connecteur_web` (le nouveau périmètre
  ouvert à Odoo ne déborde pas sur les concepts propres à la stratégie `web`).

## Critères d'acceptation

- [x] Le formulaire enregistré est TOUJOURS préféré à la détection générique quand il existe,
  jamais un mélange des deux.
- [x] Jamais de valeur/secret capturé, stocké ou logué — seulement rôle/nom.
- [x] Une reconfirmation sans les 3 clics guidés efface tout formulaire antérieur.
- [x] Comportement historique 100 % inchangé pour tout projet (web ou Odoo) qui n'a jamais rien
  enregistré.
- [x] Extension Odoo strictement optionnelle, activée uniquement si le projet a enregistré
  quelque chose.
- [x] Suite complète verte, ruff critique vert, frontend vert (type-check + vitest).
- [x] Revue `verdict-reviewer` menée, verdict OK, aucun bloquant.

## Mesures

`python -m pytest -q` (hors `conformance`/`banc`) sur la branche `lot-formulaire-connexion` : 2942
passed, 16 skipped, 0 failed (avant cette extension, sur `origin/master` : 2938 passed).
`npm test -- --run` (frontend) : 368 passed (avant : 359). `npm run type-check` : aucune erreur.
`ruff check --select E9,F63,F7,F82 src behave_runtime tests scripts` : vert.

## Écarts constatés avec le plan

- `tests/test_runtime_connection.py::test_project_env_ignore_la_sequence_pour_odoo` — test
  préexistant qui figeait l'ANCIENNE décision (« Odoo n'a pas ce problème, jamais transmis ») —
  renommé `test_project_env_transmet_aussi_la_sequence_pour_odoo` et son assertion INVERSÉE pour
  accompagner la décision explicite du porteur d'ouvrir le mécanisme à Odoo. Ce n'est pas une
  assertion affaiblie pour faire passer un test au vert (CLAUDE.md §4) : la spécification elle-même
  a changé, sur demande directe et documentée dans la conversation — le nouveau test documente la
  nouvelle spécification, avec un second test dédié qui vérifie que le périmètre ouvert reste
  strictement limité au chemin de connexion (jamais la stratégie `web`, restée réservée).

## Risques / points à surveiller

- Pour Odoo, le chemin `login_form` réutilise le même signal de succès que le chemin par défaut
  (`page.wait_for_url(lambda url: "/web/login" not in url, ...)`, inchangé par ce diff) — si une
  instance Odoo personnalisée redirige hors de `/web/login` pour une autre raison qu'une connexion
  réussie (page d'erreur à une autre URL), les DEUX chemins concluraient à tort à un succès. Risque
  préexistant, pas aggravé par cette extension, non couvert par un test (aucun test avec une page
  qui change d'URL sans être connectée) — signalé par la revue `verdict-reviewer`, à garder en tête
  si un tel comportement est un jour observé en conditions réelles.
- Odoo est un essai explicitement demandé, jamais mesuré sur un déploiement personnalisé réel (à la
  différence du connecteur `web`, dont le bug d'origine venait d'une mesure réelle sur staging).

## Suggestions hors périmètre

- `OdooConnector._attempt_login_sync` a sa PROPRE implémentation inline de la connexion Odoo
  (jamais déléguée à `odoo_login.playwright_login`, contrairement à `_ensure_page`/
  `crawl_relogin_hook`) — ne bénéficie donc pas de ce mécanisme. Pas touché ici (périmètre : la
  connexion PRINCIPALE d'exploration/exécution, pas la calibration avec des identifiants de
  scénario) ; à revoir si le besoin se présente.
- Aucun écran ne permet de RETIRER un `login_form` enregistré indépendamment de toute la séquence
  (seule une reconfirmation complète l'efface) — suggestion déjà notée pour `sequence_connexion`
  dans le rapport de clôture du chantier, vaut aussi ici.
