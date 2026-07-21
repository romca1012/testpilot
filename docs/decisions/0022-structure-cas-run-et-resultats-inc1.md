# 0022 — La structure complète : cas de test, run, et résultats

Date : 2026-07-20
Statut : **DÉCIDÉE** — 8 décisions tranchées par le porteur, une par une. Aucune n'a été prise en
autonomie. Amendement du brief associé (journal, 2026-07-20).
Incrément : **1** (§12 — cœur du référentiel & exécution) · rouvre `0006`, prolonge la séparation
Spécification (schéma livré, migration 13).
 
> **Ce document est la référence de la construction backend de l'étape 3.** Il fige *ce qu'est* un
> cas de test, *comment* il naît, *où* vit son résultat, et *ce qui reste ouvert*. Il se lit avec
> `docs/notes-fonctionnelles-onglets-cas.md` (le cadrage TestRail, écran par écran).

---

## Le modèle, en une image

```
Spécification (case_group)   ← LE DOCUMENT fourni une fois, source des cas
   └── Cas de test           ← le document métier (1 angle) + son Gherkin exécutable
                                 il n'est PAS exécutable seul

Jalon « Release septembre »        ← un objectif daté (n'exécute rien)
   └── Plan « Tous navigateurs »   ← un conteneur de runs (n'exécute rien, ne porte aucun cas)
          ├── Run « Chrome »       ← LA liste de cas à jouer — SEUL niveau qui s'exécute
          │      └── Cas C9 DANS ce run  ← porte LE RÉSULTAT (Passed/Failed/…)
          └── Run « Firefox »
```

**Trois niveaux à ne jamais confondre** : le **cas** (le document), le **run** (la campagne), le
**cas dans un run** (le résultat). Un même cas a **autant de résultats que de runs** où il figure —
ce n'est pas une contradiction, c'est son historique.

---

## Décision 1 — La spec génère les DEUX

