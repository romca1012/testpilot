# Déployer TestPilot — V1 bêta interne

Cette procédure vise un pilote avec **1 à 3 équipes internes**, sur un serveur unique. Elle ne
décrit pas une exposition directe sur Internet ni une installation haute disponibilité.

Le périmètre et les critères de GO sont fixés dans `docs/RELEASE-V1-BETA.md`.

## 1. Architecture du pilote

- FastAPI sert l'API et le frontend Vue compilé sur un même port ;
- un reverse proxy fournit HTTPS ;
- SQLite conserve le référentiel ;
- `data/` conserve aussi les cartographies, règles apprises et artefacts d'exécution ;
- des comptes réels et des rôles par projet protègent les données.

Ne lancez pas le serveur Vite (`npm run dev`) en production.

## 2. Installation reproductible

Prérequis : Python 3.12, Node.js 22, accès vers l'application testée et le fournisseur IA.

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

Pour l'installation finale sans outils de développement, `python -m pip install -e .` suffit
après la validation de la release.

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

Générez une clé Fernet pour `TESTPILOT_SECRET_KEY` :

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Générez séparément une autre valeur aléatoire longue pour `TESTPILOT_SESSION_SECRET`. Les deux
secrets ont des responsabilités différentes et ne doivent pas être réutilisés.

Le premier Admin est créé uniquement si la table des utilisateurs est vide. Après sa première
connexion, changez son mot de passe, retirez `TESTPILOT_ADMIN_PASSWORD` de l'environnement, puis
redémarrez le service.

## 4. Démarrage et HTTPS

Lancez un seul processus applicatif pour le pilote SQLite :

```powershell
python -m uvicorn testpilot.api.app:app --host 127.0.0.1 --port 8000
```

Le reverse proxy publie `https://testpilot.<domaine-interne>` vers `http://127.0.0.1:8000`. Le port
8000 ne doit pas être directement accessible aux utilisateurs. Le mode `--reload` est réservé au
développement.

`TESTPILOT_COOKIE_SECURE=true` exige un accès HTTPS : sous HTTP, le navigateur ne renverrait pas le
cookie et la connexion semblerait échouer.

## 5. Vérifications après démarrage

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

## 6. Sauvegarde

TestPilot combine deux mécanismes complémentaires — aucun ne remplace l'autre :

### 6.1. Automatique, avant chaque migration

À **chaque démarrage du serveur**, avant qu'une migration de schéma en attente n'écrive quoi que
ce soit dans `testpilot.db`, le code (`testpilot.store.db.get_initialized_db`, pas une consigne
documentée à part) copie la base telle quelle à côté d'elle-même :
`testpilot.db.avant-migration-{schéma de départ}-{horodatage}`. Sur une base déjà à jour ou neuve,
aucune copie n'est produite — rien ne migre, rien à sauvegarder. Si la copie échoue (disque plein,
droits insuffisants) alors qu'une migration allait réellement s'exécuter, le démarrage est
**refusé** et journalisé en `CRITICAL` : mieux vaut un serveur qui ne démarre pas qu'une migration
jouée sans filet. Ce mécanisme ne couvre QUE l'instant de la migration ; il ne remplace pas une
politique de sauvegarde périodique.

### 6.2. Périodique, via `scripts/sauvegarder.py`

Un script autonome, appelé par le **planificateur du système** (pas un thread dans le process
`uvicorn` — voir le docstring du script pour le pourquoi) :

```powershell
python scripts/sauvegarder.py
```

Copie `data/testpilot.db` (à chaud, via l'API `sqlite3.Connection.backup()` — sûre même si le
serveur écrit au même moment, contrairement à une copie de fichier brute) vers `data/sauvegardes/`,
horodatée, puis applique une **rétention** : les 30 plus récentes sont conservées par défaut
(`--garder N` pour ajuster), les plus anciennes au-delà sont supprimées — comme
`data/executions/`, cette politique ne laisse jamais grossir le dossier sans fin.

Planification recommandée (quotidienne) :

