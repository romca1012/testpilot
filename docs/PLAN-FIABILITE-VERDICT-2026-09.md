# Plan — Fiabilité du verdict et couverture web / ERP

Date : 2026-09-23. Statut : **À VALIDER par le porteur** (registre des décisions, §4).
Exécution : Claude Code, un lot à la fois, via les commandes `.claude/commands/lot-NN-*.md`.
Règles de travail : `CLAUDE.md` à la racine.

## 1. Objectif

Qu'un statut produit par TestPilot soit **vrai** — `passed` veut dire que l'application a été
sollicitée et a prouvé le comportement attendu, `failed` qu'elle a dévié, `blocked` que
l'environnement a empêché de juger, `retest` que le test lui-même est à corriger — et que ce soit
vrai pour une application web quelconque comme pour un ERP Odoo au-delà du portail.

## 2. Point de départ mesuré

`docs/QUALITE-GENERATION-2026-09-22.md` : sur 7 premiers passages, 4 erreurs techniques, 1 seul
verdict métier exploitable. L'audit du 2026-09-23 a identifié les causes suivantes.

### 2.1 Défauts qui rendent un statut faux

| Réf | Où | Défaut | Conséquence |
|---|---|---|---|
| F1 | `_base_helpers.py` : `record_count_not_increased` (l.278), `memorize_record_count` (l.1704), `check_count_not_increased` (l.1772), `check_count_increased_by_one` (l.1987) | Comptage global `search_count([])` | Faux PASSED si un tiers crée pendant que le test échoue ; faux FAILED si deux créations. **Corrigé par le lot 01** (comptage cloisonné par `id > max_id`, affiné par un marqueur de tentative sur les champs à contrainte d'unicité). **Résidu documenté par D10** : sans marqueur (champs sans contrainte d'unicité — la majorité), une création tierce unique dans la même fenêtre de quelques secondes reste indiscernable de celle du scénario ; fermer ce résidu à zéro exigerait un marqueur sur TOUT scénario de création (hors périmètre du lot 01, cf. D10) |
| F2 | `defect_taxonomy.classify_failure` + `@given` de `odoo/_odoo_background_steps.py` et `_odoo_steps.py` | Tout `AssertionError` devient `ASSERTION_MISMATCH`, quel que soit le type de step | Prérequis absent ou bug du test rapporté comme défaut applicatif. **Mesuré le 2026-09-24 (mesure de base du lot 12, cas 101, tirage 1)** : un `Soit le module Odoo "pilote_p1_c101_i1_…" est installé` (assertion d'ENVIRONNEMENT inventée par l'agent, dans un `@given`) lève `AssertionError: Le module Odoo … n'est pas installé` → classé `non_conforme` alors que rien n'a été testé sur l'application : c'est exactement F2 (à traiter au lot 02, D1/D2) |
| F3 | `_adaptive_resolution.py`, `executor.py` (retry l.64) | Un vert obtenu par résolution LLM ou au 2ᵉ essai n'est pas distingué | Régressions d'UI absorbées en silence |
| F4 | `status.scenario_verdict` | `passed` → `conforme` sans preuve qu'une assertion s'est exécutée ; `assertion_lint` statique et non bloquant | Tests verts par construction |
| F5 | `status.statut_de_test` | `technical_error` est toujours couplé à `indetermine` → `retest` ; `blocked` n'est jamais produit automatiquement | Panne d'environnement confondue avec script cassé |
| F6 | `environment.py` l.118 et l.397-409 | Teardown limité à `helpdesk.ticket` ; restauration de `employee_front_role_ids` (champ Sapian) dans le harnais générique | Pollution, collisions d'unicité au rejeu, code client dans le socle. **Ajout du 2026-09-24 (ticket 30298)** : une création sans step de comptage n'est pas nettoyée — le registre ne voit que ce qui a été explicitement enregistré (`register_created`) ; F9 ferme la cause observée (les steps du catalogue enregistrent), pas le cas général |
| F7 | `_base_helpers.py` : `verifier_soumission_non_bloquee`, `_refus_par_le_navigateur`, `click_first_actionable` | Le contrôle de refus se déclenche sur N'IMPORTE QUEL clic (y compris une navigation intermédiaire — onglet, lien, changement d'étape d'un formulaire multi-écrans), pas seulement sur une vraie soumission | Faux `donnee_invalide` : accuse le jeu de données à tort alors qu'aucune soumission n'a eu lieu (mesuré en campagne réelle le 2026-09-23, cas 95, projet 1) — trouvé en cherchant à valider le lot 01 |
| F8 | `_base_helpers.py` : chaîne de diagnostic de refus (`diagnostic_soumission`, assertions générées sur le texte d'un message attendu) | Une assertion générée fige un texte de message DEVINÉ par l'agent plutôt qu'observé pendant la génération | Faux `non_conforme`/`failed` : l'application refuse correctement, c'est le texte attendu par le test qui est faux (mesuré le 2026-09-23, cas 97, projet 1) |
| F9 | `generation/tools/write.py` : `write_steps_file` | Un step GÉNÉRÉ recompte lui-même (`search_count([])`, `len(search(...))`, `len(read(...))`) hors des helpers cloisonnés du lot 01 — le prompt et le message de refus recommandaient même ce motif | Réintroduit le faux PASSED/FAILED de F1 dans le code généré, là où aucun test du dépôt ne le voit (mesuré le 2026-09-23, cas 95 régénéré : comptage global décalé de 1 → faux `non_conforme`, ticket créé mais non nettoyé faute de `register_created`). **Corrigé par le lot 11** : refus bloquant par AST |
| F10 | `_base_helpers.py` : `check_count_increased_by_one` (fin de la chaîne de diagnostic), `diagnostic_soumission` | Un refus SILENCIEUX (rien créé, ni la page ni le serveur n'ont donné de raison) lève une `AssertionError` classée `non_conforme`, alors que le diagnostic joint dit lui-même « Verdict honnête — l'outil NE conclut PAS à un défaut sans preuve. À instruire côté application » | Faux `non_conforme` (I2) : le statut affirme un défaut que le message refuse d'affirmer. Mesuré le 2026-09-24 (mesure de base du lot 12, cas 99, 3 tirages sur 3 : `numero_facture1` = « 1234567 » accepté par le masque, soumission sans effet, cause NON instruite — ce n'est plus le masque). Attendu : `indetermine` (« à instruire »), jamais `conforme` ni `non_conforme`, tant qu'aucune preuve ne désigne l'application ; à traiter avec les causes du lot 02 (nouveau type de constat « refus non expliqué », D-à ouvrir) **Analysé le 2026-09-24 (lot 02, sans correctif)** : ce n'est pas un silence — HTTP 500 (`KeyError: 0`, équipe de support absente) non capturé par l'outil ; voir `docs/mesures/lot02-analyse-f10-cas99-2026-09-24.md` ; **traité par la décision D12 (2026-09-24), lot 02** : 5xx → `non_conforme` prouvé, silence total → `indetermine` (cause `refus_non_explique`) ; rejeu des 6 tirages : `docs/mesures/lot02-rejeu-f10-cas99-2026-09-24.md`. **Hypothèse à instruire au lot 03, NON confirmée** : le `KeyError: 0` du cas 99 viendrait d'une équipe de support absente de la configuration de l'instance de test (défaut de configuration, pas de l'application) ; si elle se confirme, le cas 99 relève d'une précondition d'environnement (`blocked`), pas d'un `non_conforme`. |
| F11 | `generation/references.py` : `verifier_references` (cellules `Examples` d'un Scénario Plan) | Les valeurs des tables `Examples` ne sont jamais vérifiées : seuls les paramètres `<x>` sont ignorés, donc une valeur d'`Examples` inexistante (produit halluciné, partenaire absent) passe le refus D11 | Faux départ non détecté à l'écriture : le run est gaspillé alors que D11 promet de l'éviter. Relevé à la revue du lot 12 (2026-09-24). Attendu : vérifier chaque cellule d'`Examples` contre la même source, ou avis détectif ; lot futur |
| F12 | `generation/tools/inspect.py` : `ctx.options_select` (indexé par nom de champ pour TOUTES les pages inspectées) | Deux pages qui portent un champ de même nom (`type`, `ville`) mais des options différentes fusionnent leurs options dans un même ensemble : la valeur légitime d'une page peut être refusée à tort (ou une valeur d'une autre page acceptée) | Refus D11 à tort (budget) ou faux accord. Relevé à la revue du lot 12 (2026-09-24). Attendu : indexer par route et par champ, comme `contextual_warnings` le fait pour les preuves UI ; lot futur. **Même famille** (revue du 2026-09-24, dernier passage) : deux `<select>` de MÊME NOM sur une page se confondent (`base` de la sonde et `options_select` sont des dictionnaires par nom) : seul le premier est changé, le dernier écrase l'autre. **Même famille aussi — lot 03 (2026-09-24)** : le rattachement des constats consignés à leur scénario se fait par NOM de scénario (`behave_result.rattacher_constats`) : deux scénarios de même nom dans un `.feature` partageraient leur décompte (un constat sur l'un masquerait l'absence sur l'autre — faux `conforme` rare). Une seule entrée pour la famille « collision de clé par nom/libellé » : indexer par identité (route + champ ; nom + index de scénario) ou refuser les doublons à l'écriture (`write_feature_file`) ; lot futur |
| F13 | `connectors/_sonde_saisie.py` : `_sonder_champ` (`remplir` refusé) et `_garde_reseau` (course de 40 ms) | (1) Quand `fill` est refusé par le navigateur (`remplir` rend `False`), le `continue` saute le test `ecritures` avant la chaîne suivante ; (2) une requête d'écriture émise par une saisie peut n'être traitée par le gestionnaire d'interception qu'au tour suivant : `_SETTLE_MS` = 40 ms réduit la course sans la supprimer | (1) fenêtre minuscule et théorique (un `fill` qui lève n'écrit rien) ; (2) au pire UNE saisie de plus après une écriture, jamais une écriture qui atteint le serveur (la requête est abandonnée avant l'envoi). Relevés à la revue du lot 12 (2026-09-24), non corrigés dans ce lot par décision du porteur. Attendu : tester `ecritures` avant chaque chaîne, y compris après un refus ; mesurer la course avant de la régler |

### 2.2 Manques de couverture

| Réf | Périmètre | Manque |
|---|---|---|
| C1 | Web générique | Aucun step de connexion à l'exécution : `WEB_USER`/`WEB_PASSWORD` posés dans `before_all`, jamais utilisés, alors que l'exploration se connecte (`tenter_connexion_generique`) |
| C2 | Web générique | Pas de `storage_state`, pas de stratégie d'auth déclarée (TOTP, session injectée, SSO) |
| C3 | Tous | `new_context()` sans `locale`, `timezone_id`, `viewport` (`environment.py` l.181) |
| C4 | Web générique | Vocabulaire incomplet (tableaux, dialogues, téléchargements, iframes, onglets, réponses réseau) et steps propres à une appli dans `generic/` (« je force le nom du ticket », « … avec accessoires ») |
| C5 | Web générique | Aucun oracle backend : verdict `ui_only` sans alternative |
| C6 | Odoo | Aucun vocabulaire ERP : boutons de workflow, barre d'état, lignes one2many, assistants, filtres de liste, effets en chaîne, rapports, changement d'utilisateur / de société |
| C7 | Odoo | Pas de détection de version à l'exécution (`/odoo/…` ≥ 17.2 vs `/web#…`, structures DOM 16/17/18) |
| C8 | Mesure | Aucune instance Odoo de référence : la conformité ne tourne que sur SauceDemo / the-internet, la fiabilité Odoo n'est mesurable que sur la recette client |
| C9 | Agents | Outils de perception limités aux formulaires (`inspect_page_form`) ; aucune vue des boutons/états d'une vue Odoo ni de l'arbre d'accessibilité d'une page ; aucune règle « assertion uniquement en `Alors` » |
| C10 | Génération | Valeurs de champ écrites par l'agent sans avoir été observées (masque de saisie non relevé, référence relationnelle/option de liste inexistante) — même défaut mesuré deux fois en campagne réelle le 2026-09-23 : `numero_facture1` transformé par un masque de saisie (cas 99, 101, 126 — 3 essais sur 8), produit inventé absent du catalogue (cas 13). Même cause racine que le correctif many2one déjà fait pour `inspect_schema` : une valeur saisie doit avoir été vue |

**Note (2026-09-23)** : le timeout de clic menu mesuré en campagne réelle (cas 128, projet 12,
3 essais sur 3) — `discover_menus` capture le libellé anglais du menu alors que la session
d'exécution tourne en français — est rattaché aux sous-lots **07c** (contexte navigateur figé,
`locale`/`timezone_id`) et **08a** (détection de version) déjà prévus par le plan. Pas de nouveau
défaut ni de nouveau lot pour ce point.

