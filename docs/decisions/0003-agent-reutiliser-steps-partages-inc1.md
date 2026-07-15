# 0003 — Génération : l'agent doit réutiliser les steps partagés, pas les réinventer (Inc. 1)

Date : 2026-07-15
Statut : acté — reporté à l'Incrément 1
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

## Pistes de correction (à explorer en Inc. 1)

- Rendre les libellés de steps partagés **plus saillants** dans le prompt (liste explicite
  des steps réservés du connecteur actif, déjà amorcée via `_reserved_steps`).
- Renforcer la règle « réutiliser d'abord » : avant d'écrire un step custom, l'agent doit
  justifier qu'aucun step partagé ne couvre le besoin.
- Éventuellement : détecter à la génération les appels réseau bruts (`requests`,
  `/web/dataset/*`) dans les steps produits et les refuser au profit du connecteur/RPC.

## Lien

Même e2e que [[0002-parser-message-erreur-steps-errored-inc1]] : le parser opaque a
masqué la cause (404) que seul le formatter `plain` a révélée — les deux se combinent pour
rendre ce type d'écart difficile à diagnostiquer aujourd'hui.
