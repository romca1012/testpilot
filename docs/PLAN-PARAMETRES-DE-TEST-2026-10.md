# Plan de réalisation — Paramètres de test (lots PT-00 à PT-07)

Date : 2026-10-13. Statut : **validé par le porteur le 2026-10-13** (plan, ordre et les deux arbitrages du §5) ; PT-00 et
PT-01 lancés le même jour. Référence de code : `master` = `846ef04`.
Source des décisions : `reports/parametres-de-test-dossier-de-cadrage-2026-10-13.pdf` (version 3) — décisions prises
**A1 à A17**, décisions ouvertes **V1 à V16** (V12 tranchée, devenue A16).
Remplace l'ordre de `PLAN-CALCUL-DE-VALEURS-2026-10.md` : le calcul de valeurs devient les lots PT-03 et PT-06 de ce plan.

## 1. Ce que le plan doit rendre

> Les paramètres de test sont tout ce qu'on règle pour qu'un même test puisse être joué dans des conditions différentes,
> sans le réécrire (A1).

Six familles (A2) : configurations, comptes et rôles, données de test, état de départ, valeurs attendues, réglages
d'exécution. Quatre niveaux (A3) : bibliothèque commune → projet → campagne → test, le plus précis l'emporte.

## 1 bis. Décisions prises après le dossier de cadrage

