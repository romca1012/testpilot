# Déroulé de démo — TestPilot

> Préparé le 2026-07-21. Objectif : montrer le parcours complet, de la spécification
> métier jusqu'à une **campagne d'exécution multi-modules**.

---

## Avant de commencer (vérifications, 30 secondes)

1. **L'application testée tourne** : le Portail Sapian doit répondre sur
   `http://localhost:10017`. Si elle est éteinte, les exécutions échoueront.
2. **TestPilot tourne** : ouvrir **http://localhost:8011/** — faire un `Ctrl+F5` la
   première fois.
3. Vous arrivez dans le projet **Portail Sapian**.

**L'état préparé pour vous** :

| | |
|---|---|
| Projet | Portail Sapian, connecté et **exploré** (37 routes cartographiées) |
| Modules prêts | **Achats & Investissements** · **Gestion Clients** · **Comptabilité Client** |
| Cas existant | 1 cas déjà généré dans « Demande materiel » (montre l'historique) |
| Spécifications | 3 fichiers dans `specs/demo/` — à copier-coller **ou** à importer |

---

## Le fil narratif (ce que la démo raconte)

> « Un outil de gestion de tests classique attend qu'on lui **apporte** des résultats.
> Celui-ci va chercher l'application, la **comprend**, et **écrit les tests** lui-même —
> puis les exécute et suit sa propre fiabilité. »

Trois temps : **il connaît l'application** → **il écrit les tests avec vous** →
**il les joue et rend un verdict**.

---

## 1. Il connaît l'application *(1 min)*

Menu projet (en haut à gauche) → **« Gérer les projets… »**.

Sur la carte du projet, montrer :
- la **connexion** (`odoo · http://localhost:10017 · …`) : c'est l'application réellement testée ;
- la ligne **« 37 routes · N transitions · N champs — mesuré le … »**.

> **À dire** : « L'outil a parcouru l'application tout seul et en a fait une carte :
> les pages, les formulaires, les champs obligatoires, les valeurs possibles de chaque
> liste. Aucune IA ici — c'est une mesure. C'est ce qui lui permet d'écrire des tests
> qui marchent au lieu de deviner. »

Revenir au projet (cliquer sa carte).

---

## 2. Il écrit les tests avec vous *(≈ 4 min par cas)*

Répéter pour les **trois** modules. *(Astuce : le 1ᵉʳ en entier, les suivants plus vite.)*

1. Barre latérale → **« Générer des cas de test »**.
2. **Module** : choisir le module correspondant.
3. **Spécification** : coller le contenu du fichier — ou **📎 Importer un fichier**
   (`.txt`, `.md`, `.docx`).
4. **« Rédiger le cas de test »** → *(~1 min)*

| Module | Spécification |
|---|---|
| Achats & Investissements | `specs/demo/1-achat-siege.md` |
| Gestion Clients | `specs/demo/2-mutation-client.md` |
| Comptabilité Client | `specs/demo/3-remboursement-client.md` |

**⏸ LE MOMENT FORT — la pause.** L'IA affiche le cas **en français** : titre,
préconditions, étapes numérotées, résultat attendu. Tout est **modifiable**.

> **À dire** : « Il ne part pas écrire du code tout de suite. Il me montre d'abord ce
> qu'il a compris, **en langage métier**. Je corrige si besoin — et c'est **mon** texte
> qui servira à écrire le test. On ne paie pas du technique pour une intention fausse. »

*(Modifier un mot du titre en direct : ça rend la maîtrise tangible.)*

5. **« Valider et générer le test »** → *(~2 min)* → on arrive sur le cas.

Sur la page du cas, montrer :
- le **contenu métier** (préconditions / étapes / résultat) — lisible par un non-technicien ;
- les **métadonnées** (Type, État, Priorité modifiable en ligne, Test automatisé : Oui) ;
- s'il y en a, les **« Points de vigilance »** : l'outil signale lui-même les faiblesses
  du test qu'il vient d'écrire.

> **À dire** : « Le test technique existe, mais ce qu'on lit ici reste du métier. Le
> Gherkin est réservé au mode développeur. »

---

## 3. Il les joue ensemble — la campagne multi-modules *(≈ 5 min)*

1. Barre latérale → **« Exécutions et résultats de test »** → **« + Ajouter une exécution »**.
2. **Nom** : `Recette transverse — démo`.
3. **Sélection** → **« Sélectionner des cas de test spécifiques »**.
4. La liste s'ouvre **groupée par module**. Cocher **un cas dans chacun des 3 modules**.

> **LE POINT CLÉ** : dès que deux modules sont cochés, le badge
> **« Transverse — 3 modules »** apparaît.
>
> **À dire** : « Une campagne de régression traverse les modules. Ici je joue un test
> d'achat, un de gestion clients et un de comptabilité **dans la même exécution**. »

5. **« Ajouter une exécution de test »** → la campagne est créée **en brouillon**.

> **À dire** : « Créer une campagne ne lance rien. Lancer, c'est un geste explicite —
> ça engage du temps machine et de l'argent. »

6. **« Lancer l'exécution »** → les cas sont joués **l'un après l'autre**, contre la
   vraie application. Les résultats tombent au fur et à mesure ; la barre d'avancement
   se remplit.

7. Une fois terminé : cliquer une ligne → le **rapport détaillé** du cas.

> **À dire** : « Deux verdicts, jamais fondus : *le test a-t-il pu tourner* et
> *l'application est-elle conforme*. Un test qui tourne et détecte un vrai bug, c'est un
> succès technique — pas un échec de l'outil. »

8. **« Clôturer »** → la campagne passe en lecture seule, ses résultats sont figés.

---

## 4. Il suit sa propre fiabilité *(1 min — la conclusion)*

Barre latérale → **« Qualité de génération »**.

> **À dire** : « Le taux de tests qui tournent sans erreur technique, mesuré sur les
> exécutions réelles, suivi dans le temps. C'est ce qui nous dit si l'outil progresse —
> on est passés de 25 % à 75 % en corrigeant des causes identifiées par cette mesure. »

---

## Questions probables — réponses courtes et honnêtes

**« Combien ça coûte ? »**
~0,11 € par cas généré (analyse + rédaction + test technique). L'objectif produit est de
rester sous 1 € par cas ; on est à 10 %.

**« Est-ce que ça marche à tous les coups ? »**
Non, et c'est mesuré : **75 %** des tests tournent sans erreur technique au premier jet.
L'outil affiche ce chiffre lui-même. Les échecs sont analysés et corrigés — chaque
correction est vérifiée par une nouvelle mesure.

**« Ça marche avec autre chose qu'Odoo ? »**
L'architecture le prévoit (un connecteur par application), mais un seul est implémenté
aujourd'hui. On ne l'annoncera pas avant de l'avoir fait pour de vrai.

**« Qui écrit le test, l'IA ou moi ? »**
Vous décidez **ce qui est testé** (la pause métier). L'IA écrit **comment** le tester.
Et vous pouvez aussi saisir un cas entièrement à la main : « Ajouter un cas de test ».

---

## En cas de pépin pendant la démo

| Symptôme | Réponse |
|---|---|
| La génération échoue | Le dire simplement : c'est le 25 % connu. Enchaîner sur un cas déjà généré (module « Demande materiel ») pour montrer la suite. |
| L'exécution échoue | Vérifier que le Portail Sapian tourne sur `:10017`. Un test qui ne peut pas tourner est signalé « Blocked » — l'outil ne ment pas sur son état. |
| Un écran semble figé | `Ctrl+F5`. |
| Trop long | La génération prend 2-3 min : préparer **un cas d'avance** avant la démo, et ne générer qu'un seul cas en direct. |

> **Conseil** : générer **un des trois cas avant l'arrivée du collaborateur**. On garde
> l'effet « on le fait devant vous » sur un seul, et on ne subit pas trois attentes.