## 3. Indicateurs de réussite

Mesurés par `scripts/banc_mesure.py` (lot 04) sur l'instance de référence, à chaque lot à partir
du lot 05, et reportés dans `docs/QUALITE-GENERATION-*.md`.

| Indicateur | Définition | Cible |
|---|---|---|
| I1 — Faux PASSED | bugs injectés dont le cas sort `passed` / bugs injectés couverts | **0**, sous réserve du résidu D10 (F1 sans marqueur de tentative) |
| I2 — Faux FAILED | cas `failed` sur l'instance saine / cas exécutés | ≤ 2 % |
| I3 — Exécution au 1er passage | cas sans `technical_error` au premier run / cas générés | ≥ 85 % (départ : 43 %) |
| I4 — Verdict exploitable | cas `passed` ou `failed` au 1er passage / cas générés | ≥ 75 % (départ : 14 %) |
| I5 — Blocage correctement attribué | pannes d'env. injectées rapportées `blocked` / pannes injectées | 100 % |
| I6 — Coût | coût moyen par nouveau cas, réparations comprises | < 1 € (§9) |

Toujours publier l'échantillon (nombre de cas, versions Odoo, date). Ne jamais moyenner des
régimes différents (PRINCIPES).

**Règles de mesure (2026-09-24)** :

