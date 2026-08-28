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

Une copie brute de SQLite pendant une écriture peut être incohérente. Pour le pilote, utilisez une
fenêtre de maintenance courte :

1. arrêter le service TestPilot ;
2. vérifier qu'aucun processus n'utilise la base ;
3. archiver tout le répertoire `data/` dans une sauvegarde datée ;
4. conserver les deux clés dans le coffre de secrets, séparément de l'archive non chiffrée ;
5. redémarrer le service et contrôler `/api/health`.

La sauvegarde doit contenir la base, `domain/`, `regles-apprises/`, `executions/` et `reports/`.
Fréquence recommandée : quotidienne et avant chaque mise à jour.

## 7. Test de restauration obligatoire

1. préparer un répertoire temporaire vide ;
2. y restaurer l'archive ;
3. fournir la même `TESTPILOT_SECRET_KEY` ;
4. démarrer une instance de contrôle sur un autre port avec `TESTPILOT_DATA_DIR` pointant dessus ;
5. vérifier la connexion, les projets, un cas, une campagne et un résultat ;
6. arrêter l'instance de contrôle et consigner le résultat.

Ne testez jamais une restauration en écrasant directement l'instance active.

## 8. Mise à jour

1. arrêter le service après avoir annoncé la maintenance ;
2. réaliser une sauvegarde ;
3. récupérer le commit de release identifié ;
4. mettre à jour les dépendances et reconstruire le frontend ;
5. exécuter les tests ;
6. démarrer le service et rejouer les contrôles du §5.

## 9. Limites connues

- serveur unique et SQLite ;
- pilote interne uniquement ;
- absence de scheduler, d'environnements multiples et de champs projet personnalisables ;
- un seul connecteur principal validé ;
- artefacts non purgés automatiquement.

Une ouverture à des clients externes exige une nouvelle revue sécurité et exploitation.
