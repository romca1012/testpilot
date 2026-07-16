# 0007 — Génération : l'agent passe le libellé humain là où le step attend le nom technique (Inc. 1)

Date : 2026-07-15
Statut : **DÉCIDÉ** (arbitrage du porteur, 2026-07-15 — voir § *Verdict*). **B, B+ et A1 livrés**
(2026-07-16). Reste la **mesure d'obéissance d'A1**, en attente d'une instance Odoo joignable.
Priorité : **2** (après `0008`) — cf. `BACKLOG.md`

---

## En tête — la question de la famille (tranchée par les données)

**0007 est un HYBRIDE : même racine de famille que `0008`/`0003`, mais avec un remède technique
que `0008` n'avait pas.**

- **Racine = un trou de consigne (famille `0003`/`0008`).** Le catalogue montré à l'agent
  (`steps_library.as_prompt_section`) ne rend que les **libellés** des steps —
  `je renseigne le champ "{field}"` — et **rien** sur ce que `{field}` désigne : libellé humain
  ou attribut HTML `name` ? L'agent comble le vide avec une convention **raisonnable mais
  fausse** (libellé humain pour l'UI). C'est exactement le motif de `0003` (« on montre *quoi*
  réutiliser, pas *comment le paramétrer* ») et la même nature que `0008` (le pipeline n'exige
  pas assez de rigueur sur un point précis).

- **MAIS, contrairement à `0008`, il existe un remède purement TECHNIQUE.** Une tautologie ne
  peut pas être rendue « tolérante ». Un **champ**, si : il est résoluble **et** par son `name`
  **et** par son libellé. Le helper partagé peut donc **absorber** l'ambiguïté (essayer
  `[name=…]`, puis retomber sur le libellé). C'est l'option « step tolérant / `get_by_label` »
  évoquée plus tôt — elle n'avait pas d'équivalent pour `0008`.

**Conséquence — ça oriente la correction, et ça inverse l'emphase de `0008`.** Pour `0008`, le
prompt était **porteur** (aucun correctif technique possible). Ici, le remède **technique** peut
être porteur (déterministe, indépendant de l'obéissance du LLM, protège **toutes** les
générations futures), avec l'annotation du catalogue en **renfort** (pour que l'agent apprenne
aussi la convention propre). Donc la correction peut toucher **soit** la couche technique
**seule** (suffisant), **soit** les deux (défense en profondeur). Elle n'est **pas** obligée de
passer par le prompt — à la différence de `0008`.

---

## Contexte — l'écart 1 du run #2, confirmé et DÉTERMINISTE

Confirmé par exécution au run #2 (`CONTINUITE.md` §6.1) : l'agent réutilise le bon step partagé
mais lui passe le **libellé humain** là où le helper attend le **nom technique** du champ.

```gherkin
Et je renseigne le champ "Raison de la demande" avec la valeur "..."
Et je laisse le champ "Raison de la demande" vide
```
```python
def fill_field(page, name, value):
    page.wait_for_selector(f'[name="{name}"]', timeout=10000, state="attached")  # attend [name=...]
```
`[name="Raison de la demande"]` n'existe pas → `TimeoutError`. Le champ **existe** sous
`name="name"` (sonde `probe_champs_formulaire.py`) : c'est un **paramétrage**, pas un bug
applicatif.

**Le bug se reproduit à l'identique** (mesuré sur la base réelle) — ce n'est pas un aléa de
génération :

| Cas | Step UI (saisie) | Assertion RPC |
|---|---|---|
| **2** | `champ "Raison de la demande"` (libellé) ❌ | `champ "name"` (technique) ✅ |
| **3** (re-généré après A) | `champ "Raison de la demande"` (libellé) ❌ | `champ "name"` (technique) ✅ |

La phase A de `0008` (falsifiabilité) n'a **rien** changé ici — attendu : elle ne parlait pas
de nommage.

## Diagnostic — un modèle d'agent COHÉRENT, pas une confusion

⚠️ **Correction d'un diagnostic antérieur** : le premier rapport parlait d'une « incohérence
interne » de l'agent. C'est **faux**. L'agent applique une règle **stable et défendable** :
**libellé humain pour l'UI, nom technique pour le RPC**. Les deux registres sont cohérents dans
sa tête ; c'est le **contrat implicite** du placeholder `{field}` (côté UI) qui n'est écrit nulle
part. L'agent dispose pourtant du nom technique (la spec le donne — `name` — et il l'utilise
correctement pour le RPC) : il ne l'emploie simplement pas pour le step UI, faute qu'on le lui
demande.

