# CONCEPTION — règles de fabrication de l'application, audit et plan

> **Écrit le 2026-07-24**, après une revue des pratiques de conception d'applications de gestion
> de données (architecture de l'information, tables denses, contrat d'API, état serveur,
> accessibilité, jetons de design) et un **audit du code réel** contre elles.
>
> Ce document dit **comment on fabrique**, là où le brief dit **quoi on fabrique** et le PLAN **où
> on en est**. Il lui est subordonné : toute règle ici qui contredirait le brief est caduque.

---

## 1. Les règles retenues

### 1.1 Architecture de l'information

- Barre latérale + hiérarchie explicite pour une application dense : elle laisse explorer
  beaucoup de sections sans noyer. *(C'est déjà notre patron — à ne pas casser.)*
- Quatre principes : **objets** (chaque entité a une identité propre et un écran qui la montre),
  **choix** peu nombreux et clairs, **divulgation progressive**, **exemples**.
- Corollaire pour nous : la Spécification, le Cas, la Campagne et l'Exécution sont **quatre
  objets** — chacun mérite son écran, son URL partageable et son fil d'Ariane.

### 1.2 Données serveur ≠ état client — **la règle structurante**

Les données du serveur ne nous appartiennent pas : elles périment, d'autres les changent. Elles
exigent une couche dédiée (cache, revalidation, invalidation après mutation).

> **Ne jamais recopier l'état serveur dans un store global.** On crée alors deux sources de
> vérité, et la dérive entre les deux est le genre de bug qu'on ne débogue pas.

### 1.3 Contrat d'API

- **Erreurs RFC 9457** : `type` / `title` / `status` / `detail` / `instance`, plus un **code métier
  stable**. Un client ne doit jamais lire une phrase française pour décider quoi faire.
- **Pagination par curseur**, pas par décalage : la seule qui survive aux écritures concurrentes.
- **Filtres nommés** (`?status=&module=`), tri `?sort=-created_at`, versionnage d'URI.

### 1.4 Tables et listes denses

- Densité réglable, en-tête et première colonne collants.
- Texte à gauche, **nombres à droite**, jamais de centrage (il empêche le balayage visuel).
- Actions de ligne **révélées au survol** ; actions en lot affichées **seulement après sélection**.
- Virtualisation au-delà de quelques centaines de lignes.
- **Préférences conservées** (filtre, tri, colonnes) **avec un bouton « réinitialiser »**.

### 1.5 Vitesse perçue

La vitesse est un problème de conception autant que d'ingénierie. Repérer les **trois gestes les
plus fréquents** et les rendre à latence zéro (interface optimiste), même si le serveur met 500 ms.
Palette de commandes (`Cmd+K`) avec le raccourci affiché à côté de chaque action — c'est ainsi
qu'on les apprend.

### 1.6 Jetons de design en trois couches

**brut** (`--blue-600`) → **sémantique** (`--primary`) → **composant** (`--button-bg`). Le graphe
de jetons est la source unique de vérité ; sans lui, le style dérive d'un écran à l'autre.

### 1.7 Accessibilité (WCAG 2.2 AA)

Focus visible (contraste ≥ 3:1), taille de cible minimale, aide cohérente, pas de ressaisie
redondante, **tout au clavier**. Un bouton à icône seule a besoin d'un **nom accessible** —
`title` est une infobulle, pas un nom.

### 1.8 Données : ne jamais détruire

Suppression **douce** (horodatage + auteur), historique par version, purge définitive comme geste
séparé. *C'est déjà l'exigence du §7 du brief — le code ne la respecte pas partout (voir §2).*

---

## 2. L'audit du 2026-07-24 — ce que le code fait vraiment

### Ce qui tient (à préserver)

| | |
|---|---|
| **25 jetons sémantiques** en CSS + bibliothèque `ui/` (Button, Card, Chip, Modal, Spinner, Icon) | Il manque la couche « composant » et la documentation, pas le principe |
| **Statuts centralisés** dans `lib/status.ts` | Un seul endroit décide de la couleur et du libellé d'un verdict |
| **Barre latérale + arbre Module → Spécification** | Exactement le patron recommandé |
| **États vides et d'erreur qui disent POURQUOI** | « Aucune trace conservée » ≠ « dossier introuvable ». Rare, et c'est un atout |
| **Vocabulaire métier constant** | Jamais d'énumération brute à l'écran (§8 du brief) |

### Ce qui ne tient pas

| # | Constat vérifié | Coût |
|---|---|---|
| 1 | **Aucune couche de données** : 22 pages/composants appellent l'API en direct ; le shell **et** la page rechargent modules+cas à chaque navigation | Requêtes en double, invalidation à la main, désynchronisation silencieuse |
| 2 | **Aucune pagination** : `listCases` rend *tous* les cas ; seul `executions` a `limit=50`, sans curseur | S'effondre vers 1 000–2 000 cas — la cible du produit |
| 3 | **Erreurs non normalisées** : 68 `HTTPException` en `{"detail": "texte français"}` | Le front **lit du français** pour décider |
| 4 | **Pas de versionnage d'API** | La CI ou un client externe cassera en silence |
| 5 | 🔴 **Suppressions dures** (`delete_project` = 12 `DELETE FROM`) | **Contredit le §7 du brief.** Seul endroit du produit où le principe est violé |
| 6 | **21 attributs `aria`/`role`/`tabindex` pour 91 boutons** ; icônes identifiées par `title` | Inutilisable au lecteur d'écran, hors WCAG 2.2 AA |
| 7 | **Aucun patron de liste avancé** (sélection multiple, actions en lot, densité, colonnes, vues) | Composer une campagne de 20 cas = 20 gestes |
| 8 | **Aucune recherche** | À 500 cas, l'arbre est un mur |
| 9 | **Rien n'est optimiste** | Le produit *paraît* lent alors qu'il ne l'est pas |
| 10 | **5 pages mortes** jamais routées | Voir l'encadré ci-dessous |
| 11 | **Mono-processus assumé** : l'état « en cours » vit en mémoire (`_RUNNING`) | À plusieurs testeurs et 2 workers, un run lancé par l'un n'est pas « en cours » chez l'autre |

> ⚠️ **Le code mort trompe — preuve du jour.** `ExecutionsList.vue`, `ModulesOverview.vue`,
> `CasesList.vue`, `ModuleDetail.vue` et `CaseDetail.vue` ne sont référencés nulle part. Or **au
> lot 1 du chemin de déploiement, l'affichage « testé contre… » a été ajouté dans
> `ExecutionsList.vue`** — une page morte. L'information est bien visible ailleurs (rapport,
> onglet Tests & Résultats), mais cette modification-là n'a jamais été atteignable. Du code mort
> qui a l'air vivant trompe jusqu'à celui qui vient de le lire.

