# Suite du chantier — restes consignés et état du calcul de valeurs

Date : 2026-10-12. Référence de code : `master` = `846ef04` (PR #80 à #83 fusionnées, en ligne sur `/dev`).
Statut : **note de passation**. Le plan de la suite est `PLAN-PARAMETRES-DE-TEST-2026-10.md`.

Demande du porteur (2026-10-12) : consigner tout ce qui reste, puis se concentrer sur le calcul de valeurs.

## 1. Restes consignés — génération (mis de côté, pas abandonnés)

Mesure de référence : campagne `base-7` (`docs/mesures/banc-agents-2026-10-11-base-7.md`), 10 cas × 3 essais sur la
boutique locale du banc : 0 faux vert sur 25, 0 faux rouge sur 23, 7 cas sur 10 justes au premier essai (23 essais sur 30),
0,166 $ par génération.

| # | Reste | Détail mesuré | Où dans le plan |
|---|---|---|---|
| G1 | 7 essais sur 30 en erreur technique | `commande_persistance_serveur` 3/3 et `commande_confirmation` 1/3 : l'agent ne connaît pas la FORME de la réponse de l'oracle ; `panier_remise_arrondi` 2/3 : génération sans essai à blanc passé ; `client_creation_nom_requis` 1/3 | bilan base-6/base-7 |
| G2 | Essai des actions avant l'écriture | première version (connecteur web), gain non mesuré hors `panier_total_tva` ; **à ne pas activer sur une application réelle avant le lot 8** | VH-07 |
| G3 | Preuve de chaque `conforme` | source de chaque valeur attendue, certificat de falsifiabilité, « preuve forte / faible » | VH-08, pas commencé |
| G4 | Réparation bornée et revérifiée | adressage seulement, jamais la vérification | VH-09, pas commencé |
| G5 | Mesure de clôture sur application jamais vue | critères D27, ~15 $ | VH-10, pas commencé |
| G6 | Lots partiels | VH-04 (vérifications partagées), VH-06 | plan VH §suivi |
| G7 | Menu Odoo cherché en anglais, session en français | `navigate_menu` ; vu de nouveau le 2026-10-12 (run 33, « Surveys ») | chantier F |
| G8 | Correctif écarté : session perdue en cours de test (hotfix 07b-2) | faux `conforme` possible ; décision bloquer / reconnecter à prendre | hors PR #81 |
| G9 | Correctif écarté : champ identifiant sans `type` (PR #53, ouverte) | faux `blocked` ; n'élargir que si un mot de passe est visible | PR #53 |
| G10 | `attendre_page_rendue` : suites de relecture | 3 tests à ajouter, grâce à déclencher sur la fin de chargement | PR #81 |
| G11 | Test instable de garde de session | `tests/test_vh04_garde_session.py`, 1 échec sur 12 en CI, 0 sur 14 en local | tâche proposée |
| G12 | Bloc dépliant déjà ouvert au rejeu de la connexion (mode strict) | non reproduit sur le portail Odoo, à couvrir | enregistrement |
| G13 | Bouton « Automatiser avec l'IA » | jamais testé de bout en bout | écran des cas |
| G14 | Interrupteurs restés éteints | mode strict des outils, descriptions V2, règles du connecteur | VH-10 point 3 |

Mise en ligne : `/staging` est toujours sur `91c1797` (6 octobre) ; son déploiement est lancé par le porteur, après ses essais
sur `/dev` (enregistrement de la connexion sur le portail Odoo, exécutions automatiques).

## 2. Calcul de valeurs — ce qui est FAIT (vérifié dans `master` le 2026-10-12)

| # | Élément | État | Preuve |
|---|---|---|---|
| C1 | Comparer une valeur affichée à côté d'un libellé : `la valeur affichée pour "<libellé>" est "<valeur>"` | en service, connecteur web. Comparaison de **texte entier** (espaces normalisés), relue jusqu'au délai | `_base_helpers.valeur_affichee_vaut` |
| C2 | Comparer une valeur lue sur le serveur (oracle HTTP) | en service. Nombre contre nombre, virgule acceptée, **sans tolérance** | `_base_helpers._valeurs_egales` |
| C3 | Odoo : `le champ "<champ>" de ce document vaut <nombre>` | en service. Tolérance = demi-arrondi de la devise, annoncée dans le constat (D19, validée le 2026-10-08) | `_odoo_effets_steps._tolerance_avec_source` |
| C4 | Lecteur de nombre affiché (`lire_nombre`) : « 1 234,50 € », « 1,234.50 », « (12,50) », devises dont le franc CFA ; refuse une lecture ambiguë | **écrit, 15 tests, relu — utilisé par aucun step** (aucun import hors de son fichier) | `steps_library/_lecture_nombre.py` |
| C5 | Comparateur à tolérance déclarée (`comparer`) | **idem : écrit et testé, branché nulle part** | même fichier |
| C6 | Banc : deux cas de montants et un défaut injecté « total faux » (+1 %) | `panier_total_tva` juste 3/3 ; `panier_remise_arrondi` juste 1/3 (2 générations échouées) ; aucun total faux validé | base-7 |
| C7 | Recherche documentaire | faite : un modèle qui calcule de mémoire n'est pas fiable (impôt, paie) ; moteur officiel français disponible ; OpenFisca-Sénégal « expérimental », à ne pas prendre comme référence | `docs/SOURCES-DE-REFERENCE-AGENTS.md` |
| C8 | Proposition d'atelier de calcul (cadrer, chercher, calculateur, contre-vérifier, signer, exécuter) | écrite, **non validée** (D22) | `PLAN-QUALITE-AGENTS-2026-10.md` §4 |
| C9 | Explication pour le manager | section « bulletins de paie de Yros » du point d'avancement | `reports/point-avancement-testpilot-2026-10-11.pdf` |

**Rectification** (à ne pas répéter) : il a été dit que « l'IA calcule le montant attendu à partir de la règle, et c'est mesuré
sur le banc ». C'est inexact. Dans les deux cas du banc, les montants attendus (129,51 € ; 10,56 €) sont **écrits dans la
spécification**. Ce qui est mesuré est donc « valeur écrite dans la spec, comparée à l'écran ». **Aucune mesure n'existe** sur
une valeur que l'IA calcule elle-même, et aucune consigne du prompt n'encadre ce calcul.

## 3. Calcul de valeurs — ce qui RESTE

| # | Reste | Nature |
|---|---|---|
| R1 | Brancher C4 et C5 sur un step de montant (connecteur web, puis oracle) ; test de falsifiabilité ; revue `verdict-reviewer` ; mesure sur le banc avant et après | code, sans LLM |
| R2 | Source de chaque valeur attendue (`spec` / `observé` / `calculé`) ; une valeur observée ne justifie jamais `conforme` | VH-08 point 1, pas commencé |
| R3 | Décision « montant attendu calculé » à inscrire au registre (prolonge VH-08) | décision du porteur |
| R4 | Atelier de calcul : fiche de calcul (sources, formule, exemples, validité), calculateur testé en `Decimal`, second calcul indépendant, signature humaine, détail montré au relecteur | Q5, **rien de codé** |
| R5 | Modèle de données de la fiche, écran de relecture et de signature, verdict « écart à arbitrer » tant que la fiche n'est pas signée | décisions structurantes (schéma, statut à l'écran) |
| R6 | Calibrage sur la France contre le moteur officiel (écart mesuré) | mesure, pas commencée |
| R7 | Cas de banc où la valeur attendue **n'est pas** dans la spec (seule la règle l'est), avec défauts injectés | banc, pas commencé |
| R8 | Outils 3 à 5 de D21 : valeurs limites, couverture des exigences, agent critique de plan | Q4, **aucun code** |
| R9 | Entrées attendues de Yros : règles de calcul par pays, bulletins de référence validés par un expert, pays de départ | dépend du porteur |
| R10 | Coût : séparer le coût de construction d'une fiche (une fois par règle) du coût par cas (§9 du brief, < 1 €) | à mesurer |

Décisions encore ouvertes : **D21** (« à confirmer » ; le porteur a demandé le 2026-10-07 de suivre les recommandations,
démarrage par les outils 1 et 2) et **D22** (« à confirmer »). Selon CLAUDE.md §5.3, R4 et R5 ne démarrent pas avant D22.

## 4. Suite

La vision du porteur (2026-10-12) et les décisions du 2026-10-13 remplacent l'enchaînement d'abord proposé ici : le plan
a d'abord été écrit dans `PLAN-CALCUL-DE-VALEURS-2026-10.md` (branche `lot-cv01-montants-affiches`), puis élargi le
2026-10-14 : le chantier s'appelle désormais « Paramètres de test », et son plan est `PLAN-PARAMETRES-DE-TEST-2026-10.md`
(lots PT-00 à PT-07). Le calcul de valeurs en devient les lots PT-03 et PT-06.
