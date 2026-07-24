# Comprendre TestPilot — document d'accueil

> **Pour qui.** Un développeur ou un chef de projet qui arrive sur le projet et doit, en une
> lecture, comprendre **ce que fait le produit**, **avec quoi il est construit**, et **où toucher**.
>
> Écrit le 2026-07-24. Compte 45 minutes de lecture attentive, puis 30 minutes pour l'installer.
>
> ⚠️ **Ce document n'est pas la source de vérité.** Elle est dans
> `docs/brief-produit-outil-test-management-ia.md`, avec son journal d'amendements. Ici on
> **explique** ; là-bas on **décide**. En cas de contradiction, c'est le brief qui a raison.

---

## 1. Le problème, avant l'outil

Une équipe qui recette un ERP (ici Odoo) vit avec deux plaies :

1. **Écrire les tests coûte plus cher que les jouer.** Rédiger 200 cas fonctionnels prend des
   semaines, et ils se périment à la première évolution.
2. **Le statut « testé » ment.** Dans la plupart des outils de test management, « Passed » est une
   **case qu'un humain coche**. Rien ne garantit que quoi que ce soit ait tourné.

TestPilot attaque les deux : l'IA **écrit** les tests à partir d'une spécification, et la machine
les **exécute réellement** contre l'application. Le statut n'est jamais déclaratif — il est la
**conséquence d'une exécution**.

### La phrase qui résume le produit

> **Un outil qui ne dit jamais « ça marche » sans pouvoir le prouver, ni « c'est cassé » sans
> pouvoir le montrer.**

Tout le reste — l'architecture, les quatre verdicts, la relecture humaine — découle de cette
phrase. Si tu ne retiens qu'une chose de ce document, retiens celle-là : elle explique la plupart
des choix qui paraissent, au premier coup d'œil, trop prudents.

---

## 2. Le parcours, de bout en bout

```
CRÉER UN PROJET          ─ on saisit la connexion à l'application testée (URL, base, compte)
   ↓
EXPLORER l'application   ─ crawl DÉTERMINISTE, aucune IA → une cartographie des écrans et champs
   ↓
CRÉER UN MODULE          ─ un périmètre fonctionnel ("Demandes", "Achats"…)
   ↓
OBTENIR DES CAS          ─ deux chemins, au choix :
   │                        • saisie MANUELLE du cas métier, puis « Automatiser avec l'IA »
   │                        • « Générer des cas » depuis une spécification (texte ou fichier)
   ↓
RELECTURE HUMAINE        ─ le « gate » : un cas généré par l'IA ne s'exécute PAS avant approbation
   ↓
COMPOSER UNE CAMPAGNE    ─ un lot de cas, transverse aux modules, à sélection FIGÉE
   ↓
LANCER                   ─ Behave + Playwright pilotent un vrai navigateur sur la vraie appli
   ↓
VERDICT + RAPPORT        ─ deux axes, la trace brute, le coût réel
   ↓
CLÔTURER                 ─ lecture seule, réversible
```

**Le cas d'usage fondateur** (celui qui justifie le produit) : *« l'application a changé — quels
modules dois-je retester ? »* Il n'est **pas encore livré** : c'est le principal reste à faire.

---

## 3. Les six idées à comprendre avant de toucher au code

Ce sont elles qui expliquent le code. Sans elles, beaucoup de choix ressemblent à de la complexité
gratuite.

### 3.1 Le verdict a **deux axes**, jamais un seul

Un statut unique force à mentir. Si le test plante au démarrage, est-ce « échec » ? L'application
n'a rien fait de mal. Alors on sépare :

| Axe | Répond à | Valeurs |
|---|---|---|
| **Exécution** | *le test a-t-il pu tourner ?* | succès / erreur technique |
| **Fonctionnel** | *l'application est-elle conforme ?* | conforme / non conforme / **donnée du test invalide** |