Un cas a deux visages : le **document métier** (ce que l'humain lit) et le **Gherkin exécutable**.
Les deux sont **générés depuis la spécification** et **stockés** (option (b) des trois proposées).

⚠️ « Document métier » = **des champs en base**, PAS un fichier. L'interface les affiche et les
rend éditables ; un export (PDF/CSV/…) est un *rendu* à la demande, jamais la source.

## Décision 2 — Le template de spec

- **2.a — Forme : hybride.** Formulaire guidé (garantit les infos nécessaires) **+ zone libre**
  (absorbe les règles métier qu'aucun formulaire ne prévoit). Le brief §4 exigeait déjà « guidée,
  pas un champ libre » — la zone libre est le complément, pas le retour au document libre.
- **2.b — Part de technique : spec métier + contexte technique.** Le fonctionnel écrit le métier ;
  les faits mesurables (routes, champs, valeurs) sont **lus dans l'annuaire**, plus recopiés dans
  chaque spec ; les pièges non mesurables (« ces cases sont cachées et pré-cochées ») vivent dans
  les **notes de steps** (mécanisme éprouvé, `0012`), une fois pour toutes.
- **2.c — Les angles : l'IA propose, l'humain valide.** Conforme au §4bis du brief.

## Décision 3 — L'anatomie d'un cas

- **3.a — Étapes : liste numérotée simple + UN résultat attendu global** (modèle « Text » de
  TestRail), pas d'attendu par étape. Conséquence assumée : le verdict est **par cas**, pas par
  étape — c'est déjà notre fonctionnement.
- **3.b — Les champs** :

| Champ | Rempli par | Existe ? |
|---|---|---|
| Titre (phrase métier) | IA, éditable | ✅ `title` |
| Préconditions | IA, éditable | ❌ à créer |
| Étapes (liste numérotée) | IA, éditable | ❌ à créer |
| Résultat attendu (une phrase) | IA, éditable | ❌ à créer |
| Angle / Type | IA, éditable | ✅ `angle` |
| Priorité | humain | ✅ `priority` |
| État (validation) | système | ✅ `validation_status` |
| Références (tickets externes) | humain | ❌ à créer |
| Estimation | humain | ❌ à créer (débloque le burndown) |
| Gherkin + steps | IA | ✅ `test_case_version` |

- **3.c — Obligatoires : Titre + Étapes + Résultat attendu.** Le reste est optionnel. Un cas sans
  ces trois-là ne teste rien — c'est le « cas fantôme » que `0006` refusait déjà.

⚠️ **Le titre est une phrase MÉTIER**, jamais un préfixe d'angle (`[NOMINAL]` interdit). `angle`
reste une métadonnée interne, utile à la couverture, jamais dans le titre.

## Décision 4 — Où vit le résultat

- **Le résultat appartient au cas DANS un run**, pas au cas. Le run peut être autonome ou dans un
  plan : même comportement.
- **Deux statuts distincts** : l'**état du cas** (cycle de vie du document) et le **résultat du
  test** (Non testé / Passed / Failed / Blocked / Retest).
- **Un raccourci sur le cas** — « dernier résultat connu », **le plus récent par date, tous runs
  confondus** — sert UNIQUEMENT à la colonne « Statut » de la liste des cas.
  ⚠️ **C'est une copie, jamais la vérité.** En cas de divergence, **les runs gagnent**.
- **La page d'un cas ne montre jamais le raccourci seul** : elle liste **toutes** les lignes
  (une par run), chacune avec le nom du run **en lien cliquable vers son rapport**.

## Décision 5 — Le flux de génération

```
1. Créer une Spécification
2. DÉCOUVERTE    → un appel LLM dédié : l'IA lit spec + annuaire, propose les angles
3. CONFIRMATION  → l'humain coche les angles voulus                     (§4bis du brief)
4. GÉNÉRATION    → un appel PAR CAS, en DEUX PASSES :
                     4a. les champs métier  → l'humain valide/corrige
                     4b. le Gherkin, écrit DEPUIS le métier validé
5. RELECTURE     → le gate, sur le CAS ENTIER (métier + Gherkin, un seul geste)
6. Le cas est prêt → il peut être inclus dans un run
```

- **Deux passes (4a/4b)** et non une : le Gherkin est écrit à partir d'une intention **déjà
  validée par un humain** — on ne paie plus du code technique pour une intention fausse.
  Coût mesuré : ~0,16 $ en une passe → **~0,20-0,25 $ attendu en deux**, soit ~20 % du §9. Marge
  confortable.
- **Trois interventions humaines distinctes** (périmètre, métier, gate) — volontairement **non
  fusionnées** : valider le sens *avant* de payer le technique est tout l'intérêt des deux passes.
- **Coût de la découverte → rattaché à la SPÉCIFICATION** (ajout de `group_id` au `cost_ledger`).
  Raison : la dépense a lieu **avant qu'aucun cas n'existe** — même piège que la génération du
  chemin écran (migration 12), où le coût était perdu faute de point d'attache. Le coût d'un cas
  reste propre (analyse + génération de CE cas) ; le coût de la spec est visible à part. **Rien
  n'échappe au comptage.**

## Décision 6 — Édition et synchronisation

- **1 cas = 1 scénario Gherkin.** Les préconditions → `Contexte`, les étapes → les actions, le
  résultat attendu → l'assertion finale.
- **Édition métier → Gherkin : signaler + régénérer sur demande.** Un badge dit « métier modifié
  depuis la génération » ; un bouton « Régénérer le test technique » laisse l'humain choisir le
  moment. Régénérer à chaque sauvegarde coûterait un appel LLM par frappe ; ne rien signaler
  laisserait vivre un cas dont le document ne décrit plus ce que le test fait.
  ⚠️ **On réutilise le patron `spec_hash`** (« généré depuis une spec dépassée »), déjà éprouvé.
- **Réparation → métier : signaler la divergence**, sans rien réécrire. Une réparation change
  *comment* le test s'y prend, pas *ce qu'il vérifie* — mais si elle ajoute une navigation, le
  document mérite de le dire. On informe, l'humain tranche.

## Décision 7 — Qui produit un résultat (⚠️ amendement du brief)

- **Un humain PEUT saisir un résultat**, à condition qu'il soit **étiqueté « déclaré »**,
  visuellement distinct d'un résultat *exécuté*. Motif : les tests non automatisables existent, et
  la liaison d'un défaut passe par la saisie d'un résultat.
- **Un résultat déclaré donne l'état « validé manuellement »**, distinct de « validé » (réservé à
  une exécution réelle).
- **Ce qui reste interdit** : qu'un statut déclaré soit **indiscernable** d'un statut exécuté.
  La promesse du §1 n'est pas « aucun humain ne saisit », c'est « **on sait toujours d'où vient un
  statut** » — exactement la discipline déjà appliquée aux coûts (`estimated` vs `anthropic_api`).
- → **Amendement inscrit au journal du brief le 2026-07-20** (§1, §5).

## Décision 8 — Le modèle du run

- **8.a — Entrée des cas dans un run** : on construit **« tous les cas »** (sélection vivante) et
  **« sélection figée »**. Le **filtrage dynamique est REPORTÉ** (il exige un job qui réévalue les
  cas de chaque run à chaque modification — lourd et fragile).
- **8.b — Plan : OUI** (simple conteneur de runs). **Configurations : REPORTÉES** (génération
  combinatoire navigateur × OS — si on veut 2 runs, on les crée à la main).
- **8.c.1 — Lancement EXPLICITE** : créer un run ne déclenche rien ; un bouton « Lancer » démarre
  l'exécution. Créer une campagne ne doit pas engager une dépense non demandée (§9).
- **8.c.2 — Un cas non relu BLOQUE le run entier.** Rien ne part tant qu'un cas du run n'a pas
  passé le gate. Option la plus stricte, choisie délibérément : un run est un tout cohérent.

## Décision 9 — Les champs à valeurs listées

**Valeurs FIGÉES** (angle, priorité) — les mêmes pour tous les projets. Pas d'administration par
projet pour l'instant.

Ce choix n'enferme pas : `angle` est **déjà un champ libre** (décision 3.b), donc ajouter une
valeur ne demandera **aucune migration**. Rendre les listes paramétrables par projet reste
possible plus tard (une table + un écran d'administration) — c'est une **fonctionnalité
d'administration**, pas un détail de structure, et elle sera décidée quand elle sera le sujet.

## Décision 10 — Une version = LE CAS ENTIER

Les champs métier **sont versionnés avec le Gherkin** : `test_case_version` accueille
préconditions / étapes / résultat attendu (+ titre au moment de la version), et `test_case` ne
garde que le **pointeur vers la version courante** et son **état de cycle de vie**.

Trois décisions déjà prises en dépendaient :
- **l'onglet Historique** affiche des **diffs** (ancienne → nouvelle valeur) : il faut avoir gardé
  l'ancienne ;
- **le gate approuve « le cas entier »** (5.c) : ce qu'il approuve doit être **une version
  cohérente** métier + technique ;
- **la détection de divergence** (6) devient triviale : une version = un couple figé ensemble.

C'est aussi ce que fait TestRail (il versionne le cas complet).

---

## Ce que ça change par rapport à aujourd'hui

| Aujourd'hui | Cible |
|---|---|
| Un cas s'exécute **directement** (`POST /api/cases/{id}/runs`) | Un cas **n'est pas exécutable seul** — il passe par un run |
| `execution` = un run **d'un seul cas** | `run` = campagne **de N cas** ; le résultat vit sur le **cas × run** |
| Le résultat est stocké **sur le cas** (`last_*`) | Le résultat vit sur le cas×run ; le cas garde un **raccourci dérivé** |
| Le métier est **dérivé du Gherkin** à l'affichage (provisoire) | Le métier est **stocké en champs**, éditable, source de la génération technique |
| La génération produit **3 scénarios** dans un cas | **Un cas = un angle = un scénario**, un appel par cas |

## Ce qui est REPORTÉ (décidé, pas oublié)

Filtrage dynamique · Configurations (combinatoire) · Planification récurrente · Burndown/forecast
réel · Rapports planifiés · Mode dev/utilisateur (à implémenter une fois le produit voulu obtenu).

## Ce qui reste OUVERT

- Les **11 décisions backend** de `notes-fonctionnelles-onglets-cas.md` (versioning, snapshot des
  runs clos, modèle de défauts interne vs externe, permissions, agrégats…).
- **Le modèle d'utilisateur n'existe pas** : « Testé par » et « Assigné à » resteront vides tant
  que les rôles du §2 ne sont pas implémentés. Aucun nom ne sera fabriqué.