Ce qui laisse passer l'écart, mesuré :
1. **Le catalogue n'expose pas la sémantique des placeholders.** `as_prompt_section` rend le
   libellé `je renseigne le champ "{field}"` sans dire que `{field}` = attribut HTML `name`.
2. **Les helpers UI sont stricts.** `fill_field`, `leave_field_empty`, `select_field_value`
   résolvent **uniquement** par `[name="…"]`. Aucun repli si l'argument est un libellé.

## Options

### Option A — Annoter la sémantique des paramètres (prompt/catalogue) — famille `0008`
Rendre le contrat explicite. Deux granularités :
- **A1 (globale, coût quasi nul)** : une ligne dans l'en-tête du catalogue / une règle du prompt :
  « dans les steps UI, un `{field}`/`{name}` de champ est l'**attribut HTML `name`** (que tu peux
  lire sur le formulaire réel), **jamais** son libellé affiché ».
- **A2 (par step, plus riche)** : porter une annotation de placeholder par step (docstring →
  `SharedStep` → `as_prompt_section`). Plus de travail ; utile au-delà de ce cas.
- Limite (comme A de `0008`) : repose sur l'**obéissance** du LLM → **à mesurer**, jamais présumé.

### Option B — Rendre les helpers UI tolérants (couche technique) — remède propre à `0007`
Résoudre le champ **par `name` d'abord, libellé en repli**, en un point unique réutilisé par
`fill_field`/`leave_field_empty`/`select_field_value` :

```python
def resolve_field_name(page, ident):
    # 1. nom technique exact (cas nominal, sélecteur le plus fiable)
    if page.locator(f'[name="{ident}"]').count() > 0:
        return ident
    # 2. sinon, traite `ident` comme un libellé → retrouve le contrôle → lit son `name`
    labelled = page.get_by_label(ident, exact=False)
    if labelled.count() > 0:
        return labelled.first.get_attribute("name") or ident
    return ident  # laisse échouer proprement en aval (message d'origine conservé)
```
- Avantage : **déterministe**, indépendant du LLM, protège toutes les générations. `name` étant
  essayé en premier, le repli ne se déclenche que sur le cas fautif.
- ⚠️ **Nuance d'invariant (§4.6 « affiché ≠ réel »)** : un repli **silencieux** qui « trouve
  toujours » le champ pourrait **masquer** une vraie régression produit (champ réellement
  renommé/supprimé). Atténuations : essayer `name` d'abord (le repli ne couvre que l'écart de
  paramétrage, pas une disparition), et éventuellement **tracer** l'usage du repli. Le repli ne
  touche que la **résolution du champ** (infrastructure de test), pas les assertions métier :
  il ne peut pas verdir un faux « conforme ». Risque résiduel : libellé ambigu → `get_by_label`
  vise un autre champ. Faible (name-first), à couvrir par test.

### Combinaison
A et B ne s'excluent pas. B = filet déterministe ; A = l'agent apprend la convention propre
(sélecteur exact = plus fiable, et code plus lisible).

## Recommandation (à valider — rien n'est tranché)

**B porteur + A1 en renfort.** Inverse volontairement l'emphase de `0008` : là-bas le prompt
était porteur faute de correctif technique ; ici le correctif **technique** (helper tolérant)
est déterministe et protège tout, donc il porte — et l'annotation catalogue A1 (coût quasi nul)
apprend à l'agent le nommage propre. **A2** (annotation par step) : plus tard, si d'autres
placeholders posent le même problème. Puis **mesurer** : re-générer et vérifier que le step UI
paramétré au libellé **passe** désormais (via B), et/ou que l'agent bascule au nom technique
(via A).

## Verdict (arbitrage du porteur — 2026-07-15)

**Décision confirmée et propre** (cette note, `0007`).

1. **B porteur + A1 en renfort — VALIDÉ.** Helper tolérant (name-first, libellé en repli)
   comme correctif déterministe ; annotation du catalogue en renfort.
