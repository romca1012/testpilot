# 0023 — La règle apprise à chaque refus, et la mémoire de réparation

> **Arbitré et livré le 2026-08-03.** Met en œuvre le **mécanisme n°1 du §5bis** du brief
> (« zéro verdict non concluant »), désigné comme le plus rentable, et solde le **volet
> connaissance** de `0018` que l'adoption sur progrès ne pouvait pas fermer.

---

## Le problème

Le crawl ne lit que des attributs HTML. Une règle de validation écrite en **JavaScript**
(`setCustomValidity()`) lui est **structurellement invisible** — ce n'est pas un défaut
d'implémentation, c'est une limite de la méthode, déjà nommée dans `PLAN.md` §2bis :

> `tva_intracommunautaire` n'a **aucune** contrainte HTML. L'annuaire le voit « libre ».
> À l'exécution, le navigateur le refuse : *« Le numéro de TVA doit contenir uniquement des
> chiffres. »*

L'outil **détectait** déjà parfaitement ce refus (composant A, `DonneeRefuseeError`, 4ᵉ verdict
`donnee_invalide`) et rendait le bon verdict. Puis il **oubliait tout**. Le rejeu suivant
réécrivait la même valeur invalide, indéfiniment.

Même motif côté réparation : `0018` a corrigé l'**adoption** d'une version (le progrès partiel
n'est plus jeté), mais chaque tentative reconstruisait son prompt **de zéro**, sans rien savoir de
ce que les précédentes avaient établi. `repair_attempt` portait pourtant la signature d'échec, la
cause et l'issue de chaque tentative **depuis toujours** : personne ne la relisait.

---

## Les arbitrages (porteur, 2026-08-03)

### 1. « Enrichir l'annuaire » = enrichir la CONNAISSANCE, pas le FICHIER

Le §5bis dit « chaque refus enrichit l'annuaire du projet ». L'en-tête de `domain_model.py`
interdit d'écrire `data/domain/*.json` autrement que par le crawl. **Les deux sont tenus** : les
règles vivent dans `data/regles-apprises/projet-{id}.jsonl`, fusionnées **à la lecture**.

**Pourquoi c'est la bonne lecture, et pas un contournement.** La revue de l'annuaire existe pour
protéger un **détecteur de régression applicative** — *« un modèle qui change tout seul n'est pas
une référence »*. Une liste de valeurs refusées n'est la référence de rien : elle contraint
**notre fabrication de données de test**. Rien en elle ne peut faire taire un détecteur.

*Écarté* : écrire dans le fichier du crawl. Casserait l'invariant, et le smoke-check ne verrait
plus une régression de l'application.

### 2. Application immédiate, revue a posteriori

Une règle apprise s'applique **tout de suite** ; sa revue se fait après. Tenable parce que
**la direction de l'erreur est sûre** (§4.4) : au pire le résolveur produit une autre valeur, ou
aucune → `ResolveurIncompletError` → verdict **`indetermine`**. **Jamais une accusation contre
l'application.**

⚠️ **La revue ne passe PAS par `git diff`, contrairement à l'annuaire — et c'est délibéré.**
Le fichier est **gitignoré** (`data/regles-apprises/`), au même titre que la base et les
artefacts : il est **propre à une instance** et grossit à chaque run. Le versionner salirait le
dépôt à chaque exécution, et le bruit ferait cesser de le lire — l'inverse d'une revue.

La revue est donc : **ouvrir le fichier et supprimer la ligne**. C'est du JSONL, un fait par
ligne, lisible tel quel, horodaté et portant son `execution_id`. Moins cérémonieux que le diff
git de l'annuaire — mais l'annuaire est une **référence** relue *avant* adoption, alors que
ceci est une **mesure d'exécution** appliquée immédiatement. Deux natures, deux rituels.

*Écarté* : revue préalable obligatoire. Reviendrait à **ne pas livrer le mécanisme** — une règle
en attente de relecture se reproduit à chaque rejeu, c'est exactement le défaut qu'on corrige.

**L'asymétrie est la vraie garde, pas la revue** :

| | s'applique au résolveur ? |
|---|---|
| **interdire** une valeur prouvée refusée | ✅ toujours |
| **affirmer** une contrainte nommée par le navigateur (`pattern`, `maxlength`…) | ✅ si elle remplit un blanc |
| **affirmer** « ce champ est obligatoire » (`valueMissing`) | ❌ **jamais** |

`valueMissing` est exclu parce que le code documentait déjà le piège : sur `/remboursement`,
choisir `motif = "avoir"` rend 4 champs obligatoires qui ne l'étaient pas au crawl. Une exigence
**conditionnelle** généralisée serait une invention. Le fait est enregistré et remonté à l'agent ;
il ne devient pas une contrainte.

### 3. Faits runtime seulement — jamais la prose de l'agent

`what_was_tried` et `change_summary` sont des textes de LLM. `_failure_report` porte déjà la
doctrine inverse : *« on ne lui souffle pas de diagnostic … le cas 6 l'a montré »*. Les réinjecter
ancrerait une piste fausse **à travers les sessions** — pire que dans une seule.

*Écarté* : un bloc séparé « ce que l'agent a DIT avoir tenté (non vérifié) ». À rouvrir si les
faits runtime seuls s'avèrent insuffisants — mesure d'abord.

### 4. Fichier JSONL, pas table SQLite

Le lecteur principal est le résolveur, qui tourne **dans le sous-processus Behave** — lequel ne
connaît pas la base. L'y faire ouvrir SQLite prendrait un verrou de lecture pendant qu'un run de
plusieurs minutes écrit, sans WAL : « database is locked » intermittent, invisible en test, fatal
en campagne.

*Contrepartie assumée* : deux campagnes **simultanées** sur un même projet ne sont pas garanties.
Les campagnes sont séquentielles (arbitrage). À rouvrir si ça change — le format est structurant.

### 5. Aucune migration, aucune colonne, aucun écran

Doctrine de la migration 7 : *on ne code pas pour alimenter ce que personne ne lit.* La
traçabilité « quel run a appris quoi » est portée par `execution_id` dans le JSONL, et le sidecar
est archivé avec les autres artefacts du run.

⚠️ **Argument renforcé par un constat** : le gabarit « colonne → API → écran » de `0007` B+ n'a
**jamais été mené au bout** — `FieldFallbackNotice.vue` n'est monté par aucune page (vérifié :
aucune référence hors du composant et de son test). Ajouter une colonne sans écran aurait reproduit
le même angle mort. **Si le porteur veut voir les règles apprises à l'écran, c'est un lot distinct
qui commence par réparer ce trou-là.**

