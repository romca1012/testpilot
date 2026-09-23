# Fiabilisation de la génération — suivi du 23 septembre 2026

Le plan est approuvé. Les changements sont locaux, sans déploiement ni migration de la
base métier du poste. Le diagnostic avec LLM sur staging est lancé ; aucune réussite
de bout en bout ni qualité « parfaite » n'est revendiquée.

Le porteur a confirmé le **projet 12 « Portail Sapian - Integration »** comme cible.
Les contrôles RPC et UI en lecture seule ont été exécutés sur ce staging. Le contrôle
automatique d'autorisation a ensuite refusé le premier appel LLM réel : accord explicite
sur la transmission des spécifications/métadonnées à Anthropic demandé, puis explicitement
accordé par le porteur (« oui j autorise »). Le diagnostic du cas 128 est lancé avec
réserve budgétaire ; il ne constitue pas la campagne statistique de qualification.

## Changements implémentés

- Migration 47 SQLite et Alembic/PostgreSQL : journal des tentatives physiques et métadonnées
  de génération. Chaque tentative conserve son verdict, sa durée et ses propres artefacts.
- Mode qualification : aucun rejeu automatique, aucune réparation après exécution,
  aucune calibration par soumission pendant la génération.
- Indicateur strict séparé de l'historique dans l'API, l'audit en lecture seule et le tableau
  de qualité. Une ancienne exécution sans trace physique n'est pas comptée comme un succès
  au premier essai. Les traces de chaque tentative sont consultables avec les accès du projet.
- Preuves UI datées, associées à la cible, la route et l'origine du site. Un schéma RPC,
  un champ masqué ou une observation de plus de 24 h ne satisfait pas ce contrôle.
- Conservation des observations lors des copies, corrections et éditions ; conservation du
  document métier lors des réparations. Un plan technique ancien n'est pas certifié pour
  un script modifié.
- Outil de plan technique structuré : compilation des étapes du catalogue partagé,
  contrôle des références métier et des références aux observations, présence d'assertions,
  rejet des étapes inconnues et des injections de nouvelles lignes.
- Validation locale des arguments des outils et enrichissement de l'inspection des formulaires
  avec libellés, visibilité, options et contraintes. Aucun sélecteur de soumission inventé.
- Test Chromium sur DOM local et workflow CI correspondant, sans service externe ni LLM.
- Connexion Odoo partagée entre exploration et exécution : le probe staging a révélé que
  l'ancien chemin d'exploration remplissait des champs de login masqués, puis présentait la
  page de connexion comme une observation valide. Après correction, `/web#action=menu&cids=1`
  est atteint. Une redirection de page métier vers le login est maintenant un échec explicite.
- Réserve budgétaire durable avant appel pour Sonnet 4.6, SDK sans retry, réconciliation après
  usage, coût inconnu conservé en réserve, suppression des secrets connus des prompts. Enveloppe
  interne de 50 USD, inférieure au plafond approuvé de 120 € avec marge. La qualification
  interdit la lecture libre de données métier et la résolution adaptative à l'exécution.
- Calculateur des seuils du plan : 90 essais attendus, manquants comptés, réserve et cas critiques
  vérifiés séparément, faux verts bloquants. Il exige des verdicts de référence indépendants ;
  il ne fabrique pas ces références.

## Validation locale

Environnement utilisé : `.venv-v1/Scripts/python.exe` (Python 3.12.14).
L'ancien `.venv` pointe vers un interpréteur indisponible et ne doit pas servir de preuve.

- 90 tests ciblés : versions, réparations, migration portable, génération et tentatives.
- 85 tests ciblés supplémentaires : artefacts, permissions, connecteur web, contrats de qualité.
- 6 tests du tableau de qualité ; vérification TypeScript réussie.
- 1 test Chromium réel : champ visible accepté, mutation vers un champ masqué détectée.
- Suite frontend complète : 300 tests réussis sur 51 fichiers.
- Suite navigateur ciblée : 8 tests réussis, dont 7 sur fixtures locales et 1 sur la page
  publique de connexion SauceDemo (lecture seule).
- PostgreSQL 16 réel jetable : migration de zéro jusqu'à la révision `c47f22092026`,
  13 tests réussis et 1 ignoré, puis 1 test supplémentaire du journal des tentatives réussi.
  Le conteneur et son volume jetables ont été supprimés après validation.