| ID | Décision | Date |
|---|---|---|
| A18 | Le déplacement des comptes, du navigateur et de la remise à zéro est **définitif**. Aucune ligne de renvoi dans l'ancienne fenêtre : « ne pas être brusque » veut dire que le nouvel écran est bien fait et **vérifié avant** que l'ancien soit retiré, pas que l'utilisateur est guidé de l'un à l'autre. Remplace la proposition V14 et la page « transition » du dossier (les trois fenêtres côte à côte). | 2026-10-13 |
| A19 | Le compte principal se modifie dans l'onglet « Comptes », au même endroit que les autres, avec sa façon de se connecter. La fenêtre « Identité et application » ne garde que le nom du projet, le connecteur, la version et l'adresse. (V15) | 2026-10-13 |
| A20 | Rien n'est poussé avant la fin de tout le chantier (voir R9). | 2026-10-13 |
| A21 | Quand l'application visée par un projet change (adresse ou base de données), l'autorisation donnée à l'IA d'agir pendant la génération est **retirée d'office** et doit être redonnée dans l'onglet « État de départ ». Règle **globale**, la même pour tous les connecteurs ; l'écran le dit quand cela arrive. Appliquée côté serveur (`routes/projects.py`). | 2026-10-13 |
| A22 | Rappel du porteur : aucune fonctionnalité propre à un type d'application. Une fonctionnalité qui ne peut pas être étendue à toutes les applications est supprimée. | 2026-10-13 |
| A23 | La remise à zéro de l'application, et l'essai des actions par l'IA qui en dépend, sont étendus à **toutes** les applications (aujourd'hui : connecteur web seulement). | 2026-10-13 |
| A24 | **Valeur attendue sans unité alors que l'écran en affiche une** (ancienne V9) — choix « prudent » du porteur : jamais de réussite sans que l'unité soit vérifiée. Si l'écran affiche un montant et que le projet a **déclaré sa monnaie**, la valeur attendue est lue dans cette monnaie (une autre monnaie à l'écran est un défaut) ; sinon l'outil ne se prononce pas et demande d'écrire l'unité dans le test. Même prudence, appliquée par extension et annoncée au porteur : une notation partagée par plusieurs monnaies (« $ », « F CFA ») ne prouve une monnaie précise que si le projet l'a déclarée ; une mention écrite d'un seul côté (« TTC », « k » de « 5 k€ ») ne conclut pas ; l'écriture des nombres déclarée par le projet ne tranche une valeur **affichée** ambiguë que pour les séparateurs qu'elle nomme (« 1 234,56 » ne dit rien du point), jamais la valeur attendue. | 2026-10-13 |
| A25 | **Unités ajoutées par un projet** (« palette », « point de fidélité ») — choix du porteur : « reconnaître ses écritures ». Le projet déclare l'unité et ses autres écritures exactes (« palettes », « Palettes ») ; l'outil les reconnaît alors comme la même unité. Aucune conversion (« 1 palette = 48 cartons » n'est pas retenu), aucune tolérance au-delà des écritures déclarées. Une unité que l'outil connaît déjà (« kg », « € ») ne peut pas être déclarée. | 2026-10-13 |
| A26 | **Écriture d'une variable dans un test** (ancienne V2) : `{{nom}}`, entre doubles accolades — choix du porteur, écart voulu avec TestRail (`%nom%`) et avec la première rédaction de ce plan. Aucune confusion possible avec un pourcentage. | 2026-10-13 |
| A27 | **Case vide d'un jeu de données** (ancienne V3) : elle reprend la valeur de la colonne « Par défaut ». | 2026-10-13 |
| A28 | **Lancement avec plusieurs jeux de données** (ancienne V4) : une exécution par jeu, regroupées dans un plan ; l'écran annonce le nombre d'exécutions avant de créer ; **50 au plus** par lancement. | 2026-10-13 |
| A29 | **Jeu de données modifié pendant une exécution** (ancienne V7) : les valeurs sont figées au lancement ; un rejeu reprend les mêmes. Écart voulu avec TestRail. | 2026-10-13 |
| A30 | **Qui modifie les données de test d'un projet** (ancienne V5, pour le niveau projet) : testeurs, développeurs et administrateurs du projet, comme pour les tests ; les lecteurs consultent. Écart avec la proposition du dossier (développeurs et administrateurs seulement). Le niveau « bibliothèque commune » reste à décider au lot PT-05. | 2026-10-13 |
| A31 | **Supprimer une variable ou un jeu de données utilisé** (ancienne V13) : mise à la corbeille, restaurable ; l'outil montre d'abord les tests concernés ; tant qu'elle y est, ces tests sortent « bloqué ». | 2026-10-13 |

Interrupteur (confirmé par le porteur le 2026-10-13) : il ne sert qu'au temps de la construction, pour comparer
l'ancien écran et le nouveau. Le changement étant définitif, il est retiré au lot PT-07 avec l'ancien écran.

Écart à la règle A22, relevé le 2026-10-13 : l'onglet « État de départ » n'offre l'adresse de remise à zéro qu'aux projets
du connecteur web, parce que l'essai des actions par l'IA n'existe que pour lui (lot VH-07). **Tranché (A23) : on l'étend à
toutes les applications**, au lot PT-04. D'ici là le champ reste réservé au connecteur web.

## 2. Règles de réalisation — valables pour tous les lots

| # | Règle | Décision | Comment elle est tenue |
|---|---|---|---|
| R1 | Ne rien casser | A6 | Sans réglage, le comportement est celui d'aujourd'hui. Chaque nouveauté est livrée derrière un interrupteur éteint. Migrations **additives** seulement. Suite complète verte avant chaque commit. |
| R2 | Rien à ressaisir | A17, A18 | Un écran déplacé relit les **mêmes** données ; aucune copie, aucune conversion de données existantes. |
| R3 | Générique | A4 | Aucun nom de client, de métier ou de logiciel dans le code commun, les migrations, les libellés ni les tests. |
| R4 | Dans l'existant, comme TestRail | A5, A14 | Aucune entrée ajoutée au menu du projet. Un bouton dans « Paramètres du projet », une entrée dans le menu d'administration. |
| R5 | Écrans sobres | A15 | Libellés, valeurs, pastilles, boutons. Aucune phrase d'explication à l'écran. Skill UI UX Pro Max appliqué à chaque écran. |
| R6 | Verdict intact | CLAUDE.md §3, §4 | Un paramètre est **déclaré par une personne**, jamais écrit par l'agent. Aucun chemin nouveau vers `conforme` sans preuve. Revue `verdict-reviewer` avant le premier commit de tout lot qui touche `verdict/`, `execution/`, `behave_runtime/`, `generation/` ou le schéma. |
| R7 | Mesurer avant d'activer | CLAUDE.md §5, §8 | Tout ce qui change ce que l'agent reçoit est mesuré sur le banc (faux verts, premier essai, coût) avant d'être allumé. Budget annoncé avant chaque campagne. |
| R8 | Schéma : les quatre pièces | CLAUDE.md §6 | Migration SQLite idempotente (la prochaine est la **64** ; 62 et 63 sont prises par PT-03), révision Alembic chaînée sur `f3a8d1c6b257`, `schema_sa.py`, test de migration + `test_schema_sa_portable.py`. |
| R9 | Rien n'est poussé avant la fin du chantier | porteur, 2026-10-13 | Un lot = une branche **locale**, des commits atomiques. **Aucun push, aucune PR, aucune fusion** tant que les lots PT-00 à PT-07 ne sont pas tous terminés, vérifiés (contrôles automatiques ET essais à l'écran sur l'instance locale) et verts. Remplace, pour ce chantier, « un lot = une PR » de CLAUDE.md §5. `master` est ramené régulièrement dans les branches, en local, pour ne pas dériver. |

## 3. Architecture cible

### 3.1 Données

| Objet | Stockage proposé | Lot |
|---|---|---|
| Navigateur de test, comptes, remise à zéro | **inchangé** : colonnes `project.browser_*`, table `project_account`, `project.bac_a_sable_reset` | PT-01 |
| Variable, jeu de données, valeur | tables nouvelles `test_variable`, `test_dataset`, `test_dataset_value` ; colonne `project_id` **nullable** dès la création (NULL = bibliothèque commune, A3) | PT-02 |
| Valeurs figées d'une exécution | colonnes nouvelles sur `test_run` : `dataset_id`, `parametres_figes` (JSON : variables résolues, configuration, compte) | PT-02 |
| Valeurs jouées par un test | colonne nouvelle sur `execution` : `parametres_joues` (JSON), copiée depuis l'exécution au lancement | PT-02 |
| Monnaie, écriture des nombres, unités du projet | colonnes nouvelles sur `project` (`devise`, `format_nombre`) ; table `test_unit` | PT-03 |
| Environnement | table nouvelle `project_environment` (nom, adresse, version, par défaut) ; l'adresse actuelle du projet devient l'environnement par défaut, **sans être déplacée** | PT-04 |
| Compte d'une exécution | `test_run.account_id` (NULL = compte principal) | PT-04 |
| Cartographie par compte | un fichier de cartographie par projet **et par compte** ; celui du compte principal garde son nom actuel | PT-04 |
| Partage entre projets | `project_id` NULL + table `test_parameter_share` (élément, projet autorisé) | PT-05 |
| Règle de calcul, taux, cas de référence | tables nouvelles `calc_rule`, `calc_rule_step`, `calc_rate`, `calc_reference_case` | PT-06 |

### 3.2 Résolution des niveaux

Un module **pur** `src/testpilot/parametres/resolution.py` (aucune I/O, aucun LLM) : il reçoit les valeurs de chaque niveau
et rend la valeur retenue avec **son niveau d'origine**. Appelé à un seul endroit : au lancement d'une exécution.

### 3.3 Où une variable est remplacée

- Écriture `{{nom}}` (A26). Nom fait de lettres minuscules (accents admis), de chiffres et de `_`, sans espace : « 10 % de
  remise » n'est jamais concerné. Seul le **texte du test** (le `.feature`) est lu ; le code des steps n'est jamais modifié
  (des accolades doublées y ont un autre sens).
- Remplacement au **lancement**, dans `run_service._assurer_script_sur_disque` : le test stocké garde ses `{{nom}}`, la copie
  jouée reçoit les valeurs figées. Chaque exécution reçoit **son propre dossier** de script (aujourd'hui partagé par nom de
  module), pour que deux jeux de données joués en même temps ne s'écrasent pas.
- Variable inconnue ou sans valeur : l'exécution n'est pas lancée, le cas sort « bloqué » avec la variable nommée — jamais
  une chaîne `{{nom}}` saisie telle quelle dans l'application.
- Les valeurs sont **figées au lancement** (A29) et relues depuis `parametres_figes` pour tout rejeu.

### 3.4 Interface

| Écran | Route proposée | Habillage |
|---|---|---|
| Paramètres de test d'un projet, cinq onglets | `/admin/projects/:pid/parametres-de-test/:onglet` | administration (`InstanceAdminShell`) ; route ajoutée à `ROUTES_SANS_SHELL` |
| Bibliothèque commune | `/settings/parametres-de-test` | administration |
| Bouton d'accès | `ProjectsList.vue`, zone « Paramètres du projet » | existant |
| Lancement | `AddTestRunForm.vue`, `SchedulesList.vue` | existant |
| Résultats | `PlanDetail.vue`, `RunDetail.vue`, `RunTestDetail.vue`, `ReportView.vue` | existant |
| Cas de test | `CaseDetailTR.vue` | existant |

Chaque onglet a sa propre adresse (lien direct, retour arrière prévisible).

## 4. Lots

Taille : **P** petite, **M** moyenne, **G** grosse. Chaque sous-lot est une PR.

### PT-00 — Préparation (P)

But : partir sur des bases mesurées et des décisions prises.

1. Faire trancher les décisions ouvertes qui bloquent PT-01 et PT-02 (§6).
2. Écrire, pour chaque maquette, la fiche d'écran : champs, états vides, erreurs, droits, clavier (UI UX Pro Max).
3. Relever les références avant travaux : suite complète, contrôles d'interface, campagne `base-7` du banc.
4. Interrupteur d'interface `parametres_de_test` (réglage d'installation, éteint) : il permet de revenir à l'ancienne
   fenêtre complète à tout moment (A17).
