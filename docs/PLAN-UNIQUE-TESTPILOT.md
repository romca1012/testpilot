# TestPilot — le plan unique

*Version du 2026-10-20. Remplace les sept plans précédents (annexe B), qui deviennent des archives.*

**Tes deux priorités, dans cet ordre de valeur :**
1. **Finir proprement les paramètres de test** — les six familles, utilisables et sûres.
2. **Une génération juste du premier coup** — un test prêt à lancer, qui donne un bon verdict, sans relecture.

Tout le reste (Odoo au-delà du portail, réparation, recette complète du produit) vient **après**, en partie C.

---

## 1. Pourquoi un seul plan

TestPilot est une seule application, pilotée jusqu'ici par sept plans successifs, chacun avec sa numérotation (lots
01-12, Q1-Q5, VH-01 à VH-10, CV-01 à CV-07, PT-00 à PT-07, IT-1 à IT-4, AV-1 à AV-9, E1 à E10). À partir d'aujourd'hui :
**un seul plan, numéroté 1 à 10** dans l'ordre où on le fait. Les anciens codes ne sont qu'en annexe A.

## 2. Les règles qui ne bougent pas

1. Un faux « Passed » est le pire défaut : rien n'est livré qui pourrait en produire un.
2. Le texte écrit par l'IA n'est jamais une preuve : le verdict s'appuie sur ce que l'application a réellement fait.
3. Une génération est prête à lancer (A61, A62, A63) : pas de « à relire » ; ce qui ne va pas est corrigé par l'IA
   pendant qu'elle écrit, sinon le test est livré **bloqué** avec la raison.
4. Rien n'est spécifique à un client dans le socle.
5. Aucune dépense d'IA sans ton accord ; chaque mesure annonce son budget.
6. Aucun push avant la fin du chantier (ta règle du 2026-10-13), sauf si tu décides d'une mise en ligne intermédiaire.

---

## 3. Les paramètres de test, d'un seul coup d'œil

*Tout ce qu'on règle pour jouer un même test dans des conditions différentes, sans le réécrire (A1).*

| Famille | Fait (en local) | Reste | Étape |
|---|---|---|---|
| **1. Configurations** (où) | Page « Paramètres de test » ; environnements Test / Production ; Chromium | — (Firefox : hors plan) | 10 |
| **2. Comptes et rôles** (avec qui) | Onglet Comptes, plusieurs comptes | Compte choisi au lancement ; exploration par compte (V16) | 4 |
| **3. Données de test** (avec quelles valeurs) | Variables ; tableau en lignes ; itérations ; « de la ligne X à Y » ; lignes propres à un cas ; l'IA technique les emploie ; l'IA des cas les propose (éteint) ; Excel | Finir et sécuriser ; vrais clients de l'application ; lignes devenues fausses | 1, 6 |
| **4. État de départ** | Onglet ; remise à zéro du bac à sable web | Remise à zéro pour toutes les applications ; état de départ montré à l'IA | 4, 5 |
| **5. Valeurs attendues** (ce qu'on vérifie) | Valeurs avec unité (éteint) ; résultat attendu par ligne | Valeur attendue calculée | 7 |
| **6. Réglages d'exécution** | Campagne stricte ; sans repli par l'IA (en ligne) | — | — |

Niveaux : test ✓, campagne ✓, projet ✓, **bibliothèque commune** à faire (étape 7).

---

## 4. Le plan

### PARTIE A — Socle : finir l'en-cours et rendre la génération prête à lancer

*Pourquoi d'abord : chaque paramètre de test produit des tests générés. S'ils finissent « à relire » ou « bloqués » à
tort, aucun paramètre n'est vraiment utilisable. Ces deux étapes servent tes deux priorités à la fois.*

#### Étape 1 — Finir l'en-cours (paramètres de test : données et itérations)
- Corriger le point bloquant trouvé par la relecture : une régénération après un vrai défaut de l'application ne doit
  jamais recopier la mauvaise valeur et passer au vert → dans ce cas précis, test **bloqué** avec la raison.
- Deux autres corrections de la relecture ; mettre l'invariant « relecture humaine » (CONTINUITE §4.3) en accord avec
  A61-A63.
- Committer ; redémarrer l'instance d'essai.
- **De toi :** valider l'assouplissement « champ vu après un clic » (web et Odoo) ; tes essais avec
  `docs/GUIDE-ESSAI-LIGNES.md`.
- **1 jour — 0 $**
- **État : fait en local le 2026-10-20** (branche `lot-pt02g-iterations`, non poussé). Relu en six passes jusqu'à « aucun bloquant ». Décisions prises en route : A64 (champ vu après un clic), A65 (régénération après un défaut : jamais approuvée seule), A66 (après une donnée refusée, changer la seule donnée est permis). Écart : le cas A65 porte pour l'instant l'avis « défaut ? » ; il deviendra « bloqué » à l'étape 2.

#### Étape 2 — Génération prête à lancer (A61, A62, A63)
- Les points de vigilance vérifiés **pendant** l'écriture : l'IA corrige avant de finir.
- S'il en reste : test livré **bloqué** avec la raison (nouvel état à l'écran, en français).
- Corriger les 7 fausses alertes connues qui mettaient un cas « à relire » à tort (aucune preuve enregistrée, adresse
  avec un chemin, alerte qui apparaît 24 h après, page qui change après un clic, « Exemple: », cadre, connexion par
  compte nommé).
