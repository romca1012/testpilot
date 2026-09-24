## Lot 07a — Connexion à l'exécution du connecteur web générique — terminé (sous réserve de la revue et de la fusion)

Décisions utilisées : aucune `D#` du registre. Conception **validée par le porteur le 2026-09-24**, avec
deux ajustements : un *step* (et non une balise de scénario) pour les cas qui testent la connexion,
cohérent avec la décision 0015 ; un avis détectif du smoke_check fondé sur l'intention déclarée. Le porteur
a aussi demandé de confirmer que le critère de connexion par défaut suffit seul (fait, ci-dessous).

Changements :
- `behave_runtime/steps_library/_base_helpers.py` — `connexion_web_utilisateur` (délègue à
  `tenter_connexion_generique`, la fonction de l'exploration : aucune seconde implémentation),
  `connexion_reussie` (critère pur : URL partie **et** plus de champ mot de passe visible), `_mot_de_passe_visible`,
  `_schema_de_connexion`. Tout échec → `PreconditionNonRemplieError` (→ `blocked`, lot 02) avec l'URL, le schéma
  tenté (un écran / deux écrans) et le message affiché par l'application.
- `behave_runtime/steps_library/generic/_generic_steps.py` — le step d'entrée « j'accède à la page d'accueil de
  l'application » connecte **automatiquement** ; nouveau step « j'accède à la page de connexion sans me connecter »
  pour les cas dont le sujet est la connexion.
- `behave_runtime/steps_library/web/_web_steps.py` (nouveau dossier, un par connecteur) — « je me connecte avec mes
  identifiants utilisateur » pour un projet `web` (connexion en milieu de parcours) ; libellé identique au step
  Odoo, sans collision car `generic/` + **un seul** connecteur sont chargés.
- `src/testpilot/execution/behave_runner.py` — `_steps_library_files` : sans `connector_type`, « tout copier » exclut
  désormais `web/` (generic + le connecteur par défaut `odoo`, comme avant la séparation). Sans cela, le libellé
  « je me connecte… » déclaré des deux côtés produisait un `AmbiguousStep` (constaté : dry-run du harnais et 3 autres
  tests en échec à la première suite complète).
- `src/testpilot/generation/smoke_check.py` + `api/services/generation_service.py` — avis détectif
  `connexion_non_testee` (projet `web` seulement) : l'intention **déclarée** (titre, description, préconditions,
  étapes et résultat attendus métier — jamais le Gherkin) est un test de connexion et le cas n'emploie ni
  « je me connecte… » ni « … sans me connecter ». Jamais bloquant.
- `frontend/src/components/ReviewGate.vue` — famille « connexion » pour ce nouvel avis (§4.7).
- `src/testpilot/generation/prompts/system_prompt.md` — un paragraphe : ne jamais écrire de step de connexion
  pour entrer ; ouvrir un test de connexion par « … sans me connecter ».
- `docs/mesures/lot07a-connexion-execution-2026-09-24.md`, plan (ligne 07a) — mesures et suivi.

Tests ajoutés :
- `tests/test_connexion_execution.py` — le critère exige les DEUX conditions (7 cas dont « URL inchangée seule » et
  « URL bougée mais mot de passe présent ») ; le step d'entrée appelle la fonction PARTAGÉE ; échec, SSO/2FA,
  identifiants vides (application qui exige / publique), application sans formulaire ; step explicite (connecte,
  bloque sans formulaire, ne bloque pas après une connexion automatique) ; l'exception se classe
  `precondition_non_remplie` que le step soit `given` ou `when` ; aucun libellé dupliqué par connecteur ; aucun
  step `generic/`/`web/` ne référence `context.odoo` (AST).
- `tests/test_smoke_intention_connexion.py` — reconnaissance de l'intention (6 positifs, 4 négatifs dont « après
  connexion »), avis émis / tu selon les deux steps, l'avis ne lit jamais le Gherkin pour deviner l'intention,
  seulement pour un projet `web`, famille du gate et paragraphe du prompt présents.
- `tests/test_bibliotheque_par_connecteur.py::test_sans_connecteur_ne_copie_pas_les_steps_d_un_autre_connecteur_que_le_defaut`
  — un run sans connecteur ne charge jamais `web/` ; un run `web` le charge.
- `tests/test_conformite_connexion_execution.py` (`-m conformance`, navigateur réel) — sur SauceDemo, the-internet
  et la fixture à deux écrans : l'entrée connecte, un mauvais mot de passe est bloqué, « … sans me connecter »
  laisse la page de connexion intacte, le step explicite reconnecte. 12 passés.

Critères d'acceptation :
- [x] Un cas sur the-internet (`/login`) et sur SauceDemo s'exécute connecté sans step de connexion écrit par l'agent —
      mesuré de bout en bout par Behave réel : `passed` sur les deux (avant : `failed`, application testée en anonyme).