5. Décider du sort de la branche `lot-cv01-montants-affiches` (voir PT-03).

Acceptation : décisions du §6 marquées « validée » pour PT-01 et PT-02 ; références archivées dans `docs/mesures/`.

### PT-01 — Rassembler l'existant (M) — décisions A14, A16, A17, A18, A19 ; V1

But : un seul endroit pour régler les tests d'un projet, sans rien changer à ce qui est enregistré.

| Sous-lot | Contenu |
|---|---|
| PT-01a | Page « Paramètres de test » du projet, onglets **Configurations** (langue, fuseau, taille d'écran actuels), **Comptes**, **État de départ**. Bouton dans « Paramètres du projet ». Mêmes appels serveur qu'aujourd'hui. |
| PT-01b | **Décidé le 2026-10-13.** Le déplacement est **définitif**, sans ligne de renvoi : la fenêtre « Identité et application » ne garde que le nom, le connecteur, la version et l'adresse. Le compte principal se règle dans l'onglet « Comptes », avec sa façon de se connecter. L'ancien écran n'est retiré qu'une fois le nouveau vérifié (contrôles et essais à l'écran). Message de l'outil qui cite l'ancien emplacement mis à jour. |

Schéma : **aucun changement**. Serveur : aucune route modifiée (si V15 = oui : le compte principal devient modifiable depuis
l'onglet « Comptes », par la route existante de mise à jour du projet).

Tests : contrôles d'interface (affichage des valeurs existantes, enregistrement, renvois, droits `admin`/`dev`, interrupteur
éteint = fenêtre d'aujourd'hui) ; `shell.spec.ts` étendu à la nouvelle route.

