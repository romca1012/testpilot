# Brief à destination de Claude — structurer une présentation de TestPilot à un QA externe

> **Ce document n'est pas la présentation.** C'est la matière première et le cadrage.
> À coller dans une conversation Claude neuve, avec la demande : *« structure-moi cette
> présentation ».*

---

## 0. La mission, en une phrase

Structurer une présentation orale d'environ **20 à 30 minutes**, destinée à un **professionnel du
test (QA) d'une autre entreprise**, pour qu'il puisse :

1. **comprendre vite** ce qu'est TestPilot et pourquoi il existe ;
2. **apporter des idées** en tant que testeur expérimenté ;
3. **évaluer si l'outil pourrait l'aider** sur ses propres sujets.

⚠️ **Ce n'est pas une démo technique et ce n'est pas un argumentaire de vente.** C'est une mise en
commun : on montre un projet réel, avec ses réussites *et* ses murs, pour déclencher une
conversation de professionnel à professionnel.

---

## 1. Qui présente *(à placer en ouverture)*

- **Romaric Capo-Chichi**, chez **AXENEO**.
- **Formation** : développeur **data et IA**.
- **Rôle sur ce projet** : à la fois **porteur produit / chef de projet** et **développeur** — c'est
  la même personne qui décide la vision et qui écrit le code.
- **TestPilot** est un projet **interne**, en construction active, pas un produit commercialisé.

⚠️ *Note pour Claude* : les pronoms de Romaric n'ont pas été précisés. **N'en présume aucun** — si
la présentation doit parler de la personne à la troisième personne, tourne les phrases pour éviter
tout accord genré, ou emploie le prénom.

**Angle d'ouverture suggéré** : ce double rôle est un atout à énoncer d'emblée. Il explique
pourquoi les décisions produit et les contraintes techniques sont discutées ensemble tout au long
de la présentation — et pourquoi le QA invité peut influencer les deux.

---

## 2. Qui écoute, et ce qu'on attend de lui

Un **QA / testeur professionnel d'une autre entreprise**. Il ne connaît ni le projet, ni le
contexte Odoo d'AXENEO.

**Ce qu'on veut obtenir de lui** :

