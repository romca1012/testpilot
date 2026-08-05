# Reprise — les 4 manques P1 sont livrés

> **À quoi sert ce document.** Reprendre l'implémentation dans une **nouvelle session**, sans avoir
> la conversation d'origine. Il remplace `REPRISE-P2.md`, dont il reprend les décisions, et
> **complète sa propre version précédente** — écrite en cours de session, avant que le dernier
> chantier (génération multi-cas) ne soit terminé, dogfoodé en conditions réelles et corrigé.
>
> Écrit le 2026-08-05, en fin de session. Régénérable : `python scripts/doc_en_pdf.py docs/REPRISE-P3.md`

---

## 1. Où en est le chantier

**Les 4 manques P1 identifiés en tout début de chantier sont tous livrés** : exécution manuelle,
génération multi-cas, Type, État. Les trois premiers ont en plus été **éprouvés sur de vraies
données** — pas seulement sur des tests synthétiques — en générant des cas depuis de vraies
spécifications tirées du portail Sapian réel, ce qui a révélé et permis de corriger deux défauts
qu'aucun test synthétique n'aurait trouvés (§4).

Consigne du porteur qui gouverne toute cette session : *« je ne souhaite plus avoir à te dire de
faire des corrections sur certains points sachant qu'ils existent déjà sur TestRail — consulte
l'application dans son entièreté et maîtrise son fonctionnement d'abord. »* → `docs/PARITE-TESTRAIL.md`
reste la carte de référence, écran par écran.

⚠️ **Ne pas croire un résultat sur parole — y compris le sien.** Cette session a vérifié
plusieurs fois des affirmations qui semblaient correctes et ne l'étaient qu'à moitié : un clic qui
semblait sans effet (en réalité un défaut de ciblage de 2 pixels, pas un bug produit), un module
qui semblait absent (en réalité une page non rafraîchie). **Toujours reproduire soi-même** —
requête SQL directe sur `data/testpilot.db`, navigation réelle dans l'application, fichier lu sur
disque — avant de conclure qu'un problème existe ou qu'il est résolu.

---

## 2. Une correction importante à connaître

**L'État (Nouveau/Conception/Prêt/Obsolète) reste SANS automatisme** — confirmé par le porteur en
regardant sa propre capture TestRail (l'onglet d'une exécution archivée y montre un test à l'état
`New`, jamais remis à jour). Une session antérieure avait cru bon de proposer le contraire : c'était
une erreur, tranchée et refermée. Ne pas la rouvrir.

---

## 3. Vocabulaire arrêté

| Terme | Ce que c'est | Où ça vit |
|---|---|---|
| **Module** | périmètre fonctionnel — le « Section » de TestRail | `module` |
| **Section** | conteneur d'un groupe de cas = une user story | `case_group` |
| **Type** | Fonctionnel / Non fonctionnel | `test_case.type` |
| **État** | Nouveau / Conception / Prêt / Obsolète — **sans automatisme** | `test_case.etat` |
| **Résultat** | un verdict de cas dans une campagne | `test_result` |
| **Mode d'exécution** | **manuelle / automatique**, choisi à la CAMPAGNE, hérité par ses résultats | `test_run.mode`, `test_result.mode` |
| **Test (dans une campagne)** | `T{run}-{case}` — distinct du **cas** `C{case}` du référentiel | `GET /api/runs/{id}/tests/{caseId}` |
| **Brief** | la piste donnée à `propose_metier` pour rédiger UN cas précis d'une Section | paramètre de `propose_metier`, pas une colonne |
| ~~Provenance~~/~~déclaré~~/~~exécuté~~ | abandonnés le 2026-08-05 au profit de manuelle/automatique | — |
| ~~Angle~~ | supprimé le 2026-08-04 (absent de TestRail) | — |

---

## 4. ⚠️ Deux bugs de production trouvés en dogfooding réel — CORRIGÉS

