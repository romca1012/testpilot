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
| A21 | **Remplacée par A43 le 2026-10-16** — Quand l'application visée par un projet change (adresse ou base de données), l'autorisation donnée à l'IA d'agir pendant la génération est **retirée d'office** et doit être redonnée dans l'onglet « État de départ ». Règle **globale**, la même pour tous les connecteurs ; l'écran le dit quand cela arrive. Appliquée côté serveur (`routes/projects.py`). | 2026-10-13 |
| A22 | Rappel du porteur : aucune fonctionnalité propre à un type d'application. Une fonctionnalité qui ne peut pas être étendue à toutes les applications est supprimée. | 2026-10-13 |
| A23 | La remise à zéro de l'application, et l'essai des actions par l'IA qui en dépend, sont étendus à **toutes** les applications (aujourd'hui : connecteur web seulement). | 2026-10-13 |
| A24 | **Révisée par A44 le 2026-10-16** (plus d'écriture des nombres déclarée par le projet : la prudence sur l'unité reste) — **Valeur attendue sans unité alors que l'écran en affiche une** (ancienne V9) — choix « prudent » du porteur : jamais de réussite sans que l'unité soit vérifiée. L'outil ne se prononce pas et demande d'écrire l'unité dans le test. *Révisée le 2026-10-15 (A38)* : la lecture « dans la monnaie déclarée par le projet » est retirée avec la monnaie du projet. Même prudence, appliquée par extension et annoncée au porteur : une notation partagée par plusieurs monnaies (« $ », « F CFA ») ne prouve pas une monnaie précise ; une mention écrite d'un seul côté (« TTC », « k » de « 5 k€ ») ne conclut pas ; l'écriture des nombres déclarée par le projet ne tranche une valeur **affichée** ambiguë que pour les séparateurs qu'elle nomme, jamais la valeur attendue. | 2026-10-13 |
| A25 | **Retirée par A44 le 2026-10-16** — **Unités ajoutées par un projet** (« palette », « point de fidélité ») — choix du porteur : « reconnaître ses écritures ». Le projet déclare l'unité et ses autres écritures exactes (« palettes », « Palettes ») ; l'outil les reconnaît alors comme la même unité. Aucune conversion (« 1 palette = 48 cartons » n'est pas retenu), aucune tolérance au-delà des écritures déclarées. Une unité que l'outil connaît déjà (« kg », « € ») ne peut pas être déclarée. | 2026-10-13 |
| A26 | **Écriture d'une variable dans un test** (ancienne V2) : `{{nom}}`, entre doubles accolades — choix du porteur, écart voulu avec TestRail (`%nom%`) et avec la première rédaction de ce plan. Aucune confusion possible avec un pourcentage. | 2026-10-13 |
| A27 | **Case vide d'un jeu de données** (ancienne V3) : elle reprend la valeur de la colonne « Par défaut ». | 2026-10-13 |
| A28 | **Lancement avec plusieurs jeux de données** (ancienne V4) : une exécution par jeu, regroupées dans un plan ; l'écran annonce le nombre d'exécutions avant de créer ; **50 au plus** par lancement. Précision annoncée le 2026-10-14 : une **planification** retient ses jeux et fait de même à chaque déclenchement ; une planification qui n'a rien pu lancer ne laisse aucun brouillon (voir A36). | 2026-10-13 |
| A29 | **Jeu de données modifié pendant une exécution** (ancienne V7) : les valeurs sont figées au lancement ; un rejeu reprend les mêmes. Écart voulu avec TestRail. | 2026-10-13 |
| A30 | **Qui modifie les données de test d'un projet** (ancienne V5, pour le niveau projet) : testeurs, développeurs et administrateurs du projet, comme pour les tests ; les lecteurs consultent. Écart avec la proposition du dossier (développeurs et administrateurs seulement). Le niveau « bibliothèque commune » reste à décider au lot PT-05. | 2026-10-13 |
| A31 | **Supprimer une variable ou un jeu de données utilisé** (ancienne V13) : mise à la corbeille, restaurable ; l'outil montre d'abord les tests concernés ; tant qu'elle y est, ces tests sortent « bloqué ». | 2026-10-13 |
| A32 | **Par où un testeur atteint le tableau des données de test** : par un lien là où il en a besoin (création d'une exécution, fiche d'un test), qui ouvre une page du projet montrant le seul tableau. Rien n'est ajouté au menu du projet ; les autres onglets des paramètres de test restent à l'administration. | 2026-10-13 |
| A33 | **Relancer une exécution dont la colonne a été mise à la corbeille depuis** : l'outil rejoue les valeurs figées au lancement de cette exécution (A29 l'emporte ; la corbeille n'empêche que le PREMIER lancement). | 2026-10-14 |
| A34 | **Texte entre doubles accolades qui n'est pas une variable** (modèle de courriel d'Odoo, par exemple) dans un projet qui a des données de test : le test sort « bloqué » avec le texte en cause, l'outil ne devine pas. Une façon d'écrire des accolades « pour de vrai » reste à prévoir si le besoin se présente. | 2026-10-14 |
| A35 | **Plusieurs jeux cochés au lancement, et des tests qui n'écrivent aucune variable** : ces tests ne sont joués qu'UNE fois, dans la première exécution (celle du jeu « Par défaut » s'il est coché) ; les exécutions des autres jeux (une par jeu, toujours créées) ne jouent que les tests qui écrivent des variables. Ce tri se fait **au lancement**, comme les valeurs (A29) : un test qui gagne une variable après la création est joué avec chaque jeu ; un test qui a déjà un résultat dans une exécution y reste. Une exécution qui n'a alors aucun test à variables refuse de se lancer en le disant. L'écran l'annonce avant de créer. Écart voulu avec TestRail, qui rejoue tout à chaque jeu. | 2026-10-14 |
| A36 | **Planification dont une colonne a été mise à la corbeille** : elle ne joue **rien** (ni les autres colonnes, ni « Par défaut » à la place) tant qu'on ne l'a pas corrigée — restaurer la colonne ou recréer la planification. La liste des planifications affiche « Ne se déclenche pas : un jeu de données est à la corbeille ». | 2026-10-14 |
| A37 | **Import Excel du tableau des données de test** : il **complète** le tableau — ajoute les variables et les colonnes qui manquent, met à jour les cases qu'il remplit ; une case vide du fichier ne vide rien, rien n'est supprimé. L'écran montre ce qui va changer avant d'enregistrer ; une seule erreur dans le fichier (nommée par sa case) et rien n'est écrit. L'export du tableau sert de modèle. | 2026-10-14 |
| A38 | **Aucune base toute faite dans les paramètres** (porteur, 2026-10-15) : l'outil ne fournit pas de réglage tiré d'un cas particulier. La **monnaie du projet est retirée** (réglage, colonne, règle A24 pour sa partie « monnaie déclarée ») ; **l'écriture des nombres reste** un réglage ; **les unités ajoutées restent** (une liste vide que chaque projet remplit lui-même). La lecture des nombres continue de reconnaître « € » et « EUR » comme la même unité : c'est de la lecture, pas un réglage. Une valeur attendue écrite sans unité face à un montant affiché : l'outil ne se prononce pas et demande d'écrire l'unité (règle prudente d'A24, inchangée). | 2026-10-15 |
| A39 | **Validée par le porteur le 2026-10-15** — option en plus, le parcours d'aujourd'hui ne change pas pour un projet sans paramètre. *Le cas fait foi, aussi pour les données* : quand le projet a déclaré des données de test, c'est le CAS (sa description, relue et validée par une personne) qui dit quelles données de test il emploie, écrites `{{client}}` ; l'IA les y propose à partir des variables du projet, la personne valide ; le test technique doit ensuite reprendre exactement ces variables — vérifié sans IA, refusé sinon. Les tests déjà écrits s'associent d'un clic (proposition sans IA, aperçu, nouvelle version à relire). | 2026-10-15 |
| A40 | **Validée par le porteur le 2026-10-15** — associer d'un clic est ouvert à tous ceux qui modifient un test (testeurs compris), y compris quand l'association touche une VÉRIFICATION (une étape « Alors »), sans condition de rôle : la nouvelle version est à relire comme toute modification. Écartées : réservé au rôle développeur ; relecture obligatoirement par une autre personne. À savoir : une valeur saisie dans une action peut décider de ce qu'un « Alors » compte (« je filtre par "Martin SARL" » puis « la liste affiche 1 enregistrement ») ; la relecture de la nouvelle version reste le garde-fou. | 2026-10-15 |
| A41 | **Validée par le porteur le 2026-10-15** — associer d'un clic remplace AUSSI la valeur dans le texte du cas (préconditions, étapes, résultat attendu) quand elle y est écrite, avec l'avant/après dans la même fenêtre : le cas et le test restent d'accord, une régénération garde la variable. Quand le cas n'écrit pas la valeur, la règle « le test technique reprend exactement les variables du cas » (E2) admet aussi les variables que le test actuel emploie déjà. Écartées : garder le cas tel quel ; bloquer la régénération. | 2026-10-15 |
| A42 | **Validée par le porteur le 2026-10-15** — quand une modification faite à la main fait que le cas cite une donnée de test (`{{client}}`) que son test technique n'emploie pas, la modification est enregistrée mais le test ne peut plus être approuvé ni exécuté tant que l'écart existe ; la fiche affiche « le cas cite {{client}}, le test ne l'emploie pas ». On règle en régénérant le test ou en corrigeant le cas. L'inverse (le test emploie une donnée que le cas ne cite pas) reste admis (A41). Seulement avec PT-02f allumé et pour un projet qui déclare des données de test. Écartées : refuser la modification ; prévenir seulement. | 2026-10-15 |
| A43 | **Validée par le porteur le 2026-10-16** — « L'IA peut agir sur cette application pendant la génération » est COCHÉ PAR DÉFAUT, pour les nouveaux projets et les projets existants : TestPilot vise des environnements de test, et l'agent doit pouvoir explorer et essayer pour générer et exécuter juste. La règle A21 est retirée : changer l'adresse de l'application ne décoche plus rien. Restent : la protection de la production (jamais d'action sur une production) et, pour une application web, l'adresse de remise à zéro, sans laquelle l'essai reste indisponible. Le banc d'agents fixe le réglage explicitement (éteint sauf `--bac-a-sable`) pour garder ses mesures comparables. | 2026-10-16 |
| A44 | **Validée par le porteur le 2026-10-16** — l'onglet « Valeurs attendues » est RETIRÉ (écriture des nombres du projet, unités ajoutées) : l'outil relève lui-même la façon dont l'application écrit ses nombres (exploration, essai) et la comparaison se comporte partout comme « Non déclarée » (deux écritures reconnues, un nombre ambigu jamais tranché, l'unité toujours vérifiée). Ce qui a été enregistré reste en base, inutilisé. Règle maintenue : ce que l'IA observe sert à connaître le FORMAT, jamais la VALEUR attendue, qui vient du cas validé. Un écran reviendra seulement si les valeurs calculées (PT-06) en ont besoin. | 2026-10-16 |
| A45 | **Validée par le porteur le 2026-10-16** (revue d'A43, bloquant) — la « protection de la production » n'agit que pour toute l'installation (`ODOO_ENV=prod`), jamais projet par projet. Pour un projet ODOO, l'IA n'écrit réellement dans l'application (soumission d'un formulaire pendant la génération ou la correction) que si le projet déclare AUSSI « instance de test » (onglet « État de départ ») — comme le web exige une adresse de remise à zéro. Une soumission dont le nettoyage n'est pas garanti (aucun modèle donné) est toujours refusée. La migration 67 ne recoche pas un projet web qui avait déclaré une remise à zéro et décoché l'autorisation (refus délibéré). | 2026-10-16 |
| A46 | **Validée par le porteur le 2026-10-16** (mesures M1 et ciblée) — la génération avec données de test est ALLUMÉE par défaut (`TESTPILOT_VARIABLES_DE_TEST`, `TESTPILOT_CAS_DIT_SES_DONNEES` : un `0` explicite les éteint) : sur les cas qui emploient des données, 9 tests justes sur 10 allumé contre 7 sur 10 éteint, zéro faux vert, second jeu prouvé 5 fois sur 5 là où le cas crée une donnée. La comparaison des montants avec unité (`TESTPILOT_STEP_NOMBRE`) reste ÉTEINTE : aucun jeu concluant (génération qui n'aboutit pas sur « remise », mauvaise page sur « TVA ») ; à remesurer avec le bac à sable après AV-7. Le banc éteint un réglage par un `0` explicite. | 2026-10-16 |
| A47 | **Validée par le porteur le 2026-10-16** (revue d'A45, bloquant) — la déclaration « Instance de test » vaut pour UNE application : si le connecteur, l'adresse ou la base du projet changent, elle se DÉCOCHE (même si l'enregistrement la renvoie cochée) et doit être redéclarée. « L'IA peut agir » reste cochée (A43 inchangée). Comme le web, dont la remise à zéro déclarée ne vaut plus pour une autre adresse. | 2026-10-16 |
| A48 | **Validée par le porteur le 2026-10-16** (PT-04a) — un environnement a une NATURE obligatoire, « Test » ou « Production », choisie à sa création sans valeur par défaut. Un environnement « Production » est affiché mais jamais joué : le lancement est refusé, et le harnais le refuse aussi de son côté (`ODOO_ENV=prod` posé pour son exécution). L'environnement par défaut des projets existants est « Test » (ce qu'il est aujourd'hui de fait). La protection de toute l'installation (`ODOO_ENV=prod`) reste inchangée. | 2026-10-16 |
| A49 | **Validée par le porteur le 2026-10-16** (PT-04a) — un environnement porte un nom, une adresse, une version, une base (Odoo) et l'adresse de son oracle. Les comptes de l'onglet « Comptes » servent sur tous les environnements ; des identifiants propres à un environnement viendront avec le choix du compte au lancement (E5, PT-04b). | 2026-10-16 |
| A50 | **Validée par le porteur le 2026-10-16** (PT-04a) — l'exploration, la génération, ses essais et la remise à zéro restent sur l'environnement PAR DÉFAUT, comme aujourd'hui. Les autres environnements servent seulement à rejouer des tests déjà écrits. | 2026-10-16 |
| A51 | **Validée par le porteur le 2026-10-16** (VH-08) — l'IA connaît la FORME des réponses de l'oracle (objet ou liste, clés, types ; jamais une valeur, jamais un nombre d'éléments) : relevée à l'exploration, et surtout relevée À LA FIN DE CHAQUE ESSAI sur le bac à sable, avant sa remise à zéro — à l'exploration, les listes de l'application sont souvent vides et la forme de leurs éléments inconnue. Seules les requêtes GET sont appelées (lecture). Derrière l'interrupteur `TESTPILOT_FORME_ORACLE`, éteint jusqu'à la mesure M2. Avec : un test qui cite une requête d'oracle non déclarée est refusé à l'écriture. Revue du 2026-10-16 : après un essai, la
| A52 | **Validée par le porteur le 2026-10-16** (itérations, sur le modèle du « Data Table » de QTP/UFT montré par son tuteur) — un test lancé avec plusieurs lignes de données de test donne UNE exécution, avec UNE ITÉRATION par ligne et un résultat par itération ; le test est en échec si une itération échoue. Remplace la partie « une exécution par jeu, regroupées dans un plan » d'A28 ; les environnements restent une exécution chacun (PT-04a). | 2026-10-16 |
| A53 | **Validée par le porteur le 2026-10-16** — quand la spécification décrit des comportements différents selon une valeur (« moins de 18 ans : refusé »), l'IA PROPOSE les lignes et le résultat attendu de chacune, valeurs limites comprises ; une personne les relit et les valide, comme un cas. Une personne peut toujours les saisir ou les importer. Une valeur attendue reste déclarée par une personne : proposée par l'IA, elle ne compte qu'une fois validée. | 2026-10-16 |
| A54 | **Validée par le porteur le 2026-10-16** — le tableau des données de test se lit comme le Data Table et Excel : les variables en colonnes, UNE LIGNE par jeu de valeurs (une itération) ; le jeu « Par défaut » reste la première ligne (A27 inchangée : une case vide en reprend la valeur). | 2026-10-16 |
| A55 | **Validée par le porteur le 2026-10-16** — remplir une colonne avec des enregistrements qui existent dans l'application (« plusieurs clients déjà en base ») : lot SÉPARÉ, après les itérations, avec sa propre mesure. | 2026-10-16 |
| A56 | **Validée par le porteur le 2026-10-18** — les données de test sont FACULTATIVES au lancement : aucune ligne cochée, un test qui emploie une variable est joué avec les valeurs « Par défaut » (jamais bloqué faute de ligne ; une valeur absente du jeu « Par défaut » le bloque toujours, en la nommant). | 2026-10-18 |
| A57 | **Validée par le porteur le 2026-10-19** (après comparaison avec UFT, Azure DevOps, Xray, Katalon, Cucumber) — les données de test ont DEUX niveaux : le tableau du PROJET garde ce qui est partagé par plusieurs cas (client de référence, comptes…) ; chaque CAS peut avoir ses propres lignes (ses classes de valeurs et le résultat attendu de chacune), jouées en itérations quand on lance ce cas. L'essentiel (porteur) : jouer un test avec TOUTES les valeurs d'une variable, une itération par valeur. | 2026-10-19 |
| A58 | **Validée par le porteur le 2026-10-19** — ce que l'IA fait pour qu'aucune tâche manuelle piégeuse ne reste : (1) elle propose les lignes d'un cas, valeurs limites comprises, et le résultat attendu de chacune (A53, validées par une personne avec le cas) ; (2) elle reprend une donnée déjà dans le projet au lieu de la recopier ; (3) lancer un cas joue ses propres lignes, sans rien cocher (réduire à une ligne ou « de la ligne X à Y » reste possible) ; (4) une case vide d'une ligne du cas reprend la valeur du projet ; (5) elle signale les lignes d'un cas que la spécification a rendues fausses et propose les nouvelles. | 2026-10-19 |
| A59 | **Validée par le porteur le 2026-10-19** (revue IT-3a, bloquant) — un cas dont les lignes font varier une variable que son test n'emploie pas (valeur écrite en dur) ne se joue pas : bloqué en nommant la variable, « régénérez le test ». Sinon ses lignes fusionneraient en UNE itération jouée avec la valeur en dur, et l'écran annoncerait toutes les classes jouées. Même règle qu'A42 (écart cas/test). | 2026-10-19 |
| A60 | **Validée par le porteur le 2026-10-19** (IT-3c) — l'IA qui rédige les cas ne propose des lignes que pour des variables DÉJÀ déclarées dans le projet ; elle n'en crée aucune. Sans variable qui porte la valeur, elle ne propose aucune ligne. | 2026-10-19 |
| A61 | **Demandée par le porteur le 2026-10-20** — « après une génération, tout doit être bon et prêt à lancer » : l'écran « à relire » est l'exception, pas la règle. Tout contrôle qui mettrait un cas à relire ou le bloquerait au lancement est, autant que possible, appliqué PENDANT la génération (un refus que l'IA corrige avant de rendre la main), et un contrôle qui alerte à tort est corrigé. Premières applications : navigation web reconnue par le contrôle de preuve, test non rejouable ligne par ligne refusé à l'écriture. Indicateur à suivre dans les mesures : part des cas générés prêts à lancer sans relecture. | 2026-10-20 |
| A62 | **Décidée par le porteur le 2026-10-20** — ni après une génération ni après une régénération, un test ne doit rester « à relire » : la règle « une régénération impose une relecture humaine » (backlog 0.2) est SUPPRIMÉE ; une régénération suit le chemin d'une génération (approuvée si propre). La protection contre une vérification affaiblie passe par des contrôles appliqués pendant la génération (A61), jamais par une relecture systématique. | 2026-10-20 |
| A63 | **Décidée par le porteur le 2026-10-20** — si, malgré ses essais, l'IA n'arrive pas à écrire un test sans point de vigilance, le test est LIVRÉ MAIS BLOQUÉ au lancement, et la fiche du cas dit pourquoi ; jamais « à relire ». Construit le 2026-10-20 (étape 2 du plan unique) : raisons en français sur la fiche et dans la liste « Cas bloqués » ; contrôle de fin d'écriture derrière l'interrupteur `TESTPILOT_CONTROLE_FIN_ECRITURE` (éteint jusqu'à la mesure de l'étape 3). | 2026-10-20 |
| A64 | **Validée par le porteur le 2026-10-20** — un test qui arrive sur une page par un clic (menu, lien) peut employer un champ si une preuve d'écran de la génération l'a vu visible : preuve récente, de la même cible, jamais un schéma RPC. Vaut pour les applications web et pour Odoo. Pire cas : le champ manque sur la page atteinte, la saisie échoue (erreur technique), jamais un « conforme ». | 2026-10-20 |
| A65 | **Validée par le porteur le 2026-10-20** — exception à A62 : une régénération faite après un défaut FONCTIONNEL de l'application (non_conforme, donnée refusée), dont le nouveau test ne vérifie plus la même chose, n'est jamais approuvée d'office, même si le cas a été retouché entre-temps (sinon l'IA recopie la valeur fausse vue sur l'écran et le test passe au vert). Le signal suit les corrections automatiques ; seule une approbation humaine l'éteint. Aujourd'hui : point de vigilance « défaut ? » ; avec A63 (étape 2) : test livré bloqué, raison sur la fiche. | 2026-10-20 |
| A66 | **Validée par le porteur le 2026-10-20** — précise A65 pour la « donnée refusée » (l'application n'est pas en cause, c'est la donnée du test) : un test régénéré qui change SEULEMENT la donnée saisie est prêt à lancer ; s'il change ce qu'il vérifie (un « Alors », ou une colonne d'Exemples qu'un « Alors » cite), il porte l'avis comme après un « non conforme ». Une donnée que le métier validé cite (« 18 ans et plus » : la valeur 18) n'est pas « seulement une donnée » : la changer porte l'avis (revue, quatrième passe : une application qui refuse à tort le 18 exigé) ; par prudence, un nombre ou une date ne se change sans avis que si le cas n'en cite aucun (« 1 000 € » ne ressemble pas à « 1000 »), et seule la valeur saisie peut changer, jamais le champ visé. Limite acceptée : une application qui refuse à tort une donnée valide que le cas n'impose pas n'est pas signalée. Même revue : après un « non conforme », une donnée écrite en dur dans un « Quand » (17 → 16 ans) compte comme une vérification changée. | 2026-10-20 |
| A67 | **Validée par le porteur le 2026-10-20** — (étape 2, A63) l'état « bloqué » n'est PAS enregistré en base : il est recalculé à chaque affichage (version non approuvée + raisons tirées des points de vigilance). Ce qui autorise un lancement reste la seule approbation de la version et les écarts A42/A59 : un test ne se débloque jamais seul, seule une personne le débloque. Aucune migration. Condition : un calcul stable dans le temps (âge des preuves mesuré à l'écriture du test). | 2026-10-20 |
| A68 | **Validée par le porteur le 2026-10-20** — écran « Bloqué » à la place de « Relecture requise » sur la fiche du cas : « Bloqué — Ce test ne sera pas lancé. », la raison en une ligne, boutons « Débloquer » / « Rejeter » ; dans la liste : « Bloqué : <raison> ». Essai réel avec l'IA à la fin de l'étape 2 accepté (environ 1 $). | 2026-10-20 |
forme montrée est le CUMUL exploration ∪ essais ; les clés d'un objet viennent de l'exploration seule (un objet vide à
l'exploration puis rempli : « ses clés sont des données ») ; une clé vue seulement à l'essai n'est montrée que dans un
élément de liste et si elle a la syntaxe d'un nom de champ. Ce qu'un essai laisse encore deviner, ASSUMÉ : qu'un élément a
existé (la forme d'une liste devient connue) ; à l'inverse, une liste encore « vide, forme inconnue » ou un champ encore
« vide » après les essais disent qu'ils ne se sont jamais remplis ; une clé de donnée écrite comme un nom de champ
(snake_case) passerait. Aucun de ces cas ne donne une valeur attendue : elle vient toujours du cas validé. | 2026-10-16 |
| — | Précisions annoncées au porteur le 2026-10-13, sans objection : la **mise à la corbeille** d'une variable ou d'un jeu reste réservée à l'administrateur du projet (comme toute suppression de l'outil : lui seul restaure) ; le **nom d'une variable ne se modifie pas** (les tests la désignent par ce nom) ; un lancement **sans jeu choisi** joue le jeu « Par défaut » si le projet a des variables, et rien ne change pour un projet qui n'en a pas. | 2026-10-13 |

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
| Paramètres de test d'un projet, quatre onglets (« Valeurs attendues » retiré par A44) | `/admin/projects/:pid/parametres-de-test/:onglet` | administration (`InstanceAdminShell`) ; route ajoutée à `ROUTES_SANS_SHELL` |
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
4. fait — monnaie et écriture des nombres du projet (migration 62, onglet « Valeurs attendues »), règle A24 ; onglet retiré le 2026-10-16 (A44) ;
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

**Remplacé le 2026-10-15 par le §9 (génération et paramètres menés ensemble) pour tout ce qui reste.** Ordre d'origine : PT-00 → PT-01 → **PT-03** → PT-02 → PT-04 → PT-05 → PT-06 → PT-07 (ordre A7, modifié sur un point le 2026-10-13 :
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

## 9. Génération et paramètres de test, menés ensemble (2026-10-15)

Demande du porteur, 2026-10-15 : les deux chantiers vont de pair. Les paramètres de test ajoutés doivent être compris et
employés par l'IA, qui doit savoir à quels cas chacun s'applique ; la génération doit rester juste ; le but est un outil qui
soit un atout en entreprise, pas une contrainte. Ce chapitre remplace l'ordre du §5 pour tout ce qui reste à faire. Il reprend
les lots restants du plan `PLAN-VERDICT-HONNETE-ZERO-ERREUR-2026-10.md` (VH-02, VH-06, VH-08 à VH-10), qui n'est donc plus
mené à part.

### 9.1 Où en est la génération (mesuré, banc d'agents, 2026-10-11, `base-7`)

- 0 faux vert sur 131 jeux concluants (base-2 à base-7) ; 0 faux rouge en base-7 ;
- 23 essais sur 30 justes partout, 6 cas sur 10 justes aux trois essais — un test généré sur quatre n'est pas encore juste ;
- causes restantes : l'agent ne connaît pas la FORME de la réponse de l'oracle (4 des 7 essais non justes), une génération
  sur dix n'aboutit pas ;
- limite : c'est notre application ; rien n'est mesuré sur une application jamais vue.

### 9.2 Le principe (A39, validée le 2026-10-15)

**Le parcours d'aujourd'hui ne change pas** (porteur, 2026-10-15) : une spécification devient des cas, les cas deviennent des
tests techniques, on lance une exécution — exactement comme maintenant, pour tout projet qui ne déclare aucun paramètre de
test. Les paramètres de test sont une **option en plus** : ce qui suit ne s'applique qu'à un projet qui en a déclaré, et la
génération les prend alors en compte en plus de ce qu'elle fait déjà. Un projet sans paramètre reçoit la même génération,
octet pour octet (garde : test d'identité, interrupteurs éteints).

1. **Le cas fait foi, aussi pour les données** (seulement si le projet a déclaré des données de test). Quand une spécification devient des cas, l'IA reçoit les variables du projet
   (noms et descriptions, jamais les valeurs) et écrit dans la description du cas `{{client}}` là où le cas emploie cette
   donnée. La personne qui relit le cas voit et valide ce lien — en clair, sans lire de script.
2. **Le test technique suit le cas, contrôlé sans IA.** Chaque variable du cas doit apparaître dans le test technique, et
   aucune autre : sinon l'écriture est refusée et l'agent corrige. Le lien ne dépend donc jamais d'une supposition de l'IA.
3. **Les tests déjà écrits s'associent d'un clic, sans IA.** L'outil repère dans le test les valeurs identiques à celles du
   jeu « Par défaut » (« Martin SARL ») et propose `{{client}}` ; la personne coche, voit l'aperçu, valide (nouvelle version
   à relire, comme toute modification).
4. **Les paramètres servent la génération.** Des valeurs déclarées par une personne remplacent les valeurs que l'IA invente
   aujourd'hui (client inexistant, format refusé) ; la vérification des nombres avec leur unité remplace des comparaisons de
   texte fragiles ; la forme de réponse de l'oracle et la cartographie par compte lui montrent ce qu'elle devait deviner.
5. **Rien ne s'allume sans mesure.** Chaque nouveauté qui change ce que l'IA reçoit reste derrière un interrupteur éteint
   jusqu'à une campagne du banc : zéro faux vert, au moins autant de tests justes, coût par cas sous 1 €.

### 9.3 Les étapes

| Étape | Paramètres de test | Génération | Mesure | Coût IA |
|---|---|---|---|---|
| E1 — Finir et corriger | PT-02d enregistré ; monnaie du projet retirée (A38) ; « associer d'un clic » (PT-02e, sans IA) | — | suites complètes | 0 |
| E2 — Le cas dit ses données | PT-02f : l'IA propose `{{nom}}` dans la description des cas, la personne valide ; contrôle « le technique reprend exactement les variables du cas » | même lot : la génération du technique lit les variables du cas validé | banc : cas qui emploient des données | 0 (code) |
| E3 — Mesure M1 (**faite le 2026-10-16**, 7,91 $) | PT-02d et PT-02f ALLUMÉS (A46) ; PT-03 reste éteint | — | M1 : 10 cas × 2, éteint 14/20, allumé 12/20, 0 faux vert ; ciblée : données 6/6 allumé contre 4/6 éteint, montants non concluants | ≈ 8 $ |
| E4 — Ce que l'IA devait deviner | PT-04a : plusieurs environnements (protection de la production évaluée pour chacun) — sans IA | VH-08 : l'agent voit la FORME de la réponse de chaque requête d'oracle (objet ou liste, clés, types, un exemple aux valeurs masquées — relevée par un appel en lecture à l'exploration) ; restes VH-02 et VH-06 (route inconnue = refus) | campagne M2 | ≈ 6 $ |
| E5 — Comptes et état de départ pour tous | PT-04b : compte choisi au lancement ; PT-04d : remise à zéro pour toutes les applications | l'agent reçoit la cartographie du compte visé ; l'essai « exécuter puis écrire » devient possible hors connecteur web | campagne M3 (dont Odoo) | ≈ 8 $ |
| E6 — Réparer sans tricher | — | VH-09 : réparation de l'adressage seulement, un test réparé doit refaire échouer les défauts qu'il détectait | régressions injectées | faible |
| E7 — Réutiliser, calculer | PT-05 bibliothèque commune ; PT-06 valeur attendue calculée | l'agent emploie « vaut le résultat calculé » sur des spécifications sans résultat écrit | campagne M4 (erreurs de calcul introduites exprès) | ≈ 8 $ |
| E8 — L'IA ne part plus à l'aveugle (§9.6) | AV-4 : l'état de départ de l'application, déclaré dans les paramètres de test | AV-1 à AV-3, AV-5 à AV-9 : tout ce que l'exploration a déjà relevé est MONTRÉ à l'IA avant qu'elle écrive | campagne M5 appariée | ≈ 8 $ |
| E9 — La preuve | tous les paramètres allumés qui ont passé leur mesure | VH-10 : application jamais vue (jeu mis de côté), Odoo réel | campagne de clôture | ≈ 15 $ |
| E10 — Clôture | PT-07 : ancien écran et interrupteurs retirés, guide utilisateur | — | suites complètes, vérification à l'écran | 0 |

Total des mesures avec IA : **≈ 53 $**, chaque campagne annoncée et validée par le porteur avant d'être lancée, avec un
plafond bloquant. Les étapes sans IA (E1, le code de E2, PT-04a, PT-05) avancent sans attendre les campagnes.

**À mesurer en E3 (limites connues de PT-02f, revue du 2026-10-15)** : le contrôle « le test reprend les variables du cas »
vérifie leur PRÉSENCE dans le test, pas qu'elles servent — un step écrit à la main qui ne fait rien de `{{client}}` passerait ;
la campagne compte donc les variables placées dans un step de la bibliothèque qui consomme son paramètre. Une variable
impossible à placer fait boucler l'agent jusqu'à sa limite d'itérations ou de coût (0,50 $) : compté dans le coût par cas.
PT-02f n'agit qu'avec PT-02d allumé.
Le banc d'agents crée ses cas sans IA (spécifications fixes) : avec `--donnees-de-test` et PT-02f allumé, leur texte cite
`{{nom_client}}` par le remplacement de l'association d'un clic. La campagne M1 mesure donc le test TECHNIQUE ; ce que l'IA
qui rédige les cas fait des variables (proposées, oubliées, inventées) et son coût se mesurent à part, par une génération
complète depuis une spécification.
Second jeu (porteur, 2026-10-16) : chaque test généré qui écrit une variable, et dont le jeu sur la saine est juste, est rejoué sans IA sur la saine avec un second jeu (« Martin Lefèvre SA », « Paris »). La variable est PROUVÉE seulement si le jeu est conforme ET si l'état du serveur montre les valeurs du second jeu sans celles du premier ; compté à part de pass@k et des faux verts.

### 9.4 Ce que l'entreprise y gagne, étape par étape

| Après | Ce qu'un utilisateur peut faire |
|---|---|
| E1 | Relier ses tests existants aux données de test d'un clic, sans toucher au script |
| E3 | Écrire « le client » dans un cas : l'outil propose la variable, et le test généré la joue pour chaque jeu choisi |
| E4 | Jouer une campagne sur la recette et sur la préproduction ; des tests générés plus souvent justes du premier coup |
| E5 | Jouer un même test sous plusieurs rôles ; préparer l'application avant chaque test, quelle que soit l'application |
| E7 | Vérifier un montant sans l'avoir recopié de la spécification ; reprendre les réglages d'un autre projet |
| E8 | Des tests techniques justes du premier coup plus souvent : l'IA écrit avec ce qu'on a observé de l'application, pas avec ce qu'elle suppose |
| E9 | Des chiffres mesurés sur une application jamais vue, publiables à un client |

### 9.5 Décisions à obtenir

- **A39** : validée le 2026-10-15.
- **A40** (droits de l'association d'un clic) : validée le 2026-10-15 — ouverte à tous, sans condition.
- **A41** (l'association d'un clic touche aussi le texte du cas) : validée le 2026-10-15.
- **A42** (écart entre le cas et son test après une modification à la main : exécution bloquée) : validée le 2026-10-15.
- **Budget de M1** (≈ 8 $, plafond 9 $) : accordé le 2026-10-15 ; le montant est rappelé au porteur juste avant le départ de la campagne.
- Restent ouvertes, à leur étape : V16 (exploration par compte, E5), V5 et V6 (bibliothèque commune, E7), V8 et V10 (valeur
  calculée, E7).
- **V-AV1, V-AV2, V-AV3** (§9.6, E8) : validées le 2026-10-16.
- **A43** (« L'IA peut agir » coché par défaut, A21 retirée) et **A44** (onglet « Valeurs attendues » retiré) : validées le 2026-10-16.
- **A45** (Odoo : « instance de test » en plus) et **A46** (données de test allumées, montants avec unité éteints) : validées le 2026-10-16.
- **A47** (« Instance de test » décochée quand l'application change) : validée le 2026-10-16.
- **A48** (nature Test / Production obligatoire), **A49** (mêmes comptes partout, oracle par environnement) et **A50** (génération sur l'environnement par défaut) : validées le 2026-10-16 pour PT-04a.
- **A51** (forme des réponses de l'oracle lue à l'exploration et à la fin de chaque essai) : validée le 2026-10-16.
- **A52** à **A55** (itérations dans une exécution, lignes proposées par l'IA et validées, tableau en lignes, remplissage depuis l'application à part) : validées le 2026-10-16.
- **A56** (données de test facultatives au lancement : aucune ligne cochée = valeurs « Par défaut ») : validée le 2026-10-18.
- **A57** (deux niveaux : projet partagé, lignes propres au cas), **A58** (ce que l'IA fait) et **A59** (test qui n'emploie pas les variables des lignes de son cas : bloqué) : validées le 2026-10-19.
- **A60** (lignes proposées par l'IA : variables déjà déclarées seulement) : validée le 2026-10-19.

### 9.6 L'IA ne part plus à l'aveugle (demande du porteur, 2026-10-16)

**Le but.** Un test technique juste du PREMIER coup : exécutable sans rejeu, sans réparation, sans qu'une personne ait à
relire le script. Mesuré au banc : un test est « juste du premier coup » s'il sort conforme sur l'application saine et
non conforme sous chaque défaut, sans réparation. Aujourd'hui (`base-7`) : 23 essais sur 30. **Objectif (V-AV3, validé par le porteur le 2026-10-16) :
27 sur 30, toujours zéro faux vert.**

**La vision du porteur (2026-10-16), qui commande ce chapitre.** TOUT le parcours de l'utilisateur sert à recueillir ce
dont la génération a besoin : (1) il crée un projet et y met les identifiants ; (2) la CONNEXION est enregistrée une fois et
rejouée autant de fois qu'il le faut — un test technique ne la réécrit jamais, elle est déjà validée ; (3) l'EXPLORATION
relève les pages, champs, boutons et liens de l'application — elle doit servir à la génération ; (4) les PARAMÈTRES DE TEST,
s'il en a déclaré, disent ce qu'il veut voir employé — à la génération, à nous de comprendre exactement ce qu'il veut ; à
l'exécution, on lui demande s'il faut les utiliser (déjà en place). L'outil relève tout seul ce qui n'est pas fourni. L'IA
n'est pas une source de vérité, mais avec les bonnes informations elle écrit des tests propres. **Ce qui manque au moment
de la génération est RELEVÉ, jamais inventé** (porteur, 2026-10-16) : l'agent doit disposer, pour chaque connecteur, des
outils qui lui permettent d'aller chercher lui-même le détail qui lui manque, et ce qu'il n'a pas observé reste refusé à
l'écriture (gardes existantes). Un test juste du premier coup se rejoue à chaque nouvelle
fonctionnalité pour vérifier qu'il n'y a pas de régression ; ses statuts (passé, échoué, bloqué) disent la vérité sur
l'application.

**Le principe.** L'exploration de l'application mesure déjà, page par page, presque tout ce dont l'IA a besoin ; aujourd'hui
une grande partie ne sert qu'à REFUSER après coup ce qu'elle a inventé. On le lui MONTRE avant qu'elle écrive. Une règle ne
change pas : ce qui est OBSERVÉ dans l'application sert à savoir OÙ aller et QUOI toucher ; ce qu'un test VÉRIFIE (message de
résultat, montant, valeur attendue) vient toujours du cas validé par une personne — jamais de ce que l'application affiche
aujourd'hui, sinon un test recopierait un défaut et le déclarerait conforme (D26, condition 4).

**L'inventaire (2026-10-16).** Ce que l'IA reçoit aujourd'hui, ce qu'elle peut aller chercher, et ce qui lui manque, croisé
avec les causes d'échec mesurées de `base-1` à `base-7`. Les manques, et ce qui permet de les combler :

| Lot | Manque | Mesuré | Déjà là, réutilisable | À construire |
|---|---|---|---|---|
| VH-08 (E4) | La FORME de la réponse de l'oracle : l'agent n'en connaît que le nom | 4 des 7 échecs de `base-7` | requêtes déclarées dans le projet | un appel en lecture de chaque requête à l'exploration ; la structure (objet ou liste, clés, types) et un exemple aux valeurs masquées dans le prompt |
| AV-1 | Un projet web est annoncé « Type de système : odoo » ; l'analyse de la spécification lui suggère des modèles Odoo ; le prompt système renvoie à une section « Connecteur actif » vide par défaut | non mesuré, erreur franche (vérifiée dans le code) | le type de connecteur du projet | le passer à l'analyse ; toujours fournir la section du connecteur (ou retirer ses renvois) |
| AV-2 | Le NOM EXACT des champs (nom technique et libellé visible, type, obligatoire), boutons et liens de chaque page : relevés par l'exploration, ils ne servent qu'au refus `LITTERAL_NON_OBSERVE` | 8 à 12 refus par campagne (tours et coût en plus) ; `base-3` : champs inventés ×4 | la cartographie du projet (`data/domain/projet-<id>.json` : champs, actions, liens par page) ; les formats et contraintes observés | une section « pages observées » : le détail complet des pages que le cas vise, un index court des autres ; les contraintes de TOUS les champs de ces pages, pas seulement des obligatoires |
| AV-3 | Le texte affiché non cliquable : titres, en-têtes de tableau, libellé à côté d'une valeur (« Numéro de commande ») | `base-6`, `base-7` : 2 échecs, 1 faux rouge | — | l'exploration relève ces libellés de STRUCTURE (titres, en-têtes, couples libellé–valeur) ; les messages de RÉSULTAT restent pris dans le cas (règle ci-dessus) |
| AV-4 | L'état de départ : quelles données existent déjà (clients, produits, commandes) | indirect : enregistrement existant réutilisé (F26) | la forme de l'oracle (VH-08) ; le nombre de lignes des listes vues à l'exploration | **V-AV1 (porteur, 2026-10-16)** : si l'utilisateur a décrit l'état de départ dans les paramètres de test, il est employé ; sinon l'outil le RELÈVE TOUT SEUL (exploration : listes et nombre de lignes ; oracle : forme et contenu de l'état) |
| AV-5 | La langue de l'interface | menu cherché en anglais sur une interface française (G7) ; message deviné (cas 97) | la langue déclarée du projet (`browser_locale`) | une ligne dans le prompt |
| AV-6 | La connexion est DÉJÀ faite (connexion enregistrée, rejouée par le harnais) : le test ne la réécrit pas. La consigne existe (prompt système, web : « n'écris JAMAIS de step de connexion ») mais une consigne ne suffit pas ; règles web (compte « principal », pas d'appel direct au serveur, page d'arrivée) | `base-4` : 2 tests bloqués sur un compte inventé | connexion enregistrée (`auth_strategie`, une fois par run) ; règles écrites derrière `TESTPILOT_REGLES_CONNECTEUR` (éteint) | une GARDE à l'écriture, sans IA : un test dont le cas ne porte pas sur la connexion ne peut pas saisir d'identifiants ni ouvrir la page de connexion ; mesurer les règles en M5 ; lister les attributs `context.*` du harnais (F20 : 1 sur 15) |
| AV-7 | Des générations qui n'aboutissent pas | 5 sur 5 sur le MÊME cas (`panier_remise_arrondi`) en `base-5`, `base-6`, `base-7` : pas un hasard | les rapports et traces des campagnes | instruire la cause sur les traces, corriger, ajouter le cas au contrôle |
| AV-8 | L'IA qui rédige les cas ne voit rien de l'application : elle écrit les étapes avec d'autres mots que ceux des écrans | non mesuré (le banc ne mesure pas cette passe) | la cartographie (pages, menus, libellés des boutons) | **V-AV2 (porteur, 2026-10-16)** : oui — elle emploie EXACTEMENT les termes des écrans (« Nouveau client », « Enregistrer »), relevés par l'exploration ; les cas restent écrits pour des personnes |
| AV-9 | Des outils de RELEVÉ incomplets selon le connecteur : en web, l'agent ne peut pas consulter les données (`inspect_schema` et `query_data` non implémentés) ni soumettre un formulaire pour en voir la réponse (`attempt_form_submission` non implémenté, alors que D36 le prévoyait) — il ne peut donc que supposer ou s'arrêter | non mesuré séparément (le banc coupe aussi ces outils en mode qualification) | l'oracle HTTP du projet (lecture de l'état) ; l'essai en bac à sable (VH-07) ; l'implémentation Odoo de ces outils | en web : la consultation des données par l'oracle déclaré ; la soumission d'essai dans le bac à sable (D36), le message rapporté servant à ÉCRIRE, jamais à vérifier ; chaque outil disponible dit clairement à l'agent ce qu'il peut relever |
| PT-04b (E5) | La cartographie du compte visé | non mesuré (un seul compte au banc) | déjà prévu | — |
| PT-06 (E7) | Les montants calculés attendus | non mesuré | déjà prévu | — |

**Les biais du banc à corriger dans la mesure M5** : le mode qualification prive l'agent de `query_data`, `attempt_login` et
`attempt_form_submission`, et le banc ne fournit pas les routes visées (la section des champs requis n'y apparaît jamais) ;
M5 mesure l'agent dans les conditions de la production, et compte à part la passe qui rédige les cas (AV-8).

**L'ordre.** AV-1 (une erreur, petite) ; AV-2 et AV-3 (le plus gros apport attendu, avec VH-08 déjà en E4) ; AV-5 ; AV-4 ;
AV-9 ; AV-6 ; AV-7 ; AV-8. Chaque lot derrière un interrupteur éteint, relu, testé ; un projet sans
cartographie reçoit le prompt d'avant, octet pour octet. Puis la mesure M5, appariée éteint / allumé (≈ 8 $, annoncée avant),
qui décide de l'allumage avec la même règle que M1 : zéro faux vert, au moins autant de tests justes du premier coup, coût
par cas sous 1 €.

**Décisions pour E8 : toutes validées par le porteur le 2026-10-16** — V-AV1 (état de départ : celui de l'utilisateur s'il l'a
fourni, sinon relevé par l'outil), V-AV2 (la rédaction des cas emploie exactement les termes des écrans), V-AV3 (27 tests
justes du premier coup sur 30, zéro faux vert).

### 9.7 Itérations : un test, une ligne de données par itération (demande du porteur, 2026-10-16)

**Le besoin.** Le « Data Table » de QTP/UFT (montré par le tuteur du porteur) : un même test est rejoué une fois par ligne
d'un tableau, chaque ligne portant ses valeurs ET son résultat attendu. Exemple : `{{age}}` = 5, 10, 18 et
`{{resultat_attendu}}` = « Accès refusé… », « Accès refusé… », « Bienvenue ». Un seul test, trois itérations ; si l'application
laisse entrer un enfant de 5 ans, seule l'itération 1 échoue. Décisions A52 à A55.

**Ce qui existe déjà.** Variables et jeux de valeurs (un jeu = une ligne) ; une valeur attendue peut déjà être une variable,
déclarée par une personne ; au lancement, on coche les jeux à jouer.

**Les choix techniques (annoncés au porteur).**
- Les itérations d'un test sont les lignes cochées, réduites aux valeurs DE SES variables : deux lignes qui ne diffèrent que
  par une variable qu'il n'emploie pas ne font qu'une itération ; un test sans variable est joué une fois (A35 devient
  naturelle).
- Une exécution, un seul passage de Behave : la copie du test propre à l'exécution devient un « Plan du scénario » dont les
  « Exemples » sont les itérations (`{{age}}` → `<age>`) ; un `Contexte` qui emploie une variable est recopié en tête de chaque
  scénario. Chaque itération est un scénario avec son résultat ; le verdict de l'exécution est le pire des itérations (règles
  du verdict inchangées : une itération qui n'a rien prouvé n'est jamais conforme).
- Les valeurs restent figées au lancement (A29), pour TOUTES les lignes choisies.

**Les lots.**

| Lot | Contenu | IA | Mesure |
|---|---|---|---|
| IT-1 | Itérations dans une exécution : lancement (toutes les lignes, une seule, de la ligne X à Y), valeurs figées, copie en plan de scénario, résultat par itération à l'écran et dans le rapport ; planifications | non | suites, essais à l'écran |
| IT-2 | Le tableau en lignes (A54) : variables en colonnes, une ligne par jeu ; import et export Excel dans ce sens | non | essais à l'écran |
| IT-3 | L'IA qui rédige les cas propose les lignes et leur résultat attendu (valeurs limites comprises), validées par une personne avec le cas (A53) ; l'IA technique écrit un seul test qui emploie les variables du cas | oui, interrupteur | banc : un cas « classes de valeurs » ajouté à l'application d'essai, avec un défaut à la limite |
| IT-4 | Remplir une colonne depuis l'application (A55) | — | lot séparé |

**IT-3 découpé (A57, A58, 2026-10-19).** Priorité du porteur : jouer un test avec toutes les valeurs d'une variable.

| Lot | Contenu | IA | Mesure |
|---|---|---|---|
| IT-3a | Les lignes d'un cas : un petit tableau dans la fiche du cas (variables en colonnes, une ligne par valeur, résultat attendu compris) ; les colonnes sont des variables déclarées dans le projet (choix technique annoncé le 2026-10-19 : un nom est déclaré une fois ; ses valeurs sont dans le projet, dans un cas, ou les deux — la case vide d'un cas reprend la valeur du projet) ; lancer ce cas joue toutes ses lignes en itérations (réduire possible) | non | suites, essais à l'écran |
| IT-3b | L'IA technique écrit UN test qui emploie les variables du cas (variables propres au cas comprises) ; son essai sur le bac à sable joue la première ligne | oui (existant étendu) | banc |
| IT-3c | L'IA des cas propose les lignes et leur résultat attendu (valeurs limites), reprend les variables du projet, relecture et validation avec le cas | oui, interrupteur | banc : cas « classes de valeurs » avec un défaut à la limite |
| IT-3d | Lignes rendues fausses par une spécification modifiée : signalées, nouvelles lignes proposées | oui | essais |
| IT-3e | Mesure de bout en bout (budget annoncé avant) | oui | campagne |

Choix technique annoncé : des lignes du PROJET cochées au lancement ET des lignes du cas se combinent (chaque ligne du cas jouée sur chaque ligne du projet cochée), 50 itérations au plus ; par défaut seule « Par défaut » est cochée, donc un cas joue exactement ses lignes.

## 8. Suivi

| Lot | Statut | Date | PR | Rapport |
|---|---|---|---|---|
| PT-00 | terminé en local (plan, interrupteur, mesures de référence) ; fiches d'écran faites pour PT-01 seulement | 2026-10-13 | — | |
| PT-01a | terminé en local : écrit, relu, vérifié à l'écran ; suite du serveur identique à la référence (4 207 réussis, les 5 échecs connus) | 2026-10-13 | — | |
| PT-01b | terminé en local : écrit, relu (aucun bloquant, sept points corrigés), vérifié à l'écran ; règle A21 ajoutée ; suite du serveur de clôture : 4 219 réussis, les 5 échecs connus du poste | 2026-10-13 | — | |
| PT-02a à PT-02c | fait en local, relu, suites vertes : tableau (corbeille, droits, import et export Excel A37), lancement avec un ou plusieurs jeux (A28, A35), planifications (A36), valeurs figées au lancement et affichées dans le rapport, fiche d'un test (aperçu par jeu, bouton Variable). vérifié à l'écran sur une copie locale le 2026-10-14 (lancement, plan, planifications, rapport, fiche, import et export) | 2026-10-14 | — | |
| PT-02d | code fait en local, interrupteur `TESTPILOT_VARIABLES_DE_TEST` ÉTEINT, relu en trois passes : l'agent reçoit les noms (jamais les valeurs) ; à l'écriture, variable inconnue, mal écrite, mal placée, hors guillemets ou dans le code des steps refusée ; essai du bac à sable joué avec les valeurs « Par défaut » ; valeurs masquées dans ce qui revient à l'agent ; variables figées en réparation et en correction ; banc : option `--donnees-de-test`. Mesure M1 faite le 2026-10-16 (10 cas × 2, 0 faux vert) puis mesure ciblée (données 6/6 allumé contre 4/6 éteint) : **interrupteur ALLUMÉ par défaut (A46)**, un `0` l'éteint | 2026-10-16 | — | `docs/mesures/banc-agents-2026-10-16-m1-allume.md`, `docs/mesures/banc-agents-2026-10-16-m1c-donnees.md` |
| PT-02e (E1) | fait en local, relu en six passes, vérifié à l'écran : associer d'un clic un test déjà écrit (tout ou rien par variable, seulement les paramètres qui portent une donnée, A40 ouvert à tous, A41 le texte du cas aussi) ; correctif : page figée après la fermeture d'une fenêtre | 2026-10-15 | — | |
| PT-02f (E2) | code fait en local, interrupteur `TESTPILOT_CAS_DIT_SES_DONNEES` **ALLUMÉ par défaut depuis A46** (n'agit qu'avec PT-02d), relu en quatre passes : l'IA des cas reçoit les noms des variables ; variable inconnue, mal écrite ou dans le titre refusée à la validation et à l'édition ; le test technique reprend exactement les variables du cas (A39) ; écart cas/test après une modification à la main : exécution bloquée (A42) ; banc prêt pour M1 | 2026-10-15 | — | |
| PT-03 | terminé en local, interrupteur ÉTEINT : comparaison avec unité, règle A24, écriture des nombres, unités ajoutées (A25) ; monnaie du projet retirée le 2026-10-15 (A38), relus et vérifiés à l'écran ; mesure sans IA : 8 jeux sur 8 ; mesure avec l'IA faite le 2026-10-16 : non concluante (génération qui n'aboutit pas, mauvaise page sans bac à sable) — l'interrupteur reste ÉTEINT (A46), à remesurer avec le bac à sable après AV-7 ; onglet « Valeurs attendues » retiré (A44) | 2026-10-16 | — | `docs/mesures/banc-agents-2026-10-13-pt03-step-nombre-sans-ia-methode.md` |
| PT-04a | code fait en local (branche `lot-pt04a-environnements`), décisions A48 à A50 : environnements ajoutés (nature Test/Production obligatoire, production jamais jouée), une exécution par jeu ET par environnement, valeurs figées au lancement, oracle propre à chaque environnement, génération et réparation sur le défaut seulement ; relecture et vérification à l'écran en cours | 2026-10-16 | — | |
| VH-08 | code fait en local (branche `lot-vh08-forme-oracle`), relu en deux passes, suites vertes ; interrupteur `TESTPILOT_FORME_ORACLE` ÉTEINT. **Mesure M2 (2026-10-16, 6,18 $)** : 0 faux vert des deux côtés, mais justes du premier coup 6/10 allumé contre 8/10 éteint et 7 générations qui n'aboutissent pas contre 3 (dont `connexion_refusee` 2/2, sans oracle : l'IA s'arrête d'elle-même au 9e tour sans écrire le test) — **règle non tenue, reste éteint** ; **Rejeu (2026-10-17, 0,37 $, conversation gardée)** de `connexion_refusee` et `panier_total_tva` allumé : 2/2 justes, 0 faux vert, les deux défauts vus — l'abandon ne se reproduit pas (variabilité sur un petit échantillon) ; mais le cumul entier de la forme revenait après chaque essai (6 fois sur le panier) → corrigé : seul ce qu'un essai vient d'apprendre est redit (`forme_oracle.nouveautes`). Reste éteint ; à remesurer sur un échantillon plus grand (≈ 9-10 $, accord du porteur attendu) | 2026-10-17 | — | `docs/mesures/banc-agents-2026-10-16-m2-eteint.md`, `…-m2-allume.md`, `…-m2-diag.md` |
| IT-1 et IT-2 (A52, A54) | code fait en local (branche `lot-pt02g-iterations`), relu en deux passes (trois bloquants corrigés : variable écrite autrement restée littérale, variable dans une cellule d'exemples, barre oblique doublée), suites vertes : une exécution, une itération par ligne, rapport par itération, tableau et Excel en lignes. **2026-10-18** : A56 (aucune ligne cochée = « Par défaut »), « de la ligne X à Y » et numéro de ligne dans le tableau ; résultat de chaque itération sur l'écran de l'exécution et dans le rapport (chaque « Exemples » porte `@tp_iteration_<k>` ; le serveur en tire, AVANT l'exécution et sur le texte qu'il a écrit, la table « ligne → itérations », puis rattache chaque résultat par sa ligne, que Behave fige au début du scénario — jamais par le nom ni par les étiquettes du JSON, qu'un step peut réécrire (revue, deux passes) ; migration 71 `scenario_result.iterations`). **Reste** : vérification à l'écran par le porteur | 2026-10-18 | — | |
| IT-3 (A53, A57 à A59) | découpé le 2026-10-19 en IT-3a à IT-3e (§9.7). **IT-3a fait en local**, relu en deux passes (bloquant corrigé : un test qui écrit en dur la valeur que les lignes du cas font varier jouait une seule itération en annonçant toutes les classes → bloqué, A59) : lignes propres au cas dans sa fiche, jouées en itérations (toutes ou la première), figées au lancement, combinées aux lignes du projet cochées, migration 72 ; vrai Behave : seule la valeur limite mal traitée échoue. **IT-3b fait en local**, relu en deux passes : l'IA technique apprend que le cas est joué une fois par ligne (des noms seulement), les variables des lignes sont requises dans le test (même PT-02f éteint), l'essai joue la première ligne (relue au moment de jouer, jamais transportée dans le métier) ; point de vigilance « même résultat attendu pour toutes les lignes » (aucun « Alors » ne vérifie une variable des lignes sans la saisir ailleurs) — retire l'approbation automatique, ne déclenche aucune correction par l'IA. **IT-3c fait en local**, relu en trois passes, interrupteur `TESTPILOT_LIGNES_PROPOSEES` ÉTEINT : l'IA des cas propose les lignes (classes, valeurs limites, résultat attendu) pour les seules variables déclarées (A60) ; nettoyage sans rien inventer (une ligne amputée, incomplète ou hors de l'ensemble de variables majoritaire est écartée en entier) ; relecture et correction dans l'écran des cas proposés (« N lignes proposées » visible replié) ; validées, elles deviennent les lignes du cas avant ses points de vigilance ; une erreur sur les lignes n'arrête que ce cas. **Reste** : vérification à l'écran par le porteur ; IT-3d, IT-3e (mesure ; dire que les scripts d'essai valident les lignes proposées sans relecture) | 2026-10-19 | | |
| PT-04b à PT-04d | à faire | | | |
| PT-05 | à faire | | | |
| PT-06a à PT-06d | à faire | | | |
| PT-07 | à faire | | | |
