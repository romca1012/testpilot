# Audit — verdict qui ne ment pas, tests sans erreur technique (2026-10-08)

Périmètre : branche `lot-qualite-agents-03-outils` (dépôt `testpilot-q3`), campagnes du banc d'agents `base-1`, `base-2`,
`base-3` et mesures « après réparation » (Haiku, Sonnet, 1 puis 2 tentatives). Méthode : lecture du code (deux audits
indépendants en lecture seule, puis vérification à la main des points les plus graves), relecture des 30 tests générés de
`base-3` et des rapports `docs/mesures/banc-agents-2026-10-0*.md`. Référence externe : rapport de recherche
`reports/Agent de test honnête et fiable.md` (plan en 9 étapes). Aucun code n'a été modifié pour cet audit.

## 1. Conclusion en une page

**Le verdict de TestPilot ne ment pas sur un point précis, et peut encore mentir sur plusieurs autres.**

- Ce qui est solide : un échec technique ne devient jamais `conforme` (deux axes séparés) ; un `Alors` passé sans constat
  réussi donne `indetermine` (Q1, D16/D17) ; une relance ou un repli adaptatif marque le vert « à confirmer ».
- Ce qui ne l'est pas : le verdict prouve qu'un `constater` **réussi** a été appelé, **pas** que sa condition dépend de
  l'application ni du critère métier. `constater(page.locator(".succes"))` est toujours vrai (un objet Locator est vrai en
  Python : `_base_helpers.py:202-212`, `ok = bool(condition)`). Plusieurs steps partagés vérifient trop peu (texte cherché
  par sous-chaîne n'importe où, « une erreur rouge quelque part »). La réparation peut réécrire les `Alors` et son vert est
  enregistré comme résultat du cas sans relecture. Une version sans avertissement est approuvée **d'office**, sans relecture
  humaine (`generation_service.py:574-578`).

**Les erreurs techniques après génération ont une cause unique : rien ne confronte ce que l'agent écrit à ce qui a été
observé, au moment où il l'écrit.** Le « dry-run » est `behave --dry-run` : il vérifie que chaque step a une définition, rien
n'est exécuté. L'annuaire de l'application (`data/domain/projet-*.json`) contenait pourtant les bons libellés (« Quantité de
… », `identifiant`, `mot_de_passe`, « Ajouter X au panier ») : il n'est ni injecté dans le banc, ni utilisé pour refuser un
littéral faux. Les contrôles qui existent (`smoke_check`, `assertion_lint`) tournent **après** la génération, sont
**détectifs**, et le banc ne les appelle même pas.

**Nos propres mesures sont biaisées sur trois points** (§5) : échantillon trop petit pour voir un progrès de moins de ~30 points ;
le rejeu du banc **n'active ni le mode qualification ni le mode strict**, donc le repli LLM à l'exécution a pu rattraper des
erreurs ; le banc mesure un chemin de génération qui n'est pas celui du produit (pas de `smoke_check`, pas de correction, pas
d'approbation).

**Ce qu'il faut pour atteindre l'objectif** (§6) : sept chantiers, dans cet ordre — (A) rendre le banc capable de mesurer
sans biais ; (B) fermer les trous du verdict qui produisent des faux `conforme` ; (C) rendre bloquants à l'écriture les
contrôles « littéral observé » ; (D) compléter la bibliothèque pour supprimer le code libre ; (E) « exécuter puis écrire » ;
(F) oracles traçables à la spec et certifiés par un défaut injecté ; (G) réparation bornée et revérifiée. A, B et C sont petits
à moyens, sans appel LLM, et suppriment l'essentiel des écarts observés.

## 2. Ce que les campagnes ont réellement montré

Base `base-3` (30 générations, 57 jeux) puis réparation Sonnet × 2 tentatives sur les mêmes tests.

