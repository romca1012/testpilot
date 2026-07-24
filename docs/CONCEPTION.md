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

### Lot B — Le contrat d'API *(~2 j — casse le front, donc juste après A)*

- **RFC 9457** + **code métier stable** (`connexion_incomplete`, `nom_deja_pris`, `spec_non_vide`…).
- **Pagination par curseur** sur cas / exécutions / spécifications.
- Filtres et tri normalisés ; préfixe `/api/v1`.
- **Greffé ici : la suppression douce** (même migration) — `deleted_at` + auteur sur les entités
  porteuses d'historique, corbeille, restauration, purge définitive comme geste séparé.
  *Aligne enfin le produit sur son propre §7.*

### Lot C — Le quotidien du QA *(~2,5 j)*

Recherche globale · sélection multiple + actions en lot (ajouter à une campagne, changer la
priorité, supprimer) · densité réglable · choix de colonnes · vues sauvegardées · tri complet —
préférences conservées, bouton « réinitialiser ».

### Lot D — Clavier et accessibilité *(~2 j)*

Noms accessibles sur tous les boutons à icône · focus visible conforme · piège de focus + Échap
dans les modales · cibles ≥ 24 px · puis palette de commandes `Cmd+K` avec raccourcis affichés.

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