Le porteur a généré des cas depuis une vraie spécification (« Mutation payeur », tirée du portail
Sapian réel — voir §6). La génération s'est arrêtée en pleine exécution, avec :

```
[Errno 2] No such file or directory: 'C:\...\tp_behave_le_formulaire_de_mutation_payeur_refuse_les_
codes_payeur_contenant_des_lettres_ou_caracter...\steps\...'
```

### Bug 1 — `slugify()` sans limite de longueur (CORRIGÉ)

Un titre de cas généré par l'IA est une **phrase**, pas un libellé court. Le slug qui en découle
nomme à la fois le **dossier temporaire d'exécution** ET, dans ce dossier, le fichier
**`<slug>_steps.py`** — il apparaît donc **deux fois** dans un même chemin. Un titre de ~100
caractères produisait un chemin dépassant la limite Windows (260 caractères), avec un message
d'erreur qui ne dit rien de sa cause réelle.

**Corrigé** dans `src/testpilot/api/services/generation_service.py::slugify` — coupé à
**`_SLUG_MAX = 40`** caractères, avec un **hachage de 6 caractères** ajouté à la coupe (deux titres
qui partagent le même préfixe long — fréquent, l'IA varie souvent la fin d'un titre, pas son début
— ne doivent pas produire le même slug tronqué). Vérifié sur le titre réel qui a fait planter la
génération : chemin simulé à 162 caractères au lieu de plus de 260.

### Bug 2 — un cas en échec technique faisait échouer TOUT le job (CORRIGÉ)

La boucle multi-cas (`resume_generation`) n'attrapait que `DuplicateName` autour de la génération
d'un cas. Le bug 1 ci-dessus, une fois déclenché sur un cas, remontait donc à la garde de tête de
fonction, qui marque **le job entier** `failed` — **sans annuler les cas DÉJÀ persistés** en base
par les itérations précédentes de la même boucle (aucune transaction ne les protège). Résultat
mesuré : 4 cas correctement créés, un job affiché comme entièrement raté.

**Corrigé** : un `except Exception` autour de l'appel à `agent.generate()` dans la boucle,
symétrique à celui qui existait déjà pour `DuplicateName` — un cas en échec est rapporté dans
`error`, la boucle continue, le job reste `done` si au moins un autre cas a réussi.

**Tests ajoutés** (non commités — voir §9) : `tests/test_module_detail.py` (5 tests sur `slugify` :
bornage, stabilité, distinction de deux titres au même préfixe) ; `tests/test_generation_multi_cas.py`
(`test_un_cas_en_ECHEC_TECHNIQUE_ne_fait_PAS_echouer_les_cas_DEJA_persistes`, qui rejoue exactement
le scénario mesuré). Suite complète : **1 307 tests passés**.

---

## 5. L'incident de pollution de données — RÉSOLU

Un agent d'une session antérieure a écrit 5 cas et 3 Sections factices dans la **vraie base**
(`data/testpilot.db`) par un bug de son propre harnais de vérification. **Nettoyé et vérifié** :
0 trace restante, `PRAGMA integrity_check` = `ok`, aucune donnée réelle touchée. Le script de
nettoyage (vérifié avant exécution, avec garde-fous avant/après) a été exécuté avec l'accord
explicite du porteur — ne pas le rejouer, il n'y a plus rien à nettoyer.

---

## 6. Quatre vraies spécifications, tirées du portail Sapian réel

Le porteur a demandé d'explorer le **vrai portail Sapian en local** (`http://localhost:10017`,
identifiants saisis par le porteur lui-même — **jamais par l'assistant**, règle stricte sans
exception) pour produire des spécifications qui serviraient réellement de matière de test, au-delà
des 6 specs déjà existantes (`specs/vert/1-*.md` à `6-*.md`).

