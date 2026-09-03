# Déployer TestPilot

Ce document est la **référence unique et à jour** pour déployer TestPilot. Il remplace à la fois
l'ancien `docs/DEPLOIEMENT.md` (verrou d'accès partagé, périmé depuis les comptes/rôles du
2026-08-07) et `docs/DEPLOIEMENT-V1-BETA.md` (fusionné ici, supprimé).

Cible : un pilote avec **1 à 3 équipes internes**, sur un serveur unique. Ce n'est pas une
procédure d'exposition directe sur Internet ni d'installation haute disponibilité. Le périmètre et
les critères de GO du pilote sont fixés dans `docs/RELEASE-V1-BETA.md`.

## 1. Architecture

- FastAPI sert l'API et le frontend Vue compilé sur un même port ;
- un reverse proxy fournit HTTPS ;
- la base de données est **SQLite par défaut** (zéro configuration) ou **PostgreSQL**, en option
  (§4) ;
- `data/` conserve aussi les cartographies, règles apprises et artefacts d'exécution — ce
  répertoire local existe quel que soit le moteur de base choisi ;
- des comptes réels et des rôles par projet protègent les données.

Ne lancez pas le serveur Vite (`npm run dev`) en production.

## 2. Installation reproductible

Prérequis : **Python 3.10+** (testé en CI sur 3.10) et **Node.js 22**, accès réseau vers
l'application testée et vers `api.anthropic.com`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m playwright install chromium

Set-Location frontend
npm ci
npm test -- --run
npm run type-check
npm run build
Set-Location ..

python -m pytest -q
```

⚠️ **`playwright install` n'est pas optionnel** : sans navigateur, chaque exécution finira en
erreur technique.

Pour l'installation finale sans outils de développement, `python -m pip install -e .` suffit après
validation de la release — `sqlalchemy`, `alembic` et `psycopg[binary]` (nécessaires à PostgreSQL,
§4) sont des dépendances **principales** du projet (`pyproject.toml`), pas des extras : elles sont
installées même si vous ne comptez utiliser que SQLite, sans étape supplémentaire à prévoir le jour
où vous basculez.

## 3. Configuration obligatoire

Copiez `.env.example` vers `.env` sans versionner ce dernier.

| Variable | Usage |
|---|---|
| `ANTHROPIC_API_KEY` | génération assistée par IA |
| `TESTPILOT_SECRET_KEY` | chiffrement des secrets des connexions projet |
| `TESTPILOT_SESSION_SECRET` | signature des sessions utilisateur |
| `TESTPILOT_ADMIN_USERNAME` | amorçage du premier administrateur sur une base vide |
| `TESTPILOT_ADMIN_PASSWORD` | mot de passe initial, à changer puis retirer |
| `TESTPILOT_COOKIE_SECURE=true` | interdit l'envoi du cookie hors HTTPS |
| `TESTPILOT_SESSION_DAYS=7` | durée recommandée pour le pilote |
| `TESTPILOT_DB_URL` | **optionnel.** Vide = SQLite (défaut). Une URL PostgreSQL (`postgresql+psycopg://…`) bascule le runtime dessus — voir §4 |
| `TESTPILOT_MAX_CONCURRENT_JOBS` | plafond de tâches de fond simultanées (génération, exécution, exploration), défaut 3 — voir `docs/EXPLOITATION.md` |

Générez une clé Fernet pour `TESTPILOT_SECRET_KEY` :

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Générez séparément une autre valeur aléatoire longue pour `TESTPILOT_SESSION_SECRET`. Les deux
secrets ont des responsabilités différentes et ne doivent pas être réutilisés.

Le premier Admin est créé uniquement si la table des utilisateurs est vide. Après sa première
connexion, changez son mot de passe, retirez `TESTPILOT_ADMIN_PASSWORD` de l'environnement, puis
redémarrez le service.

## 4. Choisir le moteur de base de données : SQLite ou PostgreSQL

### 4.1. SQLite — le défaut, zéro configuration

Si `TESTPILOT_DB_URL` est absente ou vide, TestPilot utilise SQLite : le fichier
`data/testpilot.db` (ou `TESTPILOT_DB_PATH` si défini) est créé et son schéma tenu à jour tout
seul — voir §7.1 pour ce que ça implique en migration. C'est le mode adapté à un pilote sur un
serveur unique, léger, sans opération supplémentaire.

### 4.2. PostgreSQL — bascule optionnelle