Acceptation :
- [ ] un projet existant retrouve toutes ses valeurs dans les onglets, sans rien saisir
- [ ] une modification faite dans un onglet est celle que l'exécution utilise (vérifié sur une exécution réelle locale)
- [ ] interrupteur éteint : écran et comportement strictement identiques à aujourd'hui
- [ ] organisation allumée : la fenêtre « Identité et application » ne montre et n'envoie que nom, connecteur, version, adresse
- [ ] le compte principal se modifie dans l'onglet « Comptes » ; un secret non saisi n'est jamais envoyé
- [ ] chaque onglet s'ouvre par son adresse
- [ ] mêmes droits qu'aujourd'hui ; navigation au clavier ; aucun texte d'explication à l'écran
- [ ] suite complète et contrôles d'interface verts

### PT-02 — Données de test (G) — décisions A2, A3, A26 à A31

But : un même test joué pour plusieurs situations.

| Sous-lot | Contenu |
|---|---|
| PT-02a | Schéma (variables, jeux, valeurs, colonnes figées), dépôts, routes de lecture et d'écriture, droits, corbeille (V13). Onglet « Données de test » : le tableau, le jeu « Par défaut », la case vide. Import Excel. |
| PT-02b | Module pur de résolution et de remplacement ; remplacement au lancement ; dossier de script par exécution ; refus d'une variable inconnue. Formulaire de lancement et planifications : choix des jeux, une exécution par jeu, regroupées dans un plan, nombre indiqué avant de créer. |
| PT-02c | Résultats : valeurs jouées dans le résultat d'un test ; jeu de données dans la liste d'un plan. Fiche d'un cas : bouton « Variable », aperçu par jeu. |
| PT-02d | Génération : l'agent reçoit le **nom** des variables du projet et peut les employer. Interrupteur éteint, mesure sur le banc, coût avant et après. |

