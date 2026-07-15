# 0003 — Génération : l'agent doit réutiliser les steps partagés, pas les réinventer (Inc. 1)

Date : 2026-07-15
Statut : **implémenté** (Inc. 1) — A+B ; C en observation
Priorité : **HAUTE**

## Contexte

Découvert lors du premier e2e complet sur `demande_materiel`. Pour compter les tickets en
baseline, l'agent de génération a fabriqué son propre step + helper `_count_tickets` qui
appelle en HTTP brut l'endpoint interne Odoo `/web/dataset/call_kw` (via `requests`) →
**404**, faisant erreurer les 3 scénarios avant même la soumission du formulaire.

Or la bibliothèque partagée (`behave_runtime/steps_library/_generic_steps.py`) fournit
déjà le comportement, proprement via `context.odoo` (RPC) :

```
Soit le nombre d'enregistrements dans le modèle "helpdesk.ticket" est enregistré pour comparaison
```

L'agent aurait dû réutiliser ce step (le prompt le lui demande — « Règle 2 : ne pas
redéfinir les steps partagés ») au lieu d'en réinventer un, cassé.

## Décision

Améliorer la fiabilité du prompt/de la boucle de génération en **Incrément 1** (hors
périmètre PoC).

## Pourquoi priorité HAUTE

Ce n'est pas un détail de ce test précis : c'est un problème de **fiabilité du prompt de
génération à l'échelle**. Le brief identifie explicitement ce type d'écart (l'agent qui
diverge des conventions / réinvente au lieu de réutiliser) comme la **cause racine du coût
de génération** quand on passe à beaucoup de cas. Chaque réinvention = itérations
supplémentaires, tokens supplémentaires, tests plus fragiles.

## Diagnostic réel (à l'implémentation) — ce n'était pas de la désobéissance

Mesuré avant de corriger :

| Fait | Valeur |
|---|---|
| Steps partagés existants | **43** |
| Steps effectivement **montrés à l'agent** | **1** (coïncidence de formulation) |
| `OdooConnector.rules()` | `''` → la section « ## Connecteur actif » n'était **jamais** rendue |

Le prompt promettait pourtant : « *La liste exacte des libellés réservés du connecteur actif
est fournie dans sa section dédiée.* » → **promesse en l'air**. `_reserved_steps()` n'alimentait
que `write.py`, pour **rejeter** les collisions — jamais le prompt. On demandait donc à l'agent
de réutiliser un catalogue qu'on ne lui montrait pas, et on ne le sanctionnait que sur une
collision **exacte** de libellé. Sa variante (« le compteur de tickets … est enregistre comme
baseline » vs « le nombre d'enregistrements dans le modèle "…" est enregistré pour comparaison »)
ne collisionnait pas → acceptée, avec son helper `requests` → 404.

**Défaut supplémentaire trouvé en chemin.** L'extraction des libellés se faisait par regex, qui
ne capture que le premier littéral : les libellés écrits en concaténation implicite multi-lignes
étaient **tronqués**, et 12 steps manquaient à l'appel (31 détectés au lieu de 43). La détection
d'`AmbiguousStep` était donc elle-même partiellement aveugle.

## Implémentation (faite) — A + B

**A — Montrer le catalogue.** Nouveau module `generation/steps_library.py` : extraction **par
AST** (le parseur fusionne les littéraux → libellés entiers), source unique pour ce qu'on
*montre* (prompt) et ce qu'on *refuse* (`write.py`). Le prompt système reçoit une section
« Steps partagés disponibles », groupée par mot-clé Gherkin : **43/43** steps exposés. La
promesse en l'air du prompt est corrigée (elle pointe vers la vraie section).

**B — Interdire le transport réinventé.** `write_steps_file` rejette les imports réseau bruts
(`requests`, `urllib`, `httpx`…) et les appels aux endpoints internes (`/web/dataset`,
`/jsonrpc`), avec un message qui **indique l'alternative** (`context.odoo` / `context.page`).
Détection par AST : une mention en commentaire ou docstring n'est pas un faux positif. Vérifié :
le fichier réellement produit par le premier e2e est désormais **refusé**. Règle 3 ajoutée au
prompt système.

**C — écarté pour l'instant** (décision du porteur) : la détection de quasi-doublon sémantique
(libellé « proche » d'un step partagé) reste en observation — à reconsidérer avec des exemples
concrets si le cas se reproduit après plusieurs runs réels.

## Reste à valider

L'effet réel se mesure sur une **génération complète** (coût LLM) : l'agent doit réutiliser le
step de comptage partagé au lieu d'en écrire un. Non fait ici (hors-ligne) ; à observer au
prochain e2e.

## Lien

Même e2e que [[0002-parser-message-erreur-steps-errored-inc1]] : le parser opaque a
masqué la cause (404) que seul le formatter `plain` a révélée — les deux se combinent pour
rendre ce type d'écart difficile à diagnostiquer aujourd'hui.