| Classe d'erreur observée | Occurrences | Où | Contrôle qui l'aurait arrêtée |
|---|---|---|---|
| Champ technique inventé (`username` au lieu de `identifiant`) | 4 | `connexion_refusee` ×3, `connexion_valide` ×1 | « champ ∈ annuaire de la route », bloquant (§4.1) |
| Libellé réécrit sans accent (`Quantite de …`) | 4 | `panier_total_tva` t2/t3, `commande_persistance_serveur` t2 | « littéral = libellé observé à l'identique » (§4.1) |
| `aria-label` pris pour du texte visible (`:has-text`) / `aria-label` cherché sur un `<label>` | 2 | `panier_total_tva` t1 (+ réparations) | interdiction du CSS / `:has-text` libres ; snapshot texte ≠ nom (fait) |
| Page supposée inchangée après une action | 4 | `client_creation_valide` ×3, `client_creation_nom_limite` t3 | suivi de route par scénario (§4.3) |
| Appel HTTP direct / attribut de contexte inventé (`page.request`, `fetch`, `context.base_url`) | 3 | `commande_persistance_serveur` ×2, `panier_total_tva` t3 après réparation | refus AST (§4.4) |
| Mot de passe inventé | 2 (base-1, base-2) | `connexion_valide` | valeur d'un champ mot de passe ∉ métier validé → refus (§4.5) |
| Forme de la réponse de l'oracle devinée (`produit` = code au lieu de `nom`) | 2 | `commande_persistance_serveur` | forme JSON de l'oracle injectée + chemins validés (§4.6) |
| `l'oracle renvoie 0 résultat` sur un objet (compté 1) | ~8 (base-2) | création de client, persistance | step de comptage ajouté (fait) |

Chiffres utiles : 91,7 % des lignes de step des tests de `base-3` viennent de la bibliothèque partagée ; **5 des 9 erreurs
techniques sont dans des steps de la bibliothèque avec un paramètre faux** — la bibliothèque seule ne protège pas, il faut
contrôler ses **paramètres**. Les 4 autres sont dans les 8,3 % de code libre, tous écrits via `write_feature_file` (qui ne passe
pas par les contrôles du plan technique), et tous pour des besoins que la bibliothèque ne couvre pas (saisir dans une ligne de
tableau, lire une valeur à côté d'un libellé, relever un numéro puis l'utiliser, oracle « la liste contient »).

