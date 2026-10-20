# Guide d'essai — paramètres de test et lignes d'un cas

Tout se fait **à la main**, par toi. Ce guide donne : l'application à tester, l'instance de TestPilot à utiliser, et
chaque valeur à saisir. Version testée : branche locale `lot-pt02g-iterations` (worktree `testpilot-cv01`), rien n'est
en ligne.

---

## 0. Ce dont tu as besoin

| Quoi | Où | Comment le démarrer |
|---|---|---|
| **Le site à tester** : « Boutique de test », page **Contrôle d'accès** | http://127.0.0.1:8095 | configuration `site-essai-lignes` (voir 1) |
| **TestPilot avec l'IA** (dernière version, copie jetable de tes données) | http://localhost:8013 | configuration `testpilot-essai-avec-ia` (voir 1) |

⚠️ **Coût** : dans cette instance, chaque génération appelle l'IA (environ 0,20 à 0,50 $ par cas). La clé est lue dans
`testpilot/.env` au démarrage, jamais copiée. Tes données réelles ne sont pas touchées (copie jetable).

**La règle du site** : l'accès est réservé aux **18 ans et plus**.
- moins de 18 ans → « **Accès refusé : il faut avoir 18 ans ou plus.** »
- 18 ans et plus → « **Bienvenue, <nom du client> !** »
- âge illisible (« dix-sept », « -1 ») → « L'âge doit être un nombre entier entre 0 et 130. »

**Le défaut que tu pourras allumer** : `limite_age_decalee` — le site laisse entrer **dès 17 ans** (seul 17 change).

---

## 1. Démarrer

Dans un terminal, depuis le dossier `testpilot` :

```bash
.venv-v1/Scripts/python.exe C:/Users/RomaricCAPO-CHICHI/AppData/Local/Temp/claude/C--Users-RomaricCAPO-CHICHI-AXENEO-testpilot/149eb401-46c6-4c06-b83f-b8e1ec945b91/scratchpad/pt/site_essai.py
```

Dans un second terminal :

```bash
.venv-v1/Scripts/python.exe C:/Users/RomaricCAPO-CHICHI/AppData/Local/Temp/claude/C--Users-RomaricCAPO-CHICHI-AXENEO-testpilot/149eb401-46c6-4c06-b83f-b8e1ec945b91/scratchpad/pt/lancer_avec_ia.py
```

(Les deux sont aussi dans `.claude/launch.json` : `site-essai-lignes` et `testpilot-essai-avec-ia`.)

**Vérification rapide du site** : ouvre http://127.0.0.1:8095, connecte-toi avec `testeur` / `motdepasse-test`, menu
**Contrôle d'accès**, essaie 17 puis 18.

Ouvre ensuite http://localhost:8013 et connecte-toi avec **ton** compte TestPilot habituel.

---

## 2. Créer le projet

**Nouveau projet** :

| Champ | Valeur |
|---|---|
| Nom du projet | `Essai lignes` |
| Connecteur | `web` |
| Adresse de l'application | `http://127.0.0.1:8095` |
| Identifiant | `testeur` |
| Mot de passe | `motdepasse-test` |
| Page de connexion (si demandée) | `/connexion` |

Dans les réglages du projet :

| Réglage | Valeur |
|---|---|
| **L'IA peut agir sur cette application pendant la génération** | coché |
| **Adresse de remise à zéro** | `/__reset` |

