# Reprise — les 4 manques P1 sont livrés

> **À quoi sert ce document.** Reprendre l'implémentation dans une **nouvelle session**, sans avoir
> la conversation d'origine. Il remplace `REPRISE-P2.md`, dont il reprend les décisions, et
> **complète sa propre version précédente** — écrite en cours de session, avant que le dernier
> chantier (génération multi-cas) ne soit terminé, dogfoodé en conditions réelles et corrigé.
>
> Écrit le 2026-08-05, en fin de session. **Complété le 2026-08-06** (§0 ci-dessous — fiabilisation
> des résultats automatisés, traçabilité, et chantier Sections/Sous-sections/glisser-déposer) puis
> le **2026-08-07** (§0bis — incident de purge corrigé ; §0ter — le job de génération survit
> désormais à un redémarrage serveur). Régénérable :
> `python scripts/doc_en_pdf.py docs/REPRISE-P3.md`

---

## 0. Mise à jour du 2026-08-06 — fiabilisation, traçabilité, et Sections/glisser-déposer

### Fiabilisation des résultats automatisés — un vrai bug TestPilot corrigé, pas applicatif

Le porteur a lancé une exécution réelle et observé deux `retest` dont la capture d'écran semblait
identique à un `failed` — signalé explicitement comme suspect : *« ca c est un bug venant de
testpilot qui fausse les resultats de test »*. Deux causes distinctes trouvées et corrigées :

1. **`page.screenshot(...)` sans `full_page=True`** (`behave_runtime/environment.py::_capturer_ecran`)
   — les captures ne montraient que le viewport, donc se ressemblaient d'un échec à l'autre alors
   que le contenu réel différait. Corrigé.
2. **`_classe_conservee(ecrit, retenu)` avait un cas dégénéré**
   (`behave_runtime/steps_library/_base_helpers.py`) : quand `retenu` est **vide**, N'IMPORTE QUELLE
   classe de caractères absente de `ecrit` « prouve » trivialement qu'elle est conservée. Une règle
   apprise erronée (`date_debut` → `[A-Za-z]`) a fait injecter `AAAAAAAA` dans un champ date sur deux
   exécutions réelles successives (résultats 128, 129 de la campagne 18), faussant le verdict.
   **Corrigé** par une garde en tête de fonction (`if not str(retenu).strip(): return ""`), avec
   régression dédiée (`tests/test_refus_mesure.py::test_un_retenu_VIDE_ne_prouve_JAMAIS_de_classe`).
   Les 2 lignes de règle apprise corrompues nettoyées dans `data/regles-apprises/projet-1.jsonl`
   (sauvegarde horodatée conservée avant nettoyage, sur demande explicite du porteur).

### Traçabilité automatique (Étape A) — livrée et vérifiée sur données réelles

Chaque exécution automatique écrit désormais un **commentaire en langage clair** généré par IA
(`src/testpilot/verdict/explication.py::propose_explication`) — pour **TOUS les verdicts**, pas
seulement les échecs : *« cela garantit une possible vérification humaine d'une exécution
automatisée grâce à une IA »* (consigne explicite du porteur). Le commentaire est écrit **au
moment de la création du résultat**, jamais par `UPDATE` — respecte l'invariant « rien n'est jamais
modifié » du registre (`test_result`). Les captures d'écran sont archivées comme pièces jointes du
résultat (`result_attachment`, plafonné par `config.ATTACHMENT_MAX_PER_RESULT`).

### Chantier Sections/Sous-sections, déplacer-copier, glisser-déposer

Plan complet et à jour : `C:\Users\RomaricCAPO-CHICHI\.claude\plans\effervescent-tinkering-pascal.md`
(seul document qui fait foi sur le détail technique de ce chantier — ce qui suit n'en est qu'un
résumé d'état).

- ✅ **Étape 0** — retrait de « créer une campagne depuis une sélection de cas » : le porteur passe
  systématiquement par « Lancer une exécution » (`AddTestRunForm.vue`), qui offre déjà le choix du
  mode et la sélection des cas en un geste.
- ✅ **Étape 1** — vraies Sous-sections : une profondeur d'imbrication (migration 28,
  `case_group.parent_group_id`), parité TestRail par défaut (pas de niveau 3). Liens inline
  « Ajouter un cas » / « Ajouter une sous-section » à l'endroit exact où TestRail les place (sous
  la liste des cas d'une Section, plus dans la barre latérale). ⚠️ Bug de déploiement réel trouvé
  et corrigé pendant la vérification : un `CREATE INDEX` sur la nouvelle colonne avait été placé
  dans `schema.sql` (qui tourne AVANT les migrations) au lieu de la migration elle-même — plantait
  le tout premier appel sur la vraie base de production. Nouveau test dédié à cette classe de bug :
  `tests/test_migration_28.py` (copie la VRAIE base et rejoue le chemin complet `init_db()`).