Réparation : Haiku 0/5 sur trois mesures ; Sonnet × 2 tentatives : 2/5 réparés, 1/5 devenu exécutable mais **faux rouge**
(la réparation a transformé une erreur technique en accusation de l'application saine). Aucun faux vert observé (0/23), avec un
intervalle qui monte à ~15 %.

## 3. Verdict qui ne ment pas : les trous, par gravité

Preuves : fichier:ligne sur `testpilot-q3`. « Vérifié » = relu à la main pendant cet audit ; les autres viennent de l'audit en
lecture seule et sont à confirmer par un test de falsifiabilité avant correction.

### 3.1 Gravité élevée — peuvent produire un faux `conforme`

| # | Trou | Preuve | Correction proposée |
|---|---|---|---|
| V1 | La condition de `constater` n'est jamais liée à l'application : Locator ou méthode non appelée toujours vrais, tautologies (`1 == 1`, `len(x) >= 0`), valeur fixée par le test lui-même, `constater` renommé/neutralisé | `_base_helpers.py:202-212` (vérifié) ; `assertion_lint.py` non bloquant | `constater` lève une erreur technique si la condition n'est pas un `bool`/nombre (refuse Locator, callable, objet) ; garde AST bloquante : la condition doit dépendre d'une lecture de `context.page`/oracle/RPC ; refus d'un alias de `constater` |
| V2 | Version sans avertissement **approuvée d'office**, sans relecture humaine | `generation_service.py:574-578` (vérifié), `review_gate.py:50-68` | Tant que V1 n'est pas fermé : relecture humaine obligatoire des `Alors` ; ensuite, approbation automatique seulement si tous les contrôles bloquants (§4) sont passés |
| V3 | La réparation peut réécrire les `Alors` et les valeurs attendues (le gel du `.feature` n'existe que dans le prompt) ; contrôle `repair_diff` seulement détectif | `repair_prompt.md:90-99` ; `repair_service.py:483-497` ; `repair_diff.py` | Refus mécanique de tout diff sur les `Alors`/`Examples` et sur le corps d'un `@then` hors des deux exceptions documentées |
| V4 | Le vert d'une version réparée **non relue** est écrit dans le résultat du cas, avec une confiance nominale, même si la réparation est ensuite refusée | `run_service.py:344-349, 512-514` ; `repair_service.py:530-553` | Pas de mise à jour du résultat pour une version non approuvée ; nouvelle confiance `apres_reparation` (libellé FR serveur + frontend) |
| V5 | Bug « élément absent » classé `wrong_field_name` → `technical_error` → **réparation** ; cause dominante calculée sur tout le run | `defect_taxonomy.py:134,142,392-401` ; `repair_circuit.py:111-133` | Un échec sous `Alors` ne déclenche jamais la réparation (→ `indetermine` + décision humaine) ; un `assertion_mismatch` dans le run bloque la réparation |
| V6 | Valeurs attendues copiées de l'application (le prompt pousse à « observer » les textes ; `smoke_check` signale tout message non observé et la correction le remplace par l'observé) : un bug devient l'attendu | `system_prompt.md:258-307` ; `inspect.py:276-331` ; `smoke_check.py:426-459` | Chaque valeur attendue porte sa source (`spec` ou `observé`) ; une valeur `observé` ne peut pas justifier `conforme` au premier run ; un écart spec/observé va à un humain, jamais résolu en faveur de l'observé |
| V7 | Steps partagés trop faibles : `page_affiche_texte` (sous-chaîne, sans casse, partout, sans ancrage sur l'action) ; `validation_error_inline` (n'importe quel élément rouge ou `role=alert`) ; scénario négatif « n'a pas augmenté » vert sans soumission prouvée ; existence Odoo par recherche globale ; `step_action_refusee` (toute exception = refus) | `_base_helpers.py:2978-3000, 1904-1921, 2354-2380` ; `_odoo_steps.py:71-89` ; `_odoo_droits_steps.py:33-41` | Une vérification = une cible précise + une fenêtre ancrée sur la dernière action ; exiger une soumission prouvée pour un scénario négatif ; cloisonner les recherches par `id > max_id` ; ne reconnaître que `AccessError` |
| V8 | Session expirée non détectée avant un `Alors` : sur la page de connexion, « n'affiche pas », « aucune erreur », « URL contient /web » et des sous-chaînes passent | `_base_helpers.py:2958-2975, 3018-3025` | Garde dans `before_step` des `then` : page de connexion détectée (champ mot de passe visible, URL de connexion) → `blocked` |
| V9 | Écritures RPC autorisées dans les steps générés : on peut « faire » l'action par RPC au lieu de l'interface, puis la constater | `write.py:66-118,342` | Interdire `write`/`create`/`unlink`/appels de méthode RPC dans le code généré (hors préparation `@given` listée) |
| V10 | Un constat **échoué** avalé (`except (AssertionError, X): pass`) n'empêche pas `conforme` si un autre constat a réussi | `behave_result.py:446-457` ; `write.py:224-232` | Tout `ok:false` dans un scénario passé → `indetermine` ; la garde `except` gère les tuples |

### 3.2 Gravité moyenne

Repli LLM à l'exécution actif hors campagne stricte (y compris dans **chaque** `je clique sur le bouton`), repli de clic par
sous-chaîne silencieux, libellés de menu appris réinjectés comme « confirmés » (`_base_helpers.py:709-713, 787-789,
1137-1171, 2124-2126` ; vérifié pour la coupure qualification/strict, l.1148-1153) ; oracle : un objet ou un corps vide comptés
1 ou 0, requêtes non cloisonnées au scénario, erreur HTTP de l'oracle envoyée en réparation ; `ground_truth` qui affirme une
vérification serveur qui n'a pas eu lieu (Odoo : `backend_verified` d'office) ; édition du métier qui conserve l'ancien Gherkin
approuvé ; refus serveur erroné classé « donnée invalide » puis **appris** (le bug est contourné au run suivant) ; agent de
correction qui réécrit librement avant tout run ; gardes de `write.py` contournables (`__import__`, `page.request`, `getattr`
avec chaîne, écriture directe du sidecar des constats).

### 3.3 Gravité faible