---

## 3. Le plan — 5 lots (ordre arbitré par le porteur le 2026-07-24)

### Lot E — Nettoyer le terrain *(~0,5 j)* — **premier**

- Supprimer les 5 pages mortes ; remettre l'affichage de la cible sur l'écran **vivant**.
- Documenter le système de jetons en 3 couches ; `ui/` devient la bibliothèque de référence
  (aucun nouveau composant ne réinvente un bouton).

### Lot A — Une couche de données unique — ✅ **LIVRÉ le 2026-07-24**

- **`@tanstack/vue-query`** (arbitré : le standard, plutôt qu'un cache maison où vivent les bugs
  subtils d'invalidation et de déduplication). Tout passe par `lib/donnees.ts` : les **clés**
  dérivent d'un seul endroit, chaque **mutation déclare ce qu'elle périme**.
- **Migrés** : le shell (arbre Module → Spécification), la liste des cas, la fiche de
  spécification, l'aperçu des campagnes.
- **Supprimé** : `watch(route.fullPath, load)` dans le shell — il rechargeait **modules +
  spécifications + cas à chaque clic**, en double avec la page affichée.

**Mesuré au navigateur, pas supposé** (Playwright, application compilée, 6 navigations internes) :

| | requêtes pendant la navigation |
|---|---|
| modules · cas · spécifications | **0** (les 3 listes de l'arbre, servies par le cache) |
| campagnes | **0** après migration de l'aperçu (**+3** avant, une par visite) |

⚠️ **Première mesure fausse, corrigée** : elle naviguait par `page.goto()`, ce qui recharge la
page entière et détruit l'application **et son cache** à chaque fois — elle aurait montré un
rechargement complet quelle que soit la qualité de la couche. La navigation doit se faire **par
clic**, dans l'application.

**Reste hors périmètre du lot** (assumé) : les écrans à sondage de tâche de fond
(`AddTestCase`, `CaseDetailTR`) gardent leurs appels directs — leur logique de *polling* est un
autre problème que le cache, et la convertir ajouterait du risque sans bénéfice. `useProjects`
(état partagé maison de la liste des projets) reste également en place : une seule requête, pas
de mutation, aucun gain à le migrer aujourd'hui.

⚠️ **Une contrainte introduite, à connaître** : `frontend/.npmrc` porte `legacy-peer-deps=true`.
La bibliothèque déclare une dépendance de pair *optionnelle* vers `@vue/composition-api` (la
rétrocompatibilité Vue 2), que npm tente de résoudre et qui fait échouer l'installation. Le coût :
npm cesse de vérifier les dépendances de pair **pour tous les paquets**. Contre-mesure : les deux
suites et le build tournent avant chaque commit.

### Lot B — Le contrat d'API — ✅ **LIVRÉ le 2026-07-24** *(sauf pagination et `/v1`)*

- ✅ **RFC 9457 + catalogue de codes stables.** Un code absent du catalogue lève à la
  construction — un code inventé passerait sinon en production, et un client bâtirait sa logique
  dessus. Le comble : **les codes existaient déjà** dans les services ; les routes les jetaient.
  *Une incohérence révélée au passage : la même situation métier répondait 422 sur une porte et
  409 sur les trois autres.*
- ✅ **Suppression douce + corbeille** (migrations 23 et 24) — `deleted_at` + auteur, visibilité
  **hiérarchique** (un cas dont le module est à la corbeille est invisible), restauration, purge
  définitive comme geste distinct, index UNIQUE devenus **partiels** (un nom supprimé se
  réutilise). Écran `Corbeille.vue` : sans lui, « restaurer » n'existerait pas pour l'utilisateur.
- [ ] **Pagination par curseur** sur cas / exécutions / spécifications — **reste à faire**.
- [ ] Filtres et tri normalisés ; préfixe `/api/v1` — **reste à faire**.

> ⚠️ **Trois défauts trouvés pendant ce lot, tous par des tests, aucun à la relecture** :
> une campagne en mode « tous les cas » aurait **exécuté des cas supprimés** contre la vraie
> application ; le nettoyage de l'enveloppe automatique avait disparu en réécrivant la
> suppression ; et le refus « cette spécification porte encore des cas » avec lui.

### Lot C — Le quotidien du QA — ✅ **LIVRÉ le 2026-07-24**

- **Recherche** instantanée, côté client (les cas sont déjà en cache) : titre, identifiant tel
  qu'affiché (`C12`), module, spécification.
- **Sélection multiple + actions en lot** : créer une campagne à sélection **figée**, changer la
  priorité, supprimer. Une action = **une requête**, avec un **compte rendu** qui distingue
  `traites` de `ignores` — un cas peut disparaître entre l'affichage et le clic, et le taire
  ferait croire à un succès complet.
- **Densité** réglable, **choix des colonnes** (ni le titre ni le statut ne sont masquables — une
  liste sans eux ne montre plus rien), **préférences conservées par projet** et bouton
  **réinitialiser**, affiché seulement quand quelque chose a été modifié.

**Mesuré au navigateur** sur 20 cas réels : recherche → **0 requête serveur** ; « tout
sélectionner » puis « créer une campagne » → **1 requête**, campagne à 20 cas en sélection figée.
*Avant : 20 gestes.*

⚠️ **Un défaut trouvé par un test, à l'endroit exact qu'il visait** : le compte rendu vivait
dans la barre de sélection — laquelle disparaît dès que l'action aboutit (la sélection est
vidée). « 18 traités, 2 ignorés » s'effaçait donc à l'instant précis où il fallait le lire.

### Lot D — Clavier et accessibilité — ✅ **LIVRÉ le 2026-07-24**

- **19 boutons muets nommés** (`aria-label`). ⚠️ `title` est une **infobulle, pas un nom** : elle
  n'apparaît qu'au survol de la souris, et les lecteurs d'écran ne s'en servent qu'en dernier
  recours. Un bouton identifié par son seul `title` est muet pour qui n'utilise pas de souris.
- **Un GARDE-FOU de non-régression** : un test lit les fichiers source et échoue dès qu'un bouton
  muet réapparaît. Corriger 19 boutons une fois ne sert à rien si le vingtième arrive la semaine
  suivante.
- **Modales** : focus donné au premier **champ** (pas à la croix de fermeture — proposer d'abord
  de renoncer est un mauvais accueil), focus **enfermé** (sans quoi `Tab` part parcourir la page
  masquée derrière), Échap, et focus **rendu** à l'élément qui avait ouvert.
- **Palette de commandes** `Ctrl`/`⌘ + K` : navigation et recherche de cas, avec les **raccourcis
  affichés** — c'est en les voyant qu'on les apprend. Elle navigue et ouvre ; elle ne supprime
  pas et ne dépense rien : une action irréversible atteinte par une frappe distraite serait le
  contraire d'un gain.

⚠️ **L'anneau de focus n'était PAS conforme, et ça ne se voyait pas à l'œil.** Il était à 70 %
d'opacité : **2,69:1** contre le fond, sous le seuil de 3:1 de WCAG 2.2 « Focus Appearance ».
Calculé, pas estimé. Rendu opaque : **4,31:1**. Sur un fond très sombre, une transparence coûte
bien plus de contraste qu'elle n'en a l'air.

**Vérifié au clavier seul, dans un vrai navigateur** : `Ctrl+K` ouvre et donne le focus au champ ·
taper puis `Entrée` ouvre le bon cas · `Échap` ferme · une modale garde le focus après 12 `Tab` ·
**0 bouton muet dans la page rendue**.

---

## 4. Arbitrages du porteur (2026-07-24)

| Question | Décision |
|---|---|
| Ordre des lots | **E → A → B → C → D** — le socle avant le confort, en acceptant que les premiers jours se voient peu à l'écran |
| Couche de données | **`@tanstack/vue-query`**, pas de cache maison |
| Suppression | **Douce + corbeille**, greffée sur le lot B |

## 5. Ce que ce plan ne traite PAS

- **Postgres** : SQLite reste suffisant tant qu'on est mono-processus. À rouvrir quand plusieurs
  workers ou plusieurs instances seront nécessaires (voir constat n°11).
- **Le fond fonctionnel** : le tableau « modules à retester », les six mécanismes du §5bis, le
  Plan (conteneur de runs) restent au `BACKLOG.md`. Ce document ne parle que de **fabrication**.