Le **quatrième verdict** — « donnée du test invalide » — est essentiel : il dit *« mon test est
mauvais »* au lieu d'accuser l'application. Il vient d'un défaut réel : le test saisissait une
valeur que le formulaire refuse, le navigateur bloquait l'envoi en silence, et l'outil concluait à
un bug applicatif. **12 des 21 routes à champ requis étaient concernées.**

### 3.2 L'outil n'accuse **jamais** sans preuve

Règle qui prime sur toutes les autres. Si l'application ne crée rien **et** n'affiche aucun message
d'erreur, l'outil nomme ce **« refus silencieux »** au lieu de le convertir en défaut. Un faux
« non conforme » détruit plus de confiance que dix « je ne sais pas ».

### 3.3 Un cas généré par l'IA ne s'exécute pas avant **relecture humaine**

C'est le **gate** (`verdict/review_gate.py`). L'approbation porte sur la **version** : rejouer la
même version approuvée ne redemande rien ; une spécification qui évolue produit une nouvelle
version, qui repasse par le gate. L'IA propose, l'humain engage.

### 3.4 Le LLM produit une **intention**, un résolveur **déterministe** l'exécute

L'IA n'invente pas les sélecteurs CSS ni les noms techniques des champs. Elle dit *« remplir le
champ Client »* ; un résolveur déterministe traduit ça en un vrai champ, en s'appuyant sur
l'**annuaire du domaine** (`data/domain/*.json`).

Cet annuaire est **produit par un crawl sans IA, versionné dans git, et relu par un humain** avant
adoption — pour deux raisons qu'il faut avoir en tête :

- un crawl à chaud rendrait l'écran de relecture dépendant de la disponibilité d'Odoo ;
- **un modèle qui se met à jour tout seul n'est plus une référence** : si l'application régresse
  (un champ disparaît), le crawl enregistrerait la régression comme la nouvelle vérité. C'est
  exactement le faux négatif que ce projet traque.

### 3.5 Supprimer, c'est **masquer**. Détruire est un autre geste

Rien ne quitte la base sur un clic de suppression : on marque `deleted_at`, la corbeille permet de
restaurer, et la visibilité est **hiérarchique** (un cas dont le module est à la corbeille disparaît
sans être marqué lui-même). La destruction réelle est `purger()`, un geste distinct et
irréversible, réservé à ce qui est déjà à la corbeille.

⚠️ **Aucune cascade n'est déclarée en base** (`ON DELETE CASCADE`), et c'est délibéré : elle
détruirait vraiment là où la suppression douce veut masquer. Détail complet dans
**`docs/LOGIQUE.md`**.

### 3.6 Une décision se prend d'**un seul côté**, et c'est le serveur

Le frontend affiche ; il ne juge pas. Ça a été appris à nos dépens : le « statut de lecture »
(*Passed / Failed / Retest / Blocked / Untested*) vivait uniquement en TypeScript, et il a fallu le
réécrire en SQL le jour où on a voulu filtrer côté serveur — deux implémentations d'une même règle,
qui divergent silencieusement. Quand la même valeur doit vraiment exister sous deux formes, **un
test les compare exhaustivement**.

---

## 4. La stack technique

### Backend — Python 3.10+

| Brique | Version | Rôle | Pourquoi celle-là |
|---|---|---|---|
| **FastAPI** | ≥ 0.115 | l'API HTTP (51 routes) | typage natif, validation d'entrée gratuite, OpenAPI généré |
| **Uvicorn** | ≥ 0.32 | le serveur | mono-processus, suffisant tant qu'on est sur SQLite |
| **SQLite** | *(stdlib)* | la persistance | zéro administration ; le schéma est écrit en **SQL portable PostgreSQL** pour que la bascule reste possible |
| **Anthropic** | ≥ 0.40 | la génération | Claude, via un adaptateur maison (`llm/adapter.py`) |
| **Behave** | ≥ 1.2.6 | le moteur BDD | Gherkin = un test lisible par le métier, exécutable par la machine |
| **Playwright** | ≥ 1.40 | le pilotage navigateur | attentes automatiques, bien plus stable que Selenium sur un ERP |
| **OdooRPC** | ≥ 0.9 | vérifier en base | on ne croit pas l'écran : on vérifie que l'enregistrement existe vraiment |
| **pdfplumber** | ≥ 0.11 | lire les specs PDF | les spécifications arrivent rarement en Markdown |
| **Jinja2** | ≥ 3.1 | rapports HTML + prompts | |
| **cryptography** | ≥ 42.0 | chiffrer les mots de passe de connexion | Fernet, préfixe `enc:v1:` |