- **Une mesure ne modifie jamais les mémoires apprises de production ; toute mémoire apprise
  pendant une campagne est examinée puis importée explicitement.** Le script de campagne tourne sur
  une copie horodatée de `data/` (`TESTPILOT_DATA_DIR`), dont le chemin figure dans sa sortie et
  dans chaque `result.json` (`data_dir`).
- Ne jamais lancer la suite pytest et une campagne en même temps sur le même poste (une campagne
  concurrente a fait échouer la garde « données réelles » de la suite le 2026-09-24).
- **F7 (lot 11)** : le signal de navigation (chemin d'URL + clés de fragment `action`, `menu_id`,
  `model`, `view_type`) est mesuré sur Odoo 17.0+e (staging Sapian) ; sa validation sur **16.0 et
  17.0 Community**, avec un scénario Behave COMPLET de vrai refus au corpus, est à faire sur le
  banc du **lot 04**. Ajouter au corpus un clic sur un onglet de formulaire (notebook), qui ne
  change pas l'URL, pour vérifier qu'il ne déclenche pas de faux `donnee_invalide`, et confirmer
  la table sur 16 / 17.0 Community (sur 17.0+e, enregistrer laisse l'URL identique : l'apparition
  de la clé `id` n'a pas été observée en réel).

## 4. Registre des décisions à valider par le porteur

Claude Code **ne démarre pas** un lot dont une décision requise n'est pas cochée.

| ID | Question | Proposition | Lots | Statut |
|---|---|---|---|---|
| D1 | Nouvelle cause `precondition_non_remplie` et projection vers un statut `blocked` automatique | Ajouter la cause ; `execution_status = blocked` (nouvelle valeur de l'axe exécution) + `functional_status = indetermine` ; lecture `blocked`. Les deux axes restent séparés | 02 | ☑ (validée le 2026-09-24) |
| D2 | Un `AssertionError` levé dans un `Quand` | Cause `broken_test_code` (le test affirme dans une action) → `retest` | 02 | ☑ (validée le 2026-09-24) |
| D3 | Scénario vert sans aucun constat exécuté | `functional_status = indetermine`, cause `aucun_constat` → `retest`. Jamais `conforme` | 03 | ☑ (validée le 2026-09-24) — **option 1 confirmée** : convertir d'abord TOUTE la bibliothèque de steps vers `constater(...)`, puis appliquer D3 aux scénarios exécutés après ce lot ; la hausse attendue et transitoire des « Retest » est un effet voulu, pas une régression à minimiser |
| D4 | Les nouvelles gardes d'écriture (assertion hors `Alors`, `Alors` sans `constater`) bloquent-elles `write_steps_file` ? | **Bloquantes** : l'agent reçoit un refus déterministe et corrige, ce qui coûte moins qu'un run réel raté. Dérogation au régime détectif de 0008 justifiée par le runtime (D3) qui rend la faute mesurable | 03, 09 | ☑ (validée le 2026-09-24) — régime bloquant confirmé, cohérent avec F9 (lot 11) ; taux de refus réel au premier passage à mesurer dès qu'un appel LLM est possible (lot 09 ou prochaine campagne) |
| D5 | Confiance du verdict | Champ `confiance` ∈ {`nominale`, `auto_resolue`, `apres_retry`} sur le résultat ; `passed` non nominal affiché « Réussi — à confirmer » ; option de campagne **stricte** (sans résolution adaptative ni retry) | 05 | ☐ |
| D6 | Code propre à une instance client | Notion de **profil d'instance** : `behave_runtime/steps_library/<connecteur>/profils/<profil>.py`, sélectionné par un réglage du projet ; Sapian devient le premier profil | 06 | ☐ |
| D7 | Oracle backend du connecteur web | Réglage de projet optionnel `oracle` (HTTP JSON authentifié, ou SQL lecture seule) ; présent ⇒ `ground_truth = backend_verified` | 07 | ☐ |
| D8 | Plusieurs comptes par projet (droits, changement d'utilisateur) | Table `project_account` (libellé, identifiant, secret chiffré via `store/secrets.py`, rôle métier) ; steps « en tant que "<libellé>" » | 07b, 08 | ☐ |
| D9 | Versions Odoo supportées et instance de référence | 16.0, 17.0, 18.0 Community + données de démo ; modules `sale_management`, `purchase`, `stock`, `account`, `crm`, `project` (helpdesk est Enterprise : exclu du banc) | 04, 08 | ☑ (validée le 2026-09-24) |
| D10 | F1 : sur un scénario de création SANS marqueur de tentative (champ sans contrainte d'unicité — la majorité des cas), le comptage cloisonné (`id > max_id`) ne peut pas distinguer un unique enregistrement du scénario d'un unique enregistrement créé par un tiers dans la même fenêtre — aucune information disponible ne permet de trancher sans marqueur (le `create_uid` est exclu, cf. formulaires publics). Accepte-t-on ce résidu (I1 non strictement à 0) plutôt que d'imposer un marqueur à TOUT scénario de création (changerait le contrat de génération, hors périmètre du lot 01) ? | **Résidu accepté** : le risque exige la coïncidence de trois conditions (tiers actif sur le même modèle, même fenêtre de quelques secondes, ET échec réel du scénario) — rare hors instance à fort trafic concurrent. Généraliser le marqueur à tout scénario de création reste une amélioration valide, à traiter comme un lot séparé si le résidu se matérialise en pratique | 01 | ☑ (validée le 2026-09-23) |
| D10 bis | Sonde de saisie du lot 12 (taper une chaîne de sonde dans un formulaire pendant l'exploration, sans jamais le soumettre) — écrire sans soumettre n'est pas sans risque (sauvegarde automatique du back-office Odoo y compris via `beforeunload`, brouillons de certaines applications) | **Acceptée avec garde-fous** : page JETABLE du contexte authentifié de l'exploration (pas un contexte neuf : les formulaires portail exigent la session) ; aucun clic ni navigation après saisie ; page fermée avec `run_before_unload=False` (défaut Playwright vérifié) ; **toute requête d'ÉCRITURE est interceptée et abandonnée avant d'atteindre le serveur** (`page.route`, zéro écriture reçue en vrai navigateur) et interrompt la sonde en marquant le formulaire « sauvegarde automatique détectée, pas de sonde ». **Amendée le 2026-09-24 (validée par le porteur, réf. `f9670e3`)** : « écriture » = tout sauf une liste blanche de méthodes RPC de lecture pure, jugée sur le champ `params.method` du corps JSON-RPC de `/web/dataset/call_kw` (`read`, `search_read`, `search`, `search_count`, `name_search`, `name_get`, `fields_get`) ; un corps illisible, un lot JSON-RPC, une méthode absente de la liste ou un corps sans JSON-RPC reconnaissable comptent comme écriture et interrompent la sonde ; `/web/session/destroy` (déconnexion) est une écriture, seuls `/web/session/check` et `/web/session/get_session_info` sont ignorés. Défaut sûr : on perd un format plutôt que de risquer une écriture ; **aucune sonde sur le back-office Odoo** (`/web#…`, `/odoo/…`) — plus strict que la décision du porteur, qui n'excluait que les enregistrements existants : les appels `onchange` d'un formulaire de création ne se distinguent pas d'un enregistrement, donc formats du back-office NON appris, à revoir au lot 08 ; aucune sonde si `ODOO_ENV=prod` ; sonde de longueur neutre (30 chiffres) avec recherche bornée (≤ 30 saisies) d'un exemple valide ET stable, jamais calibrée sur un masque connu | 12 | ☑ (validée le 2026-09-24 ; amendée et validée le 2026-09-24) |
| D11 | Références inexistantes dans un `.feature` (produit halluciné, partenaire inexistant) : refus à l'écriture ou avis ? | **Bloquant dans `write_feature_file` seulement quand la source fait autorité** : `name_search` RPC pour un champ relationnel Odoo, `<select>` dont toutes les options ont été relevées **et dont la sonde a OBSERVÉ que les options ne dépendent d'aucun autre champ** (identiques avant/après un changement des autres selects et après la saisie des champs texte ; sans observation — sonde absente, interrompue, en erreur, back-office — jamais exhaustif : refuser à tort une valeur réelle, pays → ville, coûte du budget sans raison de fond) — précision validée le 2026-09-24 ; **détectif** sinon (listes de produits web, autocomplétions non exhaustives : pagination, valeurs créées par le scénario). Jamais de refus pour une valeur créée plus tôt dans le même scénario ni marquée « rendue unique pour cette tentative ». Message de refus : les 5 valeurs réelles les plus proches (`difflib`) | 12 | ☑ (validée le 2026-09-24) |
| D12 | F10 : réponse du serveur à la soumission d'un formulaire (HTTP 5xx, silence total) | **Le code HTTP est capté** (toute réponse à `/website/form/…`, pas seulement le JSON) ainsi que le message d'erreur visible (`#s_website_form_result.text-danger`). **5xx sur une action censée réussir** → `non_conforme`, cause `erreur_serveur_5xx`, code HTTP et message capturés en preuve. **5xx sur une action censée être refusée** (scénario négatif) → `non_conforme` aussi, avec la note « le serveur a planté au lieu de refuser proprement : ce n'est PAS le refus attendu ». **Silence total** (ni réponse HTTP 4xx/5xx, ni JSON, ni message affiché, ni champ invalide côté navigateur) → `indetermine`, cause `refus_non_explique`, jamais réparé automatiquement (même régime que `blocked`). Un 4xx ou un message affiché reste le constat expliqué d'avant. Le contrat 0011 (`_require_snapshot`) n'est pas rouvert | 02 | ☑ (validée le 2026-09-24) |
| D13 | Lot 07a : lecture de « un champ mot de passe est-il visible ? » à TROIS états (visible / absent / inconnu) | `_mot_de_passe_visible` rend `True`, `False` ou `None` (page illisible : navigation en cours, page fermée) — jamais un `False` par défaut. **Chemin du critère de connexion réussie** : inconnu traité comme visible, donc connexion non aboutie (bloquant, `blocked`). **Chemin sans identifiants** : inconnu lève une précondition dédiée « la page n'a pas pu être lue » (`blocked`), jamais pris pour une application publique. Justification : défaut sûr, cohérent avec la sonde du lot 12 (« je n'ai pas pu observer » n'est pas « il n'y a rien ») ; aucun chemin vers un faux PASSED identifié (revue `verdict-reviewer` du 2026-09-24). Coût assumé : un faux « bloqué » possible sur une page instable, jamais un faux vert | 07a | ☑ (validée le 2026-09-24) |

## 5. Lots

**Ordre d'exécution (révisé le 2026-09-24) : 12 → 02 → 07a → 03 → 04 → 07b-e → 08 → 05 → 06 → 09 → 10**
(les lots 01 et 11 sont terminés). La numérotation des lots ne change pas ; seul l'ordre change.

Raison : l'objectif « tester toute application web » est bloqué par l'absence de connexion à
l'exécution (C1 : `WEB_USER`/`WEB_PASSWORD` ne sont lus par aucun step, les tests tournent en
anonyme). Le sous-lot **07a** est petit et ne dépend que de `PreconditionNonRemplieError` (lot 02),
d'où son passage juste après le lot 02, avant le banc de mesure. Le lot 12 (valeurs observées)
passe en premier : il est prêt, mesuré en campagne réelle, et ne dépend que des lots 01 et 11.

Précision du 2026-09-24 (porteur) : **un collaborateur externe a besoin de tester une application web authentifiée**. C'est ce besoin concret qui place la connexion à l'exécution (07a) juste après les causes et prérequis (02), devant le banc de mesure (04) et l'Odoo ERP (08). Vérifié : aucun lot déjà terminé (01, 11, 12) ne contredit cet ordre — 12 dépend de 01 et 11 ; 02 ne dépend de rien ; 07a de 02 ; 03 de 02 ; 05 de 02 et 04 ; 06 de 01 ; 07b-e de 02, 03 et 07a ; 08 de 04 ; 09 de 07b-e et 08. Le sous-lot 07a couvre le **formulaire de connexion simple** ; SSO, TOTP et session injectée restent au lot 07b et ne doivent pas être annoncés comme couverts.

| Lot | Commande | Objet | Décisions | Dépend de | Taille |
|---|---|---|---|---|---|
| 01 | `/lot-01-comptages` | Comptages cloisonnés au scénario (F1) | D10 | — | S |
| 02 | `/lot-02-causes-preconditions` | Cause selon le type de step, prérequis → `blocked` (F2, F5) | D1, D2 | — | M |
| 03 | `/lot-03-preuve-constat` | Preuve runtime qu'une assertion a été exécutée ; gardes d'écriture (F4) | D3, D4 | 02 | M |
| 04 | `/lot-04-banc-mesure` | Instance Odoo de référence, bugs injectés, pannes injectées, script d'indicateurs, CI nocturne (C8) | D9 | — | L |
| 05 | `/lot-05-confiance` | Confiance du verdict, mode strict (F3) | D5 | 02, 04 | M |
| 06 | `/lot-06-nettoyage-profils` | Teardown générique, profils d'instance, sortie du code Sapian (F6) | D6 | 01 | M |
| 07a | `/lot-07a-connexion-execution` | Connexion à l'exécution du connecteur web générique, échec → `blocked` (C1) | — | 02 | S |
| 07b-e | `/lot-07-web-generique` | Session réutilisée / stratégies d'auth (b), contexte figé (c), vocabulaire universel (d), oracle (e) (C2-C5) | D7, D8 | 02, 03, 07a | L |
| 08 | `/lot-08-odoo-erp` | Détection de version, sélecteurs par version, vocabulaire ERP, effets en chaîne (C6, C7) | D8, D9 | 04 | L |
| 09 | `/lot-09-agents` | Outils de perception, prompts, garde de réparation des assertions (C9) | D4 | 07b-e, 08 | M |
| 10 | `/lot-10-mesure-cloture` | Campagne de mesure complète, mise à jour de la documentation | — | tous | S |
| 11 | `/lot-11-faux-verdicts-soumission` | Faux verdicts trouvés en campagne réelle : refus déclenché hors soumission (F7), assertion sur message deviné (F8), comptage réécrit par l'agent (F9) | — | 01 | S |
| 12 | `/lot-12-valeurs-observees` | Valeurs de champ écrites sans avoir été observées : masque de saisie, référence relationnelle inexistante (C10) | D10 bis, D11 | 01, 11 | M |

Les lots 11 et 12 sont issus de la campagne de validation du lot 01 (2026-09-23,
`docs/mesures/campagne-lot01-2026-09-23.md`), pas du diagnostic initial du 2026-09-23 en §2 —
insérés dans l'ordre car ils corrigent des faux statuts (11) et une source d'erreurs techniques
répétée (12), au même titre que les lots 01-03.

### Suivi

| Lot | Statut | Date | Rapport |
|---|---|---|---|
| 01 | terminé | 2026-09-23 | `docs/RAPPORT-LOT-01-COMPTAGES-2026-09-23.md` |
| 02 | terminé (fusionné le 2026-09-24, revue faite, F10 traité par D12) | 2026-09-24 | `docs/RAPPORT-LOT-02-2026-09-24.md` ; PR n° 7 (https://github.com/romca1012/testpilot/pull/7) |
| 03 | terminé (fusionné le 2026-09-24, revue faite) | 2026-09-24 | `docs/RAPPORT-LOT-03-2026-09-24.md` ; PR n° 9 (https://github.com/romca1012/testpilot/pull/9) ; mesures : `docs/mesures/lot03-constats-2026-09-24.md` |
| 04 | à faire | | |
| 05 | à faire | | |
| 06 | à faire | | |
| 07a | terminé (fusionné le 2026-09-24, revue faite) | 2026-09-24 | `docs/RAPPORT-LOT-07A-2026-09-24.md` ; PR n° 8 (https://github.com/romca1012/testpilot/pull/8) ; mesures : `docs/mesures/lot07a-connexion-execution-2026-09-24.md` |
| 07b-e | à faire | | |
| 08 | à faire | | |
| 09 | à faire | | |
| 10 | à faire | | |
| 11 | terminé | 2026-09-24 | `docs/RAPPORT-LOT-11-2026-09-24.md` |
| 12 | terminé | 2026-09-24 | `docs/RAPPORT-LOT-12-2026-09-24.md` ; PR n° 6 (https://github.com/romca1012/testpilot/pull/6) |

## 6. Ce que chaque lot garantit (résumé)

**01.** Un comptage ne voit que les enregistrements créés après le relevé du scénario (`id >
max_id` relevé, affiné par le marqueur de tentative quand il existe). Les ids trouvés alimentent
`last_record_ids` et le registre de teardown.

**02.** Le type de step (`given`/`when`/`then`, lu dans le JSON Behave, pas dans le libellé)
entre dans la classification. Les prérequis lèvent `PreconditionNonRemplieError`. Une panne de
fixture (`odoo_session`, navigateur, connexion) devient `blocked`. Seul un échec d'assertion dans
un `Alors` devient `non_conforme`.

**03.** Toute assertion de la bibliothèque passe par `constater()` / `constater_visible()`, qui
consignent un constat dans un fichier sidecar. Un scénario vert sans constat n'est jamais
`conforme`. `write_steps_file` refuse les assertions hors `Alors` et les `Alors` sans constat.

**04.** `compose.banc.yml` lance Odoo 16/17/18 + PostgreSQL, base de démo neutralisée. Le module
`tp_bugs_injectes` active des défauts connus par `ir.config_parameter`. Un corpus
`specs/banc/` + un fichier d'attendus permettent de calculer I1 à I6. Workflow nocturne.

**05.** La résolution adaptative et le retry laissent une trace qui abaisse la confiance du
verdict ; la campagne stricte les désactive.

**06.** Le teardown supprime (ou annule puis supprime, ou archive) tout ce que le scénario a créé,
quel que soit le modèle. Le code Sapian sort du socle vers un profil.

**07.** Une application web authentifiée est testable : step de connexion générique partagé avec
l'exploration, session réutilisée, stratégies d'auth déclarées, locale et fuseau figés,
vocabulaire universel, oracle optionnel.

**08.** Un flux ERP Odoo complet (devis → commande → livraison → facture) est exprimable avec la
bibliothèque, vérifié côté UI et côté RPC, sur 16, 17 et 18.

**09.** L'agent voit les boutons, états et sous-champs d'une vue Odoo et l'arbre d'accessibilité
d'une page web ; ses prompts exposent le nouveau vocabulaire et les règles de constat ; une
réparation qui touche un `Alors` est signalée au gate.

**10.** Indicateurs I1-I6 publiés sur les trois versions Odoo et sur la fixture web ; ARCHITECTURE,
CONTINUITE et le rapport de qualité mis à jour.

## 7. Risques

- **Hausse apparente des `retest`/`blocked` après 02-03.** C'est attendu : des verts et des rouges
  faux deviennent honnêtes. À annoncer avant de publier les chiffres.
- **Taille du prompt (09)** : le vocabulaire ERP grossit le catalogue. Mesurer I6 ; si besoin,
  n'injecter que les steps du connecteur et des domaines détectés dans la spec.
- **Suppression en teardown (06)** sur un document validé : Odoo refuse souvent `unlink`. Prévoir
  annulation puis suppression, sinon archivage, et le signaler au rapport sans jamais faire
  échouer le verdict.
- **Dérive de l'instance de référence** : figer les images Docker par digest.

## 8. Mode d'emploi avec Claude Code

1. Copier à la racine du dépôt : `CLAUDE.md`, `.claude/commands/`, `.claude/agents/`, et ce plan
   dans `docs/`. Commiter sur une branche `outillage-claude-code`.
2. Le porteur coche les décisions du §4 (date + initiales). Claude Code refuse un lot dont une
   décision requise n'est pas cochée.
3. Ouvrir Claude Code à la racine du dépôt, puis pour chaque lot, dans l'ordre du §5 :
   - `/lot-01-comptages` (le lot 08 accepte un sous-lot : `/lot-08-odoo-erp a` ; la connexion à l'exécution est `/lot-07a-connexion-execution`, le reste du lot 07 `/lot-07-web-generique b`) ;
   - laisser Claude Code présenter son plan de fichiers avant d'écrire (mode plan conseillé) ;
   - à la fin, il lance le sous-agent `verdict-reviewer` et produit le rapport du lot ;
   - relire le rapport et le diff, puis fusionner. Mettre à jour le tableau de suivi du §5.
4. Une session Claude Code par lot (ou par sous-lot) : le contexte reste centré, et le rapport de
   fin sert de passation au lot suivant.
5. À partir du lot 04, ne fusionner aucun lot qui dégrade I1 ou I5 sur le banc.

## Suggestions à cadrer (hors décision, hors lot en cours)

- **Affichage des cas `indetermine` (suggestion du lot 02, 2026-09-24, NON décidée).** Aujourd'hui un cas `indetermine` s'affiche « Retest » (règle `indetermine → retest`, `verdict/status.py`), ce qui peut laisser croire à un test cassé alors qu'il s'agit d'un refus non expliqué (`refus_non_explique`) ou d'un manque d'observabilité. Piste : afficher le libellé de la cause à côté du badge « Retest » pour ces cas, **sans créer de nouveau statut de lecture**. À cadrer (écrans concernés, tests) si l'on décide un jour de l'entreprendre ; ce n'est une action d'aucun lot en cours.