Le runtime PostgreSQL est **réellement branché**, pas une simple fondation : quand
`TESTPILOT_DB_URL` pointe vers PostgreSQL, `testpilot.store.db.get_initialized_db()` retourne une
`PostgresConnection` (`src/testpilot/store/portable_connection.py`) qui adapte les requêtes
`sqlite3` historiques au dialecte PostgreSQL (via `psycopg`) sans réécrire les repositories. La
preuve tourne en CI contre un vrai PostgreSQL (`.github/workflows/ci.yml`, job *postgres* :
service Docker `postgres:16`, `alembic upgrade head`, puis `tests/test_postgres_runtime.py` et
`tests/test_tables_avec_id_postgres.py`).

Envisagez cette bascule pour un accès concurrent plus robuste ou un outillage de sauvegarde/
supervision géré par une équipe infra — pas par défaut pour le pilote interne.

**Étape 1 — provisionner une base PostgreSQL vide** (14+ recommandé, prouvé en CI sur la 16), avec
un utilisateur dédié. Exemple local jetable (le même schéma que celui de la CI) :

```bash
docker run -d --name testpilot-postgres \
  -e POSTGRES_USER=testpilot -e POSTGRES_PASSWORD=<mot-de-passe> -e POSTGRES_DB=testpilot \
  -p 5432:5432 postgres:16
```

**Étape 2 — appliquer le schéma avec Alembic, AVANT toute connexion applicative** :

```powershell
$env:TESTPILOT_DB_URL = "postgresql+psycopg://testpilot:<mot-de-passe>@<hote>:5432/testpilot"
alembic upgrade head
```

`alembic/env.py` résout l'URL de connexion dans le même ordre que l'application
(`TESTPILOT_DB_URL`, sinon repli sur le chemin SQLite local) — c'est la même variable des deux
côtés, il n'y a rien à garder synchronisé séparément.

**Étape 3 — définir `TESTPILOT_DB_URL` dans le `.env` du déploiement** (jamais commité, jamais en
clair dans un dépôt).

**Étape 4 — migrer les données existantes**, si vous partez d'une instance SQLite déjà en service
(à sauter sur une instance neuve) :

```powershell
python scripts/migrate_sqlite_to_postgres.py `
  --source data\testpilot.db `
  --target-url postgresql+psycopg://testpilot:<mot-de-passe>@<hote>:5432/testpilot
```

Options : `--snapshot-dir` (défaut `data/migration-snapshots`), `--report` (défaut
`data/migration-report.json`).

Ce que le script **garantit**, vérifié en lisant `scripts/migrate_sqlite_to_postgres.py` :

- **la source (`data/testpilot.db`) n'est jamais modifiée** : la première chose faite est un
  instantané cohérent (l'API de sauvegarde SQLite, `sqlite3.Connection.backup()`, en lecture seule
  sur le fichier source) ; toutes les étapes suivantes travaillent sur cet instantané, jamais sur
  l'original ;
- les migrations SQLite éventuellement en attente s'appliquent **sur l'instantané**, jamais sur la
  source ;
- **la destination doit être vide** (aucune table applicative non vide) et **déjà au schéma
  Alembic courant** (étape 2 ci-dessus) — sinon la migration est refusée avant d'écrire quoi que ce
  soit ;
