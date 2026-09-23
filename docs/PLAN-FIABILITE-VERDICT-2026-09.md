# Plan — Fiabilité du verdict et couverture web / ERP

Date : 2026-09-23. Statut : **À VALIDER par le porteur** (registre des décisions, §4).
Exécution : Claude Code, un lot à la fois, via les commandes `.claude/commands/lot-NN-*.md`.
Règles de travail : `CLAUDE.md` à la racine.

## 1. Objectif

Qu'un statut produit par TestPilot soit **vrai** — `passed` veut dire que l'application a été
sollicitée et a prouvé le comportement attendu, `failed` qu'elle a dévié, `blocked` que
l'environnement a empêché de juger, `retest` que le test lui-même est à corriger — et que ce soit
vrai pour une application web quelconque comme pour un ERP Odoo au-delà du portail.

## 2. Point de départ mesuré

`docs/QUALITE-GENERATION-2026-09-22.md` : sur 7 premiers passages, 4 erreurs techniques, 1 seul
verdict métier exploitable. L'audit du 2026-09-23 a identifié les causes suivantes.

### 2.1 Défauts qui rendent un statut faux

| Réf | Où | Défaut | Conséquence |
|---|---|---|---|
| F1 | `_base_helpers.py` : `record_count_not_increased` (l.278), `memorize_record_count` (l.1704), `check_count_not_increased` (l.1772), `check_count_increased_by_one` (l.1987) | Comptage global `search_count([])` | Faux PASSED si un tiers crée pendant que le test échoue ; faux FAILED si deux créations. **Corrigé par le lot 01** (comptage cloisonné par `id > max_id`, affiné par un marqueur de tentative sur les champs à contrainte d'unicité). **Résidu documenté par D10** : sans marqueur (champs sans contrainte d'unicité — la majorité), une création tierce unique dans la même fenêtre de quelques secondes reste indiscernable de celle du scénario ; fermer ce résidu à zéro exigerait un marqueur sur TOUT scénario de création (hors périmètre du lot 01, cf. D10) |
| F2 | `defect_taxonomy.classify_failure` + `@given` de `odoo/_odoo_background_steps.py` et `_odoo_steps.py` | Tout `AssertionError` devient `ASSERTION_MISMATCH`, quel que soit le type de step | Prérequis absent ou bug du test rapporté comme défaut applicatif |
| F3 | `_adaptive_resolution.py`, `executor.py` (retry l.64) | Un vert obtenu par résolution LLM ou au 2ᵉ essai n'est pas distingué | Régressions d'UI absorbées en silence |
| F4 | `status.scenario_verdict` | `passed` → `conforme` sans preuve qu'une assertion s'est exécutée ; `assertion_lint` statique et non bloquant | Tests verts par construction |
| F5 | `status.statut_de_test` | `technical_error` est toujours couplé à `indetermine` → `retest` ; `blocked` n'est jamais produit automatiquement | Panne d'environnement confondue avec script cassé |
| F6 | `environment.py` l.118 et l.397-409 | Teardown limité à `helpdesk.ticket` ; restauration de `employee_front_role_ids` (champ Sapian) dans le harnais générique | Pollution, collisions d'unicité au rejeu, code client dans le socle |

### 2.2 Manques de couverture

| Réf | Périmètre | Manque |
|---|---|---|
| C1 | Web générique | Aucun step de connexion à l'exécution : `WEB_USER`/`WEB_PASSWORD` posés dans `before_all`, jamais utilisés, alors que l'exploration se connecte (`tenter_connexion_generique`) |
| C2 | Web générique | Pas de `storage_state`, pas de stratégie d'auth déclarée (TOTP, session injectée, SSO) |
| C3 | Tous | `new_context()` sans `locale`, `timezone_id`, `viewport` (`environment.py` l.181) |
| C4 | Web générique | Vocabulaire incomplet (tableaux, dialogues, téléchargements, iframes, onglets, réponses réseau) et steps propres à une appli dans `generic/` (« je force le nom du ticket », « … avec accessoires ») |
| C5 | Web générique | Aucun oracle backend : verdict `ui_only` sans alternative |
| C6 | Odoo | Aucun vocabulaire ERP : boutons de workflow, barre d'état, lignes one2many, assistants, filtres de liste, effets en chaîne, rapports, changement d'utilisateur / de société |
| C7 | Odoo | Pas de détection de version à l'exécution (`/odoo/…` ≥ 17.2 vs `/web#…`, structures DOM 16/17/18) |
| C8 | Mesure | Aucune instance Odoo de référence : la conformité ne tourne que sur SauceDemo / the-internet, la fiabilité Odoo n'est mesurable que sur la recette client |
| C9 | Agents | Outils de perception limités aux formulaires (`inspect_page_form`) ; aucune vue des boutons/états d'une vue Odoo ni de l'arbre d'accessibilité d'une page ; aucune règle « assertion uniquement en `Alors` » |

