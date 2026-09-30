# Correctif — connexion automatique qui n'aboutit pas (3 bugs distincts, trouvés en diagnostic direct)

Continuité de `docs/RAPPORT-CONTINUITE-CONNEXION-YROS-2026-09-30.md` (mécanisme
`remplir_et_soumettre_formulaire_connexion` / crawl du connecteur `web` générique) — diagnostic
mené en local avec le porteur, sans cycle CI, jusqu'à confirmation en conditions réelles sur
SauceDemo.

## Symptôme d'origine (`yros`)

Un formulaire de connexion enregistré (3 clics guidés) se remplit et se soumet sans lever
d'erreur, mais l'exploration qui suit ne débloque aucun contenu authentifié — 3 routes trouvées,
exactement comme avant que la connexion n'existe.

## Cause 1 — race réseau sur redirection SPA (la cause d'origine, confirmée)

`page.wait_for_load_state("networkidle")`, appelé juste après le clic de connexion, ne détecte
AUCUNE navigation à attendre quand l'authentification répond par `fetch`/XHR suivi d'une
redirection côté client (History API) — cas courant d'une SPA moderne. L'appelant
(`crawl_roots`, `connexion_reussie`) lisait alors l'URL/le DOM de la page de connexion.

**Correctif** — `src/testpilot/connectors/_web_helpers.py` : nouveau helper
`_attendre_confirmation_post_connexion(page, url_avant)` (attente bornée à 2 s : URL changée OU
champ mot de passe disparu, jamais les deux à la fois) branché après `networkidle` sur les 3
points de soumission finale (`remplir_et_soumettre_formulaire_connexion`,
`tenter_connexion_generique` schémas à un et deux écrans). Ne décide jamais du succès de la
connexion — c'est toujours l'appelant (`connexion_reussie`, `crawl_roots`) qui juge l'état obtenu.

## Cause 2 — décalage des 3 clics guidés sur formulaire à un seul écran (trouvée en testant sur SauceDemo)

`src/testpilot/api/services/live_session_service.py::SessionLive._traiter_clic` : sur un
formulaire à UN SEUL écran (identifiant et mot de passe déjà visibles ensemble, ex. SauceDemo),
le mot de passe est visible DÈS AVANT le premier clic. Le code ajoutait d'abord ce clic à
`_etapes` (écran intercalé), puis basculait en mode formulaire — décalant toute la séquence :
`champ_identifiant` et `champ_mdp` capturaient tous les deux le même élément, `bouton_soumission`
restait mal capturé.

**Correctif** — vérifier la visibilité du mot de passe AVANT de router le clic (nouvelle méthode
`_basculer_en_mode_formulaire`, appelée aux deux points : avant le clic pour le cas à un seul
écran, après pour le cas à deux écrans — comportement historique inchangé pour ce dernier).

## Cause 3 — nom accessible vide sur `input[type=submit]` (trouvée en testant sur SauceDemo)

`src/testpilot/generation/accname.py` : `calculerNom` ne lisait jamais l'attribut `value` d'un
`<input type="submit"|"button"|"reset">` — élément VIDE (aucun nœud enfant/texte), donc l'étape
« nom depuis le contenu » ne trouvait jamais rien pour lui. Le bouton de SauceDemo
(`<input type="submit" value="Login">`) était capturé avec un nom vide, introuvable au rejeu par
`page.get_by_role`.

**Correctif** — `etiquetteLangageHote` lit désormais `value` pour ces trois types (règle
HTML-AAM), à l'emplacement de l'étape 2E (host language label), sans repli sur un texte par
défaut UA (« Submit »/« Envoyer ») si `value` est absent — jamais un signal deviné.

## Changements

- `src/testpilot/connectors/_web_helpers.py` — `_attendre_confirmation_post_connexion` +
  branchement sur les 3 sites de soumission finale.
- `src/testpilot/api/services/live_session_service.py` — `_basculer_en_mode_formulaire` +
  check de visibilité avant le clic.
- `src/testpilot/generation/accname.py` — lecture de `value` pour
  `input[type=submit|button|reset]`.
- `tests/test_remplir_formulaire_connexion.py`, `tests/test_connexion_generique_deux_ecrans.py`,
  `tests/test_generic_web_connector.py` — fakes enrichis (`url`, `query_selector`,
  `wait_for_timeout`) + tests de falsifiabilité pour la cause 1.
- `tests/test_live_session_service_formulaire.py` — test de falsifiabilité pour la cause 2.
- `tests/test_accname.py` — 2 tests de falsifiabilité pour la cause 3 (vrai Chromium,
  `pytest.mark.conformance`).