- toute la copie se fait dans **une transaction PostgreSQL unique** ; à l'intérieur de cette
  transaction, pour **chaque table**, le nombre de lignes ET une empreinte SHA-256 du contenu
  (colonnes triées par clé primaire) sont comparés entre la source et ce qui vient d'être écrit
  côté PostgreSQL — au moindre écart, une erreur est levée et **toute la transaction est annulée**
  (rien n'est validé côté PostgreSQL) ;
- les séquences PostgreSQL (`id` auto-incrémentés) sont repositionnées après le `MAX(id)` de
  chaque table une fois la copie validée, pour que les prochaines insertions applicatives
  continuent la numérotation sans collision ;
- **l'instantané est conservé**, y compris en cas d'échec — c'est la preuve et le filet de reprise.

En cas de succès : `Migration validée : N lignes, rapport <chemin>` sur la sortie standard, et un
rapport JSON écrit (`--report`) avec, par table, le nombre de lignes et l'empreinte retenue. En cas
d'échec : `MIGRATION REFUSÉE : <raison>` sur la sortie d'erreur, code de sortie 1, **rien n'est
écrit côté PostgreSQL**.

**Étape 5 — redémarrer le service** avec `TESTPILOT_DB_URL` positionnée. Chaque connexion passe
désormais par `PostgresConnection`, qui vérifie elle-même (une fois par URL, au premier usage)
que le schéma appliqué correspond à la révision Alembic attendue par le code — voir
`docs/EXPLOITATION.md` pour les messages d'erreur exacts et la marche à suivre en cas d'écart.

⚠️ **Ce que PostgreSQL change en exploitation, à lire avant de basculer** :

- les migrations de schéma **ne sont jamais automatiques** sur PostgreSQL — contrairement à
  SQLite (§7.1), il faut lancer `alembic upgrade head` **manuellement avant** chaque redémarrage
  qui suit une mise à jour touchant le schéma (§9) ;
- `scripts/sauvegarder.py` **refuse de s'exécuter** si `TESTPILOT_DB_URL` pointe vers PostgreSQL —
  y compris son appel par défaut sans sous-commande, celui qu'un planificateur système invoquerait
  (vérifié dans le script : le contrôle a lieu avant même l'analyse des arguments). La sauvegarde
  de PostgreSQL est votre responsabilité — service managé avec snapshots, ou `pg_dump`/
  `pg_restore` — voir `docs/EXPLOITATION.md`.

## 5. Démarrage et HTTPS

Lancez un seul processus applicatif :

```powershell
python -m uvicorn testpilot.api.app:app --host 127.0.0.1 --port 8000
```

Le reverse proxy publie `https://testpilot.<domaine-interne>` vers `http://127.0.0.1:8000`. Le port
8000 ne doit pas être directement accessible aux utilisateurs. Le mode `--reload` est réservé au
développement.

`TESTPILOT_COOKIE_SECURE=true` exige un accès HTTPS : sous HTTP, le navigateur ne renverrait pas le
cookie et la connexion semblerait échouer.

## 6. Vérifications après démarrage

```powershell
Invoke-RestMethod https://testpilot.<domaine-interne>/api/health
```

Résultat attendu :

```json
{"status":"ok","version":"0.1.0","access_lock":true}
```

Puis vérifiez :

1. une URL API protégée sans session répond 401 ;
2. l'administrateur peut se connecter ;
3. la page Projets apparaît avant l'entrée dans un projet ;
4. un compte Lecture seule ne peut rien modifier ;
5. un membre ne peut ouvrir une URL appartenant à un autre projet ;
6. thèmes clair et sombre n'occultent aucune action principale.

Pour un contrôle continu de la santé de l'instance (y compris la charge des tâches de fond), voir
`docs/EXPLOITATION.md`.

## 7. Sauvegarde

TestPilot combine deux mécanismes complémentaires — aucun ne remplace l'autre. **Ils ne couvrent
que SQLite** ; sur PostgreSQL, voir l'avertissement de fin de §4.2 et `docs/EXPLOITATION.md`.

### 7.1. Automatique, avant chaque migration (SQLite)

À **chaque connexion SQLite ouverte** — en pratique, dès le tout premier accès à la base après un
redémarrage du serveur (l'amorçage du premier Admin s'il est configuré, sinon la première requête
authentifiée) — avant qu'une migration de schéma en attente n'écrive quoi que ce soit dans
`testpilot.db`, le code (`testpilot.store.db.get_initialized_db`, pas une consigne documentée à
part) copie la base telle quelle à côté d'elle-même :
`testpilot.db.avant-migration-{schéma de départ}-{horodatage}`. Sur une base déjà à jour ou neuve,
aucune copie n'est produite — rien ne migre, rien à sauvegarder. Si la copie échoue (disque plein,
droits insuffisants) alors qu'une migration allait réellement s'exécuter, le démarrage est
**refusé** et journalisé en `CRITICAL` : mieux vaut un serveur qui ne démarre pas qu'une migration
jouée sans filet. Ce mécanisme ne couvre QUE l'instant de la migration ; il ne remplace pas une
politique de sauvegarde périodique.

### 7.2. Périodique, via `scripts/sauvegarder.py` (SQLite)

Un script autonome, appelé par le **planificateur du système** (pas un thread dans le process
`uvicorn`) :

```powershell
python scripts/sauvegarder.py
```

Copie `data/testpilot.db` (à chaud, via l'API `sqlite3.Connection.backup()` — sûre même si le
serveur écrit au même moment, contrairement à une copie de fichier brute) vers `data/sauvegardes/`,
horodatée, puis applique une **rétention** : les 30 plus récentes sont conservées par défaut
(`--garder N` pour ajuster), les plus anciennes au-delà sont supprimées.

Planification recommandée (quotidienne) :

```powershell
schtasks /create /tn "TestPilot - sauvegarde quotidienne" /sc daily /st 02:00 `
  /tr "'C:\chemin\vers\.venv\Scripts\python.exe' 'C:\chemin\vers\testpilot\scripts\sauvegarder.py'"
```

Équivalent `cron` (Linux) : `0 2 * * * /chemin/vers/.venv/bin/python /chemin/vers/testpilot/scripts/sauvegarder.py`.

⚠️ **Ce que `scripts/sauvegarder.py` NE couvre PAS** : `data/domain/*.json` (déjà versionné par
git — decision `0021`), `data/executions/`, `data/regles-apprises/` et `data/reports/`. Pour un
instantané complet incluant ces éléments, la procédure manuelle ci-dessous reste valable et
recommandée **avant toute mise à jour** (§9) ou campagne massive.

### 7.3. Instantané complet (manuel, avant mise à jour ou campagne massive)

Une copie brute de SQLite pendant une écriture peut être incohérente. Pour un instantané qui
inclut aussi `domain/`, `regles-apprises/`, `executions/` et `reports/`, utilisez une fenêtre de
maintenance courte :

1. arrêter le service TestPilot ;
2. vérifier qu'aucun processus n'utilise la base ;
3. archiver tout le répertoire `data/` dans une sauvegarde datée ;
4. conserver les deux clés (`TESTPILOT_SECRET_KEY`, `TESTPILOT_SESSION_SECRET`) dans le coffre de
   secrets, séparément de l'archive non chiffrée ;
5. redémarrer le service et contrôler `/api/health`.

Fréquence recommandée : quotidienne (couverte par `scripts/sauvegarder.py` pour la seule base) et
systématique avant chaque mise à jour.

## 8. Test de restauration obligatoire

Le cycle complet (créer une base, y écrire, sauvegarder, la perdre, restaurer, comparer) est
**automatisé et vérifié en CI** (`tests/test_sauvegarde_restauration.py`). Pour une restauration
RÉELLE d'une sauvegarde faite avec `scripts/sauvegarder.py` :

```powershell
python scripts/sauvegarder.py restaurer data\sauvegardes\testpilot.db.sauvegarde-20260828-020000 `
  --vers data\testpilot.db
```

Pour un instantané complet (archive §7.3) :

1. préparer un répertoire temporaire vide ;
2. y restaurer l'archive ;
3. fournir la même `TESTPILOT_SECRET_KEY` ;
4. démarrer une instance de contrôle sur un autre port avec `TESTPILOT_DATA_DIR` pointant dessus ;
5. vérifier la connexion, les projets, un cas, une campagne et un résultat ;
6. arrêter l'instance de contrôle et consigner le résultat.

Ne testez jamais une restauration en écrasant directement l'instance active.

## 9. Mise à jour

1. arrêter le service après avoir annoncé la maintenance ;
2. sauvegarder — `python scripts/sauvegarder.py` (SQLite) ou l'instantané complet §7.3 si la mise
   à jour touche autre chose que le schéma ; sur PostgreSQL, un mécanisme externe (pg_dump ou
   snapshot géré, §4.2) ;
3. récupérer le commit de release identifié ;
4. mettre à jour les dépendances et reconstruire le frontend
   (`pip install -e .` / `npm ci && npm run build`) ;
5. **si la base est PostgreSQL**, appliquer les migrations manuellement, `TESTPILOT_DB_URL`
   positionnée, **avant** de redémarrer le service : `alembic upgrade head`. Sans cette étape, la
   première connexion applicative refusera de s'ouvrir (schéma en retard) — voir
   `docs/EXPLOITATION.md`. **Si la base est SQLite**, rien à faire ici : la migration s'applique
   d'elle-même à la première connexion après redémarrage, sous le filet du §7.1 ;
6. exécuter les tests ;
7. démarrer le service et rejouer les contrôles du §6.

## 10. Limites connues

- pilote interne uniquement ; serveur applicatif unique (un seul process `uvicorn`) ;
- SQLite reste le mode par défaut et le plus simple à opérer ; PostgreSQL est disponible (§4) mais
  sa sauvegarde n'est PAS outillée par ce dépôt — à la charge de l'infrastructure qui l'héberge ;
- absence de scheduler applicatif, d'environnements multiples et de champs projet
  personnalisables ;
- un seul connecteur principal validé ;
- artefacts (`data/executions/`) non purgés automatiquement ;
- `scripts/sauvegarder.py` ne planifie rien lui-même (§7.2, appel externe requis), ne couvre que
  `testpilot.db` sur SQLite (pas `data/executions/`, `data/regles-apprises/` ni `data/reports/`,
  §7.3 pour un instantané complet), et refuse totalement de s'exécuter sur PostgreSQL ; aucune
  réplication temps réel.

Une ouverture à des clients externes exige une nouvelle revue sécurité et exploitation.
