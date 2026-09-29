## Lot « Enregistrement assisté du chemin de connexion » — sous-lot D — rejeu automatique + garde-fou — terminé (en attente de CI et de fusion)

Décisions utilisées : aucune décision `D#` du registre du chantier `docs/PLAN-FIABILITE-VERDICT-2026-09.md` — ce lot est
hors de ce chantier (voir rapports des sous-lots A/B/C). Aucune décision structurante nouvelle nécessaire ici : la
migration (sous-lot C, table `project_login_recording`) et l'algorithme de rejeu réutilisent des choix déjà validés.

**Décision de PÉRIMÈTRE, prise seule, à confirmer avec le porteur** : le rejeu est câblé sur les points où TestPilot
ouvre réellement une session contre l'application — **exploration** (`exploration_service.start_exploration`) et
**exécution réelle** (`run_service.resolve_connection`, `runtime_env.env_du_projet` — ce dernier alimente aussi bien
un run déclenché par la CLI que la vérification automatique lancée par la génération). Les deux appels de
`verifier_connexion` dans `generation_service.py` (lignes 168 et 624) sont des **gardes** (ils vérifient seulement que
la connexion est complète, sans lancer de navigateur à cet instant) — non modifiés, sans effet sur le comportement.
Le texte de la consigne (« au prochain lancement d'exploration ou de test ») ne nomme pas explicitement la
génération ; ce choix suit ce texte au pied de la lettre plutôt que de l'étendre par supposition.

### Ce que le sous-lot change, en clair

Au prochain lancement d'une exploration ou d'un test (run réel, y compris la vérification automatique lancée par la
génération) sur un projet qui porte une séquence de connexion confirmée (sous-lot C), cette séquence est rejouée
**avant** le mécanisme habituel de détection/remplissage — elle franchit l'écran intercalé (sélection de pays,
bannière…), puis la détection générique existante (`tenter_connexion_generique`) prend le relais sur le formulaire de
connexion ainsi révélé. Si une étape enregistrée ne se retrouve plus (application changée), le rejeu s'arrête net
avec un message clair demandant de refaire l'enregistrement — jamais un repli silencieux sur une autre hypothèse.
Sans séquence enregistrée, rien ne change (comportement historique intact).

### Relu par le sous-agent verdict-reviewer

Un bloquant réel trouvé et corrigé, vérifié avec un vrai Chromium des deux côtés (avant/après) :
`page.get_by_role(role, name=name)` fait par défaut un matching PAR SOUS-CHAÎNE et INSENSIBLE À LA CASSE — sans
`exact=True`, un bouton renommé « France métropolitaine » ou « FRANCE » aurait matché le `name` enregistré « France »
et reçu un clic SANS LEVER, alors que ce n'est manifestement plus le bon élément. Corrigé (`exact=True` ajouté), avec
deux nouveaux tests `conformance` qui reproduisent exactement ces deux cas (sous-chaîne, casse). Ce bloquant invalide
l'affirmation qui figurait ici avant correction (« un changement cosmétique de casse serait déjà traité comme une
séquence obsolète ») — c'était FAUX, jamais vérifié sur un run réel avant la revue.

Deux points « à corriger », traités :
- `crawl_relogin_hook` mesurait la page de connexion AVANT le rejeu — si franchir l'écran intercalé implique une
  vraie navigation, la mesure portait sur l'écran intercalé, pas le vrai formulaire, recréant le faux positif que le
  correctif du 2026-09-15 visait à éliminer. Corrigé (rejeu déplacé avant la mesure), avec un test qui simule une
  navigation et vérifie que la route mesurée est bien celle d'après.
- `session_injectee` : la justification de l'exclusion du rejeu était présentée comme une garantie plutôt qu'une
  hypothèse — reformulée honnêtement dans le code et les tests (voir « Risques » ci-dessous).

### Changements

- `src/testpilot/connectors/_web_helpers.py` — `SequenceConnexionObsoleteError` (nouvelle exception dédiée, jamais une
  réutilisation de `ConnexionGeneriqueImpossibleError`, un défaut différent) ; `rejouer_sequence_connexion(page,
  etapes)` : rejoue chaque `{role, name}` via `page.get_by_role(role, name=name).click()`, arrêt net à la première
  étape introuvable OU ambiguë (Playwright lève déjà en mode strict par défaut sur plusieurs correspondances).