- ✅ **Étape 2** — déplacer/copier un cas entre Sections, en base : `CaseRepo.deplacer` (réattache,
  même `id`, historique intact) / `CaseRepo.copier` (clone réel, aucun historique hérité, nouveau
  `feature_slug`, script recopié sur disque). Vérifié en direct sur données réelles (Sapian) :
  déplacement d'un cas déjà exécuté → historique byte-identique ; copie → cas neuf sans résultat,
  fichiers `.feature`/`_steps.py` distincts sur disque. Nettoyé après vérification.
- ✅ **Étape 2bis** — le porteur avait comparé l'écran livré à l'Étape 2 (icône ⋮ → fenêtre listant
  toutes les Sections cibles) à de vraies captures TestRail : chez eux c'est un **glisser-déposer
  natif** (poignée par ligne, dépôt sur une Section, petit menu QUI APPARAÎT AU POINT DE DÉPÔT —
  « Déplacer ici (ctrl/cmd) / Copier ici (maj) / Annuler », les touches déclenchant l'action
  directement sans même faire apparaître le menu). Livré : remplace le menu ⋮ pour les cas ET les
  Sections (déplacer seulement pour ces dernières — jamais de copie, ça dupliquerait en cascade
  tous leurs cas), retire la colonne « Module » du tableau (redondante avec le regroupement déjà
  affiché en en-tête). Nouveau backend : `CaseGroupRepo.deplacer` + route
  `POST /api/groups/{id}/deplacer`. **Bug trouvé et corrigé au passage** : `DuplicateName` et
  `ProfondeurInvalide` héritent toutes deux de `ValueError` en Python — l'ordre des `except` sur
  les 3 routes déplacer/copier faisait qu'une collision ou une imbrication invalide renvoyait 404
  au lieu du bon code d'erreur (409/422), sans qu'aucun test HTTP existant ne l'attrape. Vérifié en
  direct sur données réelles (nesting/promotion de Sections jetables, nettoyées après coup) + suite
  complète back/front vertes.
- ✅ **Étape 3** — génération multi-cas mise à PLAT : l'IA propose une liste plate de cas (fini le
  regroupement automatique en Sections par user story détectée), chacun avec un simple repère de
  lecture (« Issu de : … », jamais une Section). Livrée une première fois avec un choix de Section
  PAR CAS sur l'écran de validation — **remplacé le jour même par l'étape 3bis** ci-dessous, sur
  retour du manager du porteur.
- ✅ **Étape 3bis** (même jour, 2026-08-07) — la Section se choisit désormais AVANT la génération,
  UNE SEULE FOIS pour tout le lot, sur l'écran de spécification (même patron exact que le choix du
  Module, et **obligatoire** comme lui — bouton désactivé sans Section choisie/nommée). L'écran de
  validation n'a donc plus aucun sélecteur : une simple liste de cas, **repliée par défaut**, à
  déplier un par un pour consulter/corriger. `resume_generation` ne crée plus AUCUNE Section
  elle-même, et valide le `group_id` reçu UNE SEULE FOIS pour tout le lot (repli sur l'enveloppe
  automatique, par cas, si la Section a disparu entre-temps — jamais bloquant). Vérifié : suites
  complètes back (1356) + front (181), type-check propre, **et en direct sur le projet réel**
  (serveur jetable) — une Section invalide ou d'un autre module est bien refusée en 404 avant tout
  appel LLM (aucun coût), une Section valide démarre normalement, aucune trace laissée en base.
  **Bug de régression trouvé et corrigé en cours de route** : un test existant simulait
  `run_generation` avec une signature figée ignorant le nouveau `group_id` — l'appel plantait en
  silence dans la tâche de fond FastAPI, invisible tant qu'on ne lance pas la suite COMPLÈTE (les
  fichiers ciblés seuls ne l'auraient jamais montré).

**Ordre et discipline, inchangés** : chaque étape expliquée avant d'être codée, vérifiée
personnellement par le porteur (tests + vérification live sur données réelles + nettoyage des
traces de vérification) avant de passer à la suivante.

---

## 0bis. Incident réel du 2026-08-07 — purge cassée par le registre, corrigée

