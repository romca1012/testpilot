## Lot 07c — Contexte navigateur figé — terminé (en attente de fusion)

Branche `lot-07c-contexte-navigateur`, worktree `testpilot-lot07c`. Décisions utilisées : aucune (07c ne dépend ni de D7 ni de D8). Au passage, le premier commit de la
branche coche D6, D7 (HTTP d'abord) et D8 au registre (validées le 2026-09-25, précisions consignées).

### Ce que le lot change, en clair

Un navigateur lancé sans réglage prend la **langue et le fuseau horaire de la machine** qui le lance. La même campagne n'affichait donc pas les mêmes libellés, les mêmes
dates ni la même mise en page sur un poste de développement, sur le staging ou en CI — des différences que le verdict pouvait prendre pour un défaut, ou qui pouvaient en
masquer un vrai (cas mesuré : « Sondages » / « Surveys » sur Sapian, 2026-09-22). Le contexte est maintenant **décidé par le projet** — défauts `fr-FR`, `Europe/Paris`,
1440×900 — et **identique** pour l'exploration (ce que l'agent voit) et pour l'exécution (ce que le test verra).

### Changements

- `src/testpilot/connectors/contexte_navigateur.py` (nouveau, **pur**) — le contexte (`ContexteNavigateur`), sa validation en français (`erreurs`), les défauts, la lecture depuis
  un projet ou l'environnement ; une valeur invalide lue de la base retombe sur le défaut **en le disant**, sans planter une campagne.
- `store/db.py` (`_migrate_50_contexte_navigateur`), `alembic/versions/f60b4d8e1a53_…`, `schema_sa.py`, `portable_connection.ALEMBIC_HEAD` — trois colonnes `project.browser_locale`,
  `browser_timezone`, `browser_viewport` ; **vide = le défaut**, donc aucun projet existant n'a rien à renseigner.
- `api/schemas.py`, `api/routes/projects.py`, `store/repositories.py` — saisie à la création et à l'édition, **422 en français** pour une valeur mal formée, valeurs **effectives**
  exposées (`browser_effectif`) pour que l'écran dise ce qui sera réellement utilisé sans le recalculer.
- `connectors/runtime_env.py` — `project_env` transmet **toujours** le contexte (défauts compris) au sous-processus, pour Odoo comme pour le web.
- `behave_runtime/environment.py` — `contexte_navigateur_fige()` : `new_context(**…)` au lieu de `new_context()` nu.
- `connectors/generic_web.py`, `odoo.py` — les cinq créations de contexte de l'exploration prennent le contexte du projet.
- Frontend : `ProjectsList.vue` (fieldset « Navigateur de test » à l'édition, placeholders = valeurs effectives), `api.ts`.
- `.github/workflows/generation-quality.yml` — le test à vrai navigateur rejoint le job `browser-evidence` de chaque PR.

### Tests ajoutés

- `tests/test_contexte_navigateur.py` (25) — défauts, validation, **valeur invalide ⇒ défaut sans plantage (falsifiable)**, `project_env` (défauts compris, Odoo et web), le harnais relit
  exactement ce que le projet a écrit, constantes dupliquées d'accord, l'exploration passe le contexte du projet (web et Odoo) et, **sans réglage, les défauts et non ceux de la machine
  (falsifiable)**, API (défaut effectif, saisie, **422 à la création et à l'édition**, `""` = retour au défaut), et une **garde qui échoue si un `new_context()` nu réapparaît** dans les
  connecteurs ou le harnais.
- `tests/test_contexte_navigateur_reel.py` (4, `conformance`, **vrai Chromium**) — sur un contexte `ja-JP` / `Asia/Tokyo` / 1111×777, `navigator.language`, le fuseau, la fenêtre et une date
  affichée (« 2026年7月5日 8:30 » pour 23:30 UTC le 4 juillet) sont réellement ceux du projet ; l'exploration et l'exécution voient la même page ; **falsifiable : un `new_context()` nu
  donne un autre contexte** ; les défauts donnent `fr-FR` / `Europe/Paris` / 1440×900 quelle que soit la machine.
- `tests/test_migration_contexte_navigateur.py` + `test_schema_sa_portable.py` — colonnes, reprise d'une base d'avant (projets intacts, colonnes vides), idempotence.
- `frontend/src/__tests__/ProjectsList.connexion.spec.ts` (+2) — placeholders = valeurs effectives, du vide part quand on n'a rien saisi, les réglages saisis partent.

### Critères d'acceptation

- [x] **L'exploration et l'exécution utilisent le même code de connexion et le même contexte** — le contexte : prouvé (test à vrai navigateur « la même page » + garde contre un
  `new_context()` nu). Le **code de connexion** partagé est le périmètre du lot 07a (déjà livré : `tenter_connexion_generique`, `odoo_login`) ; 07c n'y touche pas.
- [ ] « Chaque nouveau step affirmatif a un test de falsifiabilité » — **sans objet pour 07c** (aucun step) ; c'est le critère du lot 07d.

### Mesures

Aucune mesure chiffrée à comparer (pas de changement de prompt, aucun appel LLM, coût nul). Preuve à vrai navigateur ci-dessus ; suites : voir le résultat final ajouté à la session.

### Écarts constatés avec le plan

- Le plan dit « passés au sous-processus par `runtime_env` » : c'est `project_env` (le traducteur pur) qui les écrit ; `verifier_connexion` n'a rien à refuser (aucun réglage n'est obligatoire).
- Le plan cite `generic_web.py` et `odoo.py` pour l'exploration : elles créaient **cinq** contextes, tous couverts ; `_sonde_saisie.py` reçoit un contexte déjà créé et n'a rien à changer.
- La création d'un projet accepte les trois réglages côté API, mais l'écran ne les propose qu'à l'**édition** (les défauts s'appliquent dès la création).

### Risques / points à surveiller

- Les projets existants passent de « la langue de la machine » à `fr-FR` / `Europe/Paris` / 1440×900. Un test écrit en anglais pour un site anglophone doit maintenant déclarer `en-US` dans le projet ;
  un site qui rend un libellé selon `Accept-Language` peut donc changer d'affichage à la première exécution après déploiement (c'est le but, mais à savoir).
- `zoneinfo` sous Windows a besoin du paquet `tzdata` ; présent ici, ajouté aux dépendances pour une installation propre.
- Le viewport est borné à 320–3840 × 320–2160 ; au-delà, le serveur refuse.

### Suggestions hors périmètre

- Proposer les trois réglages dès la création du projet (aujourd'hui : à l'édition).
- Un `Accept-Language` explicite (aujourd'hui dérivé de `locale` par Chromium) et le mode « couleurs / mouvement réduit » si un site en dépend.