`no_duplicate` / `no_partial_record` verts si rien n'est créé ; constats partagés entre scénarios de même nom ; Soit « aucun
enregistrement » qui avale les erreurs ; égalités `str(a) == b` (surtout des faux rouges : `True`/`true`, `10.0`/`10`).

## 4. Tests sans erreur technique : ce qui manque, contrôle par contrôle

Principe commun : **un contrôle déterministe, bloquant, au moment où l'agent écrit**, qui renvoie à l'agent la valeur observée.
Pas de LLM, pas de régénération.

| # | Contrôle manquant | Source de vérité | Où le brancher | Effort |
|---|---|---|---|---|
| T1 | Tout paramètre `{field}` / bouton / libellé cité dans un step (bibliothèque ou code libre) existe **à l'identique** (accents, casse) sur la route courante ; sinon refus avec l'orthographe observée | annuaire `data/domain/projet-<id>.json` (champs, actions, liens) + inspections de la session | `write_feature_file`, `write_test_plan`, `write_steps_file` (AST des `get_by_*`, `fill_field`, `click_button`) | Petit |
| T2 | Injecter l'annuaire de la route dans le prompt (noms ET libellés des champs, boutons) ; aujourd'hui seuls routes et `<select>` sont injectés, et rien du tout dans le banc (`portal_routes=[]`) | annuaire | `prompt._section_domaine_mesure`, `qualify_campaign_pilot.py:400-404` | Petit |
| T3 | Suivi de route par scénario : `j'ouvre la page "X"` fixe la route, un lien suit son `href`, une action qui soumet rend la route « inconnue » ; tout littéral cité sur une route inconnue ou absente est refusé | annuaire (transitions, `actions[].soumet`) | `write_*` | Moyen |
| T4 | Refus AST : `page.request`, `evaluate` contenant `fetch`/XHR, `goto` hors origine ou vers `/__*`, `socket`/`subprocess`/`__import__` ; lectures `context.X` limitées aux attributs posés par le runtime (calculés par AST) ou écrits par un step antérieur ; secrets (`web_password`…) interdits | AST de `behave_runtime` | `write_steps_file` | Petit |
| T5 | Valeur saisie dans un champ `type=password` ∉ texte du métier validé → refus ; connexion valide = `je me connecte en tant que "principal"` | annuaire + métier | `write_*` | Petit |
| T6 | Forme JSON de chaque requête d'oracle relevée et injectée ; chemins des steps d'oracle validés contre elle | lecture GET de l'oracle | génération + `write_*` | Petit |
| T7 | `inspect_page_form` : signaler la redirection (page de connexion vue alors qu'on est connecté), ranger la preuve sous l'URL finale, ne plus garder un seul champ par `name` ; `_apply_effect` fusionne **tous** les `verified_fields` (aujourd'hui seulement `inspect_schema`/`inspect_page_form`, vérifié `react_loop.py:163`) | outils | `inspect.py`, `_web_helpers.py`, `react_loop.py` | Petit |
| T8 | Steps manquants qui poussent au code libre : saisir dans une ligne (`… dans la ligne contenant "X"`), lire la valeur affichée à côté d'un libellé, texte selon un motif, relever une valeur puis la réutiliser, oracle « la liste contient un élément où … » | — | bibliothèque partagée (avec tests de falsifiabilité) | Moyen |
| T9 | Interdire le CSS libre et `:has-text`/`text=` dans le code généré au profit des helpers et de `get_by_role` + nom observé ; retirer du prompt les exemples CSS (`system_prompt.md:197-252`) et le mot « ASCII » ambigu | — | `write_steps_file`, prompt | Petit |
| T10 | « Exécuter puis écrire » : l'agent choisit un step et un élément observé, l'outil exécute dans un vrai navigateur et écrit le step depuis l'élément réellement touché | navigateur | nouvelle boucle de génération | Gros (décision : exécuter avant la relecture, sur un bac à sable remis à zéro) |

T1 à T7 et T9 ferment, d'après les tests de `base-3`, les 9 erreurs techniques observées sauf « page changée après une
action » quand l'annuaire ne connaît pas la page d'arrivée (réponse d'un POST) : seul T10 la ferme par construction.

## 5. Biais de nos propres mesures

1. **Taille** : 10 cas × 3 essais ≈ 10 observations indépendantes ; intervalle ≈ ±31 points ; « 0 faux vert » laisse un taux réel
   possible de 10 à 30 %. Pour affirmer < 2 % il faut ~150 défauts injectés indépendants.
2. **Repli LLM actif pendant le rejeu du banc** (vérifié) : `scripts/banc_agents.py` ne pose ni `TESTPILOT_QUALIFICATION` ni le
   mode strict pour les jeux ; `_repli_adaptatif` (`_base_helpers.py:1137-1153`) n'est coupé que par l'un des deux. Des tests ont
   donc pu être « sauvés » à l'exécution par un appel LLM (par ex. `username` → `identifiant` sur `connexion_refusee`, compté
   `conforme`). Les campagnes `base-1`…`base-3` **surestiment** peut-être l'exécutabilité ; à corriger avant toute nouvelle mesure.
3. **Chemin mesuré ≠ chemin du produit** : le banc appelle `GenerationAgent.generate` puis exécute ; il saute `smoke_check`,
   `assertion_lint`, l'agent de correction et l'approbation. Les chiffres valent pour la génération brute, pas pour le produit.
4. **Specs et attendus modifiés en cours de route** (oracle déclaré, deux specs clarifiées) : comparaisons entre campagnes
   seulement indicatives.

## 6. Ce qu'il faut faire, dans l'ordre

| Lot | Contenu | Ferme | Coût LLM | Effort |
|---|---|---|---|---|
| **A. Banc sans biais** | mode strict/qualification pendant les jeux ; 30-50 cas sur ≥ 3 applications dont une jamais vue (Odoo local + web) ; ≥ 150 défauts injectés ; comparaisons appariées dans la même campagne ; indicateur « générations par cas accepté » ; mesurer aussi le chemin produit (avec `smoke_check`) | §5 | ~5 à 15 $ par campagne | Moyen |
| **B. Verdict** | V1 (condition typée + dépendance AST), V10, V3, V4, V5, V8, V9 ; V2 tant que V1 n'est pas fermé ; puis V7 step par step | §3.1 | 0 | Moyen |
| **C. Littéraux observés** | T1, T2, T4, T5, T6, T7, T9 | 8 des 9 erreurs de `base-3` | 0 (moins de tokens perdus) | Petit à moyen |
| **D. Bibliothèque** | T8 + T3 | le code libre restant | 0 | Moyen |
| **E. Exécuter puis écrire** | T10, sur bac à sable remis à zéro | « page changée », le reste par construction | ~0,09 $/cas (calcul) | Gros, décision |
| **F. Oracles certifiés** | V6 : source `spec`/`observé` par valeur attendue ; « preuve forte » seulement si le scénario a déjà échoué sur un défaut injecté violant le critère | faux verts par oracle faible | 0 (exécutions en plus) | Moyen |
| **G. Réparation bornée** | réparation de l'adressage seulement (locator, attente), jamais des `Alors` ; diff relu ; un test réparé doit refaire échouer les défauts qu'il détectait | V3-V5, faux rouges de réparation | ~0,05 $/tentative | Moyen |

Critère de clôture proposé (à valider) : sur le jeu mis de côté, borne haute des erreurs techniques au premier run < 2 %, borne
haute des faux verts < 2 %, une génération par cas accepté, coût mesuré < 1 € par cas.

## 7. Décisions à prendre

1. **Relecture humaine** : la rétablir obligatoirement sur les `Alors` tant que V1 n'est pas fermé (aujourd'hui approbation
   automatique) ?
2. **Exécuter avant la relecture** (lot E) : sur une instance bac à sable remise à zéro, l'outil peut-il exécuter pendant la
   génération ? C'est le seul moyen de fermer « page changée après une action » par construction.
3. **Contrôles bloquants à l'écriture** (lot C) : les refus renvoient l'agent à corriger dans la même génération ; acceptable ?
4. **Repli LLM à l'exécution** : le couper par défaut (mode strict) en campagne, et ne l'autoriser qu'explicitement ?