- Après corrections : 25 tests de réparation, génération multimodale et première tentative
  réussis ; 34 tests des preuves, du budget et des seuils réussis.
- Suite backend complète : **2 019 réussis, 5 échecs, 12 ignorés, 17 exclus**, en 35 min 33 s.
  Les cinq échecs ont été corrigés pendant ce passage : trois simulations de bouton submit
  insuffisamment définies, ajout du contexte métier dans le mauvais bloc multimodal, et passage
  systématique du nouveau paramètre optionnel à un adaptateur de test historique.
  **Rejeu exact des cinq tests sur l'état final : 5 réussis.** Il n'y a pas eu de second passage
  global après ces corrections ; les résultats ciblés ci-dessus complètent cette validation.
  Journaux JUnit locaux : `.local-preview/quality-validation.xml` et
  `.local-preview/quality-regressions.xml`. Les nouveaux tests ajoutés après la collecte globale
  ont été exécutés séparément ; ils ne sont pas inclus dans le total de 2 019.

Les ensembles ciblés se recoupent : leurs nombres ne doivent pas être additionnés comme
un total de tests distincts. Le premier lancement global réalisé pendant les modifications
avait deux écarts de schéma liés au changement de migration en cours ; il ne constitue
pas la validation finale d'un état stable.

## Ce que ces preuves ne démontrent pas

La compilation structurée prouve la forme et les références du plan, pas sa fidélité sémantique.
Une référence d'observation existante ne prouve pas à elle seule que l'assertion est correcte.
Le contrôle de champs concerne les formulations reconnues par le linter et ne constitue pas
une analyse générale du code Python personnalisé. Le délai de 24 h ne détecte pas à lui seul
une modification de l'application intervenue entre observation et exécution.

La base locale contient 7 exécutions historiques : 3 succès techniques finaux, 4 erreurs,
et aucune première tentative physiquement documentée. Le taux strict reste non mesuré.

## Travail restant

1. Validation globale et traitement des régressions effectués selon le bilan ci-dessus.
2. Compléter la qualification reproductible : corpus figé de 30 cas, séparation apprentissage /
   réserve, référence de verdict indépendante, isolation des mémoires et données, plafonnement
   préalable de tous les appels payants, comptage des générations échouées.
3. Valider les préconditions de données, l'absence d'ambiguïtés, le nettoyage et l'isolation
   sur la cible réelle ; compléter les tests de mutation des assertions.
4. Exécuter les 30 essais de référence puis les 90 essais finaux selon le plan, dans l'enveloppe
   totale approuvée de 120 €. Le projet 12 est confirmé ; l'envoi des données à Anthropic
   est explicitement autorisé par le porteur.
5. Publier les mesures et établir la procédure de retour arrière avant tout déploiement
   séparément autorisé. La validation sur PostgreSQL réel est désormais faite. Un downgrade
   de schéma supprimerait le journal des tentatives : conserver un export des nouvelles traces
   et une sauvegarde avant migration ; ne pas présenter ce downgrade comme un retour arrière
   préservant automatiquement l'audit.

## Suite du 23 septembre (vérification indépendante + 3 correctifs ciblés)

Une vérification indépendante du code (pas seulement de ce rapport) a mesuré, sur les 43
versions réellement en base, **0 utilisation de `write_test_plan`** — le modèle a systématiquement
choisi `write_feature_file` libre, malgré l'ajout de `write_test_plan` au Lot 3. Cause trouvée :
la section qui le présentait était en toute fin de prompt, après le critère de terminaison, et
la section « OPTIMISATION DES COÛTS » (lue plus tôt, plus impérative) ne mentionnait que
`write_feature_file` + `write_steps_file` comme l'unique patron d'écriture. Corrigé :
`write_test_plan` est maintenant présenté comme l'outil par défaut aux deux endroits
([`prompts/system_prompt.md`](../../../AXENEO/testpilot/src/testpilot/generation/prompts/system_prompt.md)),
avec la précision qu'un `write_steps_file` minimal (sans step custom) reste requis pour la
terminaison même quand tout vient du catalogue.