2. **Le repli name→libellé DOIT TRACER — jamais totalement silencieux.** C'est le point le plus
   important du verdict : la trace évite qu'une **vraie régression** (champ réellement renommé
   côté Odoo) se fasse **absorber sans que personne ne le remarque**. Exigence : trace **visible
   en mode dev** (logs techniques, §5) — **ET surfaçage dans le rapport d'exécution REQUIS**
   (arbitrage complémentaire) : Behave masque les logs capturés sur un scénario **vert**, or le
   pire cas de l'exigence (champ renommé → repli le retrouve par libellé → scénario vert) est
   justement un succès. Le log seul a donc un **angle mort** sur ce cas précis ; le surfaçage au
   rapport (comparable aux `lint_warnings` de `0008`) le ferme. → **phase B+**, commit séparé
   après B.
3. **Annotation du catalogue (`{field}` = attribut HTML `name`) : MAINTENANT**, pas plus tard —
   coût faible, et la reporter **recréerait le trou de consigne** que cette note vient de
   diagnostiquer. (= A1 retenue d'emblée ; A2 par step reste différée.)
4. **Décision propre** : `0007` — famille de racine commune avec `0008`/`0003`, mais remède et
   point d'implémentation distincts.

## Ce qu'on ne fait PAS
- Pas de repli **muet** qui masquerait un champ réellement disparu : `name` d'abord, repli borné,
  trace si possible (§4.6).
- Pas de helper qui devine trop : un libellé ambigu ne doit pas remplir le **mauvais** champ →
  test de garde.

## Questions d'arbitrage — TRANCHÉES
Conservées pour la traçabilité ; résolues au § *Verdict*.

1. **Quelles options** ? → **B + A1**.
2. **Le repli doit-il tracer** ? → **Oui, obligatoire** en mode dev (§5) **ET** surfacé au
   rapport (arbitrage complémentaire : le log seul a un angle mort sur le scénario vert). → B+.
3. **A2 (annotation par step)** ? → **Différée** ; **A1 maintenant**.
4. **Décision propre** ? → **Oui**, `0007`.

## Suivi d'implémentation

Ordre : **B** (helpers tolérants + trace log + tests + preuve réelle cas 2) → **B+** (surfaçage
du repli au rapport, visible même sur un run vert) → **A1** (annotation catalogue + mesure).

- **B** — ✅ FAIT et PROUVÉ : `resolve_field_name(page, ident)` dans `_base_helpers.py` (name
  d'abord, libellé en repli, repli tracé via `logger.warning` + marqueur `[TP_FIELD_FALLBACK]`),
  branché dans `fill_field`/`leave_field_empty`/`select_field_value`. 4 tests à faux `page`
  (dont le repli tracé via `caplog`). **Preuve réelle** (re-run cas 2, exécution 4) : le
  `[Nominal]` **ne timeoute plus sur le champ** — avant B il erreurait en `wrong_field_name` sur
  `[name="Raison de la demande"]`, après B il **progresse** jusqu'à une erreur en aval
  (`TypeError` dans un step RPC de case 2, hors écart 1). La barrière de résolution est levée.
  185 tests verts. *NB* : la visibilité du marqueur en run réel est traitée par B+ (non persisté
  aujourd'hui — c'est précisément l'angle mort que B+ ferme).
- **B+** — ✅ FAIT. **Cible précisée par le porteur (2026-07-16)** : l'**enregistrement d'exécution
  + l'UI**, et **non** le rapport JSON au sens littéral — l'intention était « visible par un humain
  même sur un run vert », ce que l'exécution porte déjà. Donc **aucune dépendance sur l'écart 4**
  (qui reste ouvert et distinct).

  **Mesure préalable, qui a contredit l'hypothèse de départ et allégé la conception** : on
  supposait que Behave masquerait le marqueur sur un scénario vert (d'où l'idée d'un fichier
  sidecar ou d'un handler dans `environment.py`). Sonde réelle (behave **1.3.3**) : le log du step
  est réémis préfixé (`LOG_WARNING:<logger>:`) sur **stderr**, et **survit sur un scénario vert**.
  Or `BehaveRunner` passe déjà `combined_log = stdout + stderr` à `parse_behave_json` : le
  marqueur **arrivait déjà** jusqu'au parseur. Ni `environment.py`, ni sidecar, ni
  `--no-logcapture` n'ont été nécessaires.

  Chaîne livrée : `extract_field_fallbacks()` (sur le log **entier** — `raw_stdout` est tronqué aux
  3000 derniers caractères — et **avant** les retours anticipés, pour qu'un run au JSON absent ne
  perde pas ses replis) → `BehaveResult.field_fallbacks` → `run_service._persist` →
  `execution.field_fallbacks` (**migration 4**, JSON, niveau RUN) → `ExecutionSummary` (un seul
  champ couvre l'historique du cas *et* le détail d'exécution) → `FieldFallbackNotice.vue`
  (bandeau non-bloquant sur le dernier résultat) + **pastille d'historique**, cette dernière
  **uniquement** sur les lignes qui portent un repli (jamais par défaut : le signal doit survivre
  au run suivant, sinon la détection a posteriori rouvrirait un angle mort **dans le temps** —
  arbitrage du porteur).

  ⚠️ **Le test qui porte tout le dispositif** : `test_le_marqueur_survit_a_behave_sur_un_scenario_VERT`
  exerce la chaîne complète (vrai `resolve_field_name` → vrai sous-processus Behave → vrai
  parseur) sur un scénario **vert**, sans Odoo. Toute la conception repose sur un comportement
  **mesuré** de Behave que rien ne garantit contractuellement : sans ce test, une montée de
  version rendrait B+ **aveugle en silence** — précisément l'angle mort qu'il existe pour fermer.
  Ne pas le neutraliser : s'il casse, corriger la capture.

  Le marqueur est **dupliqué** entre `_base_helpers` et `behave_result` (importer le premier
  tirerait Playwright dans la couche API pour une constante) : la source unique est tenue par
  `test_marqueur_identique_des_deux_cotes`. **196 Python + 18 vitest + build verts.**

  *Limite de preuve assumée* : le run réel du cas 2 prouve le **surfaçage** ; son `[Nominal]`
  échoue en aval (`TypeError` hors écart 1), ce n'est donc pas un scénario vert. Le cas **vert** —
  le cœur de l'exigence — est prouvé par le test de garde synthétique, pas par le cas 2.
- **A1** — ✅ FAIT (annotation) ; ⏭️ **mesure d'obéissance en attente** (voir plus bas).
  Contrat écrit dans l'en-tête de `as_prompt_section` : `{field}` = **nom technique, jamais le
  libellé affiché**.

  ⚠️ **Correction du libellé de cette note** (relevé à l'implémentation, §8.4). L'option A1 était
  formulée « un `{field}`/`{name}` de champ est l'attribut HTML `name` ». **Deux inexactitudes**,
  vérifiées sur le catalogue réel :
  1. **`{field}` sert dans DEUX registres.** Steps d'interface (`je renseigne le champ "{field}"`)
     → attribut HTML `name`. Steps de vérification Odoo (`le champ "{field}" de cet enregistrement
     est égal à "{expected}"`) → nom du champ du **modèle**. Écrire « `{field}` = attribut HTML »
     aurait été **faux** pour la moitié des steps. Le point commun — et donc la règle écrite —
     est : *nom technique, jamais le libellé*.
  2. **`{name}` n'est PAS un nom technique.** Il désigne un onglet ou un produit
     (`je clique sur l'onglet "{name}"`), résolus par leur **texte visible** ; `click_button`
     passe par `get_by_role(name=…)`. Une consigne « les paramètres sont techniques » sans
     exception aurait **cassé** ces steps par surcorrection. L'annotation dit donc explicitement
     que boutons / onglets / produits se désignent par leur **libellé visible**.

  Gardé par deux tests (`test_catalogue_annonce_la_semantique_de_field`,
  `test_catalogue_ne_technicise_pas_les_boutons`).

  ⏭️ **Mesure d'obéissance NON FAITE — et volontairement pas bâclée.** Elle exige de re-générer un
  spec (appel LLM réel). Or `GenerationAgent` reçoit un `connector` pour **explorer l'application**,
  et l'annotation dit à l'agent de *lire le nom technique sur l'application réelle* : avec
  l'instance Odoo (`localhost:10017`) **injoignable**, l'agent ne peut pas le lire. La mesure
  serait donc **invalide** (elle testerait l'agent privé de la source que la consigne lui désigne),
  en plus d'être payante. À rejouer avec Odoo up : re-générer `specs/validation_champ_requis.md` et
  vérifier que le step UI est paramétré `champ "name"` et non `champ "Raison de la demande"`
  (cf. `scripts/prove_A_falsifiabilite.py` pour le dispositif). **Sans effet bloquant** : le repli
  technique (B) rattrape déjà le cas, A1 ne fait que renforcer.
