# Lot 03 — la preuve qu'une vérification a été exécutée, mesurée de bout en bout (2026-09-24)

**Protocole.** Trois cas écrits **à l'ancienne** (sans `constater`, comme tous les cas générés avant ce lot), exécutés
de bout en bout par `BehaveRunner` + `Executor` (Behave et Playwright réels, sous-processus, connecteur `web`, fixture
locale « torture », aucun appel LLM), sur `master` puis sur ce lot. Script : `l03_e2e.py` (hors dépôt).

| Cas (l'`Alors`) | Behave | Avant (master) | Après (lot 03) |
|---|---|---|---|
| un `assert` nu qui passe (l'URL contient bien `login1`) | vert | `conforme` | `indetermine` / « Retest » — cause `aucun_constat` |
| ne fait qu'attendre la soumission (`j'attends la soumission du formulaire`) | vert | **`conforme`** | `indetermine` / « Retest » — `aucun_constat` |
| l'assertion est dans une branche jamais prise | vert | **`conforme`** | `indetermine` / « Retest » — `aucun_constat` |

Lecture. Les deux dernières lignes étaient de **faux `conforme`** : rien n'avait été vérifié. Ils sont maintenant `indetermine`.
La première est l'effet **voulu et transitoire** de D3 (option 1) : l'assertion s'est bien exécutée, mais elle est nue, donc ne
consigne rien — le cas repasse en « Retest » jusqu'à sa régénération avec la Règle 4 (`constater`). C'est le prix de « pas de
`conforme` sans preuve consignée », pas une régression à minimiser.

## Avec `constater`

Les cas écrits avec la bibliothèque convertie (`tests/test_conformite_constats.py`, mêmes conditions) : un `Alors` qui constate →
`conforme` ; un constat en échec → `non_conforme` ; l'attente seule et la branche non prise → `indetermine`. Et
`constater_visible` / `constater_texte` échouent contre une vraie page qui ne satisfait pas la condition (élément masqué,
absent, texte différent).

## Taille des prompts (aucun appel LLM dans ce lot)

Caractères, fins de ligne normalisées, `origin/master` → ce lot : `system_prompt.md` 24 547 → 25 261 (+714, +2,9 %) ;
`correction_prompt.md` 5 524 → 5 548 ; `repair_prompt.md` 5 974 → 6 018. Le coût par cas n'a **pas** été mesuré.