---

## Ce qui a été trouvé en chemin (et qui n'était pas au plan)

**Il y a 5 sites qui lèvent `DonneeRefuseeError`, pas 3.** Le plan initial en connaissait 3.
Le site du **comptage** (`check_count_increased_by_one`) est celui par lequel passaient
**4 des 6 faux `non_conforme` mesurés** — donc le plus rentable, et il avait été oublié.

**Le 5ᵉ site n'apprend rien, délibérément.** `attach_file` lève la même exception quand l'agent
emploie le mauvais step sur un champ qui n'est pas un fichier. **L'application n'a rien refusé** :
c'est notre code de test qui est faux. En faire une règle remplirait l'annuaire de faits sur notre
propre outil. Un test verrouille cette exclusion, pour que personne ne « corrige » l'oubli apparent.

**Un piège de normalisation de route, latent depuis toujours.** `normaliser_route` retire un
préfixe de deux lettres qu'elle prend pour une langue — et `my` est un code ISO 639-1 valide
(birman). Sur le portail mesuré ça ne se voit pas : il redirige vers `/en/my/home`, le `/en` part,
et la clé stockée est bien `/my/home`. **Mais une URL sans locale donne `/home`** — une clé qui ne
correspond à rien dans l'annuaire. Une règle apprise se serait perdue **en silence**.
Corrigé en **contenant** le risque : le rapprochement passe par `_meme_route` (comparaison par
segments, celle que l'annuaire utilise déjà), jamais par égalité de chaînes. Corriger la regex
elle-même changerait les clés d'une référence versionnée — hors périmètre, et documenté.

**Un défaut trouvé par un test de garde, pas à la relecture.** Une classe apprise (`\d`) faisait
produire `11111111` sur un `<select>` — **exactement la valeur inventée que `0019` a corrigée**.
Les champs à options réelles sont désormais traités à part : une règle apprise peut **écarter**
une option refusée, jamais en **inventer** une.

---

## Ce qui est livré

| Où | Quoi |
|---|---|
| `_base_helpers.py` | `RefusMesure`, payload sur `DonneeRefuseeError` (`str(exc)` **inchangé**), `lever_donnee_refusee` (site de construction **unique**), sondes JS enrichies (drapeau `ValidityState` + propriété DOM), 4 sites d'émission |
| `generation/regles_apprises.py` | le store : `charger` (cache mtime, ne lève jamais), `enregistrer` (append JSONL), `pour_champ`, `fusionner` (**copie**, `setdefault`) |
| `generation/valeur_conforme.py` | `_premier_candidat` (l'historique, **inchangé**) + variation bornée (`_MAX_VARIANTES=5`), liste noire, `classe_conservee` |
| `generation/memoire_reparation.py` | l'agrégation des faits runtime, rendue pour le prompt, plafonnée |
| `store/repositories.py` | `RepairRepo.historique_pour_cas` — le trou qui rendait chaque session aveugle |
| `execution/behave_{result,runner}.py` | le transport sidecar → store, et l'archivage de la trace |

**Un seul point d'écriture** : `BehaveRunner._apprendre`. `run_service` et `cli.py` clôturent tous
deux une exécution ; le runner est le seul point que les deux traversent (principe 4). Trois bornes :
jamais sur un dry-run · on apprend **même si la version est rejetée** (un refus mesuré est un fait
sur l'application, adopter une version est une décision sur notre code) · best-effort, jamais fatal.

### Les invariants, tenus par des tests

- **`data/domain/*.json` n'est jamais réécrit** — empreinte comparée avant/après un cycle complet ;
- **sans règle apprise, la valeur produite est INCHANGÉE** — vérifié sur les **161 champs requis**
  de l'annuaire réel, 0 différence ;
- **la fusion ne mute pas le modèle servi par le `lru_cache`** (`formulaires_requis` partage son
  sous-dictionnaire `contraintes` — le muter empoisonnerait l'annuaire en mémoire) ;
- **le prompt système de réparation reste indépendant du cas** — sinon le cache Anthropic,
  aujourd'hui partagé par tous les cas, serait détruit pour tout le monde ;
- **le step libre « je renseigne le champ … » n'est PAS filtré** — un scénario négatif écrit
  délibérément une mauvaise valeur, c'est son sujet. Garde **détective**, jamais bloquante
  (borne du principe 2).

**Chaque GARDE a été vérifiée par sabotage** : 7 sur l'émission, 4 sur le transport, 4 sur le
résolveur, 2 sur la mémoire — toutes tombent sur le comportement d'avant.

**1167 tests verts** (915 avant, +252).

---

## Ce que ça ne prouve pas encore

⚠️ **Aucun test unitaire ne peut prouver ce chantier.** `PLAN.md` §4 le répète : ces défauts
n'existent que sur une **base vécue**, et les tests partent tous d'un monde neuf. Reste à faire :

1. **rejouer `fournisseur_creation` deux fois en réel** — la 1ʳᵉ doit apprendre la règle, la 2ᵈᵉ ne
   doit plus produire la valeur refusée ;
2. **rejouer un même cas sur deux sessions de réparation**, et comparer le coût avant/après — c'est
   le seul chiffre qui justifie le volet mémoire.

⚠️ Le banc **dépense** (~0,09 $/cas) et **exécute réellement** contre l'application : sauvegarder
`data/` avant.

**Aucune constante n'a été ajustée** (`REPAIR_BUDGET_DEFAULT=2`, stall inatteignable) : c'est la
mesure qui dira laquelle bouger, pas une supposition.

---

## Tensions ouvertes

**T5 — le 4ᵉ verdict recouvre deux choses.** `attach_file` lève `DonneeRefuseeError` pour un
mauvais step de l'agent : ce n'est pas « l'application a refusé notre donnée » mais « notre code de
test est faux » (`broken_test_code`). Exclu de l'apprentissage, mais **son classement n'est pas
corrigé** — à instruire séparément.

**T7 — un apprentissage est un rétrécissement permanent.** Un refus serveur transitoire noircit une
valeur durablement. La direction du dommage est sûre et une ligne se supprime, mais **aucune
expiration automatique n'est proposée**. J'ai refusé d'inventer un seuil (« n'appliquer qu'après
2 occurrences ») : ce serait la constante non mesurée que `PRINCIPES.md` reproche. `occurrences`
est enregistré **pour permettre de le calibrer plus tard, sur du réel**.

**T6 — concurrence.** L'append d'une ligne courte est robuste en pratique, pas garanti par contrat
sur Windows. Acceptable tant que les campagnes d'un projet restent séquentielles.
