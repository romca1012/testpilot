## Lot 07d — Vocabulaire universel — terminé (en attente de fusion)

Branche `lot-07d-vocabulaire-universel`, worktree `testpilot-lot07d`. Décisions utilisées : aucune (07d ne dépend ni de D7 ni de D8).

### Ce que le lot change, en clair

L'agent de génération n'avait, pour une application web quelconque, que les steps de formulaire (renseigner un champ, cliquer un bouton…). Dès qu'un test devait ouvrir une page,
lire un tableau, confirmer une boîte de dialogue, télécharger un fichier ou vérifier un appel réseau, il inventait du code — c'est-à-dire du texte non contrôlé, la source des faux
verts. Le lot ajoute **14 steps génériques** à la bibliothèque partagée (donc à son catalogue, proposé à tous les cas futurs) ; chaque vérification consigne un constat (lot 03).

| Step | Type |
|---|---|
| `j'ouvre la page "<chemin>"` | action — relatif à l'URL du projet, jamais une autre origine |
| `la page affiche le texte "…"` / `la page n'affiche pas le texte "…"` | vérification |
| `l'URL courante contient "…"` | vérification — sur le **chemin** |
| `le tableau "…" contient une ligne avec "…" et "…"` / `compte <n> lignes` | vérification |
| `je clique sur "…" dans la ligne contenant "…"` | action |
| `j'accepte la boîte de dialogue` / `je refuse la boîte de dialogue` | action — modale ARIA ou boîte native |
| `je télécharge le fichier via "…"` + `le fichier téléchargé se nomme "…"` / `contient "…"` | action + vérifications (CSV, texte, PDF) |
| `dans le cadre "…", je renseigne le champ … / je clique sur le bouton …` | actions dans une iframe |
| `un nouvel onglet s'ouvre sur "…"` | vérification (le nouvel onglet devient l'onglet courant) |
| `la requête "<méthode> <motif d'URL>" répond <code>` | vérification |

### Changements

- `behave_runtime/steps_library/_base_helpers.py` — section « Vocabulaire universel » (helpers `@constat`, sondes avec attente, ARIA d'abord).
- `behave_runtime/steps_library/generic/_generic_steps.py` — les 14 steps (actions `@given`+`@when`, vérifications `@then`).
- `behave_runtime/environment.py` — `installer_les_observateurs` (réponses réseau, boîtes de dialogue et onglets du scénario, numérotés) et un **repère posé au début de chaque action** (`before_step`).
- `tests/fixtures/torture_app/*.html` (12 pages) et `tests/test_vocabulaire_universel.py` — la preuve de bout en bout ; `tests/test_bibliotheque_falsifiable.py` — les 9 `Alors` et leurs helpers déclarés dans les listes de délégation (le garde-fou du lot 03 l'exige).
- `.github/workflows/generation-quality.yml` (job `browser-evidence`, chaque PR) et `conformance.yml` — le test rejoint la CI ; délai du job porté à 15 min.

### Tests ajoutés

`tests/test_vocabulaire_universel.py` (marqueur `conformance`, **vrai Chromium**, serveur HTTP local, aucun réseau) rejoue de VRAIS scénarios Behave dans le sous-processus complet (`BehaveRunner`, bibliothèque
de steps réelle) :

- **15 scénarios qui DOIVENT être `conforme`** (dont un tableau rempli en asynchrone, un tableau piégé, une bannière de cookies non bloquante, une boîte native acceptée AVANT l'action) ;
- **31 scénarios qui NE DOIVENT PAS l'être** : `non_conforme` quand l'application se comporte mal, `technical_error` quand le test est mal posé (ambiguïté, page vide ou en erreur, fichier jamais téléchargé, cible inconnue…) ;
  le test échoue si l'un d'eux est `conforme` (« FAUX VERT »).
- **Vérifié par mutation** (le test rouge mord vraiment) : retirer le contrôle de page vide et d'ambiguïté fait apparaître deux faux verts ; retirer le repère d'action et le chemin d'URL en fait apparaître deux autres.
- garde : aucun step de `generic/` ne référence `context.odoo` / `ODOO_*` (lu par AST) ; tests unitaires du chemin d'URL et du refus d'un paramètre vide.

### Critères d'acceptation

- [x] **Chaque nouveau step affirmatif a un test de falsifiabilité** — un scénario en échec par vérification, et un cas de revue pour chaque faux vert trouvé.
- [ ] « L'exploration et l'exécution utilisent le même code de connexion et le même contexte » — critère de 07c, déjà livré ; sans objet ici.

### Mesures

Aucun appel LLM dans ce lot. Les deux exécutions Behave du test de bout en bout durent ~4 min 40 s au total en local.

**Taille des prompts** (caractères, fins de ligne normalisées, `origin/master` → ce lot ; Règle 8 « boîte de dialogue native décidée AVANT l'action », demandée par le porteur) :
`system_prompt.md` 25 261 → 26 409 (+1 148, +4,5 %) ; `correction_prompt.md` 5 548 → 6 304 (+756, +13,6 %) ; `repair_prompt.md` 6 018 → 6 733 (+715, +11,9 %). Ordre de grandeur : +290 tokens
sur le prompt système de chaque génération (mis en cache par le fournisseur) et ~+190 tokens sur chaque appel de correction ou de réparation — une fraction de centime par cas, très en deçà du plafond de 1 € du §9.
Le coût de génération complet (`scripts/mesure_cout_cas.py`) n'a PAS été remesuré : il exige des appels LLM réels ; l'effet attendu sur le coût est négligeable, la mesure reste à faire au prochain lot qui lance une campagne.

### Revue `verdict-reviewer` — 2 bloquants et 9 points, tous traités

Verdict initial « BLOQUANT ». **Faux verts corrigés** :
1. **`la requête … répond`** jugeait la dernière réponse correspondante du scénario, y compris celle d'un `Soit` ou d'une étape antérieure : un bouton inopérant passait vert parce qu'une étape précédente avait émis la même requête. Chaque action pose maintenant un repère
   et **seules les réponses postérieures à la dernière action** sont jugées ; une 5xx suivie d'un 200 (retry) échoue au lieu d'être masquée.
2. **`l'URL courante contient`** cherchait le fragment dans l'URL entière : `/login?next=/dashboard` « contenait » `/dashboard`. Le fragment est cherché dans le **chemin** (la query ou le hash seulement si le fragment les porte).

Points « à corriger » traités : chaînes vides (déjà refusées par Behave au dry-run — un `{x}` exige un caractère — et par `_renseigne` en défense en profondeur) ; `n'affiche pas` compte aussi les cadres et les valeurs de champs, refuse une page vide **ou en erreur HTTP** ;
nom de tableau **exact** (`« Command »` ne trouve plus « Commandes »), repli sur un titre `h1`–`h6` exact, deux titres identiques = ambiguïté ; `compte N lignes` exclut l'en-tête `thead`, les tableaux imbriqués et les lignes masquées, et le zéro doit **tenir** 1,2 s ;
`contient une ligne avec a et b` compare par **cellule et par mot** (« 12 » n'est pas dans « 120 ») ; boîte de dialogue : une bannière non bloquante (`role=dialog` sans `aria-modal`) ne capte plus « j'accepte », plusieurs boutons = erreur, et **une décision prise APRÈS le clic est refusée en erreur technique** (la boîte s'est déjà ouverte et a été refusée d'office) au lieu d'être un « accepté » sans effet ;
nouvel onglet : seul un onglet **ouvert par l'action qui vient de s'exécuter** compte (le même onglet ne se constate pas deux fois) ; téléchargement : nom assaini, fichier temporaire supprimé avec le scénario, un bouton ET un lien de même nom = ambiguïté ; le journal réseau ne garde que `fetch`/`xhr`/`document` (les images et scripts noyaient la réponse utile).

### Écarts constatés avec le plan

- La consigne dit « le tableau localisé par rôle ARIA d'abord, puis par structure HTML » : c'est fait, avec des exigences en plus (nom exact, ambiguïté = erreur) issues de la revue.
- « Le fichier téléchargé … `contient` » : le plan cite CSV, TXT et PDF ; les formats texte usuels sont lus, un format illisible (xlsx…) est une **erreur technique**, jamais un vert.
- Les vérifications `nouvel onglet` et `requête` sont des `Alors` qui **agissent** aussi (changer d'onglet, lire un repère) : documenté dans leur docstring.

### Risques / points à surveiller

- **Boîte de dialogue native** : Playwright la refuse d'office à son ouverture ; le step doit donc être placé **avant** l'action qui l'ouvre (« Et j'accepte la boîte de dialogue » puis « Et je clique sur … »). Placé après, il est refusé en erreur technique — le prompt de génération l'enseigne désormais (Règle 8).
- Le comptage des lignes porte sur le **DOM rendu** ; une pagination n'est pas dépliée.
- `la page n'affiche pas le texte` ne juge pas un spinner encore à l'écran : il faut aussi constater l'état attendu (présence), pas seulement l'absence d'un défaut.
- Import différé de `installer_les_observateurs` / `poser_repere_action` dans `environment.py` : suit le motif déjà présent dans ce fichier (hooks), mais contredit la règle générale « imports au niveau module » de `CLAUDE.md` §6 — signalé.
- **Prompts** : la Règle 8 (décision de dialogue AVANT l'action, un exemple correct et un exemple refusé) est ajoutée aux trois prompts ; `tests/test_prompt_dialogue_native.py` la garde, vérifie que les steps cités existent au catalogue et que l'exemple « refusé » est celui que le test de bout en bout rejoue et refuse.
- Le test de bout en bout dure ~4 min 40 s : il tourne dans le job `browser-evidence` de chaque PR (délai porté à 15 min).

### Suggestions hors périmètre

- Un step « le tableau "…" est vide » explicite plutôt que « compte 0 lignes ».
- Déplier la pagination (« page suivante ») pour les tableaux paginés.
