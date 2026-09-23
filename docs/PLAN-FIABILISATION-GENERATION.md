# Plan de fiabilisation de la génération TestPilot

Statut : APPROUVÉ par le porteur — mise en œuvre en cours, qualification réelle non acquise.
Date : 22 septembre 2026. Sources officielles consultées à cette date.

Suivi au 23 septembre : [état de mise en œuvre](FIABILISATION-GENERATION-SUIVI.md).

## Objectif et diagnostic

Obtenir, pour une spécification métier validée et une cible disponible, un test fidèle
qui produit un verdict correct à sa première exécution réelle, sans réparation ni rejeu.
Un défaut applicatif correctement détecté compte comme une réussite du test.

Le rapport initial porte sur seulement 7 exécutions locales : 3 succès techniques,
4 erreurs techniques, et 1 verdict métier exploitable. Les 195 tests ciblés passent,
mais la suite complète et une nouvelle campagne avec le vrai LLM restent à valider.
Ces chiffres historiques ne constituent pas une mesure après correction.

Deux précisions issues de la relecture du code pour ce plan :

1. `Executor` permet par défaut un rejeu sur timeout et `run_service` utilise ce défaut.
   Une ligne `first_run` ne garantit donc pas une seule tentative physique. Le résultat
   final peut remplacer le premier résultat ; les artefacts doivent aussi être séparés.
   On ne peut pas reconstituer rétroactivement un taux strict sans preuves conservées.
2. `check_champs_existants` réunit les champs de plusieurs pages et les observations RPC.
   Un champ connu quelque part n'est pas nécessairement présent dans la vue du scénario.

Les corrections précédentes constituent le point de départ : chemins de menus, avis
sur les menus non observés, validation des scénarios et diagnostics Behave.

## Contrat de mesure

Deux périmètres seront publiés, sans changer rétroactivement l'indicateur historique :

| Indicateur | Définition proposée |
|---|---|
| Réussite de bout en bout au premier passage | Demandes éligibles donnant un artefact fidèle puis un verdict correct à la tentative physique 1 / toutes les demandes éligibles du corpus, y compris générations échouées et abandonnées |
| Réussite technique à la tentative 1 | Premières tentatives sans erreur technique / premières tentatives réellement démarrées |
| Verdict correct | Résultat conforme à une référence indépendante ; comprend une non-conformité applicative correctement détectée |
| Stabilité de génération | Part des cas réussissant les 3 générations indépendantes, chacune suivie d'une seule exécution |
| Fidélité métier | Exigences et résultats attendus validés réellement couverts ; assertions ni supprimées ni affaiblies |
| Récupération | Succès après nouvelle tentative, réparation ou résolution adaptative, présenté séparément |
| Coût et durée | Coût par demande et par verdict correct, échecs inclus ; médiane et p95 des durées |

Une donnée invalide volontairement testée et correctement refusée peut produire un verdict
correct. Une donnée nominale refusée par erreur de génération est un échec de qualité.
Une panne de cible doit être étayée et comptée séparément : aucune exclusion discrétionnaire
après observation d'un mauvais score. Publier les taux bruts, les exclusions et leurs preuves.

La boucle interne de génération peut employer plusieurs outils et contrôles statiques.
Cela ne constitue pas plusieurs exécutions métier. Toute calibration qui soumet réellement
un formulaire est toutefois tracée et exclue de la mesure stricte « sans essai métier préalable ».
Les attentes automatiques d'un locator ne sont pas des rejeux complets du scénario.

## Lot 1 — P0 : socle reproductible et mesure exacte

Travaux :
- Recréer ou réparer un environnement Python dédié à partir des dépendances du projet,
  sans mélange implicite entre interpréteurs ; relever les versions réellement utilisées.
- Exécuter entièrement la suite backend et distinguer les tests nécessitant un navigateur
  ou PostgreSQL. Diagnostiquer les régressions préexistantes avant toute attribution au lot.