**Outillage dev** : `pytest`, `ruff`, `black` (ligne à 100), `httpx`.

**Modèles par défaut** (surchargeables sans toucher au code) :
`génération` → `claude-sonnet-4-6` · `rapide` et `réparation` → `claude-haiku-4-5`.

### Frontend — Vue 3

| Brique | Version | Rôle | Pourquoi celle-là |
|---|---|---|---|
| **Vue 3** | ^3.5 | l'interface (40 composants) | `<script setup>`, Composition API |
| **vue-router** | ^4.5 | la navigation | |
| **@tanstack/vue-query** | ^5.101 | **la couche de données** | cache, invalidation explicite, états de chargement — arbitré contre un cache maison |
| **Tailwind CSS** | ^3.4 | le style | |
| **Vite** | ^6.0 | build et serveur de dev | |
| **Vitest** + `@vue/test-utils` + `jsdom` | ^2.1 | les tests d'interface | |

> ⚠️ `.npmrc` contient `legacy-peer-deps=true`. Ce n'est pas de la négligence : sans lui,
> l'installation échoue sur un conflit de pairs. Ne le retire pas sans vérifier.

### Le reste

- **`behave_runtime/`** — le harnais d'exécution : `environment.py`, une **bibliothèque de steps
  partagés** (pour que l'IA réutilise au lieu de réinventer), et `generated/` où atterrissent les
  `.feature` et `_steps.py` produits.
- **`data/`** — la base SQLite, les rapports, et `domain/` (l'annuaire versionné, **lui** est dans
  git ; le reste non).
- **`scripts/`** — ~45 scripts de **preuve et de mesure**. Ils ne font pas partie du produit : ce
  sont les expériences qui ont établi les chiffres cités dans les docs. Ne les prends pas pour du
  code applicatif, mais ne les jette pas : ils sont la trace des mesures.

### Volumétrie, pour situer

| | |
|---|---|
| Code Python | 73 fichiers, ~12 900 lignes |
| Tests Python | 86 fichiers, **915 tests** |
| Interface | 40 composants Vue, **110 tests** |
| API | 51 routes + `/api/health` |
| Base | 10 tables, schéma **v24** |
| Décisions écrites | 22 |

---

## 5. La carte du code

```
src/testpilot/
  config.py          source UNIQUE de configuration (tout passe par là, jamais os.getenv ailleurs)
  cli.py             `testpilot run <spec>` — le parcours complet en ligne de commande
  analysis/          spécification → plan de test
  generation/        plan → .feature + steps   ← le cœur, et le plus gros morceau
    react_loop.py      la boucle : tour LLM → outils → dry-run → garde-fous
    domain_model.py    l'annuaire du domaine (versionné, jamais généré)
    repair_agent.py    la réparation bornée d'un test qui échoue
  execution/         dry-run puis exécution réelle (Behave/Playwright)
  verdict/           tout ce qui JUGE : les deux axes, la taxonomie, l'origine du défaut, le gate
  guardrails/        plafonds de coût par cas, disjoncteur de réparation
  connectors/        la cible + le connecteur Odoo
  llm/               adaptateur Anthropic + registre des modèles
  reporting/         rapport JSON/HTML
  store/             SQLite, dépôts, chiffrement des secrets
  api/               FastAPI — routes (HTTP) / services (enchaînements) / erreurs
frontend/src/
  pages/             un écran = un fichier
  components/        briques réutilisables (ui/ = le socle graphique)
  lib/donnees.ts     LA couche de données (vue-query) — les écrans passent par elle
  lib/api.ts         le client HTTP, et lui seul parle au serveur
```

**Où écrire une règle ?** La réponse complète est dans **`docs/LOGIQUE.md`**. En résumé :

| Tu veux… | Ça va dans |
|---|---|
| exposer une capacité en HTTP | `api/routes/` — traduire, jamais décider |
| enchaîner plusieurs étapes | `api/services/` |
| un invariant de données (unicité, visibilité, cascade) | `store/repositories.py` |
| une règle qui **juge** | `verdict/` |
| changer la façon d'écrire un test | `generation/` |
| de l'affichage | `frontend/` — et **rien d'autre** |

---

## 6. Le modèle de données

Dix tables. La hiérarchie porte tout le reste :

```
project ──< module ──< case_group (une spécification)
                 └──< test_case ──< test_case_version ──< review_decision
                                                     └──< execution ──< scenario_result
                                                                  └──< repair_attempt
test_run ──< test_run_case  (une campagne, et les cas qu'elle a figés)
cost_ledger  (chaque dépense LLM, rattachée à un cas)
```

Points à connaître :

- **La version est l'unité qui compte**, pas le cas. Un verdict, une approbation et une exécution
  portent tous sur une **version** précise. C'est ce qui permet de dire *« ce cas passait dans sa
  v2, il échoue en v3 »*.
- **Migrations** : `PRAGMA user_version`, appliquées **automatiquement à l'ouverture**, chacune
  **idempotente**. Tu n'as aucune commande à lancer. Pour en ajouter une, suis le motif de
  `store/db.py`.
- **La sauvegarde, c'est copier un fichier** (`data/testpilot.db`) — la contrepartie de SQLite.

---

## 7. Installer et faire tourner

```bash
pip install -e ".[dev]"
python -m playwright install chromium

pytest                                  # 915 tests
cd frontend && npm install && npm test  # 110 tests
```

**En développement, deux processus :**

```bash
uvicorn testpilot.api.app:app --reload    # API      → :8000
cd frontend && npm run dev                # interface → :5173
```

**En production, un seul** : `npm run build`, et l'API sert l'interface compilée sur son propre
port. Procédure complète et vérifiée : `docs/DEPLOIEMENT.md`.

### Les variables d'environnement qui comptent

| Variable | Effet si absente |
|---|---|
| `ANTHROPIC_API_KEY` | aucune génération possible |
| `TESTPILOT_ACCESS_PASSWORD` | 🔴 **aucune protection** : quiconque atteint le port lance des tests contre ton application et lit tes rapports |
| `TESTPILOT_SECRET_KEY` | les mots de passe de connexion ne sont pas chiffrés au repos |
| `ODOO_ENV` | ⚠️ `prod` **bloque toute exécution** — garde-fou anti-production, ne le contourne pas |
| `TESTPILOT_MODEL_*` | modèles par défaut (change de modèle sans toucher au code) |
| `TESTPILOT_COST_LIMIT_RUN_USD`, `TESTPILOT_MAX_ITERATIONS` | plafonds de sécurité de la boucle de génération |

Tout est lu par **`config.py` et lui seul** : ne fais pas `os.getenv` ailleurs.

---

## 8. Comment on travaille ici

Ces conventions ne sont pas décoratives — elles expliquent la forme du dépôt.

1. **Le brief est la seule source de vérité**, avec son journal d'amendements daté. Un désaccord se
   règle en amendant le brief, pas en codant à côté.
2. **Une décision structurante s'écrit** dans `docs/decisions/NNNN-*.md` : le problème, ce qu'on a
   observé, ce qu'on a tranché. 22 à ce jour — elles se lisent comme l'histoire des pièges déjà
   rencontrés. **Lis-en trois ou quatre avant de proposer une refonte** ; il y a de bonnes chances
   que la question ait déjà été instruite.
3. **On ne détruit pas l'histoire silencieusement.** Ni les données (voir §3.5), ni les mesures.
4. **Un chiffre cité est un chiffre mesuré.** Les scripts de `scripts/` existent pour ça. On
   n'écrit pas « ~90 % » à l'estime.
5. **Les tests disent *pourquoi*.** Beaucoup de fichiers de test s'ouvrent sur un paragraphe qui
   explique le défaut réel qu'ils empêchent de revenir. Quand tu en écris un, fais pareil : dans
   six mois, c'est ce paragraphe qui empêchera quelqu'un de le supprimer par erreur.
6. **Le code et les commentaires sont en français.** C'est la langue du métier ici ; reste dessus.

### La carte des documents

| Document | Ce qu'on y trouve | Quand le lire |
|---|---|---|
| `brief-produit-*.md` | **la vision, la seule source de vérité** | avant toute décision produit |
| `PLAN.md` | l'état réel et la route | pour savoir où on en est |
| `LOGIQUE.md` | où vit chaque règle, et ce qu'une action entraîne | avant d'écrire une règle |
| `CONCEPTION.md` | les règles de conception et les audits | avant de toucher à l'interface |
| `PRINCIPES.md` | ce qu'on ne re-débat plus | une fois, au début |
| `DEPLOIEMENT.md` | installer sur un serveur | le jour du déploiement |
| `BACKLOG.md` | ce qui reste | pour choisir quoi faire |
| `decisions/` | les pièges déjà rencontrés, tranchés | quand une idée te paraît évidente |
| `CONTINUITE.md` | 📍 **périmé** — conservé pour l'histoire | jamais, sauf archéologie |

---

## 9. Les pièges (ce qu'un nouveau se trompe à faire)

- **Ajouter `ON DELETE CASCADE`.** Ça paraît propre, ça casse la suppression douce (§3.5).
- **Calculer un statut en TypeScript.** Le serveur décide (§3.6).
- **Faire `os.getenv` hors de `config.py`.** Une configuration à deux endroits diverge.
- **Supprimer une route « sans appelant »** sans suivre la chaîne *route ← `api.ts` ← écran*.
  L'audit du 2026-07-24 a trouvé trois routes sans appelant qu'il fallait **garder** : une route
  d'exploitation, un rapport imprimable auquel il manquait un lien, et un `logout` qui n'était pas
  du code mort mais une **fonctionnalité manquante**.
- **Faire régénérer l'annuaire du domaine par un LLM.** C'est une référence, pas une sortie de
  modèle (§3.4, décision `0021`).
- **Croire l'écran.** Un formulaire peut afficher un succès sans avoir rien créé. On vérifie en
  base par RPC.
- **Prendre `scripts/` pour du code produit.** Ce sont des expériences.

---

## 10. Où en est le projet

**Ce qui marche de bout en bout, prouvé en réel** : explorer une application, générer des cas
depuis une spécification, les faire relire, les exécuter contre la vraie application, en tirer un
verdict à deux axes avec sa trace, composer et clôturer des campagnes, suivre les coûts. Coût
mesuré : **~0,08 à 0,11 $ par cas**, pour une cible du brief à 1 €.

**Ce qui manque, par ordre d'importance** :

1. 🔴 **Le tableau « modules à retester »** — le cas d'usage fondateur (§2). Tant qu'il n'est pas
   là, l'outil génère et exécute, mais ne **pilote** pas encore une recette.
2. Les mécanismes du §5bis (« zéro verdict non concluant »), à commencer par la règle apprise à
   chaque refus.
3. **Pas de comptes ni de rôles.** Le nom saisi à la connexion est une *signature déclarée*, pas
   une identité. À traiter avant tout usage par un client externe.
4. HTTPS / reverse proxy — côté exploitation.

**Une décision attend le porteur** : le glisser-déposer pour réordonner les cas (décision `0009`)
n'a plus d'écran qui l'appelle. Soit on le remet, soit on retire la capacité — ce n'est pas un
arbitrage de développeur.