```powershell
schtasks /create /tn "TestPilot - sauvegarde quotidienne" /sc daily /st 02:00 `
  /tr "'C:\chemin\vers\.venv\Scripts\python.exe' 'C:\chemin\vers\testpilot\scripts\sauvegarder.py'"
```

Équivalent `cron` (Linux) : `0 2 * * * /chemin/vers/.venv/bin/python /chemin/vers/testpilot/scripts/sauvegarder.py`.

⚠️ **Ce que `scripts/sauvegarder.py` NE couvre PAS** : `data/domain/*.json` (déjà versionné par
git — decision `0021`, le dupliquer créerait une seconde source de vérité), `data/executions/`,
`data/regles-apprises/` et `data/reports/`. Pour un instantané complet incluant ces éléments, la
procédure manuelle ci-dessous (archiver tout `data/`, service arrêté) reste valable et recommandée
**avant toute mise à jour** (§8) ou campagne massive.

### 6.3. Instantané complet (manuel, avant mise à jour ou campagne massive)

Une copie brute de SQLite pendant une écriture peut être incohérente. Pour un instantané qui
inclut aussi `domain/`, `regles-apprises/`, `executions/` et `reports/`, utilisez une fenêtre de
maintenance courte :

1. arrêter le service TestPilot ;
2. vérifier qu'aucun processus n'utilise la base ;
3. archiver tout le répertoire `data/` dans une sauvegarde datée ;
4. conserver les deux clés dans le coffre de secrets, séparément de l'archive non chiffrée ;
5. redémarrer le service et contrôler `/api/health`.

Fréquence recommandée : quotidienne (couverte par `scripts/sauvegarder.py` pour la seule base) et
systématique avant chaque mise à jour.

## 7. Test de restauration obligatoire

Le cycle complet (créer une base, y écrire, sauvegarder, la perdre, restaurer, comparer) est
**automatisé et vérifié en CI** (`tests/test_sauvegarde_restauration.py`) — ce n'est pas juste une
procédure documentée jamais exercée. Pour une restauration RÉELLE d'une sauvegarde faite avec
`scripts/sauvegarder.py` :

```powershell
python scripts/sauvegarder.py restaurer data\sauvegardes\testpilot.db.sauvegarde-20260828-020000 `
  --vers data\testpilot.db
```

Pour un instantané complet (archive §6.3) :

1. préparer un répertoire temporaire vide ;
2. y restaurer l'archive ;
3. fournir la même `TESTPILOT_SECRET_KEY` ;
4. démarrer une instance de contrôle sur un autre port avec `TESTPILOT_DATA_DIR` pointant dessus ;
5. vérifier la connexion, les projets, un cas, une campagne et un résultat ;
6. arrêter l'instance de contrôle et consigner le résultat.

Ne testez jamais une restauration en écrasant directement l'instance active.

## 8. Mise à jour

1. arrêter le service après avoir annoncé la maintenance ;
2. réaliser une sauvegarde (`python scripts/sauvegarder.py`, ou l'instantané complet §6.3 si la
   mise à jour touche autre chose que le schéma) ;
3. récupérer le commit de release identifié ;
4. mettre à jour les dépendances et reconstruire le frontend ;
5. exécuter les tests ;
6. démarrer le service et rejouer les contrôles du §5.

⚠️ Le redémarrage à l'étape 6 sauvegarde LUI-MÊME la base juste avant toute migration de schéma en
attente (§6.1) — un filet de sécurité automatique, pas un remplacement de l'étape 2 : il ne
couvre que l'instant de la migration, pas une régression applicative découverte après coup.

## 9. Limites connues

- serveur unique et SQLite ;
- pilote interne uniquement ;
- absence de scheduler, d'environnements multiples et de champs projet personnalisables ;
- un seul connecteur principal validé ;
- artefacts non purgés automatiquement ;
- `scripts/sauvegarder.py` ne planifie rien lui-même (§6.2, appel externe requis) et ne couvre que
  `testpilot.db` — pas `data/executions/`, `data/regles-apprises/` ni `data/reports/` (§6.3 pour
  un instantané complet) ; aucune réplication temps réel, ni sauvegarde d'un futur backend Postgres.

Une ouverture à des clients externes exige une nouvelle revue sécurité et exploitation.