## 3. Indicateurs de réussite

Mesurés par `scripts/banc_mesure.py` (lot 04) sur l'instance de référence, à chaque lot à partir
du lot 05, et reportés dans `docs/QUALITE-GENERATION-*.md`.

| Indicateur | Définition | Cible |
|---|---|---|
| I1 — Faux PASSED | bugs injectés dont le cas sort `passed` / bugs injectés couverts | **0**, sous réserve du résidu D10 (F1 sans marqueur de tentative) |
| I2 — Faux FAILED | cas `failed` sur l'instance saine / cas exécutés | ≤ 2 % |
| I3 — Exécution au 1er passage | cas sans `technical_error` au premier run / cas générés | ≥ 85 % (départ : 43 %) |
| I4 — Verdict exploitable | cas `passed` ou `failed` au 1er passage / cas générés | ≥ 75 % (départ : 14 %) |
| I5 — Blocage correctement attribué | pannes d'env. injectées rapportées `blocked` / pannes injectées | 100 % |
| I6 — Coût | coût moyen par nouveau cas, réparations comprises | < 1 € (§9) |

Toujours publier l'échantillon (nombre de cas, versions Odoo, date). Ne jamais moyenner des
régimes différents (PRINCIPES).

## 4. Registre des décisions à valider par le porteur

Claude Code **ne démarre pas** un lot dont une décision requise n'est pas cochée.