(Ces identifiants sont des valeurs de test fixes du site d'essai : ils ne protègent rien.)

Puis lance l'**Exploration** du projet (carte du projet) et attends qu'elle finisse : la page « Contrôle d'accès » doit
apparaître dans ce qui a été exploré.

---

## 3. Déclarer les données de test du projet

Page **Données de test** du projet → **Ajouter une variable**, trois fois :

| Variable | Description |
|---|---|
| `client` | Nom du client saisi |
| `age` | Âge saisi, en années |
| `resultat` | Message attendu après la vérification |

Dans la ligne **Par défaut**, remplis seulement : `client` = `Dupont SARL`. Laisse `age` et `resultat` vides (ils viendront
des lignes du cas).

*(Facultatif, pour essayer la combinaison projet × cas en 6.3)* : **Ajouter une ligne** nommée `Pro`, avec
`client` = `Martin SA`.

---

## 4. Créer le cas — deux parcours, fais-les tous les deux

### Parcours A : l'IA propose les lignes (IT-3c)

1. **Générer des cas de test** dans le projet, colle cette spécification :

```
Contrôle d'accès selon l'âge

Dans la boutique de test, après connexion, la page « Contrôle d'accès » permet de vérifier si un client peut entrer.
On saisit le nom du client et son âge, puis on clique « Vérifier l'accès ».

Règle : l'accès est réservé aux personnes de 18 ans et plus.
- Moins de 18 ans : le message « Accès refusé : il faut avoir 18 ans ou plus. » s'affiche.
- 18 ans et plus : le message « Bienvenue, <nom du client> ! » s'affiche.
```

2. À l'écran de relecture des cas proposés, le cas sur l'âge doit afficher **« N lignes proposées »** sur sa carte repliée.
   Déplie-le : le tableau **Données de test de ce cas** montre les lignes (attendu : autour de 17 / 18, peut-être 0 ou 19,
   avec `{{age}}` et `{{resultat}}`).
3. Vérifie que les étapes et le résultat attendu emploient `{{age}}` / `{{resultat}}` (et `{{client}}`).
4. Corrige si besoin (une valeur, retirer une ligne), puis **Valider … cas et générer les tests**.

**À observer** : lignes proposées ou non ; valeurs limites ; résultat attendu de chaque ligne juste ; le test généré
emploie bien `{{age}}` et `{{resultat}}` (onglet Script du cas).

### Parcours B : tu saisis les lignes toi-même (IT-3a)

1. **Ajouter un cas** (saisie à la main) :

| Champ | Valeur |
|---|---|
| Titre | `Accès selon l'âge — lignes saisies` |
| Étapes | 1. `Ouvrir « Contrôle d'accès »` · 2. `Saisir le client {{client}} et l'âge {{age}}` · 3. `Cliquer « Vérifier l'accès »` |
| Résultat attendu | `Le message {{resultat}} s'affiche` |

2. Dans la fiche du cas, section **Données de test de ce cas** → **Modifier** :
   - colonnes (« + Colonne ») : `age`, `resultat` ;
   - lignes :

| Ligne | `{{age}}` | `{{resultat}}` |
|---|---|---|
| Mineur | `16` | `Accès refusé` |
| Juste mineur | `17` | `Accès refusé` |
| Majeur | `18` | `Bienvenue` |
| Adulte | `30` | `Bienvenue` |

   - **Enregistrer** → l'en-tête affiche « 4 itérations ».
3. **Automatiser avec l'IA** pour écrire son test.

**À observer** : le test écrit **un seul** scénario avec `{{age}}` et `{{resultat}}` (jamais « 17 » en dur) ; s'il y a
un point de vigilance « donnée » (« même résultat attendu pour toutes les lignes »), c'est que l'« Alors » n'emploie
pas `{{resultat}}`.

---

## 5. Essais de règles (sans IA)

| Essai | Ce que tu fais | Ce qui doit se passer |
|---|---|---|
| Case vide = valeur du projet | Dans une ligne du cas, vide `{{resultat}}` et enregistre | la case affiche « — » (valeur du projet) |
| Nom réservé | Nomme la 1re ligne `Ligne 3` et enregistre | refus : « nom donné d'office à une autre ligne » |
| Valeur interdite | Mets `a"b` dans une case | refus à l'enregistrement |
| Test qui écrit en dur (A59) | Dans l'onglet Script d'un cas à lignes, remplace `{{age}}` par `17` et enregistre | la fiche affiche **« Non joué »** et l'explication ; le lancer le sort « bloqué » |

(Remets `{{age}}` ensuite, ou régénère le test.)

---

## 6. Lancer et lire les résultats

### 6.1 Site sain

**Ajouter une exécution** (automatique) → choisis le cas du parcours B (puis celui du parcours A).
- Données de test : laisse **Par défaut** coché (ou décoche tout : « 1 exécution, valeurs par défaut »).
- **Lignes des cas : Toutes**.
- **Lancer l'exécution**.

**Attendu** : sous le titre du cas, une pastille par ligne, **toutes Passed** :
`1 Mineur · Passed`, `2 Juste mineur · Passed`, `3 Majeur · Passed`, `4 Adulte · Passed`. Le rapport a une colonne
« Résultat » par ligne.

### 6.2 Site avec le défaut à la limite

Allume le défaut (terminal, PowerShell) :

```bash
curl.exe -s -X POST http://127.0.0.1:8095/__defauts -H "Content-Type: application/json" -d "{\"defauts\":[\"limite_age_decalee\"]}"
```

Relance une **nouvelle** exécution du même cas.

**Attendu** : **seule** `2 Juste mineur · Failed` ; les autres Passed ; le cas est Failed.

Éteins le défaut ensuite :

```bash
curl.exe -s -X POST http://127.0.0.1:8095/__defauts -H "Content-Type: application/json" -d "{\"defauts\":[]}"
```

### 6.3 Variantes de lancement

| Essai | Réglage au lancement | Attendu |
|---|---|---|
| Première ligne seulement | Lignes des cas : **La première seulement** | 1 seule itération (Mineur) |
| Combinaison projet × cas | cocher **Par défaut** et **Pro** | 8 itérations : « Par défaut · Mineur » … « Pro · Adulte » ; Majeur/Adulte disent « Bienvenue, Martin SA ! » côté Pro |
| Plage de lignes du projet | (si ≥ 3 lignes de projet) « De la ligne X à Y — Cocher » | seules ces lignes cochées |
| Valeurs figées | lancer, PUIS modifier une ligne du cas, relancer la MÊME exécution | l'exécution rejoue les valeurs d'avant |

---

## 7. Arrêter

Ferme les deux terminaux (Ctrl+C). Rien n'est à nettoyer : le site garde tout en mémoire, TestPilot écrit dans une copie
jetable.

---

## 8. Ce qui n'est pas encore là (normal)

- « De la ligne X à Y » pour les lignes **d'un cas** (seulement Toutes / La première).
- L'écran de l'exécution ne dit pas si « La première seulement » a été choisi.
- Une spécification modifiée (18 → 21 ans) ne signale pas encore les lignes devenues fausses (IT-3d).
- Remplir une colonne avec des clients déjà dans l'application (IT-4).

Note ce que tu constates (ce qui marche, ce qui surprend) : je corrigerai à partir de tes retours.