- Introduire une trace persistée par tentative : identifiant, version, numéro, cause de
  relance, modèle/prompt, cartographie, durée, coût et emplacement d'artefacts distinct.
- Ajouter un mode d'évaluation sans rejeu automatique ni réparation. Conserver les
  mécanismes de récupération disponibles dans le parcours normal, avec mesure séparée.
- Étendre le script d'audit et l'agrégat de qualité ; migrations compatibles SQLite/PostgreSQL.

Zones : `execution/executor.py`, `execution/behave_runner.py`, `api/services/run_service.py`,
`store/`, `scripts/audit_generation_quality.py`, configuration et CI.

Acceptation : un scénario échouant puis réussissant reste un échec au premier passage ;
les deux résultats et traces sont conservés ; les générations échouées ne disparaissent
pas du dénominateur ; les anciennes lignes restent identifiées comme mesure historique.

## Lot 2 — P1 : preuves contextualisées de l'application

Travaux :
- Réexplorer avec le compte, la langue et la surface réellement utilisés pour l'exécution.
- Enrichir les observations : projet, cible, rôle/compte sans secret, langue, date, page/vue,
  état de navigation, type de champ, options, contraintes, boutons et mécanisme de sauvegarde.
- Séparer explicitement schéma RPC, champ UI observé et hypothèse non vérifiée.
- Étendre `verified_fields` de manière compatible vers des preuves contextualisées ;
  limiter le contrôle aux éléments observés sur la vue pertinente et dans le bon état.
- Vérifier une postcondition après navigation : vue ou élément attendu effectivement atteint.
- Invalider les preuves après changement pertinent de cible, compte, langue ou version ;
  dater les observations et signaler leur vieillissement, sans les déclarer éternellement vraies.

Zones : connecteurs, `generation/tools/inspect.py`, `domain_model.py`, `state.py`,
`smoke_check.py`, persistance des versions et exploration.

Acceptation : les fixtures reproduisent Surveys/Sondages, menu parent sans destination,
champ présent uniquement sur une autre page, formulaire dynamique et droits insuffisants.
Une absence de preuve reste un avis explicite ; elle n'est jamais une preuve d'inexistence.
Les avertissements incertains ne deviennent pas des interdictions générales d'explorer.

## Lot 3 — P1 : génération contrainte et fidélité métier

Travaux :
- Introduire progressivement un plan technique validable : préconditions, actions,
  références de preuve, jeux de données, résultat attendu et nettoyage.
- Pour les actions déjà couvertes, traduire ce plan vers les steps partagés de façon
  déterministe ; garder une extension Python possible pour les cas hors catalogue.
- Valider les arguments des outils côté serveur. Étudier le mode strict du fournisseur
  pour les outils compatibles ; conserver le contrôle local et tracer tout repli.
  Les sorties structurées existent déjà dans l'adaptateur : les étendre, pas les dupliquer.
- Relier les assertions aux exigences du document métier validé ; détecter disparition
  d'étapes, valeurs incohérentes, assertions tautologiques et changement du résultat attendu.
- Appliquer parsing, imports, résolution des steps et contrôles métier avant publication
  de la version. Un contrôle à blanc réussi ne reçoit pas l'étiquette « exécuté ».
- Encadrer toute correction interne par les plafonds existants et conserver le motif de
  rejet. Une correction ne peut pas changer silencieusement le métier validé.

Zones : `generation/agent.py`, `react_loop.py`, `tools/`, prompts, `assertion_lint.py`,
`llm/adapter.py`, `generation_service.py` et gate de relecture.

Acceptation : un test syntaxiquement valide mais sans vérification utile est signalé ;
un refus intentionnel reste testé ; une sortie tronquée ou un argument invalide ne devient
pas une version prête ; compatibilité vérifiée avec les anciens cas et leurs steps personnalisés.

## Lot 4 — P1 : données, navigation et assertions robustes

Travaux :
- Préférer des locators sémantiques ou des identifiants stables observés, limités à la bonne
  zone de page. Détecter l'ambiguïté au lieu de choisir arbitrairement le premier élément.