- Les anciennes règles de relecture (D23, D30, D31, valeur vue à l'essai) deviennent des blocages motivés.
- « Automatiser avec l'IA » testé de bout en bout.
- **De toi :** l'écran « bloqué » (maquette sobre d'abord).
- **3 à 4 jours — 0 $**
- **État : code fait en local le 2026-10-20** (branche `lot-etape2-bloque`, non poussé), relu en deux passes jusqu'à « aucun bloquant ». Décisions : A67 (« bloqué » recalculé, jamais enregistré), A68 (écran validé). Le contrôle de fin d'écriture est derrière `TESTPILOT_CONTROLE_FIN_ECRITURE`, **éteint** jusqu'à la mesure de l'étape 3 (règle des interrupteurs). Écarts : le gel D30 à l'écriture de la correction n'est pas fait (même issue : bloqué) ; « de bout en bout » = essai réel avec l'IA accepté par le porteur (≈ 1 $), à faire.

#### Étape 3 — Mesure de contrôle n°1
- Sur le banc (11 cas, dont « Contrôle d'accès » avec un défaut à la limite) : part des cas **prêts à lancer**
  (cible ≥ 9/10), justes du premier coup, **0 faux vert**, lignes proposées par l'IA, coût par cas.
- Sert à décider : allumer « lignes proposées par l'IA » ; repérer les erreurs de génération qui restent, pour
  l'étape 5.
- **De toi :** accord sur le budget.
- **1 jour — environ 8 à 10 $**
- **État (2026-10-20) : préparée, campagnes EN ATTENTE DE CRÉDIT d'API** (décision du porteur : pas de dépense pour l'instant). Le banc mesure désormais, sans coût, la part des tests **prêts à lancer** (même calcul que le produit), leurs raisons de blocage, le relevé du contrôle de fin d'écriture et l'état des interrupteurs (branche `lot-etape3-mesure`). À lancer dès que le crédit le permet, dans cet ordre :
  1. campagne « contrôle éteint » : 11 cas × 2, plafond 4,5 $ (`lanceurs/campagne_banc.py eteint 4.5`) ;
  2. campagne « contrôle allumé » : 11 cas × 2, plafond 5,5 $ (`campagne_banc.py allume 5.5`) ;
  3. essai réel de l'étape 2 par le porteur sur l'instance d'essai (≈ 1 $).
  Écart : les lignes proposées par l'IA ne sont pas mesurables sur le banc (ses cas viennent des specs, sans l'IA des cas) — à outiller à l'étape 6. Tant que ces mesures manquent, le contrôle de fin d'écriture reste éteint.

### PARTIE B — Tes deux priorités, menées ensemble

*Ordre choisi : ce qui donne à l'IA de meilleures conditions (comptes, remise à zéro, ce qu'elle sait de l'application)
avant ce qui ajoute des fonctions (vrais clients, valeurs calculées).*

#### Étape 4 — Comptes au lancement et remise à zéro partout (paramètres : familles 2 et 4)
- Choisir avec quel compte (rôle) un test est joué ; l'IA écrit le test en connaissant les écrans de ce compte.
- Remise à zéro avant chaque test pour **toutes** les applications (Odoo compris) : l'IA peut alors essayer ses actions
  avant d'écrire partout, pas seulement sur le web — c'est l'un des plus gros leviers pour la génération du premier coup.