- `src/testpilot/connectors/generic_web.py` — `GenericWebConnector` porte `self._sequence_connexion` (lu depuis
  `project["sequence_connexion"]` par `from_project`, jamais une lecture DB directe par le connecteur) ; rejouée
  AVANT `tenter_connexion_generique`, aux DEUX points d'appel existants (`crawl_relogin_hook` pour l'exploration,
  `_tenter_connexion_generique` pour la perception UI/génération).
- `src/testpilot/api/services/exploration_service.py` — `start_exploration` lit
  `project_login_recordings.lire(conn, project_id)` et l'ajoute au dict `connexion` transmis au connecteur.
- `src/testpilot/connectors/runtime_env.py` — `ENV_LOGIN_RECORDING` (nouvelle variable d'environnement,
  `TESTPILOT_LOGIN_RECORDING`, JSON) ; `project_env`/`verifier_connexion` acceptent un paramètre
  `sequence_connexion` optionnel (rétrocompatible, `None` par défaut) ; `env_du_projet` la lit et la transmet,
  réservée au connecteur `web` (Odoo n'a pas ce problème d'écran intercalé).
- `src/testpilot/api/services/run_service.py` — `resolve_connection` lit la séquence et la transmet.
- `behave_runtime/steps_library/_base_helpers.py` — `authentifier_selon_la_strategie` gagne un paramètre
  `sequence_connexion` optionnel, rejouée AVANT toute stratégie, **sauf `session_injectee`**, sous l'HYPOTHÈSE non
  vérifiée sur une application réelle que le storage_state fourni fait disparaître l'écran intercalé (documentée
  honnêtement dans le code depuis la revue, voir ci-dessous — pas présentée comme une garantie). `_verifier_ou_reconnecter_session`
  (reconnexion mid-scénario) ne la transmet délibérément PAS : cette fonction ne s'exécute que si le mot de passe est DÉJÀ visible (`_mot_de_passe_visible
  is True`), donc l'écran intercalé, par construction, n'y réapparaît jamais.
- `behave_runtime/environment.py` — lit `TESTPILOT_LOGIN_RECORDING`, la parse en JSON (best-effort : une valeur
  invalide ne peut venir que d'un bug de ce dépôt, jamais d'une saisie humaine — continue sans rejeu plutôt que de
  bloquer tout le run pour un signal qui n'est pas le mécanisme d'authentification principal) et la transmet à
  `authentifier_selon_la_strategie`.

### Tests ajoutés

- `tests/test_rejouer_sequence_connexion.py` (5, pages factices) — séquence vide sans effet, rejeu dans l'ordre,
  **falsifiable** : étape introuvable lève avec message clair (rôle+nom), étape ambiguë lève aussi, arrêt NET (l'étape
  suivante n'est jamais tentée après un échec).
- `tests/test_login_recording_generic_web.py` (6) — `from_project` lit/défaut la séquence ; rejeu AVANT détection sur
  les deux points d'appel (`crawl_relogin_hook`, `_tenter_connexion_generique`), preuve par ordre d'appels observé ;
  **falsifiable** : une séquence obsolète arrête net, la détection générique n'est jamais tentée après ; **falsifiable**
  (ajouté en revue) : la mesure de la page de connexion porte bien sur la route APRÈS le rejeu, pas l'écran intercalé.
- `tests/test_login_recording_exploration.py` (2) — `start_exploration` transmet `[]` sans séquence, la séquence
  exacte si confirmée.
- `tests/test_runtime_connection.py` (+5) — `project_env`/`env_du_projet`/`resolve_connection` transmettent bien
  `TESTPILOT_LOGIN_RECORDING`, l'omettent sans séquence, l'ignorent pour Odoo.
- `tests/test_login_recording_authentification.py` (4) — rejeu avant stratégie ; `session_injectee` ne rejoue
  JAMAIS ; **falsifiable** : une séquence obsolète lève `PreconditionNonRemplieError` (→ `blocked`) sans jamais
  tenter la détection générique ; non-régression explicite sans séquence.
- `tests/test_login_recording_rejeu_reel.py` (4, marqueur `conformance`, **vrai Chromium**) : reproduit le scénario
  même qui motive ce chantier (écran de sélection de pays avant un formulaire de connexion) — la séquence enregistrée
  franchit l'écran, puis la connexion générique aboutit réellement (page finale atteinte) ; **falsifiable** : une
  séquence périmée (bouton renommé) lève sans jamais tenter la connexion ; **falsifiable** (ajoutés en revue,
  bloquant `exact=True`) : un libellé qui CONTIENT le nom enregistré comme sous-chaîne est rejeté, un libellé de
  CASSE différente est rejeté.

26 tests au total, tous vérifiés falsifiables là où la consigne l'exige (étape 8 : jamais un repli silencieux). Les
trois nouveaux tests issus de la revue (`exact=True` ×2, ordre mesure/rejeu ×1) ont chacun été observés rouges en
revenant temporairement au code d'avant correctif — avec EXACTEMENT le mauvais résultat décrit par la revue — puis
verts avec le correctif restauré.

### Critères d'acceptation

- [x] Au prochain lancement d'exploration ou de test, la séquence enregistrée est rejouée automatiquement avant le
      mécanisme habituel.
- [x] Un élément introuvable arrête proprement avec un message clair demandant de refaire l'enregistrement — jamais
      une tentative silencieuse de deviner autre chose.
- [x] Garde-fou étape 9 (un seul essai, jamais de retry en boucle) : `rejouer_sequence_connexion` ne boucle pas en
      interne (arrêt net à la première étape en échec) ; ses appelants (`before_all`, exploration) ne l'invoquent
      qu'une fois par run/session, jamais en boucle de nouvelle tentative.

### Mesures

- `pytest -q -m conformance tests/test_login_recording_rejeu_reel.py` : 4 passed (~18 s, vrai Chromium), après
  correctif `exact=True`.
- `pytest -q` (suite complète) : 2914 passed, 16 skipped, 135 deselected — aucune régression, mesuré avant ET après
  les correctifs de revue (les trois correctifs ne touchent que des chemins déjà exercés par les nouveaux tests).
- `ruff check --select E9,F63,F7,F82 src behave_runtime tests scripts` : vert.
- Aucun appel LLM dans ce sous-lot — coût nul.

### Écarts constatés avec le plan

- **Périmètre volontairement limité à exploration + exécution réelle**, pas la génération elle-même (guard-only,
  voir « Décisions utilisées » ci-dessus) — à confirmer avec le porteur si un élargissement est souhaité.
- **`session_injectee` exclue du rejeu** — décision technique prise en cours de route (pas anticipée dans le plan
  ÉTAPE 0), justifiée ci-dessus (l'écran intercalé n'existe plus une fois authentifié par storage_state).
- Le point de branchement `_verifier_ou_reconnecter_session` (reconnexion mid-scénario) ne reçoit délibérément pas la
  séquence — l'écran intercalé ne peut pas y réapparaître par construction (précondition `_mot_de_passe_visible is
  True` déjà remplie avant cet appel).

### Risques / points à surveiller

- Le message d'erreur d'une séquence obsolète nomme le rôle et le nom enregistrés, mais ne dit pas CE QUI a changé
  sur la page — une personne devra comparer elle-même avec ce qu'elle voit avant de refaire l'enregistrement.
- Aucun écran n'affiche encore qu'une séquence a été rejouée avec succès ou a échoué, en dehors du message
  `blocked`/du log d'exploration — une personne qui ne consulte pas le détail d'un échec pourrait ne pas comprendre
  que le problème vient d'un écran intercalé changé, plutôt que de l'application elle-même.
- `page.get_by_role(role, name=name, exact=True)` — avec `exact=True`, la comparaison est stricte : un changement
  cosmétique du libellé (casse, espace, texte enrichi) est bien traité comme une séquence obsolète. C'est le
  comportement voulu (jamais une correspondance approximative), mais qui peut surprendre si le changement semble
  mineur à l'œil humain (ex. « France » → « FRANCE »).
- `session_injectee` repose sur une HYPOTHÈSE non vérifiée sur une application réelle (l'écran intercalé disparaît
  une fois authentifié par le storage_state fourni) — documentée comme telle dans le code depuis la revue, pas
  présentée comme une garantie. Si elle est fausse pour une application donnée (écran affiché à chaque visite, ou
  storage_state expiré/partiellement invalide), le diagnostic « session valide » pourrait être posé à tort sur
  l'écran intercalé lui-même — pas identifié comme un chemin vers un faux `conforme` (les étapes suivantes du
  scénario échoueront très probablement), mais un diagnostic erroné reste possible.

### Suggestions hors périmètre

- Étendre le rejeu à `generation_service.py` si le porteur juge que « lancement d'exploration ou de test » doit aussi
  couvrir la génération technique elle-même.
- Un écran qui affiche explicitement « chemin de connexion rejoué avec succès » ou l'inverse, plutôt que de le
  déduire d'un message d'erreur générique.