Cette bascule a révélé un trou de Lot 4 non détecté par le rapport précédent : un scénario
100 % catalogue (celui que `write_test_plan` produit) n'a AUCUN Python custom pour appeler
`register_created` — le mécanisme de nettoyage déjà en place dans `environment.py::after_scenario`
existait mais n'était atteignable que depuis un step custom généré à la main. Corrigé en un seul
point sûr : `_capturer_dernier_enregistrement` (`_base_helpers.py`), qui ne s'exécute qu'après que
`check_count_increased_by_one` a PROUVÉ qu'un enregistrement de plus existe, appelle désormais
`register_created` — jamais les steps « … existe dans le modèle … » (qui peuvent pointer un
enregistrement préexistant, jamais à supprimer).

Un petit correctif indépendant restait aussi de la session précédente : `_SOUMET`
(`smoke_check.py`) reconnaît maintenant « enregistre/enregistrer/save », même classe de faux
positif que « Confirmer » (C19), cette fois sur le bouton de sauvegarde standard d'Odoo.

Tests ajoutés/étendus : `tests/test_smoke_champs_requis.py`
(`test_enregistrer_est_reconnu_comme_une_vraie_soumission`), `tests/test_comptage_falsifiable.py`
(`test_le_nouvel_enregistrement_est_enregistre_pour_nettoyage`,
`test_un_enregistrement_preexistant_verifie_par_ailleurs_n_est_jamais_enregistre`). Vérifié sans
régression sur les suites touchées (95 tests ciblés) ; sweep complet non relancé à ce stade.

Reste à faire pour le Lot 4 à cette date : isolation de session entre scénarios — VÉRIFIÉE déjà en
place (`environment.py::before_scenario` ouvre un `BrowserContext` Playwright neuf et une session
RPC Odoo neuve à CHAQUE scénario, aucun changement nécessaire). Données uniques par tentative :
traité séparément ci-dessous, le même jour.

## Lot 4 (suite) — valeur unique par tentative physique (23 septembre)

Motivé par le diagnostic réel interrompu sur le cas 128 (« Sondage », Sapian) : un des trois
défauts relevés était un **nom de donnée FIXE** dans le Gherkin généré — un risque de collision
avec ce qu'une tentative précédente a créé si son nettoyage (voir plus haut) a échoué entre-temps.

Nouveau step partagé, connecteur-agnostique
(`generic/_generic_steps.py::step_fill_unique`) : « je renseigne le champ "…" avec la valeur "…"
rendue unique pour cette tentative » — suffixe la valeur par un jeton unique à CETTE tentative
physique, jamais par défaut (le step nominal reste inchangé). Chaîne de bout en bout :

1. `BehaveRunner._subprocess_env` génère un jeton frais (`{execution_id}-{6 car. aléatoires}`)
   à CHAQUE appel — donc à chaque tentative physique, y compris un rejeu après timeout.
2. `environment.py::before_all` l'expose sur `context.tentative_token` (`"tentative-locale"`
   hors run piloté — jamais vide, pour qu'un appel direct du step ne lève pas).
