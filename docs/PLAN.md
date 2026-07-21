# PLAN — état réel et route jusqu'au produit fini

> **Version 1 — 2026-07-21.** Document de référence **vivant** : il dit ce qui EST vrai
> aujourd'hui, ce qui est DÉCIDÉ, et ce qui RESTE. À mettre à jour à chaque jalon.
>
> ⚠️ **Pourquoi ce fichier existe.** Un plan validé oralement (le « A/B/C ») s'est **perdu entre
> deux conversations** : seules deux traces en commentaire de code en avaient survécu. La reprise
> suivante a donc dérivé sur un ordre inventé, jusqu'à ce que le porteur le signale. **Un plan qui
> ne vit que dans une conversation n'existe pas.** Celui-ci vit dans le dépôt.
>
> Hiérarchie des documents : le **brief produit** reste la seule source de vérité (avec son
> journal d'amendements). `0022` fige la structure cas/run/résultats. Les **notes fonctionnelles
> TestRail** cadrent le comportement écran par écran. **Ce plan-ci est subordonné aux trois.**

---

## 1. Ce que le produit fait aujourd'hui — le parcours COMPLET par l'interface

```
Créer un projet  →  saisir/corriger sa connexion (l'application testée)
   →  EXPLORER l'application (crawl déterministe, aucun LLM) → sa cartographie
   →  créer un module
   →  créer un cas :
         • « Ajouter un cas de test »   = saisie MANUELLE (métier, sans IA)
              puis « Automatiser avec l'IA » → son test technique
         • « Générer des cas de test »  = l'IA depuis une spec (texte OU fichier)
              → pause : l'IA rédige le métier, l'humain corrige → puis le Gherkin
   →  regrouper des cas en CAMPAGNE (run) — TRANSVERSE multi-modules
   →  LANCER la campagne (cas joués en séquence) → résultats par cas × run
   →  CLÔTURER la campagne (lecture seule, réversible)
   →  suivre la qualité dans le temps (onglet « Qualité de génération »)
```

**Chaque maillon est prouvé en réel**, pas seulement testé. Coût mesuré : **~0,11 $ par cas**
(≈ 10 % de la cible du §9).

### Les chiffres du jour

| | |
|---|---|
| Tests | **630 Python · 73 vitest** |
| Schéma | `user_version = 16` |
| Fiabilité — réussite technique au 1ᵉʳ jet | **75 %** sur le banc (n=4), **80 %** cumulé projet |
| Coût d'un cas (analyse + génération) | ~0,11 $ |

---

## 2. Décisions structurantes prises pendant cette session

| Décision | Portée |
|---|---|
| **Les deux boutons ont des rôles DISTINCTS** | « Ajouter » = manuel sans IA ; « Générer » = IA. Ils étaient confondus (« Ajouter » lançait l'IA), source de la confusion. |
| **Amendement §4.3** (journal du brief) | La validation du **métier** à la création **vaut relecture** — plus de gate humain séparé sur le Gherkin. Approbation automatique mais **tracée** (`validation-metier`), jamais silencieuse. |
| **Un cas ne s'exécute pas seul** | Le lancement a quitté la page du cas : l'exécution vit dans un **run**. |
| **Le budget de réparation quitte le cas** | Il se gère au niveau du run. |
| **L'annuaire est propre au PROJET** | `data/domain/projet-{id}.json` — `0005` appliqué à ce qui lui avait échappé. Deux instances Odoo ne partagent plus leur cartographie. |
| **Onglet Confirmations supprimé** (front + back) | L'arbitrage humain des diagnostics (`0013`) est retiré. ⚠️ La **réparation automatique** (`0014`) est intacte — elle ne partageait que la table. |
| **Archivage d'un run** | Clôture = lecture seule, **réversible**, garde côté serveur. Distinct du statut (`draft/running/completed`). |
| **Filtrage dynamique** | Retiré de l'écran (reporté, `0022` 8.a). Le serveur le refuse explicitement. |

---

## 3. Ce qui RESTE — la route jusqu'au produit fini

### Phase 1 — Consolider *(en cours)*

- [x] **Écrire ce plan** + réalignement de la documentation.
- [ ] **Finir la fiabilité** :
  - [ ] `demande_avoir` — dernier échec du banc (`partner_email` introuvable, timeout). Cause
        différente des champs fichier, non diagnostiquée.
  - [ ] **Élargir le banc à ~8 specs.** ⚠️ **n = 4 n'est pas un chiffre solide** : c'est une
        tendance, pas une statistique.

### Phase 2 — Rendre déployable

- [ ] 🔴 **Mot de passe de connexion en clair** dans SQLite — **bloquant avant tout usage client**.
- [ ] **Repli silencieux vers `localhost:10017` / `admin`** quand un projet n'a pas de connexion :
      un run peut réussir contre **une autre application que celle affichée**.
- [ ] **La cible n'est pas tracée dans l'historique** : `execution` n'enregistre aucune URL — un
      rapport ne dit pas contre quoi il a tourné.
- [ ] **Une seule identité pour trois usages** (navigateur, RPC de test, RPC d'exploration).
      Conséquence produit : impossible de tester « un employé ne doit pas voir la page admin » —
      ça bloque toute une famille de cas « erreur / permission ».

### Phase 3 — Compléter *(confort, pas essentiel)*

- [ ] **Le Plan** (conteneur de runs) — incrément 2. Le Run couvre déjà le JTBD essentiel.
- [ ] **Snapshot d'un run clos** (décision n°2 des notes fonctionnelles) — reporté et assumé :
      un cas modifié après clôture s'affiche dans son état actuel.
- [ ] Jalons · défauts (interne vs référence externe) · historique en diffs · rôles et permissions.
- [ ] **Multi-connecteur** — ⚠️ à ne PAS abstraire avant d'avoir un **deuxième** connecteur réel :
      avec une seule implémentation, toute interface serait une supposition. `connector_type` est
      aujourd'hui une **étiquette**, pas un point d'aiguillage (`OdooConnector` est câblé en dur).

---

## 4. Le banc de mesure — l'instrument à préserver

`scripts/mesure_taux_erreur_technique.py` + les specs de `specs/mesure/` + l'onglet **Qualité**.

Il répond à **une** question : *un test fraîchement généré tourne-t-il sans erreur technique ?*
(axe **exécution** — un test qui tourne et détecte un vrai bug est un **succès** technique.)

**Il est rejouable** : il trace ses artefacts (`specs/mesure/.artefacts.json`) et supprime ceux de
la mesure précédente. C'est ce qui permet de mesurer une **évolution**, pas un instantané.

⚠️ Il **dépense** (~0,11 $/cas) et **exécute réellement** contre l'application. Backup avant.

### Ce qu'il a déjà trouvé — que 626 tests verts ne voyaient pas

1. **Les champs fichier** : l'agent remplissait un `<input type="file">` comme du texte. Il ne
   *pouvait* pas réussir — la bibliothèque n'avait **aucun step d'upload**. 13 des 37 routes ont un
   champ fichier requis : c'était un **plafond structurel**. → 25 % → **75 %**.
2. **Un cas dans une campagne était insupprimable** (FK `test_run_case` oubliée de la cascade) —
   le **même** défaut que celui déjà documenté pour `cost_ledger`, rejoué un mois plus tard.
3. **Supprimer un cas laissait sa Spécification orpheline**, ce qui bloquait la regénération du
   même titre. 8 fantômes dans la vraie base.

> **La leçon, répétée trois fois** : ces défauts n'existent que sur une **base vécue**. Les tests
> partent tous d'un monde neuf — c'est leur limite structurelle, pas leur faiblesse (§8.8).

---

## 5. Le motif qui revient — *l'annuaire savait, personne ne transmettait*

Quatre fois le même schéma, à chaque fois coûteux :

| # | Ce que l'agent ignorait | Ce que l'annuaire savait déjà |
|---|---|---|
| `0019` | valeur de `<select>` inventée (`"new"`) | les options réelles |
| `0020` | onglet cliqué depuis la mauvaise page | où vit chaque onglet |
| champs requis | 2 champs remplis sur 8 | les 8 champs requis |
| champs fichier | texte écrit dans un champ fichier | le `type` du champ |

**Réflexe à garder** : avant d'améliorer un prompt, vérifier si **la donnée est déjà mesurée** —
et si l'agent a seulement l'**outil** pour l'appliquer.

---

## 6. Dette et écarts connus (assumés, pas oubliés)

- `test_case_version.spec_content` — copie legacy, à supprimer par migration dédiée.
- Colonnes `confirmation_status` / `confirmed_by` de `repair_attempt` : **plus lues ni écrites**
  (feature retirée) mais non droppées — SQLite imposerait de reconstruire la table.
- **4 scripts non commités** (`confirmation_run_9`, `probe_*`, `regeneration_preuve_contrainte`) :
  antérieurs à cette session, jamais relus — je ne commite pas du code que je n'ai pas lu.
- `CONTINUITE.md` reste **périmé au-delà du 2026-07-17** ; ce plan et `BACKLOG.md` font foi.