- [x] Un échec de connexion donne « bloqué » (jamais `failed`) — `blocked` / `precondition_non_remplie` sur les deux.
- [x] L'exploration et l'exécution utilisent le même code de connexion (`tenter_connexion_generique`) — test dédié.
- [x] Le critère par défaut suffit seul sur the-internet et SauceDemo (et sur la fixture à deux écrans), sans sélecteur
      « connecté » (demande du porteur).
- [x] `python -m pytest -q` vert : 2395 passés, 16 ignorés (17 min) ; ruff critique vert ; Vitest : 305 passés, type-check propre.

Mesures : voir `docs/mesures/lot07a-connexion-execution-2026-09-24.md` (6 cas avant → après, mêmes cas sur `master`
puis sur ce lot). Coût (§8) : le prompt système gagne un paragraphe d'environ 90 mots ; **le coût par cas n'a pas
été mesuré** (aucun appel LLM dans ce lot) — à mesurer avec le lot 09 (`scripts/mesure_cout_cas.py`).

Écarts constatés avec le plan :
- **Un test existant modifié, sans changer son assertion** : `tests/test_generic_navigation_step.py` — la double de page
  du step d'entrée n'avait pas d'attribut `url` ; le step le lit maintenant (connexion automatique). La double reçoit
  `url` (mis à jour par `goto`) ; les assertions (goto appelé avec `web_url`, refus sans URL) sont inchangées.
- Mes propres tests de steps chargeaient `web/` dans le registre GLOBAL de Behave et faisaient lever `AmbiguousStep`
  aux tests Odoo suivants (26 échecs à la première suite complète) : ils isolent maintenant le registre (fixture de
  module qui le restaure). Ce n'était pas un défaut du produit, mais celui du run sans connecteur (ci-dessus) en était un.
- La commande du lot affirme qu'aucun projet ne charge à la fois le step Odoo et le step web de même libellé. C'est
  vrai pour les exécutions réelles (`generic/` + un seul connecteur), **faux** pour un `BehaveRunner` sans
  `connector_type`, qui copie tout et produirait un `AmbiguousStep` ; les runners réels (`run_service`,
  `generation_service`) passent toujours le connecteur. Le step web vit donc dans un dossier `web/` dédié.
- Le plan parle d'« un sélecteur « connecté » déclaré dans les réglages du projet » : **ce réglage n'existe pas**. Non
  créé (il aurait exigé une migration en quatre volets) ; le critère par défaut est le seul, comme le porteur l'a confirmé.
- Le step « … sans me connecter » est dans `generic/` (avec le step d'entrée), pas dans `web/` : il est visible du
  catalogue Odoo (où `web_url` est vide → `NavigationImpossibleError`, comme le step d'entrée déjà présent).

Risques / points à surveiller :
- **Faux « bloqué », jamais faux PASSED.** Une application monopage dont l'URL ne change pas après connexion serait
  déclarée « connexion non aboutie » (le critère exige que l'URL parte) ; une application **publique** dont la page
  d'entrée affiche un champ mot de passe (formulaire dans l'en-tête) avec un projet sans identifiants serait bloquée.
  Les deux relèvent du lot 07b (stratégies d'authentification) si un projet réel les rencontre.
- **Connexion silencieusement absente.** Si l'URL du projet est une page d'accueil sans formulaire (le lien
  « Se connecter » mène à `/login`), aucune connexion automatique n'a lieu et le cas tourne anonyme — comportement
  historique conservé (une application peut être publique). Ce n'est pas un faux PASSED (un cas qui exige d'être
  connecté échoue), mais l'URL du projet doit être celle de la page de connexion ou d'une page protégée.
- Un cas qui teste la connexion et que l'agent ouvre par le step d'entrée arrive connecté : il échoue (jamais ne passe
  à tort) ; l'avis détectif réduit la fréquence sans l'annuler.
- Une connexion par scénario (nouveau contexte navigateur à chacun) : quelques secondes par cas ; la réutilisation de
  session est le lot 07b.
- the-internet est lente à charger depuis ce poste (25-29 s) : les tests de conformité utilisent un délai de 60 s.

Suggestions hors périmètre :
- Réglage projet « sélecteur connecté » (uniquement si un projet réel met le critère par défaut en défaut).
- Mesurer le coût par cas avec le paragraphe ajouté au prompt (lot 09).

### Ce qu'on peut tester concrètement après ce lot (à communiquer)

Applications web **avec un formulaire de connexion simple** : identifiant + mot de passe sur la même page, ou en
deux écrans (identifiant puis mot de passe), dont l'URL renseignée dans le projet est la page de connexion (ou
une page protégée qui y redirige), avec un compte de test enregistré dans le projet. Vérifié sur SauceDemo,
the-internet et la fixture à deux écrans.

**Pas couvert, à ne pas annoncer** (lot 07b) : SSO / OAuth (Google, Microsoft…), second facteur (TOTP, SMS), session
injectée ou jeton, CAPTCHA, formulaire de connexion ouvert dans une fenêtre après un clic, page d'accueil sans
formulaire vers laquelle il faut naviguer avant de se connecter.