3. Le prompt système documente le step explicitely (leçon tirée de `write_test_plan`, dont
   l'adoption était restée à 0 % faute de mise en avant suffisante) : section dédiée
   « Valeur unique par tentative », plus le libellé lui-même déjà visible dans le catalogue
   injecté au modèle.

15 tests ajoutés (`test_valeur_unique_par_tentative.py`, extensions de `test_behave_harness.py`
et `test_runtime_connection.py`), plus une vérification manuelle que `write_test_plan` accepte
bien un plan utilisant ce nouveau step sans ambiguïté avec le step nominal. Aucune régression sur
118 tests ciblés.

## Lot 2 — mémoire de libellés de menu APPRIS (23 septembre)

Ferme la boucle laissée ouverte par « Chantier F » (résolution adaptative construite plus tôt
cette session) : le repli adaptatif de `navigate_menu` retrouvait déjà le VRAI libellé d'un menu
affiché dans une langue différente de celle capturée par `discover_menus` (mesuré : « Surveys »
capturé, « Sondages » affiché en run réel, Sapian 2026-09-22, cas C127) — mais rien ne renvoyait
cette découverte vers la génération, qui reproposait indéfiniment le même libellé faux à chaque
régénération.

Nouveau module [`generation/menu_appris.py`](../../../AXENEO/testpilot/src/testpilot/generation/menu_appris.py),
même patron que `selector_memory`/`regles_apprises` déjà en place (un fichier JSONL par projet,
`enregistrer()` best-effort, cache `(chemin, mtime, taille)`). Chaîne de bout en bout :

1. `_adaptive_resolution.py` expose désormais le libellé RÉEL de l'élément élu
   (`page._tp_dernier_libelle_choisi`), en plus de `_tp_dernier_choix_menu_parent` déjà posé.
2. `navigate_menu` (`_base_helpers.py`) consigne ce libellé dans un nouveau sidecar
   (`TP_MENU_APPRIS_FILE`) à chaque clic adaptatif réussi — y compris un clic intermédiaire sur un
   menu parent, écrasé par le clic final plus précis sur le même segment (dernier écrit gagne).
3. `BehaveRunner` lit le sidecar après le run (`result.menus_appris`) et persiste dans la mémoire
   du projet via une nouvelle méthode `_apprendre_menus`, même trois bornes que `_apprendre`/
   `_detecter_derive` (jamais en dry-run, un seul point d'entrée, best-effort).
4. `_section_modeles_backoffice` (`prompt.py`) lit cette mémoire par `project_id` (déjà présent
   dans le modèle de domaine) et ajoute une note « confirmé « X » en exécution réelle » à côté du
   chemin mesuré, sans jamais le remplacer en silence — l'instruction « ne traduis pas les
   libellés » est explicitement assouplie pour ce cas précis.

19 tests ajoutés/étendus (`test_menu_appris.py`, `test_transport_menus_appris.py` — garde de bout
en bout avec un vrai `BehaveRunner`, comme `test_transport_derive_selecteurs.py` —, et des ajouts
à `test_resolution_adaptative.py`/`test_prompt_domaine_mesure.py`). 130 tests ciblés passent sans
régression sur l'ensemble des fichiers touchés (`behave_result.py`, `behave_runner.py`,
`_base_helpers.py`, `_adaptive_resolution.py`, `prompt.py`).

## Diagnostic réel repris sur le cas 128 (23 septembre, après Lots 2/3/4 du jour)

`scripts/qualify_generation_probe.py --case 128 --trial diagnostic-c128-lot234-20260923` —
génération réelle (Sonnet 4.6, staging Sapian confirmé, projet 12), **sans exécution métier**
(portée du script : diagnostic de la génération seule, jamais un run réel). Coût : 0,1148 USD ;
enveloppe cumulée 0,2513 USD / 50 USD.

Comparé à la version interrompue du 22 septembre (avant les correctifs du jour) :

- **Valeur unique par tentative — ADOPTÉE SPONTANÉMENT.** Sans qu'on le lui redemande, le modèle
  a utilisé le nouveau step `… avec la valeur "Sondage BDD Test" rendue unique pour cette
  tentative` pour le champ `title` — exactement le défaut « nom de donnée fixe » relevé par le
  diagnostic précédent. Effet de bord observé : l'assertion finale est passée de « un
  enregistrement avec le champ title égal à X existe » (valeur exacte, maintenant inconnue
  d'avance à cause du suffixe) à « le champ title de cet enregistrement n'est pas vide » — une
  assertion plus faible. Compromis réel, pas un bug : à surveiller si ça se généralise.
- **Chemin de menu et libellés de bouton** : `Surveys/Surveys` → `Surveys` (un seul segment,
  plus proche de la structure réelle) ; `Save manually`/`New` (anglais) → `Nouveau`/`Enregistrer
  manuellement` (français, cohérent avec `language: 'fr-FR'` observé sur `/odoo/surveys`).
  Aucune mémoire apprise n'a pu jouer ici (aucune résolution adaptative n'a encore été
  enregistrée pour le projet 12 depuis la construction du Lot 2 aujourd'hui) — cette
  amélioration vient du modèle lui-même, pas encore de `menu_appris`.
- **Toujours PAS de preuve UI pour le champ `title`** : l'unique observation UI enregistrée
  (`observation-2`, `/odoo/surveys`) est la page de LISTE des sondages, avec `fields: []` — le
  modèle n'a jamais appelé `inspect_page_form` sur le formulaire de création réel (visible
  seulement après le clic sur « Nouveau »). L'evidence du step de remplissage reste `observation-1`,
  qui est le schéma RPC, pas une observation de page. C'est exactement le défaut que la note
  « Un schéma RPC ne prouve ni le libellé d'un bouton ni la présence d'un champ dans la vue »
  (déjà dans le prompt) essaie de prévenir — elle n'y suffit pas seule ici.

Conclusion honnête : deux défauts sur trois du diagnostic du 22 septembre sont désormais
adressés par l'infrastructure (unicité, francisation spontanée du chemin) ; le troisième
(absence de preuve UI post-navigation) persiste et n'a reçu aucun correctif ce jour — resterait
à traiter avant de considérer ce cas prêt pour la campagne du Lot 5. Ce diagnostic ne prouve
RIEN sur l'exécution réelle : `dry_run_passed=true` seulement (parsing/résolution des steps),
aucune écriture n'a eu lieu sur Sapian.

## Défaut de preuve UI traité (23 septembre)

Root cause trouvée en conditions réelles (script de sonde jetable, lecture seule, staging
Sapian) : `inspect_page_form` ne fait qu'un `page.goto(url)` — il ne peut pas rejouer une
navigation menu + clic « Nouveau ». Le formulaire de CRÉATION d'un modèle back-office n'apparaît
que derrière ce clic, donc l'agent ne l'a jamais observé et cite le schéma RPC comme seule
« preuve » d'un champ.

Vérifié en conditions réelles (même sonde, staging Sapian, modèle `survey.survey`, action 907) :
`{base_url}/web#action=<id action>&model=<modèle>&view_type=form&cids=1`, atteint par un simple
`goto` À FROID (sans navigation préalable), rend EXACTEMENT le même formulaire qu'un clic sur
« Nouveau » — mêmes champs observés dans les deux cas. Aucune supposition : la sonde a comparé
les deux chemins côte à côte avant tout changement de code.

Deux changements :
- [`connectors/odoo.py::discover_menus`](../../../AXENEO/testpilot/src/testpilot/connectors/odoo.py) conserve
  désormais `action_id` (déjà lu depuis `actionID`, jamais deviné) dans chaque entrée de
  `modeles_backoffice` — jusqu'ici extrait puis jeté.
- [`generation/prompt.py::_section_modeles_backoffice`](../../../AXENEO/testpilot/src/testpilot/generation/prompt.py)
  donne le patron d'URL une fois (coût : quelques dizaines de caractères, pas un par ligne — la
  base_url ne change pas d'une entrée à l'autre) et affiche `(id action <n>)` à côté de chaque
  modèle qui en a un, pour qu'`inspect_page_form` puisse le viser SANS naviguer.