| ID | Question | Proposition | Lots | Statut |
|---|---|---|---|---|
| D1 | Nouvelle cause `precondition_non_remplie` et projection vers un statut `blocked` automatique | Ajouter la cause ; `execution_status = blocked` (nouvelle valeur de l'axe exécution) + `functional_status = indetermine` ; lecture `blocked`. Les deux axes restent séparés | 02 | ☐ |
| D2 | Un `AssertionError` levé dans un `Quand` | Cause `broken_test_code` (le test affirme dans une action) → `retest` | 02 | ☐ |
| D3 | Scénario vert sans aucun constat exécuté | `functional_status = indetermine`, cause `aucun_constat` → `retest`. Jamais `conforme` | 03 | ☐ |
| D4 | Les nouvelles gardes d'écriture (assertion hors `Alors`, `Alors` sans `constater`) bloquent-elles `write_steps_file` ? | **Bloquantes** : l'agent reçoit un refus déterministe et corrige, ce qui coûte moins qu'un run réel raté. Dérogation au régime détectif de 0008 justifiée par le runtime (D3) qui rend la faute mesurable | 03, 09 | ☐ |
| D5 | Confiance du verdict | Champ `confiance` ∈ {`nominale`, `auto_resolue`, `apres_retry`} sur le résultat ; `passed` non nominal affiché « Réussi — à confirmer » ; option de campagne **stricte** (sans résolution adaptative ni retry) | 05 | ☐ |
| D6 | Code propre à une instance client | Notion de **profil d'instance** : `behave_runtime/steps_library/<connecteur>/profils/<profil>.py`, sélectionné par un réglage du projet ; Sapian devient le premier profil | 06 | ☐ |
| D7 | Oracle backend du connecteur web | Réglage de projet optionnel `oracle` (HTTP JSON authentifié, ou SQL lecture seule) ; présent ⇒ `ground_truth = backend_verified` | 07 | ☐ |
| D8 | Plusieurs comptes par projet (droits, changement d'utilisateur) | Table `project_account` (libellé, identifiant, secret chiffré via `store/secrets.py`, rôle métier) ; steps « en tant que "<libellé>" » | 07, 08 | ☐ |
| D9 | Versions Odoo supportées et instance de référence | 16.0, 17.0, 18.0 Community + données de démo ; modules `sale_management`, `purchase`, `stock`, `account`, `crm`, `project` (helpdesk est Enterprise : exclu du banc) | 04, 08 | ☐ |
| D10 | F1 : sur un scénario de création SANS marqueur de tentative (champ sans contrainte d'unicité — la majorité des cas), le comptage cloisonné (`id > max_id`) ne peut pas distinguer un unique enregistrement du scénario d'un unique enregistrement créé par un tiers dans la même fenêtre — aucune information disponible ne permet de trancher sans marqueur (le `create_uid` est exclu, cf. formulaires publics). Accepte-t-on ce résidu (I1 non strictement à 0) plutôt que d'imposer un marqueur à TOUT scénario de création (changerait le contrat de génération, hors périmètre du lot 01) ? | **Résidu accepté** : le risque exige la coïncidence de trois conditions (tiers actif sur le même modèle, même fenêtre de quelques secondes, ET échec réel du scénario) — rare hors instance à fort trafic concurrent. Généraliser le marqueur à tout scénario de création reste une amélioration valide, à traiter comme un lot séparé si le résidu se matérialise en pratique | 01 | ☑ (validée le 2026-09-23) |

## 5. Lots

Ordre recommandé ci-dessous. Les lots 01 à 03 sont testables hors ligne et corrigent des faux
statuts : ils passent en premier. Le lot 04 construit le banc qui sert à prouver tous les suivants.

| Lot | Commande | Objet | Décisions | Dépend de | Taille |
|---|---|---|---|---|---|
| 01 | `/lot-01-comptages` | Comptages cloisonnés au scénario (F1) | D10 | — | S |
| 02 | `/lot-02-causes-preconditions` | Cause selon le type de step, prérequis → `blocked` (F2, F5) | D1, D2 | — | M |
| 03 | `/lot-03-preuve-constat` | Preuve runtime qu'une assertion a été exécutée ; gardes d'écriture (F4) | D3, D4 | 02 | M |
| 04 | `/lot-04-banc-mesure` | Instance Odoo de référence, bugs injectés, pannes injectées, script d'indicateurs, CI nocturne (C8) | D9 | — | L |
| 05 | `/lot-05-confiance` | Confiance du verdict, mode strict (F3) | D5 | 02, 04 | M |
| 06 | `/lot-06-nettoyage-profils` | Teardown générique, profils d'instance, sortie du code Sapian (F6) | D6 | 01 | M |
| 07 | `/lot-07-web-generique` | Connexion à l'exécution, `storage_state`, contexte figé, vocabulaire universel, oracle (C1-C5) | D7, D8 | 02, 03 | L |
| 08 | `/lot-08-odoo-erp` | Détection de version, sélecteurs par version, vocabulaire ERP, effets en chaîne (C6, C7) | D8, D9 | 04 | L |
| 09 | `/lot-09-agents` | Outils de perception, prompts, garde de réparation des assertions (C9) | D4 | 07, 08 | M |
| 10 | `/lot-10-mesure-cloture` | Campagne de mesure complète, mise à jour de la documentation | — | tous | S |

### Suivi

| Lot | Statut | Date | Rapport |
|---|---|---|---|
| 01 | terminé | 2026-09-23 | `docs/RAPPORT-LOT-01-COMPTAGES-2026-09-23.md` |
| 02 | à faire | | |
| 03 | à faire | | |
| 04 | à faire | | |
| 05 | à faire | | |
| 06 | à faire | | |
| 07 | à faire | | |
| 08 | à faire | | |
| 09 | à faire | | |
| 10 | à faire | | |

## 6. Ce que chaque lot garantit (résumé)

**01.** Un comptage ne voit que les enregistrements créés après le relevé du scénario (`id >
max_id` relevé, affiné par le marqueur de tentative quand il existe). Les ids trouvés alimentent
`last_record_ids` et le registre de teardown.

**02.** Le type de step (`given`/`when`/`then`, lu dans le JSON Behave, pas dans le libellé)
entre dans la classification. Les prérequis lèvent `PreconditionNonRemplieError`. Une panne de
fixture (`odoo_session`, navigateur, connexion) devient `blocked`. Seul un échec d'assertion dans
un `Alors` devient `non_conforme`.

**03.** Toute assertion de la bibliothèque passe par `constater()` / `constater_visible()`, qui
consignent un constat dans un fichier sidecar. Un scénario vert sans constat n'est jamais
`conforme`. `write_steps_file` refuse les assertions hors `Alors` et les `Alors` sans constat.

**04.** `compose.banc.yml` lance Odoo 16/17/18 + PostgreSQL, base de démo neutralisée. Le module
`tp_bugs_injectes` active des défauts connus par `ir.config_parameter`. Un corpus
`specs/banc/` + un fichier d'attendus permettent de calculer I1 à I6. Workflow nocturne.

**05.** La résolution adaptative et le retry laissent une trace qui abaisse la confiance du
verdict ; la campagne stricte les désactive.

**06.** Le teardown supprime (ou annule puis supprime, ou archive) tout ce que le scénario a créé,
quel que soit le modèle. Le code Sapian sort du socle vers un profil.

**07.** Une application web authentifiée est testable : step de connexion générique partagé avec
l'exploration, session réutilisée, stratégies d'auth déclarées, locale et fuseau figés,
vocabulaire universel, oracle optionnel.

**08.** Un flux ERP Odoo complet (devis → commande → livraison → facture) est exprimable avec la
bibliothèque, vérifié côté UI et côté RPC, sur 16, 17 et 18.

**09.** L'agent voit les boutons, états et sous-champs d'une vue Odoo et l'arbre d'accessibilité
d'une page web ; ses prompts exposent le nouveau vocabulaire et les règles de constat ; une
réparation qui touche un `Alors` est signalée au gate.

**10.** Indicateurs I1-I6 publiés sur les trois versions Odoo et sur la fixture web ; ARCHITECTURE,
CONTINUITE et le rapport de qualité mis à jour.

## 7. Risques

- **Hausse apparente des `retest`/`blocked` après 02-03.** C'est attendu : des verts et des rouges
  faux deviennent honnêtes. À annoncer avant de publier les chiffres.
- **Taille du prompt (09)** : le vocabulaire ERP grossit le catalogue. Mesurer I6 ; si besoin,
  n'injecter que les steps du connecteur et des domaines détectés dans la spec.
- **Suppression en teardown (06)** sur un document validé : Odoo refuse souvent `unlink`. Prévoir
  annulation puis suppression, sinon archivage, et le signaler au rapport sans jamais faire
  échouer le verdict.
- **Dérive de l'instance de référence** : figer les images Docker par digest.

## 8. Mode d'emploi avec Claude Code

1. Copier à la racine du dépôt : `CLAUDE.md`, `.claude/commands/`, `.claude/agents/`, et ce plan
   dans `docs/`. Commiter sur une branche `outillage-claude-code`.
2. Le porteur coche les décisions du §4 (date + initiales). Claude Code refuse un lot dont une
   décision requise n'est pas cochée.
3. Ouvrir Claude Code à la racine du dépôt, puis pour chaque lot, dans l'ordre du §5 :
   - `/lot-01-comptages` (les lots 07 et 08 acceptent un sous-lot : `/lot-07-web-generique a`) ;
   - laisser Claude Code présenter son plan de fichiers avant d'écrire (mode plan conseillé) ;
   - à la fin, il lance le sous-agent `verdict-reviewer` et produit le rapport du lot ;
   - relire le rapport et le diff, puis fusionner. Mettre à jour le tableau de suivi du §5.
4. Une session Claude Code par lot (ou par sous-lot) : le contexte reste centré, et le rapport de
   fin sert de passation au lot suivant.
5. À partir du lot 04, ne fusionner aucun lot qui dégrade I1 ou I5 sur le banc.
