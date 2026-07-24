# LOGIQUE — où vit chaque règle, et ce qu'une action entraîne

> **Écrit le 2026-07-24**, à l'issue de l'audit « ne garder que ce qui sert ».
>
> Ce document répond à deux questions qu'on se pose en ouvrant le code : **« où dois-je écrire
> cette règle ? »** et **« qu'est-ce que cette action entraîne ? »**. Il ne décrit pas
> l'architecture pour la décrire — il existe parce que la logique **s'éparpille** quand personne
> ne dit où elle va, et qu'une règle en double finit toujours par diverger.

---

## 1. Où vit quoi

| Couche | Ce qu'elle porte | Ce qu'elle ne porte **jamais** |
|---|---|---|
| **`api/routes/`** | traduire HTTP ↔ métier : lire les paramètres, appeler, choisir le code d'erreur | une règle métier. Une route qui *décide* est une règle cachée à un seul appelant |
| **`api/services/`** | les enchaînements : générer, lancer une campagne, explorer, réparer | l'accès SQL direct, le rendu |
| **`store/repositories.py`** | l'accès aux données **et les invariants de données** : unicité des noms, visibilité, cascade | une décision de produit (quand générer, quoi exécuter) |
| **`verdict/`** | tout ce qui **juge** : les deux axes, la taxonomie, l'origine d'un défaut, le gate, le statut de lecture | l'affichage |
| **`generation/`** | comment on écrit un test : prompt, résolveur, annuaire, réparation | la persistance |
| **`frontend/src/lib/`** | la **présentation** et l'accès à l'API | une règle métier — voir le cas d'école ci-dessous |

### Le cas d'école, et la règle qu'il a produite

Le **statut de lecture** (« Passed / Failed / Retest / Blocked / Untested ») projette les deux axes
du §5 en une étiquette. Cette règle vivait **uniquement en TypeScript**. Le jour où il a fallu
filtrer une liste par statut côté serveur — pour la pagination — il aurait fallu la réécrire en
SQL : **deux implémentations d'une même règle, qui divergent le jour où l'une évolue, et dont
l'écart est invisible puisque les deux « marchent »**.

> **La règle qui en sort : une décision se prend d'un seul côté, et c'est le serveur.** Le
> frontend affiche, il ne juge pas. Quand la même valeur doit exister sous deux formes
> (ici Python et SQL, parce qu'on ne filtre pas 2 000 lignes en Python), **un test les compare
> exhaustivement** — `tests/test_statut_de_lecture.py` couvre les 24 combinaisons.

---

## 2. Ce qu'une action entraîne

### Les deux mécanismes, à ne pas confondre

- **MASQUER** (`delete`) — rien n'est détruit. La visibilité est **hiérarchique** : un cas dont le
  module est à la corbeille disparaît **sans être marqué lui-même**. C'est le geste de
  l'utilisateur, et il est réversible.
- **DÉTRUIRE** (`purger`) — la cascade réelle, dans l'ordre des clés étrangères. Geste **distinct**,
  irréversible, refusé sur ce qui n'est pas déjà à la corbeille.

⚠️ **Aucune cascade n'est déclarée en base** (`ON DELETE CASCADE`), et c'est délibéré : une
cascade SQL détruirait vraiment là où la suppression douce veut masquer. L'intégrité est tenue
**dans l'application**, où elle est lisible et testable.

### La table des conséquences

| Action | Ce qui disparaît de l'écran | Ce qui est détruit | Réversible |
|---|---|---|---|
| Supprimer un **projet** | ses modules, leurs spécifications, leurs cas, les cas de ses campagnes | rien | oui |
| Supprimer un **module** | ses spécifications, ses cas, ces cas dans les campagnes | rien | oui |
| Supprimer une **spécification** | elle seule — **refusé** tant qu'elle porte des cas | rien | oui |
| Supprimer un **cas** | lui, ses exécutions, sa place dans les campagnes ; + son **enveloppe auto** si elle devient vide | rien | oui |
| **Purger** (depuis la corbeille) | — | tout : versions, relectures, exécutions, résultats, réparations, coûts, liaisons de campagne | **non** |
| **Archiver** une campagne | rien | rien | oui |
| **Restaurer** | rend l'élément **et toute sa descendance** ; ne ressuscite jamais un parent | — | — |

`tests/test_chaine_des_consequences.py` énumère ces lignes **au même endroit** et les vérifie.
C'est le point : dispersées, ces conséquences ne tiennent dans la tête de personne.

### Trois défauts que cette table a trouvés (2026-07-24)

1. 🔴 **Une campagne d'un projet supprimé référençait toujours ses cas.** La sélection vérifiait le
   cas et son module, jamais le **projet**. La lancer aurait exécuté, contre la vraie application,
   des cas que l'utilisateur croyait supprimés.
2. **Une spécification restait consultable** par son identifiant alors que son module ou son projet
   était à la corbeille — un lien direct rouvrait un document censé avoir disparu.
3. **La purge d'un projet échouait** sur la liaison campagne ↔ cas oubliée de la cascade : la clé
   étrangère annulait **toute** la purge. C'est le même défaut que celui corrigé au niveau du cas
   un mois plus tôt, **revenu au niveau du projet** — précisément parce que personne ne tenait la
   liste des conséquences au même endroit.

---

## 3. Ce qui n'existe plus, et pourquoi

L'audit a supprimé ce qui ne servait plus. **Ce qui a été gardé compte autant** :

| Supprimé | Raison |
|---|---|
| `useProjectTree.ts` | aucun import — l'arbre passe par la couche de données |
| `AxisChip`, `CaseRow`, `VerdictVersionNotice` | jamais montés, restes d'écrans retirés |
| 6 méthodes du client API | plus aucun appelant (`renameProject` faisait doublon avec `updateProject`) |
| `GET /api/modules/{id}/groups` | doublon de la liste du projet, qui rend la même chose |

| Gardé, et pourquoi | |
|---|---|
| `GET /api/health` | route d'**exploitation** : la procédure de déploiement s'en sert pour vérifier le verrou. Une route sans appelant dans l'interface n'est pas morte pour autant |
| `POST /api/auth/logout` | ce n'était pas du code mort mais une **fonctionnalité manquante** : sans elle, un poste partagé reste ouvert au suivant. Le bouton a été ajouté |
| `GET .../report.html` | rapport imprimable, réel et testé — il manquait seulement un lien. Ajouté |
| `PUT .../cases/order` | le glisser-déposer (décision `0009`). Son écran a disparu ; **supprimer la route reviendrait à revenir sur une décision produit** — arbitrage du porteur, pas du développeur |

> **La méthode, pour la prochaine fois.** L'analyse statique seule ne suffit pas : une route peut
> n'être appelée que par un script occasionnel. On suit la **chaîne complète** — route ← méthode
> du client ← écran — et on croise avec les scripts et la CLI. Une documentation qui *cite* une
> route n'en est pas un appelant. Et on retire **par petits lots**, un commit par lot, pour
> pouvoir revenir en arrière isolément.