- Remplacer les attentes fixes sur les parcours concernés par des conditions observables
  et des assertions réessayées automatiquement ; borner les délais.
- Auditer les clics forcés et accès directs existants sans interdire ceux qui sont justifiés.
- Préparer des données uniques par tentative, vérifier les relations/options nécessaires,
  puis nettoyer uniquement les identifiants créés par cette tentative.
- Remplacer les comparaisons fragiles de compteurs globaux par des vérifications portant
  sur l'objet du test lorsque le contrat métier le permet.
- Isoler les sessions et données entre scénarios. Tout nettoyage échoué reste visible.
- Conserver le repli adaptatif mais vérifier sa destination et journaliser son usage ;
  il ne peut ni affaiblir une assertion ni transformer un défaut applicatif en succès.

Zones : `behave_runtime/environment.py`, bibliothèque de steps, résolveur adaptatif,
`generation/valeur_conforme.py` et règles apprises.

Acceptation : scénarios indépendants de leur ordre, nettoyage prouvé, erreurs nominales de
jeu de données détectées, refus intentionnels correctement évalués, échec explicite si le
repli atteint la mauvaise vue. Vérification en vrai navigateur sur les fixtures locales.

## Lot 5 — P2 : campagne réelle et évaluation indépendante

Corpus proposé : 30 cas, dont 20 Odoo (portail et back-office) et 10 web génériques.
Réutiliser les fixtures de conformité existantes, dont `tests/fixtures/torture_app/`.
Les applications publiques sont un complément ; elles ne constituent pas seules le banc.

Répartition principale : 10 nominaux, 8 refus/validations, 6 navigation/langue/droits,
4 formulaires dynamiques, 2 isolation/nettoyage. Chaque cas porte sa référence métier,
son état initial et une méthode indépendante de vérification du résultat.

Protocole :
1. Figer le corpus et les critères avant réglage ; réserver 10 cas à la qualification finale,
   sans les utiliser pour ajuster les prompts. Les attentes ne sont pas fournies au générateur
   au-delà de la spécification métier nécessaire.
2. Mesurer une référence sur 30 générations/exécutions de la version de départ instrumentée.
   Les résultats détaillés des cas réservés ne servent pas à guider les corrections.
3. Développer avec les 20 cas de travail et les replays/fixtures locaux.
4. Qualifier avec le fournisseur LLM réel : 3 générations indépendantes par cas, soit
   90 essais ; une seule exécution physique par génération, sans réparation préalable.
5. Réinitialiser les données entre essais, fixer modèle/configuration/cible et isoler les
   mémoires apprises pour éviter qu'un essai bénéficie discrètement des erreurs du précédent.
6. Exécuter aussi les tests générés contre des défauts connus introduits uniquement dans
   des fixtures contrôlées : ils doivent échouer pour la bonne raison.
7. Publier comparaison avant/après, détail par famille, échecs, traces, coûts, exclusions et
   incertitude statistique. Les 90 essais ne sont pas 90 applications indépendantes.

Seuils proposés pour autoriser un pilote :
- ≥ 95 % de réussite de bout en bout : au moins 86 essais sur 90.
- ≥ 90 % des cas réussissent leurs 3 générations : au moins 27 cas sur 30.
- 100 % des cas critiques définis avant la campagne réussissent leurs 3 essais.
- Aucun défaut connu du jeu de mutations n'est déclaré conforme à tort.
- Aucune assertion métier affaiblie ; aucun coût d'échec omis ; aucune donnée créée sans suivi.
- Résultats des 10 cas réservés publiés séparément, avec au moins 29 essais réussis sur 30.

Ces seuils sont des propositions pour TestPilot, pas des valeurs prescrites par les sources.
La cible reste 100 % ; un pilote à 95 % n'est pas une certification universelle de fiabilité.
Un seuil non atteint empêche la qualification et déclenche un diagnostic, pas un changement
du barème après coup. Toute réutilisation des cas réservés pour corriger impose de renouveler
le jeu réservé avant une nouvelle qualification.