Tests : module de résolution (pur, exhaustif) ; migration ; **falsifiabilité** — un test joué avec un jeu dont la valeur
attendue est fausse sort `non_conforme`, une variable inconnue sort « bloqué », deux jeux joués en même temps ne se mélangent
pas ; non-régression — une exécution sans jeu de données produit le même script qu'aujourd'hui, octet pour octet.

Acceptation :
- [ ] un cas écrit une fois est joué pour N jeux, avec N résultats distincts
- [ ] chaque résultat affiche les valeurs réellement jouées ; un rejeu reprend les valeurs figées
- [ ] modifier un jeu après le lancement ne change pas une exécution en cours
- [ ] sans jeu choisi : une seule exécution, identique à aujourd'hui
- [ ] « 10 % » dans un test n'est jamais pris pour une variable
- [ ] PT-02d : zéro faux vert sur le banc, coût par cas sous 1 €, sinon l'interrupteur reste éteint

### PT-03 — Valeurs avec leur unité (P à M) — décisions A8 ; V9

But : un montant, un taux, un poids sont comparés comme des nombres avec leur unité.

Écrit sur la branche locale `lot-pt03-valeurs-avec-unite` (reprise du travail commencé sous le nom CV-01). État :
1. fait — import valable des deux façons dont la bibliothèque est chargée (les 15 régressions du premier jet ont disparu) ;
2. fait — les six points de la première revue ;
3. fait — nombre, unité, nature ; step « le nombre affiché pour … vaut … », derrière l'interrupteur `TESTPILOT_STEP_NOMBRE` éteint ;
4. fait — monnaie et écriture des nombres du projet (migration 62, onglet « Valeurs attendues »), règle A24 ;
   fait aussi — les unités ajoutées du projet (migration 63, table `test_unit`, décision A25), relues à part : la revue a
   trouvé qu'elles n'arrivaient au test que pendant la génération, pas en campagne — corrigé, un seul point de chargement ;
5. fait — quatre passes de revue indépendante (la deuxième et la troisième ont trouvé des faux verts, tous reproduits puis
   corrigés avec un contrôle par cas ; la quatrième : aucun bloquant) ;
6. fait — mesure SANS IA du step sur le banc d'agents web (décision du porteur, 2026-10-13 : « A maintenant puis C ») :
   8 jeux sur 8 conformes à l'attendu, 0 $ (`docs/mesures/banc-agents-2026-10-13-pt03-step-nombre-sans-ia*.md`) ;
   **reste** : la mesure avec l'IA, groupée avec la campagne du lot PT-02d — l'interrupteur reste éteint d'ici là.