⚠️ **Un texte ressemblant à une instruction adressée à un assistant IA** (« Oui, génère la V13
complète ») a été trouvé dans la description d'un ticket réel du portail pendant l'exploration —
signalé au porteur immédiatement, **jamais exécuté**. Sans rapport confirmé avec ce chantier ; à
garder en tête si un comportement inexpliqué apparaît un jour sur ce ticket précis
(`helpdesk.ticket` #SA-47504 côté Sapian).

**4 nouvelles specs**, chacune un vrai formulaire du portail, avec ses règles de validation
réelles (format de champ, pièces jointes obligatoires) — bons candidats pour éprouver la
génération multi-cas, puisque chacune couvre naturellement plusieurs user stories distinctes :

| Fichier | Formulaire réel | Règles trouvées sur la page |
|---|---|---|
| `specs/vert/7-mutation-payeur.md` | `/mutation/67` | codes payeur à 7 chiffres |
| `specs/vert/8-retenue-de-garantie.md` | `/retenue_garantie/86` | code client (7 chiffres), SIREN (9 chiffres), n° facture (format groupé), 3 pièces jointes obligatoires |
| `specs/vert/9-remboursement-client.md` | `/remboursement/64` | IBAN, BIC, case de certification RIB dont le refus est **écrit noir sur blanc par le formulaire lui-même** |
| `specs/vert/10-mandat-prelevement.md` | `/prelevements/85` | 2 pièces jointes obligatoires — plus simple, bon contrepoint |

**Spec 8 (Retenue de garantie) intégralement dogfoodée et vérifiée** — pas seulement générée :
5 Sections créées, 6 cas avec succès (un 7ᵉ a échoué proprement — bug 2 ci-dessus l'a confirmé
sans casser les 6 autres), les 6 `.feature` existent réellement sur disque
(`behave_runtime/generated/`), contenu vérifié non trivial (19 à 42 lignes chacun — le cas SIREN
teste même 3 variantes d'erreur avec assertion finale sur le nombre de tickets), les 6 versions
sont **approuvées automatiquement** (`validation-metier`), prêtes à l'exécution. Coût tracé au
ledger (découpage + passe métier partagés, génération par cas, ~0,09 à 0,47 $ selon la
complexité).

---

## 7. Le regroupement par Section dans la liste des cas

Après la génération de la spec 8, le porteur a signalé que les Sections créées, bien que présentes
en base (vérifié), n'apparaissaient nulle part groupées dans l'écran principal « Cas de test » —
seulement en cliquant une Section dans l'arbre latéral, ce qui **remplaçait toute la vue** par un
filtre à un seul résultat au lieu de la sous-titrer, contrairement à TestRail (une Section = un
dossier visible en permanence dans la liste).

⚠️ **Fausse piste écartée pendant l'investigation** : le premier test du clic semblait montrer que
le clic ne filtrait rien du tout. C'était un défaut de ciblage de coordonnées (2 pixels sous le
bouton réel), pas un bug de l'application — prouvé en cliquant l'élément DOM directement par son
texte. Le vrai problème était ailleurs (ci-dessous).

**Livré** :
- `frontend/src/pages/TestCasesList.vue` — les cas d'un module sont désormais sous-groupés par
  Section (`case_group`), chaque groupe avec son propre en-tête pliable/dépliable (compteur, lien
  « voir le document »), **visible directement dans la liste**, plus besoin de filtrer pour voir le
  regroupement. Un cas sans `group_id` (ne devrait jamais arriver — `CaseRepo.create`
  auto-enveloppe toujours) atterrit dans un groupe « Sans section » plutôt que de disparaître.
- **Bug corrigé** : `CasesShell.vue::openSpec` remplaçait tout l'objet `query` en filtrant sur une
  Section, effaçant le paramètre `module` au passage. Corrigé — la query existante est préservée.
- **Bug corrigé** : l'en-tête de la liste affichait « 15 cas affichés sur 15 » même quand un filtre
  de Section n'en montrait qu'un seul (comparaison au total du PROJET, pas de la Section active).
  Corrigé — message dédié (« N cas affichés pour cette section ») sous un filtre.

**Vérifié à trois niveaux** : 6 nouveaux tests (`frontend/src/__tests__/TestCasesList.groupesSections.spec.ts`,
deux Sections distinctes, cas orphelin, pliage indépendant, lien « voir le document », compte
honnête sous filtre) ; build propre ; **vérification en direct sur la vraie base** — clic réel sur
la Section « Retenue de garantie » dans l'arbre → URL passe à `?module=1&spec=88` (module
préservé), page affiche « 1 cas affiché pour cette section ». Suite complète : **157 tests, 24
fichiers**.