18 tests ajoutés/étendus (`test_odoo_connector.py`, `test_prompt_domaine_mesure.py`). Limite
connue, non traitée : les noms de champs DOM du formulaire Odoo créé dynamiquement portent un
suffixe d'instance de widget (`title_0`, pas `title`) — `extract_form` les cite donc tels quels,
pas le nom de champ métier ; un rapprochement par LABEL resterait à faire si ça se révèle un
problème en pratique. Cette limite est indépendante du correctif : elle existait déjà, ce
correctif rend seulement le formulaire enfin ATTEIGNABLE pour la première fois.

**Premier re-diagnostic : pas encore observable**, cause identifiée (pas un défaut du correctif) :
`data/domain/projet-12.json` datait du 18 septembre, avant ce correctif — ses entrées
`modeles_backoffice` n'avaient donc aucun `action_id`. Un crawl ne s'applique jamais
rétroactivement à un modèle de domaine déjà enregistré.

**Crawl réel relancé sur le projet 12** (37 routes, 509 transitions, 194 modèles back-office,
tous désormais avec `action_id`) — au passage, `discover_menus` capture maintenant directement
« Sondages » (français, la vraie langue de la session de crawl), là où le fichier du 18 septembre
portait encore « Surveys » : la cause du trou de langue de C127 n'est peut-être plus systématique,
juste un accident de session de crawl ce jour-là. À confirmer sur d'autres modèles avant d'en
tirer une règle générale.

**Second re-diagnostic (`diagnostic-c128-post-recrawl-20260923`, 0,15 USD) : le correctif
FONCTIONNE, mais révèle un second défaut, immédiatement corrigé.** Le modèle a bien appelé
`inspect_page_form` sur l'URL construite (`.../web#action=907&model=survey.survey&view_type=
form...`) — première preuve que l'instruction est suivie. Mais l'observation revenait avec
**0 champ**. Vérifié en conditions réelles (sonde dédiée) : `extract_form` juste après
`domcontentloaded` voit un DOM encore vide sur une route `/web#...` — les widgets `.o_field_
widget` d'Odoo (OWL) se montent après coup, via des appels RPC asynchrones ; `domcontentloaded`
ne dit que « la coquille SPA est chargée ». `networkidle` a été écarté (le bus de longpolling
d'Odoo ne devient jamais idle). Corrigé dans
[`connectors/odoo.py::_inspect_sync`](../../../AXENEO/testpilot/src/testpilot/connectors/odoo.py) :
un `wait_for_selector('.o_field_widget', timeout=5s)` best-effort, SCOPÉ aux URLs `/web#`
(comportement strictement inchangé pour toute page portail).