- **De toi :** V16 (une exploration par compte ?).
- **2 à 3 jours — 0 $** (mesuré à l'étape 8)
- *Fait (2026-10-21), commits locaux, non poussé* — tranché : A69 (révisée) à A96. Morceaux 1 à 4 (remise à zéro avant
  chaque cas, Odoo compris) faits ; morceau 5 (« Joué en tant que » sur le cas) fait, revu en trois passes ; morceau 6 fait
  (une exploration de l'application par TOUS les comptes, une carte « qui voit quoi », plus de limite de pages, progression,
  « Arrêter », application occupée pendant l'exploration ; essai réel sur le banc Odoo 17 : principal + Commercial explorés,
  mot de passe faux en « connexion impossible », 135 menus dont 98 vus par le manager seul) ; morceau 7 fait : l'IA écrit
  pour les écrans du compte du cas (interrupteur `TESTPILOT_GENERATION_PAR_COMPTE`, éteint par défaut), colonne « Compte »
  des lignes de données (A90-A94), vérifications faites avec le compte du cas et recoupées par le principal (A96), une
  ligne jouée avec un compte pour lequel le test n'a pas été écrit est bloquée (vérifié aussi sur les lignes figées d'une
  campagne).
  À mesurer à l'étape 8 : la section « onglets » du message à l'IA n'a pas de plafond — sans limite de pages, elle peut
  grossir (règle §8 : aucun changement du message sans mesure de coût, crédit indisponible).

#### Étape 5 — L'IA ne part plus à l'aveugle (génération du premier coup)
- Avant d'écrire, l'IA reçoit tout ce que l'exploration a relevé : pages, champs, listes et leur nombre de lignes,
  messages, menus **dans la bonne langue**, l'état de départ, la forme des réponses de l'oracle.
- Finir les vérifications solides (texte apparu après la dernière action, erreur rattachée au bon champ, valeur citée
  sur une page inconnue refusée).
