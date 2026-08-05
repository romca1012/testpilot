# Reprise — parité TestRail de l'exécution, l'essentiel livré

> **À quoi sert ce document.** Reprendre l'implémentation dans une **nouvelle session**, sans avoir
> la conversation d'origine. Il remplace `REPRISE-P2.md`, dont il reprend les décisions.
>
> Écrit le 2026-08-05, en fin de session (mise à jour : les deux agents alors « en cours » ont
> terminé, un troisième point a été fini à la main après une coupure réseau en plein milieu d'un
> agent — voir §5). Régénérable : `python scripts/doc_en_pdf.py docs/REPRISE-P3.md`

---

## 1. Où en est le chantier

Quatre manques bloquaient la V1. **Trois sont livrés** (exécution manuelle — avec pièces jointes
et parité d'écran —, Type, État). Le **quatrième** (génération multi-cas) reste entier, non
commencé.

Consigne du porteur qui gouverne toute cette session : *« je ne souhaite plus avoir à te dire de
faire des corrections sur certains points sachant qu'ils existent déjà sur TestRail — consulte
l'application dans son entièreté et maîtrise son fonctionnement d'abord. »* → `docs/PARITE-TESTRAIL.md`
reste la carte de référence, écran par écran. **À lire avant tout travail sur l'interface
d'exécution.**

⚠️ **Ne pas croire un agent sur parole.** Cette session l'a vérifié deux fois : un agent avait
laissé le bug `.color` (§5) sans le corriger malgré une consigne explicite de la fois précédente,
et le second a été coupé en plein milieu d'un fichier par une erreur réseau. Toujours relire les
fichiers réellement modifiés et relancer les suites soi-même avant de considérer un lot terminé.

---

## 2. Une correction importante à connaître

**L'État (Nouveau/Conception/Prêt/Obsolète) reste SANS automatisme** — confirmé par le porteur en
regardant sa propre capture TestRail (l'onglet d'une exécution archivée y montre un test à l'état
`New`, jamais remis à jour). Une session antérieure avait cru bon de proposer le contraire : **c'était
une erreur, tranchée et refermée. Ne pas la rouvrir.**

---

## 3. Vocabulaire arrêté

| Terme | Ce que c'est | Où ça vit |
|---|---|---|
| **Module** | périmètre fonctionnel — le « Section » de TestRail | `module` |
| **Spécification** | conteneur d'un groupe de cas | `case_group` |
| **Type** | Fonctionnel / Non fonctionnel | `test_case.type` |
| **État** | Nouveau / Conception / Prêt / Obsolète — **sans automatisme** | `test_case.etat` |
| **Résultat** | un verdict de cas dans une campagne | `test_result` |
| **Mode d'exécution** | **manuelle / automatique**, choisi à la CAMPAGNE, hérité par ses résultats | `test_run.mode`, `test_result.mode` |
| **Test (dans une campagne)** | `T{run}-{case}` — distinct du **cas** `C{case}` du référentiel | `GET /api/runs/{id}/tests/{caseId}` |
| ~~Provenance~~/~~déclaré~~/~~exécuté~~ | abandonnés le 2026-08-05 au profit de manuelle/automatique | — |
| ~~Angle~~ | supprimé le 2026-08-04 (absent de TestRail) | — |

---

## 4. Décisions arrêtées avec le porteur

- Statuts saisissables : Passed / Failed / Retest / Blocked. `untested` n'est **jamais**
  saisissable — c'est l'absence de résultat.
- Un seul verdict global par cas ; pas de résultat par étape.
- Saisie uniquement **dans une campagne manuelle** — jamais sur un cas isolé, jamais dans une
  campagne automatique. Le mode se choisit à la CRÉATION de la campagne, jamais résultat par
  résultat, et un déclencheur base de données l'impose (§5).
- Pas de suppression d'un résultat : corriger = en ajouter un nouveau.
- Pas de « défauts liés », pas de « temps passé » en V1.
- Identité des résultats automatiques : compte de service réglable au niveau de l'instance.
- **Pièce jointe confirmée nécessaire** (et non une extension future) : elle atteste que le test
  a réellement été joué. **Livrée cette session**, back et front.
- `assigned_to` en texte libre + suggestions — **pas encore câblé** (§6).

### Arbitrages TestRail — voir `docs/PARITE-TESTRAIL.md` §9 pour le détail complet

| Sujet | Décision |
|---|---|
| Priorité | 3 niveaux, pas de « Critique » — l'implémentation actuelle est correcte |
| Clôture irréversible | reportée au déploiement en production |
| Références (liste, hyperlien) | hors V1 |
| Modèles de cas (*Template*) | sans objet — TestPilot applique déjà le modèle *Text* |
| Sections imbriquées | rattachées au chantier génération de cas (étape 9) |
| Façons de saisir (menu en ligne, lot, Pass & Next) | à revoir plus tard, confort de saisie |

---

## 5. ✅ Ce qui est FAIT et VÉRIFIÉ (deux fois : par l'agent, puis par moi)

### Le renommage provenance → mode d'exécution

Migration **27** (`test_run.mode`, `test_result.mode`, reconstruction de table, **CHECK XOR
conservé**), un **trigger** (`trg_resultat_suit_le_mode_de_sa_campagne`) qui garantit qu'un
résultat ne peut pas avoir un mode différent de sa campagne — un `CHECK` ne sait pas lire une
autre table, l'invariant vit donc en base. `AddTestRunForm.vue` demande le mode à la création ;
`RunDetail.vue` : `estManuelle` commande « Lancer » vs « + Résultat ».

⚠️ **La migration 25 n'a PAS été réécrite** — une base l'avait déjà jouée avec l'ancien
vocabulaire ; c'est la 27 qui convertit. Règle à respecter : on ne réécrit jamais l'histoire d'une
migration déjà écrite.

⚠️ **Constaté cette session : le serveur qui tourne sur le poste (port 8000) est resté en v26**
jusqu'à ce jour — il n'avait pas été redémarré depuis avant la migration 27. Rejouée sur une copie
de la vraie base : passe proprement en v27, trigger présent, 13 résultats automatiques + 1 manuel
répartis correctement, clés étrangères intactes. **Redémarrer le serveur applique la migration.**

### L'onglet Tests & Résultats à parité

Camembert SVG fait main + légende, grand indicateur « X % réussi », barre Trier/Filtre/Colonnes,
cas groupés par statut. Le bug `.color` (composantes HSL brutes utilisées sans `hsl(...)`,
pastilles invisibles) était corrigé dans `RunDetail.vue` mais **PAS** dans `AddResultDialog.vue` —
**corrigé cette session** (`hsl(${testStatusMeta(code).color})`, ligne ~112 à l'époque).

### La page d'un test dans une campagne (`RunTestDetail.vue`)

`T{run}-{case}` distinct de `C{case}` (infobulle explicite), flèches précédent/suivant bornées à
la campagne, 3 onglets (Résultats et commentaires / Historique et contexte / Défauts — honnête,
« à venir », pas de compteur à zéro trompeur), courbe des résultats sur 30 jours, présence du cas
dans les autres campagnes groupée par mois.

**Ajouté cette session** : le bouton « Ajouter un résultat » depuis cette page (auparavant
absent — on ne pouvait saisir que depuis la liste de la campagne). Visible seulement si
`run_mode === 'manuelle'` et la campagne non archivée. Comme `TestDansRun` ne porte pas
`statuts_manuels` (cette liste n'a de sens que côté campagne), la page va la chercher via
`api.getRun()` — **best-effort**, en écran dégradé (liste vide) si cet appel échoue, jamais au prix
de bloquer la lecture du test lui-même.

Conséquence : `AddResultDialog.vue` acceptait une prop `cas: RunCaseResult | null` (quinze champs)
alors que le template n'en lit que deux (`id`, `title`). Le type a été **élargi en un type
structurel minimal** (`CasMinimal { id; title }`) — `RunDetail.vue` continue de passer un
`RunCaseResult` complet (compatible structurellement), `RunTestDetail.vue` passe l'objet minimal.

### Les pièces jointes — back ET front

**Backend** (`src/testpilot/api/services/attachment_service.py`) : liste blanche fermée (`png jpg
jpeg gif webp pdf txt log csv zip`), **`svg`/`html` explicitement refusés** (XSS stocké — servis
depuis l'origine de TestPilot, ils exécuteraient du script avec le cookie de session à portée),
nom sur disque généré (`uuid4`), jamais celui du client, écriture par morceaux avec plafond
vérifié PENDANT l'écriture (pas après). Téléchargement par deux identifiants numériques
(`/api/results/{id}/attachments/{id}`), jamais par nom — `nosniff` + `Content-Disposition`.
15 tests Python.

**Frontend — fini cette session**, après une interruption réseau qui a coupé un agent en plein
milieu de `AddResultDialog.vue` :
- `api.ts` : `requestForm()` (transport `multipart/form-data`, sans `Content-Type` forcé — c'est le
  navigateur qui doit poser le `boundary`) partageant la même extraction d'erreur RFC 9457 que
  `request()` (`erreurDepuis`, factorisée), `API_BASE` exportée (un lien de téléchargement en a
  besoin), `addAttachments()`. **`extractSpec` corrigé au passage** : il perdait le code d'erreur
  RFC 9457 (`throw new Error(...)` au lieu de `throw new ApiError(...)`).
- `AddResultDialog.vue` : champ de fichiers (toujours optionnel — n'entre dans aucune condition de
  validation), upload **après** la création du résultat, jamais avant. ⚠️ **Un échec d'upload ne
  fait PAS disparaître le résultat déjà créé** : erreur séparée (`erreurPieces` ≠ `erreur`),
  fenêtre gardée ouverte, statut réinitialisé pour empêcher un second clic de recréer le résultat.
- `ResultHistory.vue` : liste des pièces jointes par résultat, lien de téléchargement direct
  (`<a href>` — un clic est une navigation de premier niveau, le cookie de session part même
  cross-origine en dev grâce à `SameSite=Lax`, pas besoin de `fetch`/blob).
- 21 tests d'interface nouveaux (`AddResultDialog.spec.ts` +5, `ResultHistory.spec.ts` créé, 4
  tests).

### Couverture de tests des écrans livrés sans test

`RunTestDetail.vue`, `RunActivite.vue`, `RunProgression.vue`, `CourbeResultats.vue` n'avaient
**aucun** test d'interface alors que le backend l'était déjà (`test_test_dans_campagne.py`,
11 tests). **Comblé cette session** : 4 nouveaux fichiers, 16 tests — dont un qui rejoue deux fois
le même cas pour vérifier que la Progression ne le compte qu'une fois (règle : un cas compte le
jour de son PREMIER résultat, jamais un rejeu).

### Vérification finale de cette session (mesurée, pas rapportée par un agent)

```
frontend : npm run build → compile sans erreur
frontend : npm test      → 23 fichiers, 151 tests, tous verts
```

```
pytest → 1 268 passed, 0 échec (aucune erreur parasite du garde-fou data/ cette fois)
```

---

## 6. ⏳ Ce qui reste (non commencé)

### Assignation
Table `run_case_assignment` déjà créée (migration 25), rien ne l'alimente. Colonne « Assigné à »
dans `RunDetail.vue` affiche « — » en dur.

### Le dernier des 4 manques P1 : génération multi-cas

**Récapitulatif complet arrêté avec le porteur le 2026-08-05, fin de session (81 % du budget de
contexte) — ce qui suit remplace toute version antérieure de ce chantier (`REPRISE-P2.md` §6
compris) et fait foi.**

#### La logique

Depuis une spécification (texte collé ou fichier chargé) : identifier les **user stories**, puis
pour chacune générer l'**ensemble complet des cas nécessaires pour la couvrir** — un nombre
**variable, jamais fixé d'avance**.

⚠️ **« Variable » ne veut pas dire « maximal ».** On vise le **plus petit ensemble de cas qui
couvre malgré tout toute la spécification** — *« un cas de test qui peut être validé par un autre
n'est pas intéressant »* (arbitrage du porteur). Ça se traduit dans le **prompt du découpage**
(étape 9a) : pas *« énumère tout ce qui est possible »*, mais *« trouve le plus petit ensemble de
cas qui, ensemble, couvrent tout ce que la spécification décrit — sans qu'un cas soit redondant
avec un autre »*.

**Le format d'un cas de test NE CHANGE PAS** : mêmes champs qu'aujourd'hui (titre, préconditions,
étapes, résultat attendu). Aucune migration de schéma sur `test_case_version` pour ce point —
seul le nouveau module de découpage a besoin de son propre schéma de sortie structurée.

Le mécanisme `scenarios`/`angle` (nominal/erreur/limite) est **abandonné comme moteur de la
multiplication** — cohérent avec le retrait déjà fait du champ `angle` (migration 26).

#### Ce qu'on NE construit PAS

**Aucune gestion de « document spécification » en V1.** Ni écran « Nouvelle spécification », ni
écran « voir le document » fonctionnel. La spécification n'est qu'une **entrée** de la
génération — chargée en fichier ou remplie depuis un template — jamais un objet autonome
qu'on crée/édite/relit.

#### Le conteneur : `case_group` reste `case_group`

Pas de nouvelle entité. `case_group` sert de **Section** — un simple regroupement de cas par user
story, pas un document géré. **Le « 1 seul cas » actuel est un symptôme du bug (auto-enveloppe de
`CaseRepo.create`), pas une limite structurelle** : une fois corrigé, une Section contient
plusieurs cas normalement. Son **titre devient le nom de la user story**.

**Provenance conservée, pas exposée** : le texte source reste associé en interne à la Section qui
en est issue (`case_group.spec_content`), pour permettre plus tard, dans une version évoluée, de
le consulter — rien à construire côté écran maintenant.

**Une seule source pour ce texte** : `test_case_version.spec_content` (le champ legacy, marqué
dette explicite depuis 2026-07-19) est **supprimé**. Vérifié le 2026-08-05, aucune alternative
n'est nécessaire : `test_case_version.spec_hash` **reste** (il existe déjà, coûte quelques
octets) — c'est lui qui permet de détecter *« cette version a été générée depuis une spec
différente de celle d'aujourd'hui »* sans garder le texte en double. Et comme il n'y a **aucun
écran d'édition de la spécification en V1**, `case_group.spec_content` ne bouge plus une fois la
Section créée — le risque de perte de fidélité historique qui justifierait une copie par version
ne se pose donc pas.