## Lot 6 — P2 : protection contre les régressions

- Tests déterministes à chaque PR ; suite backend complète et tests de migration si concernés.
- Vrais navigateurs sur les fixtures locales en CI ; conserver le job de conformité existant.
- Évaluation LLM déclenchée explicitement lors des changements de modèle, prompt, connecteur
  ou étapes partagées ; pas de consommation payante périodique créée par ce plan.
- Versionner prompt, schéma d'outils, modèle et corpus ; conserver un rapport de qualification.
- Livrer les nouveaux comportements progressivement derrière une option de configuration,
  avec migration additive et possibilité de revenir au comportement précédent.
- Présenter le vrai premier passage, la récupération, les prérequis non vérifiés et le coût
  séparément. Vérifier les tests et le build frontend si l'écran Qualité change.

Acceptation : une régression injectée est détectée avant publication ; une version non
qualifiée n'est pas présentée comme fiable ; le retour arrière préserve versions et artefacts.

## Périmètre approuvé

Ordre : lots 1 → 2 → 3 → 4 → 5 → 6. Chaque lot apporte ses régressions et une preuve de
validation ; pas de refonte générale ni de remplacement de stack/modèle par défaut.

L'approbation autorise les modifications du dépôt, les migrations testées sur des
bases de test, et les campagnes sur une cible de staging dédiée avec données de test nettoyées.
Elle n'inclut pas un déploiement en production ni l'activation d'une calibration en écriture
sur tous les projets. La cible et le compte staging devront être identifiés sans ambiguïté
avant les actions distantes ; cette précision n'empêche pas les lots locaux.

Enveloppe approuvée : au maximum 120 € de consommation LLM cumulée pour cette qualification,
avec plafond par cas existant conservé et coût des échecs inclus. Ce montant est un plafond
autorisé, pas une estimation de facture. La campagne prévoit 30 essais de référence et
90 essais finaux ; toute consommation intermédiaire entre dans la même enveloppe.
Si le budget ou l'accès cible manque, arrêter la partie dépendante et publier l'état exact ;
ne jamais réduire silencieusement le corpus ou déclarer les seuils atteints.

La rédaction initiale de ce plan n'avait déclenché aucun appel LLM payant ni changement de code.
L'approbation reçue autorise désormais la mise en œuvre ; elle ne certifie pas ses résultats.

## Fondements documentaires

- Anthropic recommande d'évaluer l'agent et ses outils ensemble, avec plusieurs essais,
  des résultats observables et des critères vérifiables. Sa distinction entre succès au
  moins une fois et succès à chaque essai motive ici la mesure sur trois générations,
  la lecture des traces et le corpus de régression. [Évaluation des agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).
- Les sorties structurées et outils stricts contraignent la forme des échanges. Nous
  maintiendrons une validation sémantique séparée : respecter un schéma ne prouve pas
  qu'un menu existe. [Sorties structurées Claude](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
- Les locators par rôle, libellé ou contrat explicite aident à cibler les éléments ; les
  correspondances ambiguës demandent un contexte plus précis. [Locators Playwright Python](https://playwright.dev/python/docs/locators).
- Playwright vérifie l'actionnabilité et propose des assertions réessayées automatiquement.
  Les clics forcés peuvent désactiver certains contrôles. [Attentes et assertions](https://playwright.dev/python/docs/actionability).
- Les contextes de navigateur isolent cookies et stockage entre tests.
  [Isolation Playwright Python](https://playwright.dev/python/docs/browser-contexts).
- Les traces permettent d'examiner actions, états de page et échanges pour diagnostiquer
  les échecs. [Trace Viewer](https://playwright.dev/python/docs/trace-viewer).
- Behave précise que `--dry-run` n'exécute pas les steps : il ne suffit pas pour démontrer
  la réussite d'un parcours. [Utilisation de Behave](https://behave.readthedocs.io/en/stable/behave/).