- Corriger les erreurs de génération relevées à l'étape 3.
- **3 à 5 jours — 0 $** (mesuré à l'étape 8)
- *Partiellement fait (2026-10-22), commits locaux, non poussé* — périmètre réduit pour la mesure du jour (décision du porteur : mesure et démo avant 15 h). Fait : texte qui doit être apparu après la dernière action (A97) ; l'IA informée derrière `TESTPILOT_IA_INFORMEE` (A98 : vrai type d'application, langue en web, pages visées en détail). Déjà en place : une vérification constante (`constater(True)`) est refusée à l'écriture. Reste : contrôle d'arrivée après un menu Odoo (F25, il faut le banc Odoo), erreur rattachée au bon champ, valeur citée sur une page inconnue, libellés de structure et état de départ relevés par l'exploration (AV-3, AV-4), garde de connexion réécrite (AV-6), passe des cas (AV-8), outils web (AV-9), F24, F27, instruction d'AV-7, test modifié à la main qui contourne les contrôles.
- *Restes faits (2026-10-22 au soir), branche `lot-etape5-restes`, poussée, sans PR* — A101 à A103 (à confirmer) : erreur rattachée au champ ; page d'arrivée observée (interrupteur) ; garde de connexion AV-6 (interrupteur) ; état des listes et libellés de fiche relevés (AV-3, AV-4, derrière `TESTPILOT_IA_INFORMEE`) ; termes des écrans pour la passe des cas (AV-8, interrupteur) ; outils web qui disent quoi relever (AV-9) ; F24 refusé à l'écriture ; F27 signalé à la validation ; AV-7 instrumenté (cause non instruite : pas de conversation gardée, une mesure payante est nécessaire) ; test modifié à la main signalé ; restes de la revue du 22/10 (`no_test` en campagne, relance d'un « Test non livré », fonction morte). Restent : F25 (banc Odoo, Docker absent), A41 et la marque « préparation » (A104, décision du porteur), consultation des données par l'oracle et soumission d'essai en web (AV-9, deuxième moitié).

#### Étape 6 — Données de test : les vrais clients, et des lignes toujours justes (famille 3)
- Remplir une colonne `{{client}}` avec des enregistrements qui existent déjà dans l'application ; figés au lancement.
- Quand la spécification change (18 → 21 ans), signaler les lignes d'un cas devenues fausses et proposer les nouvelles.
- **De toi :** combien d'enregistrements, lesquels montrer.
- **4 à 5 jours — 0 $** (mesuré à l'étape 8)
- *Partiellement fait (2026-10-22 au soir), branche `lot-etape6-donnees-clients`, poussée, sans PR* — migration 75 ; colonne remplie depuis l'application (oracle ou Odoo), figée au lancement, derrière `TESTPILOT_COLONNE_DEPUIS_L_APPLICATION` (éteint, proposition A105 à valider : 3 enregistrements, les premiers rendus) ; lignes d'un cas signalées quand son texte change, nouvelles lignes proposées par l'IA derrière `TESTPILOT_LIGNES_PROPOSEES` (A106 : signal ou blocage, à trancher). Restent : l'écran pour déclarer une source et pour relire les lignes proposées, la mesure.

#### Étape 7 — Valeurs attendues calculées (A108, A110 — validées le 2026-10-23)
- Vérifier une valeur calculée (total, remise, taxe, échéance…) sans recopier le chiffre de la spécification.
- **Le calculateur** : du code, sans IA, qui exécute un calcul écrit en étapes simples (pourcentage, arrondi, plafond,
  barème par tranches, condition), exact, avec le détail ligne par ligne.
- **La fiche de calcul** (propre au projet, jamais partagée) : les éléments du calcul avec leur source, les étapes, les
  exemples chiffrés à retrouver (le chiffre écrit dans la spec en devient un), l'origine (IA ou personne, nom, date). Un taux
  indique sa source et sa date de vérification, rien d'autre.
- **Sur l'écran de validation des cas, après « Générer » et avant l'écriture des tests techniques** : un cas qui attend une
  valeur calculée porte la mention **« Calcul détecté »** (avec la raison) ; l'utilisateur choisit (1) la fiche **proposée
  par l'IA**, déjà présentée, (2) **fournir lui-même** le calcul, ou (3) **ne pas vérifier par calcul** — choix **par
  défaut** s'il valide sans rien faire, la valeur est vérifiée comme aujourd'hui. Choisir (1) ou (2) vaut validation par
  cette personne (V10 : rôle testeur ou plus ; nom et date gardés ; l'IA ne valide jamais ; une fiche modifiée redevient
  à valider). Il peut aussi marquer « Calcul nécessaire » un cas non détecté.
- **Le test** : « le nombre affiché pour X vaut le résultat calculé "<nom>" », recalculé à chaque exécution ; une fiche
  qui ne retrouve pas ses exemples n'est jamais utilisée.
- Abandonné (porteur, 2026-10-23) : la bibliothèque commune entre projets (V5, V6 sans objet) ; un délai d'expiration des
  taux (V8 : source et date seulement).
- **3 à 4 jours — 0 $** (coût de la proposition de fiche mesuré à l'étape 8)
- *Fait (2026-10-23), branche `lot-etape7-calculs`, poussée, sans PR* — calculateur (`parametres/calcul.py`) ; fiches en
  base (migration 77) ; choix sur l'écran de validation des cas ; calcul fait à chaque exécution, pour chaque itération,
  avec la fiche retenue la plus récente (exemples revérifiés) ; l'agent technique nomme le calcul, jamais le chiffre ;
  détection et proposition par l'IA derrière `TESTPILOT_CALCULS` (éteint). Un calcul n'est joué que si le scénario qui le
  vérifie SAISIT chacune de ses entrées (`{{entree}}`, Contexte compris), sinon « bloqué ». Limite connue : citer
  `{{entree}}` dans une action ne prouve pas que la valeur arrive dans le bon champ (relu à l'approbation du test). Reste :
  la mesure (étape 8) ; une page pour revoir ou changer les fiches d'un cas déjà créé.

#### Étape 7b — Enregistrer le parcours d'un cas de test (au choix) — *A109 validée le 2026-10-23*
- Idée du porteur : la connexion est un parcours déjà enregistré ; faire de même pour n'importe quel cas. Une personne joue
  le cas dans le navigateur en direct, l'outil retient le parcours, puis en écrit le test technique. Au choix : sans
  enregistrement, la génération reste celle d'aujourd'hui.
- Ce que l'enregistrement de la connexion retient aujourd'hui (vérifié dans le code le 2026-10-23) : **aucune vidéo,
  aucune image** (le flux d'images n'est que relayé à l'écran) ; seulement la **liste des clics**, chacun décrit par le
  rôle et le nom de l'élément (« bouton Connexion »), et les 3 éléments du formulaire de connexion ; jamais une valeur
  saisie, jamais un secret ; une seule séquence par projet, remplacée à chaque nouvel enregistrement (pas d'historique).
- À ajouter pour un cas : saisie de texte et choix dans une liste (valeurs non secrètes, ou reliées à une variable
  `{{nom}}`) ; page atteinte après chaque action ; les **points à vérifier** désignés par la personne à l'écran ;
  l'enregistrement rattaché au cas et à sa version, gardé dans l'historique (archivé, jamais écrasé).
- Règle qui ne change pas : le parcours (les actions) vient de l'enregistrement ; le **résultat attendu vient du cas
  validé** (A39), jamais de ce que l'écran montrait pendant l'enregistrement — sinon un bug présent ce jour-là deviendrait
  l'attendu.
- **De toi :** A109 (périmètre, valeurs saisies, qui écrit le test à partir du parcours).
- Placée après les calculs (porteur, 2026-10-23) : mesurée avec le reste à l'étape 8.
- **3 à 5 jours — 0 $ à construire** (moins d'appels à l'IA ensuite : les actions n'ont plus à être devinées).
- *Fait (2026-10-23), branche `lot-etape7b-parcours`, poussée, sans PR* — bouton « Enregistrer le parcours » sur la fiche
  du cas (testeur, développeur, administrateur) ; le navigateur se connecte seul avec le compte du projet (en échec : la
  personne se connecte, rien n'est gardé avant « Je suis connecté ») ; retenus : clics, textes saisis, choix dans une
  liste, page atteinte, et « C'est ici que je vérifie » — l'élément est désigné par son identifiant technique (ou
  l'étiquette d'un champ), **jamais par ce qu'il affiche** ; jamais un mot de passe, ni image ni vidéo. Table `parcours_enregistre`
  (migration 78), historique gardé, version de test rattachée. Cas automatisé : les actions sont traduites sans IA et
  imposées à l'écriture (refus « PARCOURS ») ; l'IA n'écrit que l'« Alors », avec le résultat attendu du cas ; une liste à
  recherche (relation) reste à écrire par l'IA. Cas manuel : mode opératoire affiché. Limites : la réparation d'un test
  n'est pas contrainte par le parcours (seule la génération l'est) ; une saisie de mot de passe n'entre jamais au
  parcours (un cas « changer son mot de passe » sortira « à refaire », jamais conforme) ; coût du prompt mesuré à l'étape 8.

#### Étape 8 — Mesure de contrôle n°2 et allumage
- Une seule campagne qui mesure tout ce que les étapes 4 à 7 ont apporté (Odoo compris), plus les options encore
  éteintes (forme de l'oracle, valeurs avec unité, lignes proposées par l'IA si pas encore allumées).
- On **allume** ce qui a passé sa mesure ; on retire les interrupteurs devenus inutiles.
- **De toi :** accord sur le budget.
- **1 à 2 jours — environ 20 $**

#### Étape 9 — Clôture des paramètres de test et de la génération
- Retirer l'ancien écran « Identité et application » ; guide utilisateur des paramètres de test ; guide de test et
  récapitulatif pour ton tuteur à jour ; CLAUDE.md et CONTINUITE à jour.
- **1 à 2 jours — 0 $**

#### Étape 10 — Mise en ligne
- Fusionner la chaîne de branches locales (y compris le nettoyage du lot 06 et le correctif 07b-2 jamais fusionnés),
  migrations 64 à 7x sur PostgreSQL, 4 contrôles de la CI au vert, PR en « rebase and merge ».
- **De toi :** accord avant chaque fusion ; /staging reste ta décision.
- **1 à 2 jours — 0 $**

### PARTIE C — Après tes priorités

| Sujet | Ce qu'on obtient | Durée | Coût |
|---|---|---|---|
| Odoo au-delà du portail | Back-office Odoo 16-18 et Enterprise fiables (sélecteurs par version, rapport PDF, tuiles Enterprise, comptes du banc) | 3-4 j | ~5 $ |
| Réparation honnête | Un test réparé ne vérifie jamais moins qu'avant | 1-2 j | faible |
| La preuve publiable | Chiffres sur une application jamais vue et un vrai Odoo | 2-3 j | ~15 $ |
| Recette du produit | TestPilot parcouru de bout en bout comme un utilisateur | 2 j | faible |

---

## 5. Récapitulatif

| Partie | Étapes | Durée | Coût IA |
|---|---|---|---|
| A — Socle | 1 à 3 | 5 à 6 jours | 8-10 $ |
| B — Tes priorités | 4 à 10 | 15 à 23 jours | ~20 $ |
| **Total priorités** | **1 à 10** | **≈ 4 à 6 semaines** | **≈ 30 $** |
| C — Après | | 8 à 11 jours | ~20 $ |

**Pourquoi cet ordre est le plus court :**
- l'étape 2 rend toutes les suivantes vérifiables tout de suite (chaque nouveau test généré est prêt à lancer ou
  bloqué avec sa raison) ;
- les étapes 4 et 5 améliorent la génération **avant** d'ajouter des fonctions, donc les étapes 6 et 7 sont générées
  plus juste dès leur premier essai ;
- deux mesures seulement (3 et 8) au lieu d'une par sujet : moins de coût, moins d'attente ;
- une seule mise en ligne, à la fin, conformément à ta règle — **risque à connaître :** plus on attend, plus la fusion
  est longue (une douzaine de branches, 9 migrations). Si tu préfères, une mise en ligne intermédiaire après l'étape 3
  est possible (environ 1 jour de plus).

---

## 6. Tes décisions, au moment où elles se posent

| Étape | Décision |
|---|---|
| 1 | Assouplissement « champ vu après un clic » (web et Odoo) |
| 2 | Écran « bloqué » |
| 3 et 8 | Budgets des mesures |
| 4 | V16 — une exploration par compte ? |
| 6 | Combien d'enregistrements, lesquels |
| 7 | V5, V6, V8, V10, D22 |
| 10 | Accord avant chaque fusion |
| À tout moment | Mise en ligne intermédiaire après l'étape 3 ? |
| En suspens | Session perdue en cours de test : bloquer ou se reconnecter ? Afficher les cas « indéterminés » ? |

---

## 7. Petits restes rangés

- Champ identifiant sans `type` (PR #53), 3 tests d'attente de rendu, test de garde de session instable en CI, bloc
  dépliant au rejeu de la connexion → étape 10.
- Accolades à écrire « pour de vrai » dans un test (A34) → étape 2.
- Informations perdues à la relecture des cas proposés (session séparée en cours) → étape 1.
- Défauts F20, F24, F25, F27 → étape 5 ; F11, F12 → partie C ; F13 non corrigé (ta décision).
- `data/.secret_key` dans le worktree et `C:\tmp_rv3` : à supprimer à la main.

---

## Annexe A — Correspondance des anciens identifiants

| Ancien | Où |
|---|---|
| Lots 01-05, 07a-e, 11, 12 ; fiabilisation lots 1-4 ; Q1, Q2 ; VH-03, VH-07 | faits |
| Lot 06, hotfix 07b-2 | étape 10 (fusion) |
| PT-00 à PT-04a, IT-1 à IT-3c, VH-08 | faits en local → étapes 1, 10 |
| A61, A62, A63 | étapes 1, 2 |
| IT-3e, mesure M2 (oracle), PT-03 (mesure) | étapes 3, 8 |
| PT-04b, PT-04d | étape 4 |
| AV-1 à AV-9, VH-02/04/05/06 (restes), Q3 (règles connecteur), G1, G7 | étape 5 |
| IT-3d, IT-4 | étape 6 |
| PT-05, PT-06, CV-02 à CV-07, R2-R10, Q4, Q5 | étape 7 |
| E9, PT-07 | étapes 8, 9 |
| Lot 08, F17-F19, F23, I3/I4 | partie C (Odoo) |
| VH-09, lot 09 (réparation) | partie C (réparation) |
| VH-01 (2-5), VH-10, lot 10, fiabilisation lot 5 | partie C (preuve) |
| Plan de test de bout en bout (Composio), fiabilisation lot 6 | partie C (recette) |
| PT-04c (Firefox) | hors plan |

## Annexe B — Plans remplacés (archives)

`PLAN-FIABILITE-VERDICT-2026-09.md`, `PLAN-FIABILISATION-GENERATION.md`, `PLAN-QUALITE-AGENTS-2026-10.md`,
`PLAN-VERDICT-HONNETE-ZERO-ERREUR-2026-10.md`, `PLAN-CALCUL-DE-VALEURS-2026-10.md`, `PLAN-PARAMETRES-DE-TEST-2026-10.md`,
`PLAN-TEST-E2E-CLAUDE-COMPOSIO.md`, `SUITE-2026-10-12-RESTES-ET-CALCUL-DE-VALEURS.md`. Leurs registres de décisions
restent la référence historique ; les nouvelles décisions s'inscrivent dans ce plan.