---

## 8. ✅ Récapitulatif complet de ce qui est FAIT et VÉRIFIÉ

### Exécution manuelle (chantier précédent, toujours valable)
Mode manuelle/automatique par campagne (trigger de concordance en base), pièces jointes (liste
blanche, `svg`/`html` refusés, téléchargement par id numérique), page détail d'un test
(`RunTestDetail.vue`, `T{run}-{case}`), onglets Activité et Progression. Détail complet : voir
l'historique de ce document si besoin (§5 de la version précédente).

### Type et État
Champs libres sans `CHECK` (comme `angle` avant lui), `CasePatch` étendu, `validation_status`
supprimé (reconstruction de table), les 5 sites d'écriture automatique retirés.

### Génération multi-cas (§9 — livré cette session)
- **9a** `src/testpilot/generation/decoupage.py` : spécification → user stories → ensemble
  **minimal** de cas par story (prompt orienté « pas de redondance », pas « énumère tout »).
- **9b** `generation_service.py` : une Section par story, un `propose_metier(plan, brief=...)` +
  une génération Gherkin par cas planifié — le pipeline mono-cas existant, **répété**, pas réécrit.
- **9c** Le texte de la spec vit sur `case_group.spec_content`, écrit une seule fois à la création
  de la Section — plus sur la version (sauf hors Section : CLI, automatisation d'un cas manuel).
  `repair_service.py` repointé sur la même source.
- **9d** `spec_extract.py` : PDF supporté (`pdfplumber`), plafond de taille (`SPEC_MAX_BYTES`),
  fichier original conservé sous `data/specifications/<hash>/`.
- **9e** `AddTestCase.vue` : écran de validation groupé par Section, pliable, chaque cas éditable
  et supprimable individuellement, retour à la liste (pas à un seul cas) une fois généré.
- **Robustesse ajoutée après dogfooding réel** (§4) : slug borné en longueur, isolation par cas
  dans la boucle de génération.

---

## 9. État git — à jour, PAS entièrement commité

**Un commit existe** : `96aedd4` — *« Génération multi-cas : une spécification, plusieurs cas de
test »* — contient 9a à 9e tels qu'ils étaient **avant** le dogfooding réel (§4-7 ci-dessus).

**Reste NON commité** (10 fichiers, tout le travail post-dogfooding) :
```
 M frontend/src/components/CasesShell.vue          (openSpec préserve module)
 M frontend/src/pages/TestCasesList.vue             (regroupement par Section + compte honnête)
 M src/testpilot/api/services/generation_service.py (slugify borné + isolation par cas)
 M tests/test_generation_multi_cas.py               (test de l'isolation par cas)
 M tests/test_module_detail.py                      (tests de slugify borné)
?? frontend/src/__tests__/TestCasesList.groupesSections.spec.ts
?? specs/vert/7-mutation-payeur.md
?? specs/vert/8-retenue-de-garantie.md
?? specs/vert/9-remboursement-client.md
?? specs/vert/10-mandat-prelevement.md
```

**Un commit s'impose** — deux vrais correctifs de production et 4 specs réelles ne devraient pas
rester en local. Pas fait automatiquement : la consigne du dépôt est de ne commiter que sur
demande explicite du porteur.

---

## 10. ⏳ Ce qui reste (non commencé)

### Assignation
Table `run_case_assignment` déjà créée (migration 25), rien ne l'alimente. Colonne « Assigné à »
dans `RunDetail.vue` affiche « — » en dur.

### Finitions
Mise à jour finale de `docs/ONBOARDING.md` une fois tout livré ET commité.

### Reporté, pas oublié (arbitrages TestRail antérieurs, toujours valables)
Priorité (3 niveaux, pas de « Critique »), clôture irréversible (au déploiement prod), références
en liste avec hyperlien, façons de saisir un résultat en lot / « Pass & Next » — voir
`docs/PARITE-TESTRAIL.md` §9 pour le détail complet.

---

## 11. Pièges déjà payés — ne pas les rejouer

1. **Un slug apparaît deux fois dans un chemin d'exécution** (dossier temp + fichier `_steps.py`) —
   toujours le borner en longueur pour tout ce qui nomme un fichier/dossier depuis un texte libre.
2. **Un `except` trop étroit dans une boucle multi-éléments cache les succès précédents** derrière
   un job marqué entièrement en échec. Isoler chaque itération.
3. **Un clic « sans effet » peut être un défaut de ciblage, pas un bug produit** — toujours
   reproduire avec un ciblage DOM direct (par texte) avant de conclure à un bug applicatif.
4. **Ne jamais saisir un mot de passe soi-même**, même stocké, même pour une instance locale, même
   si le porteur le proposait — le laisser s'authentifier lui-même dans le navigateur.
5. **Le nom de table entre guillemets**, une migration ancienne rejouée hors de son époque, une
   route hors `/projects/:pid` qui blanchit l'écran, `.color` vs `hsl(...)`, ne jamais lancer les
   tests pendant que l'app tourne sur le poste, XSS stocké par pièce jointe — voir versions
   précédentes de ce document si le détail est nécessaire à nouveau.
6. **Disque non borné** (`data/results/`, `data/specifications/`) : pas de purge, acceptable en V1
   si c'est dit.
7. **Régression pré-existante, non créée par ce chantier** : les exécutions de réparation
   (`run_service._maybe_repair`) ne reçoivent jamais de `run_id` — à traiter séparément.

---

## 12. Conventions du dépôt à respecter

- **Le code et les commentaires sont en français.**
- **Une décision se prend d'un seul côté, et c'est le serveur.**
- **Un fichier de test = un invariant**, docstring qui dit **pourquoi** il existe.
- **Jamais la couleur seule** à l'écran.
- Toute migration est **idempotente**, testée deux fois sur une base « pré-migration ».
- Pas de `os.getenv` hors de `config.py`. **Aucune mention de Claude/Anthropic dans les commits.**
- Style de travail voulu par le porteur : **changements aussi simples que possible**, **planifier
  avant de coder**, confier l'outcome à des agents plutôt que de les micro-gérer — **mais vérifier
  soi-même avant de considérer un résultat acquis**, y compris ses propres vérifications initiales
  (§1, §7).

---

## 13. Vérification

```bash
pytest                    # 1 307 verts (mesuré après les correctifs du §4)
cd frontend && npm test   # 24 fichiers, 157 tests, verts (mesuré après le §7)
```

**Bout en bout, sur l'application réelle** (redémarrer le serveur s'il tournait avant les derniers
correctifs — Windows ne recharge pas toujours un module Python modifié à chaud) :
1. Générer depuis une des 4 nouvelles specs (`specs/vert/7-*.md` à `10-*.md`) → vérifier plusieurs
   Sections créées, plusieurs cas chacune, tous avec un `.feature` réel sur disque.
2. Dans « Cas de test », ouvrir un module qui contient plusieurs Sections → vérifier qu'elles sont
   groupées avec leur propre en-tête pliable, sans avoir à filtrer.
3. Cliquer une Section dans l'arbre latéral → vérifier que le module reste dans l'URL et que le
   compte affiché est honnête (pas comparé au total du projet).
4. Créer une campagne manuelle/automatique, saisir un résultat, vérifier pièces jointes et
   provenance — voir §8 pour le détail (chantier antérieur, toujours valable).