## Tests ajoutés

- `test_falsifiable_attend_la_vraie_redirection_spa_au_dela_du_networkidle_premature` — prouve
  que sans le correctif 1, `page.url` reste sur la page de connexion.
- `test_falsifiable_le_schema_a_un_ecran_attend_la_vraie_redirection_spa` — idem, schéma
  générique à un écran.
- `test_falsifiable_formulaire_a_un_seul_ecran_ne_decale_pas_la_sequence_des_3_clics` — prouve
  que sans le correctif 2, le premier clic part dans `_etapes` au lieu de `champ_identifiant`.
- `test_falsifiable_input_submit_value_est_le_nom_accessible` /
  `test_falsifiable_input_button_value_est_le_nom_accessible` — prouvent que sans le correctif 3,
  le nom accessible reste vide et introuvable par `page.get_by_role` au rejeu.

Falsifiabilité vérifiée manuellement pour les 5 tests : correctif temporairement désactivé →
échec confirmé → correctif restauré → succès confirmé.

## Critères d'acceptation

- [x] Cause d'origine (race réseau SPA) identifiée par mesure directe (log diagnostique) et
  corrigée.
- [x] Chaque correctif a un test de falsifiabilité qui échoue sans lui.
- [x] Vérifié en conditions réelles (navigateur, pas seulement les tests unitaires) : capture du
  formulaire SauceDemo correcte (3/3 champs, bouton nommé), exploration relancée, contenu
  authentifié atteint (`/inventory.html`, vrais produits).
- [x] `python -m pytest -q` : 2942 passed, 5 failed — **les 5 échecs sont préexistants**, confirmés
  indépendants de ce diff par `git stash` (mêmes échecs sans les 3 correctifs, sur
  `scripts/migration_lot06_profil_instance.py` et `test_bibliotheque_par_connecteur.py`, sans
  rapport avec la connexion).
- [x] `pytest -m conformance tests/test_accname.py` : 38 passed (vrai Chromium).
- [x] `ruff check --select E9,F63,F7,F82` : vert sur les 8 fichiers modifiés.
- [x] Sous-agent `verdict-reviewer` : verdict OK, aucun bloquant.
- [ ] Confirmé sur le vrai `yros` — pas fait, ce projet n'existe qu'en staging (pas de base locale
  pour lui), pas testé pendant cette session.

## Mesures

Pas de mesure de coût (§9) : aucun correctif ne touche les prompts ni les appels LLM.

## Écarts constatés avec le plan

Aucun — ce sont des correctifs de bugs sur un mécanisme déjà en place (lot « Enregistrement
assisté du chemin de connexion »), pas une nouvelle décision structurante du registre.

## Risques / points à surveiller

- `_confirmation_post_connexion_obtenue` (`_web_helpers.py`) n'a pas de `try/except` autour de
  `page.url`/`page.query_selector`. Sur une vraie navigation plein-page (pas une SPA) qui
  détruirait le contexte d'exécution pendant le polling, Playwright peut lever une exception
  transitoire (« Execution context was destroyed »), qui remonterait comme `technical_error`
  plutôt qu'un login qui aurait en fait réussi. Signalé par `verdict-reviewer` : sans risque pour
  l'invariant « jamais de faux PASSED » (on bascule vers un échec, jamais vers un `conforme`),
  donc non bloquant — à surveiller si des faux `blocked` apparaissent en pratique sur une
  application à navigation lourde.
- Le cas « `value` absent » d'`input[type=submit]` n'a pas de test dédié (comportement déduit de
  la lecture du code : retombe proprement sur `title`/`placeholder`, jamais un texte deviné) —
  signalé par `verdict-reviewer`, faible risque.
- Le vrai `yros` n'a pas été retesté avec ces correctifs — recommandé avant de considérer le
  diagnostic totalement clos.

## Suggestions hors périmètre

- `rejouer_sequence_connexion` (`_web_helpers.py`, séquence d'écran intercalé) a le même motif
  `wait_for_load_state("networkidle")` sans confirmation post-navigation — même classe de bug,
  non corrigé ici (portée différente : navigation vers un ÉCRAN INTERCALÉ, pas la confirmation
  finale de connexion ; nécessiterait une réflexion séparée sur ce que « confirmation » signifie
  dans ce contexte).
- Ajouter un `try/except` défensif autour de `_confirmation_post_connexion_obtenue` (remarque
  verdict-reviewer ci-dessus).