Limites connues, à mesurer sur le banc : une mention affichée que le test n'écrit pas (« 129,51 € TTC » contre « 129,51 € »)
ne conclut pas ; une unité écrite dans une autre casse ne conclut pas ; un code de monnaie qui est aussi un mot (« TOP 5 »)
est lu comme un montant ; la garde « valeur recopiée de l'essai » ne voit pas une valeur convertie (« 1,5 kg » vu, « 1500 g »
écrit ; « 5 ‰ » vu, « 0,5 % » écrit), et ne compare par valeur les petits entiers que pour ce step — trois steps plus anciens
comparent aussi des nombres (deux steps d'oracle, un step de document) et pourront recevoir le même marqueur
`@compare_des_nombres` ; une réussite obtenue grâce à la monnaie du projet ne laisse pas de trace dans le résultat.

Acceptation : celle du lot CV-01, plus : une même valeur dans deux unités convertibles est reconnue ; deux natures
différentes sortent `non_conforme` ; une unité attendue et non affichée ne conclut pas.

### PT-04 — Configurations : environnements, comptes, navigateur (M à G) — décisions A16 ; V4, V15, V16

| Sous-lot | Contenu |
|---|---|
| PT-04a | Plusieurs environnements par projet ; choix au lancement ; **la protection de la production est évaluée pour chaque environnement**, jamais contournée. |
| PT-04b | Compte choisi au lancement ; exploration avec chaque compte ; l'agent reçoit la cartographie du compte visé. |
| PT-04d | **Remise à zéro pour toutes les applications (A23).** L'adresse de remise à zéro et l'essai des actions par l'IA avant d'écrire un test, aujourd'hui réservés au connecteur web, sont étendus à tous les connecteurs ; l'onglet « État de départ » devient identique pour tous. Touche la génération : interrupteur, revue `verdict-reviewer`, mesure sur le banc, coût avant et après. |
| PT-04c | Choix du navigateur. **Écart avec la maquette** : aujourd'hui tout le code lance Chromium (exécution, exploration, enregistrement, connecteurs) et le confinement réseau des essais repose sur des options propres à Chromium. **Décidé le 2026-10-13** : garder le groupe « Navigateur » dans le modèle, ne livrer que Chromium, instruire Firefox à part. |

Tests : une campagne jouée sur deux environnements produit deux exécutions distinctes ; un environnement déclaré en
production est refusé au lancement ; un test joué « en tant que » un compte sans droit sort le verdict attendu (règle D34
inchangée) ; l'exploration d'un compte n'écrase pas celle d'un autre.

### PT-05 — Bibliothèque commune (M) — décisions A3, A4 ; V5, V6

Entrée « Paramètres de test » du menu d'administration ; éléments partagés (configurations, jeux de données, unités) ;
« ouvert à » ; « utilisé par » ; remplacement local par un projet, signalé à l'écran ; avertissement avant de modifier un
élément utilisé.

Acceptation : un élément partagé modifié est vu par les projets qui l'utilisent ; un projet qui l'a remplacé garde sa
valeur ; un projet non autorisé ne le voit pas ; supprimer passe par la corbeille.

### PT-06 — Valeur attendue calculée (G) — décisions A9 à A13 ; V8, V10

| Sous-lot | Contenu |
|---|---|
| PT-06a | Moteur de calcul pur (étapes simples, arrondi, plafond, barème par tranches, condition), en `Decimal`, détail ligne par ligne. |
| PT-06b | Règles, taux (source, date d'effet, date de vérification), cas de référence, validation par une personne. Écrans. |
| PT-06c | Step « … vaut le résultat calculé "<nom>" » ; calcul à chaque exécution ; état **« à vérifier »** quand la règle n'est pas validée ou qu'un taux est périmé (nouvelle valeur affichée : les quatre pièces + libellés français serveur et interface). |
| PT-06d | Détail du calcul dans la relecture et dans le résultat ; mesure sur le banc avec des spécifications sans résultat écrit et des erreurs de calcul introduites exprès. |

Acceptation : zéro faux vert sur le banc ; aucune règle utilisable sans avoir retrouvé ses cas de référence ; une règle non
validée ne donne ni `conforme` ni `non_conforme` ; coût par cas inchangé (le calcul ne fait aucun appel à l'IA).

### PT-07 — Clôture (P)

Retrait de l'ancien écran et de l'interrupteur, une fois le nouveau vérifié de bout en bout (A18) ; guide utilisateur, avec
ses captures refaites ; mesure de clôture sur le banc ; mise en ligne sur
`/staging` par le porteur ; bilan avec les écarts au plan.

## 5. Ordre et jalons

Ordre : PT-00 → PT-01 → **PT-03** → PT-02 → PT-04 → PT-05 → PT-06 → PT-07 (ordre A7, modifié sur un point le 2026-10-13 :
PT-03 passe juste après PT-01).

| Jalon | Atteint après | Ce que l'utilisateur peut faire |
|---|---|---|
| J1 — Un seul endroit | PT-01 | Régler navigateur, comptes et état de départ d'un projet au même endroit |
| J2 — Un test, plusieurs situations | PT-02 | Jouer un même test pour plusieurs jeux de données |
| J3 — Les nombres sont compris | PT-03 | Vérifier un montant, un taux, un poids avec son unité |
| J4 — Plusieurs conditions | PT-04 | Jouer une campagne sur plusieurs environnements et avec plusieurs rôles |
| J5 — Réutilisable | PT-05 | Reprendre dans un projet ce qu'un autre a réglé |
| J6 — Valeur calculée | PT-06 | Vérifier une valeur sans l'avoir recopiée d'une spécification |

**Arbitrages du porteur (2026-10-13).**
1. PT-03 est déjà écrit et touche le fichier le plus modifié du dépôt (`behave_runtime/steps_library/_base_helpers.py`) :
   il est terminé **juste après PT-01**, avant PT-02.
2. Navigateur : seul Chromium est livré (voir PT-04c) ; un second navigateur sera instruit à part.

## 6. Décisions à obtenir, par lot

| Lot | Décisions qui le bloquent | Sans elles |
|---|---|---|
| PT-01 | aucune : V14 et V15 tranchées le 2026-10-13 (A18, A19) ; V1 acquise (le porteur emploie « Paramètres de test ») | — |
| PT-02 | aucune : V2, V3, V4, V5, V7 et V13 tranchées le 2026-10-13 (A26 à A31) | — |
| PT-03 | aucune : V9 tranchée le 2026-10-13 (A24), rôle des unités ajoutées tranché le même jour (A25) | — |
| PT-04 | V16 (exploration par compte, compte au lancement) | PT-04a peut démarrer |
| PT-05 | V5, V6 (remplacement local) | le lot ne démarre pas |
| PT-06 | V8 (délai « à revérifier »), V10 (qui valide) | PT-06a peut démarrer |
| Périmètre | V11 (première version = PT-01 à PT-03) | — |

Règle du dépôt (CLAUDE.md §5.3) : un lot qui dépend d'une décision non validée s'arrête et présente une proposition.

## 7. Risques transverses

| Risque | Réponse |
|---|---|
| Un faux `conforme` introduit par un paramètre | Un paramètre vient d'une personne, jamais de l'agent ; variable inconnue = « bloqué » ; règle non validée = « à vérifier » ; tests de falsifiabilité à chaque lot ; revue `verdict-reviewer`. |
| Régression pour les projets existants | R1, R2 ; test « sans réglage = identique à aujourd'hui » dans chaque lot ; interrupteur de retour arrière. |
| Explosion du nombre d'exécutions | Nombre indiqué avant de créer ; 50 exécutions au plus par lancement (A28) ; exécution en séquence comme aujourd'hui. |
| Deux exécutions qui se marchent dessus | Dossier de script par exécution (PT-02b), testé. |
| Coût de l'IA | Rejouer un test avec d'autres données ne régénère rien ; seuls PT-02d et PT-04b changent ce que l'agent reçoit, et sont mesurés. |
| Données sensibles | Mots de passe uniquement dans les comptes, chiffrés, jamais dans une variable ni dans un résultat ; `parametres_joues` ne contient que le **nom** du compte. |
| Dérive de périmètre | Un lot ne fait que son contenu ; le reste va en « suggestions » du rapport de lot. |
| Second navigateur | Voir PT-04c : écart signalé, arbitré le 2026-10-13 (Chromium seul). |

## 8. Suivi

| Lot | Statut | Date | PR | Rapport |
|---|---|---|---|---|
| PT-00 | terminé en local (plan, interrupteur, mesures de référence) ; fiches d'écran faites pour PT-01 seulement | 2026-10-13 | — | |
| PT-01a | terminé en local : écrit, relu, vérifié à l'écran ; suite du serveur identique à la référence (4 207 réussis, les 5 échecs connus) | 2026-10-13 | — | |
| PT-01b | terminé en local : écrit, relu (aucun bloquant, sept points corrigés), vérifié à l'écran ; règle A21 ajoutée ; suite du serveur de clôture : 4 219 réussis, les 5 échecs connus du poste | 2026-10-13 | — | |
| PT-02a à PT-02d | à faire | | | |
| PT-03 | terminé en local, interrupteur ÉTEINT : comparaison avec unité, règle A24, monnaie, écriture des nombres, unités ajoutées (A25), relus et vérifiés à l'écran ; mesure sans IA : 8 jeux sur 8 ; la mesure avec l'IA est reportée dans la campagne de PT-02d, qui décidera de l'allumer | 2026-10-13 | — | `docs/mesures/banc-agents-2026-10-13-pt03-step-nombre-sans-ia-methode.md` |
| PT-04a à PT-04d | à faire | | | |
| PT-05 | à faire | | | |
| PT-06a à PT-06d | à faire | | | |
| PT-07 | à faire | | | |