Le porteur a signalé une génération « timed out » sur Mutation Payeur, avec l'impression que
« tout a été perdu ». Investigation directe sur `data/testpilot.db` (lecture seule d'abord) :

- **Rien n'était réellement perdu** : les modules « Mutation Payeur » et « Retenue de garantie »
  avaient été mis à la corbeille (suppression douce) par le porteur lui-même après l'incident —
  leurs 13 cas et 9 sections étaient intacts, juste invisibles.
- **Cause probable du « timed out »** : le serveur du porteur a changé de PID entre deux contrôles
  — un redémarrage a eu lieu pendant la génération. Les jobs de génération ne vivaient qu'en
  mémoire (`generation_service._JOBS`, un dict Python) : un redémarrage les effaçait, l'écran
  restait bloqué sans jamais recevoir de réponse. **Corrigé le même jour** — voir §0ter.
- Sur confirmation explicite et informée du porteur (irréversibilité expliquée deux fois), les
  deux modules ont été **purgés définitivement**. La purge a d'abord échoué (`sqlite3.
  IntegrityError: FOREIGN KEY constraint failed`) sur le module ayant du VRAI historique
  d'exécution : `CaseRepo.purger` (cascade de suppression définitive) ne nettoyait jamais
  `test_result`/`result_attachment`/`run_case_assignment` (migration 25, 2026-08-06) — un cas déjà
  exécuté dans une campagne devenait **insupprimable définitivement**, même depuis la corbeille.
  Même défaut déjà payé deux fois pour `cost_ledger` et `test_run_case` (une table ajoutée après
  coup, jamais raccordée à la cascade). **Corrigé** dans `CaseRepo.purger`
  ([repositories.py](src/testpilot/store/repositories.py)), avec un test dédié qui rejoue le
  scénario exact (`tests/test_suppression_douce.py::test_purger_un_cas_AVEC_un_vrai_resultat_au_
  registre_ne_PLANTE_PAS`). Suite complète repassée : 1357 verts.
- ⚠️ **Le serveur du porteur (port 8000) tourne encore sur l'ANCIEN code** — Python ne recharge
  pas à chaud. Un redémarrage est nécessaire pour que ce correctif s'applique chez lui.

---

## 0ter. Mise à jour du 2026-08-07 — fiabilité : le job de génération survit à un redémarrage

Correctif du gap identifié en §0bis. **Le job de génération est désormais PERSISTÉ en base**, plus
seulement un dict Python en mémoire — un redémarrage serveur pendant une génération en cours ne
laisse plus l'écran bloqué indéfiniment.

- **Migration 29** ([db.py](src/testpilot/store/db.py)) : nouvelle table `generation_job` (`id`,
  `status`, `error`, `case_ids`, `module_id`, `payload` JSON, `cost_usd`, `created_at`,
  `updated_at`), index sur `status`. Testée deux fois (base fraîche + base pré-migration réelle),
  comme toute migration du dépôt.
- **`GenerationJobRepo`** ([repositories.py](src/testpilot/store/repositories.py)) remplace le
  dict `_JOBS` : `creer`/`get`/`maj`. Les champs souvent filtrés (`status`, `error`, `case_ids`,
  `cost_usd`) sont des colonnes dédiées ; tout le reste (titre, spec, auteur, section choisie,
  cas proposés…) vit dans `payload` (JSON), fusionné à la lecture — la forme du dict rendu par
  `get()` n'a pas changé pour ses appelants.
- **Détection de blocage** : un job en `status="running"` dont `updated_at` date de plus de 15
  minutes (`GenerationJobRepo.SEUIL_BLOQUE_SECONDES`) est réinterprété en `failed`, avec un message
  clair (« la génération semble interrompue — le serveur a peut-être redémarré... Relancez-la. »),
  **écrit en base** (pas juste renvoyé une fois) au moment même de la lecture — même patron que
  `ExecutionRepo.finalize`, un seul endroit qui écrit cette conclusion. `awaiting_metier` (attente
  humaine légitime, potentiellement longue) est explicitement EXEMPTÉ de cette détection.
- `generation_service.py` réécrit en conséquence : `get_job`/`validate_metier` prennent désormais
  `conn` en premier paramètre (le job vit en base, plus en mémoire globale).
- Le frontend n'a nécessité **aucun changement** : `AddTestCase.vue` affiche déjà `job.error`
  tel quel, quel que soit son contenu.

**Vérifié** : `tests/test_generation_job_repo.py` (10 tests, dont la survie du job à travers une
nouvelle connexion DB — la preuve centrale du correctif — et l'exemption `awaiting_metier`) ;
suite complète back (1370 tests) et front (186 tests) vertes, `type-check` propre. Vérification
live supplémentaire, en dehors des tests : un job `running` avec un `updated_at` vieux de 20
minutes simulé directement en base, relu via la VRAIE route `GET /api/modules/jobs/{id}` — répond
bien `status: "failed"` avec le message d'interruption, et cette conclusion est relue identique
depuis la base (pas transitoire).

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

**Mise à jour 2026-08-06** : la liste ci-dessus reflète l'état au 2026-08-05. Depuis, le chantier
§0 (fiabilisation + traçabilité + Sections/glisser-déposer) a ajouté un volume de changements bien
plus large, toujours **NON commité** en totalité — ne pas ré-énumérer ici à la main, ça se périme
à chaque session : lancer `git status` fait foi. Toujours aucun commit hors `96aedd4` et
`75a3ede`/`5c202b8`/`538f514`/`d7cc5db` (voir `git log`) pour ce périmètre.

**Un commit s'impose** — deux vrais correctifs de production et 4 specs réelles ne devraient pas
rester en local. Pas fait automatiquement : la consigne du dépôt est de ne commiter que sur
demande explicite du porteur.

---

## 10. ⏳ Ce qui reste (non commencé)

**Chantier « génération multi-cas » (§0, Étapes 0 à 3bis + AddTestRunForm) déclaré TERMINÉ par le
porteur le 2026-08-07.** Ce qui suit est la suite du programme, pas une continuation de ce chantier.

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