- son **regard de métier** sur nos choix (est-ce qu'un testeur ferait comme ça ?) ;
- ses **angles morts à lui** : quels problèmes de test le rongent au quotidien ;
- une réponse à : **est-ce que cet outil pourrait servir sur ses sujets ?**

**Conséquence directe sur le ton** : il faut lui laisser de la place. Une présentation qui déroule
30 minutes sans respiration ne produira aucune idée. Prévoir des **points d'arrêt explicites** où
on lui pose une question (voir §9).

---

## 3. Le point de départ — l'histoire fondatrice *(à raconter en premier, c'est le meilleur hook)*

Chez AXENEO, plusieurs ERP (Odoo en tête, modules natifs et sur mesure) évoluent en continu. Les
tests fonctionnels sont écrits à la main et référencés dans **TestRail**. Un cycle de test complet
peut prendre **plusieurs jours**.

**Le cas fondateur** : un test **existait**. Il n'a **pas été rejoué**, faute de temps. Le bug est
passé en production. **Ça a coûté un client.**

Le problème n'était donc pas l'absence de test. C'était que **le référentiel disait « testé » alors
que personne n'avait rien exécuté**.

> C'est le cœur de tout le projet, et ça parle immédiatement à un QA : dans TestRail, le statut
> d'un test est **un champ que quelqu'un coche**. Rien ne garantit qu'il corresponde à une
> exécution réelle contre le code actuel.

---

## 4. La promesse, en une phrase

> **Un outil honnête qui dit ce qui est réellement couvert par les tests — parce que le statut
> « testé » n'est jamais une case cochée, mais toujours la conséquence d'une exécution réelle.**

Et la formule courte qui situe le produit : **« un TestRail qui exécute aussi les tests ».**

---

## 5. Le positionnement — trois comparaisons qui suffisent

| Par rapport à… | Ce qui change |
|---|---|
| **TestRail** | Le statut n'est pas un champ modifiable : il est **produit par une exécution réelle** |
| **Playwright / Selenium seuls** | Ce n'est pas qu'un moteur d'exécution : c'est aussi un **référentiel métier structuré**, avec génération des tests à partir d'une spécification |
| **QA manuelle classique** | Supprime le **faux positif de couverture** — le test « supposé bon » mais jamais rejoué |

⚠️ **Ne pas positionner l'outil comme un remplaçant du QA.** Devant un QA, c'est à la fois faux et
maladroit. Le bon cadrage : l'outil **supprime la corvée de rejeu** pour que le QA garde le
jugement — quoi tester, et si un écart est grave.

---

## 6. Le parcours, en langage d'utilisateur *(le cœur de la présentation)*

À présenter comme **un chemin que quelqu'un parcourt**, pas comme une architecture.

1. **Créer un projet** et lui donner l'accès à l'application à tester.
2. **Explorer l'application** — l'outil la parcourt automatiquement et en dresse la carte : quelles
   pages existent, quels formulaires, quels champs, quelles règles de saisie. **Payé une fois par
   projet.** *(Aujourd'hui : 37 pages, 373 champs, 36 règles de saisie sur le portail interne.)*
3. **Décrire un besoin** — soit en écrivant une spécification, soit en **déposant un fichier**
   (Word, Markdown, texte).
4. **L'IA reformule d'abord en langage métier** ce qu'elle compte tester, et **s'arrête**.
   L'utilisateur **valide ou corrige avant** qu'une seule ligne de test soit écrite.
5. **Génération du test** — rangé dans le module concerné du référentiel.
6. **Relecture humaine obligatoire** avant la toute première exécution.
7. **Exécution** — on compose une **campagne** en piochant des cas dans **plusieurs modules**
   (les régressions transverses sont le vrai sujet), on la nomme, on la lance.
8. **Rapport** — deux lectures : mode *utilisateur* (le verdict) et mode *dev* (les détails).

⚠️ **L'étape 4 mérite d'être appuyée.** C'est un choix de conception fort : l'IA **demande la
permission** avant de produire. Un QA verra tout de suite ce que ça évite — un test généré sur un
malentendu, qu'il faut ensuite lire en entier pour découvrir qu'il ne teste pas le bon scénario.

---

## 7. L'idée technique qui structure tout : **deux verdicts, jamais fondus**

C'est le concept le plus important à faire passer. Il est simple et il parle aux testeurs.

Chaque exécution répond à **deux questions séparées** :

| Question | Réponse |
|---|---|
| Le test a-t-il **pu tourner** ? | *déroulement* — ou erreur technique (crash, timeout, environnement) |
| L'application s'est-elle **comportée correctement** ? | *conformité* — conforme / non conforme |

**Pourquoi c'est capital** : fondre les deux donne « échec », et « échec » ne dit pas si c'est
**l'application** qui a un défaut ou **le test** qui est cassé. Un outil de test qui confond les
deux fait perdre un temps considérable — chaque QA a déjà vécu ça.

Ces deux axes se recroisent ensuite en statuts familiers de TestRail (Passed / Failed / Retest /
Blocked / Untested), pour que le référentiel reste lisible par quelqu'un qui vient de TestRail.

**Autres règles à mentionner brièvement** :

- **Ligne rouge : jamais de masquage d'un échec.**
- **Garde-fou asymétrique** : si l'IA conclut « c'est le test qui est cassé » (non bloquant), un
  **humain doit confirmer**. Si elle conclut « c'est un vrai bug », ça remonte directement. *Le
  risque d'une fausse alerte est acceptable ; celui d'un bug manqué ne l'est pas.*

---

## 8. Les technos — **à évoquer, pas à détailler**

Règle : **une phrase chacune, et seulement pour situer**. Si le QA veut creuser, il demandera.

| Techno | La phrase qui suffit |
|---|---|
| **Gherkin** | Les tests sont écrits en langage quasi naturel (`Quand je renseigne le champ… Alors…`), donc **relisibles par un fonctionnel**, pas seulement par un développeur |
| **Playwright** | Ce qui pilote réellement le navigateur — les tests cliquent et remplissent comme un utilisateur |
| **Claude (Anthropic)** | Ce qui lit la spécification et rédige le test |
| **Odoo** | La cible actuelle — l'outil est pensé pour accueillir d'autres types d'applications |

⚠️ **À ne PAS faire** : montrer du code, une base de données, une architecture de fichiers. Un
**extrait de Gherkin de 5 lignes** est la seule chose techniquement dense qui vaille d'être
projetée — parce qu'elle démontre la lisibilité, ce qui est justement l'argument.

---

## 9. Ce qui est **vrai aujourd'hui** — et c'est là que la présentation devient intéressante

⚠️ **Instruction ferme à Claude** : cette section ne doit **pas** être polie en argumentaire. Le
projet est en construction, l'honnêteté est le sujet même du produit, et un QA repérera
instantanément une présentation qui embellit. **La crédibilité vient de ce qu'on assume.**

**Ce qui fonctionne, mesuré sur un banc de 8 formulaires réels :**

- **88 %** des tests générés tournent **au premier jet**, sans erreur technique.
- Il y a un mois, ce chiffre était de **25 %**.

**La montée n'a rien d'un réglage de prompt** — dix causes distinctes ont été trouvées, chacune sur
des exécutions réelles, et **neuf ont le même motif** :

> **« La carte de l'application savait, mais personne ne transmettait l'information au générateur. »**

Exemples parlants pour un QA :
- l'IA écrivait du texte dans un champ « pièce jointe » — la bibliothèque n'avait **aucun** moyen
  d'envoyer un fichier ; 13 pages sur 37 étaient donc **inatteignables** ;
- l'IA inventait un numéro dans l'URL (`/demande_avoir/29789`) alors que la carte contenait une
  vraie adresse visitée ;
- l'IA remplissait 2 champs obligatoires sur 8, puis s'étonnait que rien ne soit créé.

**Et surtout — le défaut le plus grave, trouvé cette semaine :**

Le formulaire de remboursement exige un code client de **7 chiffres exactement**. Le test y écrivait
`TEST_REMB_CLI001`. Le navigateur **refuse silencieusement d'envoyer**. Rien n'est créé. Le test en
concluait : **« l'application est non conforme »**.

**L'application avait raison. C'était notre donnée de test qui était invalide.**
**12 des 21 formulaires** étaient exposés à ce faux verdict.

> La phrase à retenir, et à dire telle quelle : **« un outil de test qui accuse à tort est pire
> qu'un outil qui ne teste rien — il détruit la confiance dans ses verdicts justes. »**

**Le correctif** : quand rien n'est créé, l'outil **interroge la page** au lieu de conclure. Dernière
campagne, sur 8 formulaires :

```
4 × « c'est NOTRE donnée qui est invalide »   (le navigateur l'a refusée)
2 × refus SILENCIEUX — indécidable en l'état
1 × conforme
1 × erreur technique
────────────────────────────────────────────
0 × défaut applicatif prouvé
```

Avant ce correctif, ces mêmes résultats auraient annoncé **« votre application a 6 défauts »**.

---

## 10. Les murs actuels — **la vraie matière à discussion**

⚠️ **Instruction à Claude** : c'est la section qui doit générer les idées du QA. Elle doit être
présentée comme **des questions ouvertes**, pas comme une liste de bugs. Prévoir un vrai temps
d'échange ici — c'est le moment le plus utile de la réunion.

**Mur 1 — Le refus silencieux.**
Deux formulaires refusent la soumission **sans afficher le moindre message**. Rien ne permet de
distinguer un refus métier légitime d'un vrai défaut.
👉 *Question au QA : comment diagnostiques-tu un formulaire qui refuse sans rien dire ?*

**Mur 2 — Les règles invisibles.**
La carte de l'application est construite en lisant le HTML. Mais certaines règles de validation sont
écrites en **JavaScript** — elles n'apparaissent nulle part avant l'exécution. Exemple réel : un
champ TVA sans aucune contrainte déclarée, que le navigateur refuse pourtant.
👉 *Constat à partager : on ne peut pas tout savoir à l'avance. Il faut lire le navigateur pendant
l'exécution.*

**Mur 3 — Les champs conditionnels.**
Choisir une option dans une liste **fait apparaître de nouveaux champs obligatoires**. Notre carte
est une photo prise avant ce choix — elle dit « pas obligatoire », et le test échoue.
👉 *Question au QA : comment gères-tu les formulaires à branches dans tes propres tests ?*

**Mur 4 — Les données de test valides.**
Un SIRET, un IBAN, un numéro de TVA, un SIREN : chacun a son format, parfois sa clé de contrôle.
Générer des données **acceptables par l'application** est un problème en soi.
👉 *Question au QA : c'est très probablement un sujet qu'il connaît mieux que nous.*

**Mur 5 — Le nettoyage.**
Les tests créent de vrais enregistrements dans une vraie application.
👉 *Question au QA : jeu de données dédié ? restauration ? suppression après coup ?*

---

## 11. Ce qu'on veut lui demander explicitement *(à placer en fin)*

1. **Sur nos choix** : les deux verdicts séparés, la validation métier avant génération, la
   relecture obligatoire — est-ce que ça correspond à sa façon de travailler ?
2. **Sur ses sujets** : quelles applications teste-t-il ? Combien de temps lui coûte un cycle de
   régression ? Où est sa douleur ?
3. **Sur la faisabilité** : voit-il un cas chez lui où cet outil ferait une différence ?
4. **Sur les murs du §10** : comment aborderait-il ces problèmes ?

---

## 12. Contraintes de forme — **à respecter strictement**

- **Durée** : 20-30 min de présentation, **plus** un temps d'échange réel.
- **Niveau** : compréhensible par quelqu'un qui **ne connaît ni Odoo, ni le projet, ni notre code**.
- **Vocabulaire** : bannir *annuaire*, *gate*, *dry-run*, *repository*, *migration*, *verdict
  fonctionnel/exécution* sans les avoir expliqués une fois en clair.
- **Support** : peu de texte par écran. Le récit porte, pas les diapositives.
- **Une seule métaphore filée** si nécessaire : *la carte de l'application* (ce que l'outil connaît
  du terrain avant d'écrire un test). Ne pas en empiler d'autres.

**Ce que la présentation ne doit pas faire :**

- ❌ prétendre que l'outil est fini ou prêt à l'emploi ;
- ❌ positionner l'IA comme remplaçant le jugement du testeur ;
- ❌ dérouler l'architecture technique ;
- ❌ masquer les 10 causes d'échec — **elles sont l'argument le plus convaincant**, pas une faiblesse
  à cacher : elles prouvent que le projet est mesuré et non supposé ;
- ❌ transformer l'échange en démonstration à sens unique.

---

## 13. Livrable attendu de Claude

1. Un **plan de présentation** minuté, section par section, avec l'intention de chacune.
2. Pour chaque section : **ce qu'on dit** (les idées clés, en langage parlé) et **ce qu'on montre**.
3. Les **3 ou 4 moments d'arrêt** où l'on rend la parole au QA, avec la question exacte à poser.
4. Une **ouverture** (les 2 premières minutes, mot pour mot ou presque — c'est le moment qui décide
   de l'attention) et une **clôture** qui appelle une suite concrète.
5. Une **version courte de repli en 10 minutes**, au cas où le temps serait réduit.

---

## Annexe — chiffres vérifiés au 2026-07-22

*(Utilisables tels quels ; ils viennent de mesures réelles, pas d'estimations.)*

| | |
|---|---|
| Réussite technique au premier jet | **88 %** (banc de 8 formulaires réels) — contre **25 %** il y a un mois |
| Coût de création d'un cas de test | **~0,11 $** (cible produit : < 1 €) |
| Temps de génération d'un cas | **~80 à 150 secondes** |
| Carte de l'application testée | **37 pages, 373 champs, 36 règles de saisie** |
| Causes d'échec identifiées et corrigées | **10**, dont **9** partagent le même motif |
| Défauts applicatifs **prouvés** sur la dernière campagne | **0** sur 8 formulaires |