⚠️ **Conséquence à ne pas oublier** : `repair_service.py:449` lit aujourd'hui
`version["spec_content"]` — à repointer vers `case_group.spec_content` (via le `group_id` du cas)
**dans le même mouvement** que la suppression de la colonne, sinon la réparation perd
silencieusement son contexte.

#### Références

`refs` (champ existant sur le cas, texte libre comme TestRail) **auto-rempli avec le nom de la
user story** à la génération. Aucune nouvelle colonne.

#### L'écran de validation

Un écran **unique** après génération : cas groupés par Section (pliable/dépliable), consultation
et modification d'un cas via **l'écran de détail actuel, inchangé** (`CaseDetailTR.vue` —
aucune refonte), suppression d'un cas si voulu, retour facile à la vue complète. Génération
**directe et complète** (pas de présélection sur titres seuls façon TestRail 9.5 — arbitrage déjà
acté, confirmé aujourd'hui).

⚠️ **Conséquence de coût, assumée en connaissance de cause** (recherche faite le 2026-08-05 :
TestRail lui-même limite le coût par un tri sur les TITRES avant de rédiger le détail complet —
voir `PARITE-TESTRAIL.md`). Sans ce tri, le coût est proportionnel à ce que l'IA décide
nécessaire, pas à ce qu'on choisit d'avance. Le seul point de contrôle possible reste l'écran de
validation, **après** génération.

**À la validation** : Sections et cas créés pour de vrai, scripts (Gherkin) générés et prêts à
l'exécution — pas avant.

#### Le plan technique, en 6 étapes

Principe retenu : ne pas réinventer la génération, la **répéter**. Le pipeline `propose_metier` →
`GenerationAgent.generate()` est déjà testé pour UN cas ; le nouveau module se contente de
**planifier** quoi écrire, la boucle existante fait le travail une fois par cas planifié.

- **9a** — `src/testpilot/generation/decoupage.py` (nouveau) : spécification → `[{user_story,
  cases: [{title, brief}, …]}]`. Sorties structurées (même patron que
  `metier_writer._data_metier`), prompt orienté « ensemble minimal qui couvre tout », pas
  « énumère tout le possible ».
- **9b** — `generation_service` boucle : une Section (`case_group`) par user story
  (`CaseGroupRepo.create`, rien de nouveau) ; pour chaque cas planifié, `propose_metier(plan,
  brief=...)` (le paramètre `brief` remplace l'ancien `angle`, **à ajouter** — vérifié le
  2026-08-05, `propose_metier` n'a plus aucun paramètre de ce genre) puis
  `GenerationAgent.generate(..., group_id=section.id, metier=...)`. **`group_id` est déjà un
  paramètre de `generate()`** (`generation/agent.py:45-48`), simplement jamais passé.
- **9c** — Le texte s'écrit sur `case_group.spec_content` (`generation/agent.py:137` aujourd'hui
  écrit sur la version — à corriger), et `repair_service.py:449` repointé sur la même source
  (voir ci-dessus). Une fois les deux recâblés et un audit confirmant plus aucun lecteur,
  `test_case_version.spec_content` part dans une **migration 28 dédiée** — pas avant.
- **9d** — Fichier original conservé (`data/specifications/<spec_hash>/`). PDF **déjà lisible**
  côté CLI (`spec_analyzer._read_spec`, `pdfplumber` déjà une dépendance) mais **pas côté route
  web** : `routes/modules.py:136-150` délègue à `spec_extract.extract_text`, dont le docstring
  dit encore *« PDF nécessiterait une dépendance »* — **faux aujourd'hui**, simple branchement à
  ajouter dans `spec_extract.py`. Taille maximale d'upload : aucune aujourd'hui, même patron que
  `config.ATTACHMENT_MAX_BYTES`.
- **9e** — `AddTestCase.vue` : écran unique de validation décrit ci-dessus. Renommage de schéma :
  `GenerationJobOut.metier` → `sections`, `case_id` → `case_ids`.
- **9f** — Sections imbriquées : **absentes du récapitulatif du 2026-08-05** (une version
  antérieure de ce document les rattachait à ce chantier). Ne pas les construire tant que le
  porteur ne les redemande pas explicitement — silence ≠ confirmation.

**Ordre suggéré** : 9a → 9b → 9c ensemble (se testent mal séparés) ; 9d et 9e peuvent suivre
indépendamment.

### Finitions
Mise à jour finale de `docs/ONBOARDING.md` une fois tout livré.

---

## 7. Pièges déjà payés — ne pas les rejouer

1. **Le nom de table entre guillemets.** `ALTER TABLE … RENAME TO x` réécrit le schéma stocké en
   `CREATE TABLE "x"`. Toujours rejouer une migration sur une **copie de la vraie base**, jamais
   seulement sur la base synthétique d'un test.
2. **Une migration ancienne rejouée hors de son époque.** Garde-fous d'introspection nécessaires
   quand une migration suppose l'état « juste avant elle ».
3. **Page entièrement blanche.** Une route hors `/projects/:pid` rendue dans le shell de projet
   lève « Missing required param "pid" » pendant le rendu, sans erreur visible.
   `frontend/src/lib/shell.ts` + `shell.spec.ts` existent pour ça.
4. **`.color` vs `hsl(...)`.** `testStatusMeta(k).color` rend des composantes HSL BRUTES
   (`152 56% 46%`), jamais une couleur CSS utilisable telle quelle. **Payé deux fois** dans
   `AddResultDialog.vue` — corrigé une première fois « signalé mais pas fait », vérifié et
   confirmé corrigé cette session. Vérifier `grep -rn "\.color}" frontend/src` avant de clore un
   lot qui touche à l'affichage des statuts.
5. **Ne jamais faire tourner la suite de tests pendant que l'application tourne sur ce poste** :
   `tests/conftest.py` compare le vrai `data/` avant/après chaque test et accuse le test en
   cours, pas le serveur qui a vraiment écrit.
6. **XSS stocké par pièce jointe** — traité dès la livraison : liste blanche fermée, `svg`/`html`
   refusés, `nosniff`, nom sur disque jamais celui du client.
7. **Ne pas recopier `extractSpec`** — corrigé cette session, il utilise maintenant `requestForm`
   et perd son ancien défaut (`throw new Error` au lieu de `throw new ApiError`).
8. **Un agent interrompu par une erreur réseau laisse un fichier dans un état intermédiaire, pas
   forcément cassé mais incomplet.** Toujours relire le fichier réellement modifié (pas le
   résumé de l'agent) avant de considérer une tâche terminée — la fin exacte où il s'est arrêté
   se lit dans la trace de l'événement d'échec.
9. **Disque non borné** : `data/results/` grossira sans purge ni quota ; supprimer un cas ne
   libère rien. Acceptable en V1 si c'est dit, pas si c'est oublié.
10. **Régression pré-existante, non créée par ce chantier** : les exécutions de réparation
    (`run_service._maybe_repair`) ne reçoivent jamais de `run_id` — un cas réparé avec succès
    pendant une campagne y affiche encore son verdict *d'avant* réparation. À traiter séparément.

---

## 8. Conventions du dépôt à respecter

- **Le code et les commentaires sont en français.**
- **Une décision se prend d'un seul côté, et c'est le serveur.** Le front affiche, il ne juge pas.
  Quand une même valeur doit exister sous deux formes, **un test les compare exhaustivement**
  (`tests/test_statut_de_lecture.py` est le modèle, 192 combinaisons).
- **Un fichier de test = un invariant**, nommé en français, docstring qui dit **pourquoi** il
  existe et quel défaut réel il empêche.
- **Jamais la couleur seule** à l'écran — toujours un libellé ou une icône en plus.
- `frontend/src/lib/status.ts` est le point **unique** de traduction code → libellé.
- Toute migration est **idempotente**, testée en l'appelant deux fois sur une base
  « pré-migration » écrite en SQL brut.
- Pas de `os.getenv` hors de `config.py`.
- **Aucune mention de Claude/Anthropic dans les commits.**
- Style de travail voulu par le porteur : **changements aussi simples que possible**, **planifier
  avant de coder**, confier l'outcome à des agents plutôt que de les micro-gérer — **mais vérifier
  leur travail soi-même avant de le considérer acquis** (§1, §5, §7 point 8).

---

## 9. État git — rien n'est commité

Toutes les sessions depuis le début de ce chantier (exécution manuelle, Type/État, retrait de
l'angle, renommage du mode, parité TestRail, pièces jointes) vivent en **modifications locales non
commitées** : une centaine de fichiers touchés, une trentaine de nouveaux. Le dernier commit réel
du dépôt reste antérieur à tout ce travail.

**Un commit s'impose dès qu'un état stable est atteint** — un plantage de poste effacerait
plusieurs sessions de travail. Ce n'est PAS fait automatiquement : la consigne du dépôt est de ne
commiter que sur demande explicite du porteur.

---

## 10. Vérification

```bash
pytest                    # 1 268 verts (mesuré cette session, aucune erreur)
cd frontend && npm test   # 23 fichiers, 151 tests, verts (mesuré cette session)
```

**Bout en bout, sur l'application réelle** (redémarrer le serveur pour appliquer la migration 27
s'il tournait déjà) :
1. créer une campagne **manuelle**, voir « + Résultat » sur chaque ligne et pas de « Lancer » ;
   créer une campagne **automatique**, l'inverse ;
2. saisir un résultat manuel avec une capture jointe **depuis la liste de la campagne** ;
3. ouvrir un test (`T{run}-{case}`), saisir un résultat **depuis cette page** (nouveau) — vérifier
   que le bouton disparaît sur une campagne archivée ou automatique ;
4. vérifier que la pièce jointe se télécharge, et qu'un fichier `.svg` ou `.html` est refusé avec
   un message qui l'explique ;
5. onglet Tests & Résultats : camembert, % de réussite, groupes par statut, pastilles de couleur
   visibles (y compris dans la fenêtre de saisie) ;
6. onglets Activité et Progression d'une campagne : courbe, fil chronologique, pourcentage qui ne
   double pas un cas rejoué.
