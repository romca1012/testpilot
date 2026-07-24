# Déployer TestPilot sur un serveur interne

> **Écrit le 2026-07-24**, pour la cible arrêtée par le porteur : un **serveur interne**,
> **plusieurs testeurs**, pour des tests complets — **même si les verdicts ne sont pas encore tous
> concluants**. Cette procédure a été suivie de bout en bout, elle n'est pas théorique.

---

## Ce que vous obtenez — et ce que vous n'obtenez pas

**Vous obtenez** : le parcours complet (créer un projet → explorer l'application → écrire ou
générer des cas → les regrouper en campagne → lancer → verdict et rapport), un secret de connexion
chiffré au repos, un verrou d'accès partagé, et la trace de **contre quelle application** chaque
résultat a été obtenu.

**Vous n'obtenez pas** — et il vaut mieux le savoir avant qu'après :

- **pas de comptes ni de rôles** (hors V1, §8 du brief) : un mot de passe partagé, et un nom que
  chacun déclare. Ce nom signe les cas ; il n'est **pas vérifié** ;
- **pas de verdicts tous concluants** : il reste des « erreur technique » et des « donnée du test
  invalide ». C'est assumé à ce stade — le §5bis du brief décrit la route pour les faire tendre
  vers zéro ;
- **pas de HTTPS ni de reverse proxy fournis** : à mettre devant l'application si elle sort du
  réseau de confiance (le cookie de session voyage alors en clair).

---

## 1. Prérequis

- **Python 3.10+** et **Node 18+** (uniquement pour compiler l'interface) ;
- accès réseau du serveur vers **l'application à tester** et vers **api.anthropic.com** ;
- une **clé API Anthropic**.

## 2. Installation

```bash
git clone <votre-dépôt> testpilot && cd testpilot
python -m venv .venv && . .venv/bin/activate     # Windows : .venv\Scripts\activate
pip install -e .
python -m playwright install chromium            # le navigateur qui exécute les tests
```

⚠️ **`playwright install` n'est pas optionnel** : sans navigateur, chaque exécution finira en
erreur technique — et l'outil dira honnêtement qu'il n'a pas pu tourner, ce qui ressemblera à un
défaut de l'outil alors que c'est une installation incomplète.

## 3. Configuration

```bash
cp .env.example .env
```

Trois valeurs à renseigner **avant** de démarrer sur un réseau :

| Variable | Pourquoi |
|---|---|
| `ANTHROPIC_API_KEY` | sans elle, aucune génération |
| `TESTPILOT_SECRET_KEY` | chiffre les mots de passe de connexion en base. Sans elle, une clé est créée dans `data/.secret_key` — ça protège les copies de la base, pas un accès à la machine |
| `TESTPILOT_ACCESS_PASSWORD` | **le verrou**. Vide = instance grande ouverte : qui atteint le port lance des tests contre votre application et lit vos rapports |

Générer une clé de chiffrement :

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> 🔑 **Sauvegardez cette clé, séparément de la base.** Sans elle, les mots de passe de connexion
> enregistrés deviennent illisibles — l'outil ne les inventera pas : il dira que le mot de passe
> est manquant et il faudra le ressaisir dans l'écran Projets.

## 4. Compiler l'interface

```bash
cd frontend && npm install && npm run build && cd ..
```

L'API sert ensuite l'interface compilée : **un seul port**, aucun serveur web supplémentaire.

## 5. Démarrer

```bash
uvicorn testpilot.api.app:app --host 0.0.0.0 --port 8000
```

Ouvrez `http://<serveur>:8000`. Avec un mot de passe d'instance configuré, l'écran de connexion
apparaît : chacun saisit **son nom** et **le mot de passe partagé**.

**Vérifiez que le verrou est bien actif** — une seule commande, depuis n'importe où :

```bash
curl http://<serveur>:8000/api/health
# {"status":"ok","version":"0.1.0","access_lock":true}
```

`"access_lock": false` signifie que **l'instance est ouverte** : corrigez avant d'aller plus loin.

> ⚠️ Ne vous fiez pas au journal pour ça. Lancé par la commande ci-dessus, uvicorn ne configure
> pas les journaux de l'application : le message d'état au démarrage n'apparaît pas. C'est
> précisément pourquoi l'état est exposé sur `/api/health` — vérifier une protection ne doit pas
> dépendre d'une configuration de journalisation.

Pour un service permanent (`systemd`, service Windows), lancez la même commande avec le `.env`
chargé et un redémarrage automatique.

## 6. Premier usage

1. **Créer un projet** avec sa connexion **complète** — adresse, base, utilisateur, mot de passe.
   Une connexion partielle fait **refuser** l'exploration, la génération et les lancements : c'est
   voulu, l'outil refuse de travailler sans savoir contre quoi.
2. **Explorer l'application** (gratuit, aucun appel LLM, quelques minutes). Vérifiez le compteur
   de **règles de saisie** sur la carte du projet : à zéro sur un portail qui en a, la mesure est
   à refaire.
3. Créer un module, puis un cas — à la main ou par l'IA — puis une campagne.

## 7. Sauvegardes

Tout l'état tient dans **`data/`** :

| Élément | Contenu |
|---|---|
| `data/testpilot.db` | référentiel complet : projets, cas, versions, exécutions, coûts |
| `data/domain/projet-*.json` | la cartographie mesurée de chaque application |
| `data/executions/<id>/` | la **trace brute** de chaque exécution (journal du moteur, détail par scénario, test joué) |
| `data/.secret_key` | la clé de chiffrement, **si** elle n'est pas dans l'environnement |

> 📈 **`data/executions/` grandit** — quelques dizaines de kilo-octets par exécution. Rien ne le
> purge automatiquement, et c'est délibéré : le projet n'efface jamais d'historique en silence
> (§7 du brief). Surveillez la taille ; pour faire de la place, archivez puis retirez les dossiers
> les plus anciens — l'interface dira alors « la trace a été archivée mais son dossier est
> introuvable », ce qui est la vérité, plutôt que de faire croire qu'aucune trace n'a existé.

```bash
tar czf testpilot-$(date +%F).tar.gz data/
```

⚠️ **Une sauvegarde qui contient la base ET la clé ne protège plus rien** : si la clé est dans
`data/`, chiffrez l'archive ou déplacez la clé vers `TESTPILOT_SECRET_KEY`. C'est la raison
principale de préférer la variable d'environnement.

⚠️ **Avant toute campagne massive, sauvegardez** : les tests créent de vraies données dans
l'application testée, et le banc de mesure dépense (~0,08–0,11 $ par cas).

## 8. Mise à jour

```bash
git pull && pip install -e . && (cd frontend && npm install && npm run build)
```

Les migrations de base s'appliquent **toutes seules** à l'ouverture, dans l'ordre, et sont
idempotentes. Sauvegardez quand même avant : une migration se relit mieux sur une copie.

---

## Ce qu'il reste à faire avant un usage par un client externe

Ce déploiement vise l'**usage interne**. Avant d'ouvrir l'outil hors de l'équipe, il manque —
c'est écrit au brief, ce n'est pas un oubli :

- **des comptes et des rôles** (aujourd'hui : un mot de passe pour tous, et un nom déclaré) ;
- **la vue client externe** (rapport simplifié) ;
- **HTTPS** devant l'application.