**Troisième re-diagnostic (`diagnostic-c128-render-wait-20260923`, 0,21 USD) : confirmé de bout
en bout.** `observation-2` porte désormais les 3 vrais champs du formulaire
(`radio_field_0`, `title_0`, `user_id_0`) — la même liste que celle mesurée manuellement. Le
défaut de preuve UI original (schéma RPC cité comme seule « preuve » d'un champ jamais vu à
l'écran) est refermé pour ce cas. Variabilité observée et non corrigée aujourd'hui : ce run a
utilisé `write_feature_file` libre (`technical_plan: {}`), pas `write_test_plan` — l'adoption
reste probabiliste malgré le renforcement du prompt du Lot 3 ; à surveiller sur d'autres cas,
pas encore un problème à corriger seul.

3 tests ajoutés dans `test_odoo_connector.py` pour le câblage de l'attente (`/web#` scope, jamais
de blocage si le widget n'apparaît jamais, comportement portail inchangé). 109 tests ciblés
passent sans régression sur l'ensemble touché aujourd'hui.

## Lot 5 — pilote réduit (2 cas, projet 12) et trois défauts réels trouvés et corrigés

Périmètre réduit approuvé le 23 septembre : le corpus complet du plan (30 cas, 20 Odoo + 10 web)
n'existe pas encore (0 cas web-générique, projet 1 injoignable en local). Script
[`scripts/qualify_campaign_pilot.py`](../../../AXENEO/testpilot/scripts/qualify_campaign_pilot.py) :
2 cas (127, 128), 3 générations indépendantes chacun, exécution physique unique
(`TESTPILOT_QUALIFICATION=1`, `max_retries=0`), isolation des mémoires apprises entre essais
(snapshot/restauration de `menu_appris`/`selector_memory`/`regles_apprises`), verdict calculé par
`derive_verdict` (même logique qu'en production), vérification RPC indépendante best-effort.

Le premier essai de validation a immédiatement échoué techniquement, révélant en cascade **trois
défauts réels distincts**, tous vérifiés en conditions réelles avant correction (jamais devinés) :

1. **Nom de champ volatil.** Le web client Odoo (OWL) pose le nom technique STABLE d'un champ sur
   le `<div class="o_field_widget" name="...">` qui ENGLOBE le contrôle, jamais sur l'`<input>`/
   `<textarea>` interne — qui, lui, n'a souvent aucun `name` et un `id` (`name_0`, `partner_id_0`)
   dépendant du nombre de widgets déjà montés dans LA SESSION du navigateur. Un nom observé à la
   génération (session isolée, compteur bas) ne correspond à RIEN à l'exécution (session réelle,
   compteur avancé). Corrigé en deux temps, vérifiés séparément sur le vrai formulaire Sapian :
   - [`connectors/odoo.py::_extract_odoo_form_fields`](../../../AXENEO/testpilot/src/testpilot/connectors/odoo.py)
     lit `.o_field_widget[name]` (stable) au lieu de `input/select/textarea` + repli sur `id`
     (volatil), pour toute URL `/web#` — révèle au passage des champs qu'`extract_form` ratait
     entièrement (widgets sans `<input>` natif : `priority`, `tag_ids`…).
   - [`_base_helpers.py::locate_field`](../../../AXENEO/testpilot/behave_runtime/steps_library/_base_helpers.py)
     descend désormais vers le premier contrôle éditable réel quand un sélecteur technique résout
     un conteneur non éditable, avant de rendre la main — jamais l'inverse.
2. **Absence de guidance many2one.** Un champ relationnel (`partner_id`) rempli via
   `fill_field` (« je renseigne … avec la valeur … ») pose la valeur dans le DOM sans jamais
   sélectionner un enregistrement réel — Odoo refuse alors l'enregistrement SANS message lisible
   (verdict honnête : `non_conforme`, cause non tranchée automatiquement). Le step correct
   (`select_many2one_odoo`, déjà écrit et vérifié une session précédente) existait, mais rien ne
   disait à l'agent de l'utiliser. Corrigé : `inspect_schema`
   ([`generation/tools/inspect.py`](../../../AXENEO/testpilot/src/testpilot/generation/tools/inspect.py))
   annonce désormais, ligne par ligne, quel step utiliser pour un champ `many2one`. Reproduit
   avec succès en re-générant le cas 127 : le Gherkin utilise maintenant « je sélectionne … dans
   le champ "partner_id" ».
3. **`force_name_field` héritait du même trou.** Cette fonction pré-existante (contourne
   l'auto-génération Odoo du titre) résolvait `[name="name"]` en assumant que c'était directement
   le contrôle — même erreur que (1), plus un prototype de setter figé sur `HTMLInputElement`
   alors que le champ réel est une `<textarea>` sur ce formulaire. Corrigée pour descendre dans
   le conteneur et choisir le bon prototype selon le tag réel ; vérifiée directement sur le vrai
   formulaire Sapian (valeur posée sur le vrai contrôle, confirmé par lecture DOM).

25 tests ajoutés/étendus (`test_odoo_connector.py`, `test_select_field_value_sans_name.py`,
`test_case_a_cocher.py`, `test_generation_verified_fields.py`, `test_force_name_field.py` —
nouveau). 194 tests ciblés passent sans régression.

**Résultat mesuré après les trois correctifs** (cas 127, re-généré) : `execution_status: success`
pour la première fois de toute cette investigation — plus aucune erreur technique de résolution
de champ. La chaîne complète (génération → exécution → verdict correct) sur ce cas précis reste
à confirmer par un nouvel essai, non relancé à ce stade pour ne pas consommer davantage le budget
avant validation du prochain tour de campagne.

## Trois défauts de la campagne pilote corrigés (23 septembre)

1. **Vérification indépendante du pilote, deux bugs dans mon propre script** (pas dans
   TestPilot) : `time.mktime` interprétait `write_date` (déjà en UTC côté Odoo) comme une heure
   LOCALE — décalage silencieux qui masquait même l'essai réellement réussi (`nouveaux: 0` malgré
   un succès confirmé par le Gherkin) ; `search(model, [], limit=0)` ramenait la totalité du
   modèle (37 955 tickets mesurés) avant lecture côté client — cause du `TimeoutError`
   systématique sur `helpdesk.ticket`. Corrigé : seuil construit explicitement en UTC, filtre
   `write_date >=` appliqué CÔTÉ SERVEUR avec une limite de sécurité. 4 tests ajoutés.
2. **`remplir_formulaire_valide` utilisé à tort sur un cas back-office** — ce step est
   structurellement incompatible avec `/web`/`/odoo` (hors du périmètre du crawl dont il dépend),
   et rien ne le disait à l'agent. Corrigé : la note affichée dans le catalogue de prompt le dit
   désormais explicitement (« NOMINAL, PORTAIL UNIQUEMENT — jamais un back-office, échec
   certain »).
3. **Grille d'applications Odoo (`.o_app`) pas prête à `domcontentloaded`** — même trou que celui
   déjà corrigé sur les formulaires, cette fois sur la page d'accueil du back-office
   (`/web#action=menu`) : 0 tuile immédiatement après le chargement, 25 après ~2 s de rendu
   client. Cause du timeout intermittent sur le clic « Sondages » (2 essais sur 3 en campagne
   réelle). Corrigé par la même attente `wait_for_selector` best-effort déjà employée pour les
   formulaires. 1 test de garde ajouté ; vérifié en conditions réelles (Sapian).

9 tests ajoutés/étendus au total pour ces trois correctifs.

## Sources complémentaires vérifiées le 23 septembre

- [Tarifs Anthropic](https://platform.claude.com/docs/en/about-claude/pricing) et
  [limites Sonnet 4.6](https://platform.claude.com/docs/en/models/sonnet-4-6/overview) : la réserve
  de 6,12 USD borne 1 M tokens d'entrée au tarif cache 1 h et 8 000 tokens de sortie.
- [Taux BCE USD/EUR](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-usd.sk.html) : référence consultée
  de 1,149 USD pour 1 EUR au 21 septembre, sans assimiler ce taux à la facture du fournisseur.
