# PLAN — état réel et route jusqu'au produit fini

> **Version 3 — 2026-07-24.** Document de référence **vivant** : il dit ce qui EST vrai
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

**Chaque maillon est prouvé en réel**, pas seulement testé. Coût mesuré : **~0,08 à 0,11 $ par cas**
(≈ 10 % de la cible du §9).

### Les chiffres du jour

*(Vérifiés le 2026-07-24 en relançant les deux suites.)*

| | |
|---|---|
| Tests | **915 Python · 110 vitest** — tous verts |
| Schéma | `user_version = 24` |
| Fiabilité — réussite technique au 1ᵉʳ jet | **88 %** sur le banc (**n=8**), re-confirmé au rejeu du 2026-07-23 |
| Verdicts | **0 fausse accusation par invention de champ** ; 4ᵉ verdict `donnee_invalide` déclenché en réel |
| Coût d'un cas (analyse + génération) | **~0,08 à 0,11 $** — modèle **Sonnet 4.6** |
| Annuaire projet 1 | 37 routes · 373 champs · **373 rôles · 287 libellés · 21 règles de saisie en français** |

### La progression, mesurée (et non supposée)

```
25 %  (4 specs)  →  correctif champs FICHIER          (13 routes sur 37 concernées)
75 %  (4 specs)  →  champs CACHÉS + URL RÉELLE
88 %  (8 specs)  →  banc DOUBLÉ, et plus dur (jusqu'à 17 champs requis, 3 fichiers)
```

⚠️ **Je m'attendais à une baisse sur un banc plus dur — c'est monté.** Les correctifs étaient
plus structurels que prévu : les 4 formulaires ajoutés sont passés du premier coup.

⚠️ **Nuance non mesurée** : les 7 succès sont tous `success / non_conforme` — les tests
**tournent** et trouvent des écarts fonctionnels. Savoir si ces écarts sont réels ou dus à des
assertions trop strictes est **une autre question, non instrumentée**.

🔴 **Cette nuance a trouvé sa réponse le 2026-07-21, et elle est mauvaise pour nous.** Au moins une
partie de ces `non_conforme` n'était **pas** un écart de l'application : le test écrivait une
valeur que le formulaire **refuse** (motif `\d{7}` violé), la soumission n'avait jamais lieu, et
l'assertion de création échouait mécaniquement. 12 des 21 routes à champ requis étaient exposées.
Correctif en place (9ᵉ cause, §5) ; **re-mesure lancée le 2026-07-22 pour établir l'écart réel.**
Tant que ce chiffre n'est pas tombé, le 88 % reste vrai sur l'axe *exécution* — et le
`non_conforme` reste **non crédible** sur l'axe *fonctionnel*.

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

## 2bis. ✅ ARCHITECTURE — *arbitrée et LIVRÉE (22-23/07), inscrite au brief le 24/07*

> **Statut au 2026-07-24 : LIVRÉE pour l'essentiel.** Composants **1** (annuaire enrichi), **A**
> (lire la page au lieu d'accuser), **2** (résolveur déterministe), **3** (vérification par l'état
> + réponse serveur) et **4** (4ᵉ verdict) sont en production dans l'outil. **Restent** : le
> **contrat de connecteur** (repoussé au 2ᵉ connecteur, décision du 24/07) et le **validateur
> pré-exécution** (en filet).
>
> **Forme retenue, plus précise que la proposition initiale** : le step d'intention est le chemin
> **imposé sur le scénario nominal** ; l'agent nomme encore un champ quand ce champ **est le sujet
> du test** (scénario négatif) ou quand l'annuaire ne couvre pas la situation. Le brief porte cette
> rédaction (§6, amendement du 2026-07-24) — pas la version absolue « le LLM ne nomme plus jamais
> un champ », qui aurait promis plus que le produit ne tient.
>
> ⚠️ **Ce que ça a changé, mesuré** : le taux technique **n'a pas bougé** (88 % avant, 88 % après).
> Le gain est ailleurs — zéro fausse accusation par invention, et un verdict honnête là où l'outil
> accusait l'application à tort. *Ne pas raconter cette architecture comme un gain de fiabilité
> technique : ce serait faux.*

### Le problème qu'elle résout

Huit causes d'échec technique trouvées, **huit correctifs un par un**. Six relèvent du même motif
(*l'annuaire savait, personne ne transmettait*), deux sont des trous d'outil. Et les trois filets
existants — smoke-check, dry-run, boucle de réparation — **n'en ont attrapé aucune**.

Ce n'est pas huit bugs : c'est **un défaut de conception répété**.

**La cause racine** : le LLM écrit lui-même les sélecteurs et les noms de champs
(`je renseigne le champ "partner_email"`). Chaque fait de l'application qu'il ignore devient une
panne. On lui a enseigné huit faits ; il en reste un nombre inconnu.

### L'inversion proposée

> **Le LLM produit une INTENTION. Une couche déterministe la résout en actions, en lisant le
> modèle mesuré.**

```gherkin
Quand je remplis le formulaire de demande d'avoir avec des données valides
Et je soumets le formulaire
Alors un enregistrement « helpdesk.ticket » a été créé
```

Le résolveur lit l'annuaire : il remplit **tous** les champs requis visibles, avec des valeurs du
**bon type**, téléverse pour les fichiers, choisit une **vraie** option, ignore les champs cachés,
clique le vrai bouton. **Le LLM ne nomme plus jamais un champ — il ne peut donc plus se tromper
dessus.** Les huit causes deviennent structurellement impossibles.

### Ce que la recherche a confirmé (2026-07-21)

| Constat | Source |
|---|---|
| La guérison **par intention** rattrape **75-90 %** des échecs, contre **40-70 %** pour le rattrapage de sélecteurs | [Keysight — Self-healing 2026](https://www.keysight.com/blogs/en/tech/software-testing/2026-self-healing-test-automation-beyond-locator-patching) |
| Les locateurs **orientés utilisateur** (`getByRole`, `getByLabel`) survivent aux refontes ; CSS/attributs sont un dernier recours | [Playwright — Best Practices](https://playwright.dev/docs/best-practices) |
| L'**arbre d'accessibilité** est ce que lisent `getByRole`, les lecteurs d'écran **et les agents IA** (Playwright MCP l'expose en YAML) | [TestDino — Accessibility tree](https://testdino.com/blog/accessibility-tree) |
| En *model-based testing*, **l'exactitude du modèle est tout** — un modèle inexact produit des tests trompeurs | [Sauce Labs — MBT](https://saucelabs.com/resources/blog/the-challenges-and-benefits-of-model-based-testing) |
| Un crawler doit **extraire les contraintes de validation** ; toute donnée générée doit être validée contre les règles réelles | [testRigor — Test data generation](https://testrigor.com/blog/test-data-generation-automation/) |
| Vérifier l'**état persisté** (API/base) prouve ce qu'un message d'écran ne prouve pas | [API testing & DB integration](https://tenjinonline.com/blog/api-testing/api-testing-database-integration-guide/) |

### Les quatre composants

**1. Enrichir le modèle mesuré** *(gratuit, sans LLM, conditionne tout le reste)*

| Ce qu'on capture | Usage | Portabilité |
|---|---|---|
| **rôle + nom accessible** | AGIR (cliquer, remplir) — résiste aux refontes | **universel**, tout connecteur web |
| **nom technique** (`partner_email`) | VÉRIFIER l'état par RPC/API | propre au connecteur |
| **contraintes** (`pattern`, `min/max`, `maxlength`, `type`, options) | générer des valeurs **conformes** | universel |

✅ **FAIT le 2026-07-21.** L'annuaire du projet 1 porte désormais **373 rôles / 373 champs**,
**287 libellés** et **36 règles de saisie**, sur 37 routes. Le compteur de règles est affiché sur
la carte du projet — c'est le seul témoin visible qu'une cartographie est fraîche.

🔴 **MAIS ce composant a un PLAFOND STRUCTUREL, découvert le 2026-07-22 et à ne pas oublier.**
Sur `/fournisseur/creation`, le champ `tva_intracommunautaire` n'a **aucune contrainte HTML** —
l'annuaire le voit « libre ». À l'exécution, le navigateur le refuse : *« Le numéro de TVA doit
contenir uniquement des chiffres. »* La règle est appliquée en **JavaScript**.

**Aucun crawl statique ne verra jamais une règle écrite en JavaScript.** Enrichir davantage
l'annuaire ne corrigera pas ça — c'est une limite de la méthode, pas de son implémentation.

**Conséquence directe sur la stratégie** : *prévenir* ne peut pas être exhaustif ; *détecter à
l'exécution*, si. Le navigateur rapporte son verdict que la règle vienne d'un attribut ou d'un
script (`checkValidity()` / `validationMessage`). D'où le composant A ci-dessous, qui n'était pas
prévu et qui s'avère plus fondamental que le reste.

**A (non prévu, FAIT le 2026-07-22). Lire la page au lieu d'accuser.**

Quand le comptage n'augmente pas, `diagnostic_soumission` interroge la page : validation native
d'abord (si un champ est `:invalid`, l'envoi n'a **jamais eu lieu**), puis les messages affichés,
puis le silence — nommé comme tel. **Aucun statut ne change** ; on explique.

Résultat sur 3 exécutions réelles :

| Cas | Diagnostic |
|---|---|
| `fournisseur_creation` | **notre donnée** — `tva_intracommunautaire` refusé par le navigateur |
| `achat_siege` | refus **SILENCIEUX** |
| `demande_avoir` | refus **SILENCIEUX** |

⚠️ **Les deux silences sont le vrai résultat.** Aucun raffinement du verdict ne fera parler une
page muette : c'est ce qui rend le composant 3 (vérification par l'état) nécessaire, et pas
seulement souhaitable. On ne le savait pas avant A ; on l'aurait découvert après avoir construit
B et C dessus.

**2. Steps métier + résolveur déterministe.** Le LLM fournit le **sens** (valeurs métier
plausibles) ; le déterministe garantit la **forme** (conformité aux contraintes mesurées).

**3. Vérification par l'ÉTAT, pas par l'écran.** Nos 8 succès sont tous `non_conforme` —
probablement des assertions sur du texte affiché. Un verdict honnête vérifie que la donnée existe.

**4. Un QUATRIÈME verdict.**

```
le test n'a pas pu tourner              → erreur technique
le test a tourné, l'app est conforme    → conforme
le test a tourné, l'app ne l'est pas    → non conforme
le test a tourné, ses DONNÉES refusées  → test à corriger   ← MANQUANT
```

Sans lui, une donnée mal formée fait dire à l'outil « votre application est cassée ». **C'est le
pire mensonge possible pour un outil de test** — et la machinerie existe déjà
(`test_a_reparer` vs `vrai_bug`), elle n'est simplement pas branchée sur ce cas.

### Ce que ça garantit — et ce que ça ne garantit PAS

**Ça ne donne pas « zéro erreur technique ».** Ça change la NATURE de ce qui reste :

> Aujourd'hui : « le modèle a inventé quelque chose » — surface **illimitée**, imprévisible.
> Après : « le modèle mesuré est incomplet ou périmé » — surface **bornée, détectable, réparable**.

**Limites qui subsistent, quoi qu'on fasse** :
- les **états dynamiques** (champs conditionnels, assistants, modales) — le crawl reste une photo ;
- les **règles métier absentes du HTML** (« l'IBAN doit correspondre au client ») — d'où le 4ᵉ verdict ;
- le **périmètre exploré** : on ne valide que ce qu'on a mesuré. Le back-office Odoo
  (`/web`, `/odoo`) est **hors périmètre du crawl** — l'y étendre serait un autre produit,
  **décision du porteur**.

### Écarté, et pourquoi

**Un agent IA qui pilote le navigateur en direct** (Playwright MCP, outils « agentic ») : coût par
exécution, non-déterminisme **à chaque run**, et surtout **aucun artefact versionnable**. Un outil
de gestion de tests a besoin d'un test **stable, relisible, rejouable**. On garde la génération
d'un test statique — mais on **explore** via l'arbre d'accessibilité.

### Impact sur l'existant

| | |
|---|---|
| **Inchangé** | toute l'interface · le parcours (spec → pause métier → validation → test → campagne) · le référentiel · les campagnes multi-modules · l'onglet Qualité · le suivi des coûts |
| **Enrichi** | l'exploration relève plus d'informations → **ré-explorer** (gratuit, sans LLM) |
| **Interne** | la façon dont le test est écrit sous le capot — **invisible pour l'utilisateur** |
| **Devient inutile** | les 8 « leçons » enseignées au prompt : elles ne deviennent pas fausses, elles ne servent plus |

⚠️ **Les tests déjà générés continuent de fonctionner** : on ajoute une façon d'écrire, on ne
retire pas l'ancienne. Deux générations cohabiteront — sans danger.

**Risque : faible** (on ajoute une couche, le socle reste). **Effort : réel** — le plus gros
chantier depuis le début.

### Ordre imposé

1. **Enrichir le modèle** *(gratuit, sans risque)* ;
2. **Steps métier + résolveur** ;
3. **Vérification par l'état + 4ᵉ verdict** ;
4. **Contrat de connecteur**, extrait de ce que le résolveur exige ;
5. **Validateur pré-exécution** — en filet, plus en pièce maîtresse.

> **1 avant 2, impérativement** : le résolveur ne peut pas être meilleur que le modèle qu'il lit.

### Critère d'acceptation

Un **corpus de non-régression des 8 causes historiques** : les 8 Gherkin qui ont échoué doivent
être rejetés — ou rendus impossibles à produire. Vérifiable, falsifiable, et interdit qu'une cause
revienne.

---

## 3. Ce qui RESTE — la route jusqu'au produit fini

### Phase 1 — Consolider *(en cours)*

- [x] **Écrire ce plan** + réalignement de la documentation.
- [x] **Élargir le banc à 8 specs** — n=4 n'était pas un chiffre défendable.
- [x] **`demande_avoir`** — résolu : l'agent inventait l'identifiant de route.
- [x] **`sinistre_client`** — résolu : `leave_field_empty` aveugle au `<select>`.
- [x] **Remesurer** — fait le 2026-07-23 : 88 % technique, 0 fausse accusation par invention.
- [x] 🔴 **ARBITRER la proposition d'architecture du §2bis** — arbitrée ET livrée (22-23/07).
- [x] **Le doute sur les `non_conforme`** — tranché : une partie n'était pas un écart de
      l'application mais **notre donnée refusée**. D'où le 4ᵉ verdict. Le reste (« l'app rejette en
      silence une saisie valide ») est désormais **nommé** au lieu d'être converti en défaut.
- [x] **Auditer le brief contre le code réel** — fait le 2026-07-24 : **17 écarts** relevés, tranchés
      un par un par le porteur, **11 amendements** inscrits au journal du brief. Le travail qui en
      découle est en tête de `BACKLOG.md`.
- [ ] **Mettre en œuvre le §5bis du brief** — « zéro verdict non concluant », 6 mécanismes.
      Le premier (la **règle apprise à chaque refus**) est le plus rentable : il attaque les règles
      JavaScript, seul angle mort structurel de l'annuaire.

### Phase 2 — Rendre déployable

> **Cible arrêtée le 2026-07-24** : un **serveur interne**, **plusieurs testeurs**, pour des tests
> complets — même si les verdicts ne sont pas encore tous concluants. L'ordre suivi est : lot 1
> *savoir contre quoi on teste* → lot 2 *sortir de la machine* → lot 3 *rendre les résultats non
> concluants exploitables* → lot 4 *écran Spécification*.

- [x] **Repli silencieux vers `localhost:10017` / `admin`** — **levé le 2026-07-24**. Un projet dont
      la connexion est incomplète (adresse, base, utilisateur ou mot de passe) fait désormais
      **refuser** le lancement d'un cas, d'une campagne, d'une exploration et d'une génération, avec
      un message qui dit **quoi corriger**. `project_env` reste un traducteur sans jugement pour la
      ligne de commande ; `verifier_connexion` est la garde de l'API. *Un test qui figeait le repli
      comme comportement voulu a été réécrit — il documentait le défaut.*
- [x] **La cible n'est plus absente de l'historique** — **fait le 2026-07-24** (migration 20).
      `execution` porte `target_url` / `target_database` / `target_username` — **jamais le mot de
      passe** — écrits à l'ouverture de la ligne, exposés par l'API, affichés dans le rapport, la
      liste des exécutions et l'onglet Tests & Résultats. Les exécutions antérieures restent vides :
      *« on ne sait pas »* est la vérité ; une cible reconstituée depuis la configuration du jour
      serait une supposition présentée comme un fait.
- [x] **Mot de passe de connexion chiffré au repos** — **fait le 2026-07-24** (migration 21). La
      colonne porte un jeton `enc:v1:…` ; les secrets déjà stockés sont repris par la migration,
      idempotente. Clé par `TESTPILOT_SECRET_KEY`, sinon `data/.secret_key` (gitignoré).
      **Honnêteté sur la portée** : ça protège la base **au repos** (copies, sauvegardes, export),
      pas quelqu'un qui a la base **et** la clé. Une clé perdue ne fait **jamais** passer le jeton
      pour un mot de passe : on rend vide, et la garde de connexion dit quoi corriger.
- [x] **Verrou d'accès d'instance** — **fait le 2026-07-24**. `TESTPILOT_ACCESS_PASSWORD` : un
      secret partagé, une session signée (changer le mot de passe invalide toutes les sessions),
      un écran de connexion. **Ce n'est pas un système de comptes** (hors V1) et l'écran le dit.
      Vide = aucun verrou, comme avant.
- [x] **Qui a fait quoi** — **fait le 2026-07-24**. Le nom saisi à l'arrivée signe les cas créés et
      les relectures. **Signature déclarée, pas identité vérifiée** — dit à l'écran. Sans nom,
      l'auteur reste vide : « on ne sait pas » plutôt qu'un « admin » inventé.
- [x] **Procédure de déploiement** — `docs/DEPLOIEMENT.md`, **suivie de bout en bout**, pas
      théorique. README et `.env.example` refaits (le README annonçait encore l'Incrément 0 et
      « frontend hors périmètre » ; le `.env` portait le budget de 50 € retiré du produit).
      ⚠️ **Défaut trouvé en démarrant vraiment le serveur** : la procédure demandait de vérifier
      une ligne de journal qui n'apparaît **jamais** sous la commande `uvicorn` recommandée.
      L'état du verrou est désormais exposé sur `/api/health` — vérifier une protection ne doit
      pas dépendre d'une configuration de journalisation.
- [ ] **HTTPS / reverse proxy** si l'instance sort du réseau de confiance : le cookie de session
      voyage sinon en clair. Hors outil (affaire d'exploitation), écrit dans la procédure.
- [ ] **Une seule identité pour trois usages** (navigateur, RPC de test, RPC d'exploration).
      Conséquence produit : impossible de tester « un employé ne doit pas voir la page admin » —
      ça bloque toute une famille de cas « erreur / permission ».

### Phase 2bis — Ce que le brief a tranché le 2026-07-24 *(détail en tête de `BACKLOG.md`)*

- [x] **Artefacts bruts d'exécution conservés** — **fait le 2026-07-24** (migration 22). Le dossier
      de run était **détruit** en sortie (`rmtree`) : journal du moteur, détail par scénario,
      `.feature` et steps joués partaient avec. Ils sont désormais archivés dans
      `data/executions/<id>/` et consultables depuis le rapport. Archivage **best-effort** : un
      disque plein ne fait pas tomber une exécution qui a créé de vraies données.
      *« Aucune trace conservée » et « dossier introuvable » sont deux messages distincts — une
      absence de signal n'est pas un signal.*
- [x] **Temps et taux de verdicts concluants** affichés au banc — **fait le 2026-07-24**. Le
      récapitulatif de fin de banc a été **extrait en fonction pure et couvert par des tests** :
      il avait planté une fois *après* la dépense, et n'était atteignable qu'en repayant un banc.
- [x] **Écran de la Spécification + modèle de spécification** — **fait le 2026-07-24**. Le CRUD
      existait côté serveur depuis le 2026-07-20 **sans qu'aucun écran ne l'appelle** : personne ne
      pouvait créer ni relire une spécification, et les seules existantes étaient les enveloppes
      auto-créées par la génération (une par cas). Le modèle du brief — *une spec → N cas, un par
      angle* — était donc **inatteignable par l'interface**. Désormais : création depuis l'arbre,
      fiche avec le document, cas qui en sont nés, génération **depuis** la spec, et un **modèle**
      proposé quand la page est blanche. Éditer ne génère rien et ne dépense rien.
- [ ] 🔴 **Tableau de bord « modules à retester »** — le JTBD 2, la promesse qui justifie l'outil.
      Sans lui, un critère du §9 reste non observable.
- [ ] **Provenance d'un résultat (exécuté / déclaré)** — promis au brief le 2026-07-20, jamais bâti.
- [ ] **Mode dev / mode utilisateur.**
- **Hors V1, arbitré** : comptes/rôles/client externe (prérequis déploiement client) · Jira, charge,
  sécurité, CI-CD (V2) · abstraction multi-connecteurs (au 2ᵉ connecteur).

### Phase 2ter — Conception : rendre l'application tenable *(→ `docs/CONCEPTION.md`)*

Revue des pratiques de conception + **audit du code réel** (2026-07-24). Ordre arbitré par le
porteur : **E → A → B → C → D**.

- [x] **Lot E — nettoyer le terrain** *(fait le 2026-07-24)*. 5 pages **jamais routées**
      supprimées (`CaseDetail`, `CasesList`, `ExecutionsList`, `ModuleDetail`, `ModulesOverview`).
      ⚠️ **Le code mort trompe, et j'en suis la preuve** : l'affichage « testé contre… » du lot 1
      avait été ajouté dans `ExecutionsList.vue`, une page morte. Remis sur l'écran **vivant** —
      le détail d'une campagne — et lu sur ses **exécutions réelles**, jamais sur la connexion
      actuelle du projet. Deux cibles dans une même campagne sont **signalées**, pas arbitrées.
      Système de jetons documenté en 3 couches (aucune couleur en dur : vérifié, 0 occurrence).
- [x] **Lot A — une couche de données unique** *(fait le 2026-07-24)*. `@tanstack/vue-query` +
      `lib/donnees.ts` : clés dérivées d'un seul endroit, chaque mutation déclare ce qu'elle
      périme. Le rechargement du shell à chaque clic (`watch(route.fullPath, load)`) est supprimé.
      **Mesuré au navigateur** sur l'application compilée : **0 requête redondante** sur 6
      navigations internes (les 3 listes de l'arbre + les campagnes). ⚠️ Ma première mesure était
      fausse — elle naviguait par rechargement de page, ce qui détruit le cache à chaque fois.
- 🟡 **Lot B — le contrat d'API** *(2 tiers faits le 2026-07-24)*. ✅ Erreurs **RFC 9457** avec un
      catalogue de codes stables ; ✅ **suppression douce + corbeille** (migrations 23-24) — le
      produit tient enfin son §7, `delete_project` ne détruit plus rien sans filet.
      ✅ **Pagination par curseur** + recherche et filtre **au serveur** *(fait le 2026-07-24)* :
      mesuré sur 600 cas — page de 100 en 31 ms, reprise exacte, recherche en 21 ms.
      Au passage, la règle du **statut de lecture** a quitté le TypeScript pour `verdict/status.py` :
      elle est calculée par le serveur et exposée sur les cas, exécutions, scénarios et campagnes —
      **un seul endroit décide**, et un test compare les deux formes (Python / SQL) sur les
      24 combinaisons possibles.
      ⏳ `/api/v1` **volontairement reporté** : un versionnage protège un consommateur qu'on ne peut
      pas déployer avec l'API. Il n'en existe aucun aujourd'hui (le front est servi par l'API).
- [x] **Lot C — le quotidien du QA** *(fait le 2026-07-24)*. Recherche instantanée, sélection
      multiple, actions en lot (campagne à sélection figée, priorité, suppression), densité,
      colonnes, préférences conservées + réinitialisation. **Mesuré au navigateur sur 20 cas** :
      recherche = 0 requête ; composer une campagne de 20 cas = **1 requête** au lieu de 20 gestes.
- [x] **Lot D — clavier et accessibilité** *(fait le 2026-07-24)*. 19 boutons nommés + un
      **garde-fou** qui refuse qu'un bouton muet revienne ; modales au clavier (focus donné,
      enfermé, rendu) ; palette de commandes `Ctrl/⌘+K`. ⚠️ L'anneau de focus était à **2,69:1**,
      sous le seuil WCAG de 3:1 — calculé, pas vu. Opaque : **4,31:1**.
      Vérifié **au clavier seul** dans un vrai navigateur.

### Phase 2quater — Audit « ne garder que ce qui sert » *(fait le 2026-07-24 → `docs/LOGIQUE.md`)*

- [x] **Inventaire du mort**, en suivant la chaîne route ← méthode du client ← écran (une route
      citée par un document n'a pas d'appelant pour autant). Retirés : `useProjectTree.ts`,
      3 composants jamais montés, 6 méthodes du client, 1 route en doublon.
      **Gardés à raison** : `/api/health` (exploitation), `logout` (fonctionnalité *manquante*, le
      bouton a été ajouté), le rapport imprimable (il manquait un lien).
      ⏳ `PUT /cases/order` (glisser-déposer, décision `0009`) : son écran a disparu — **le
      supprimer reviendrait à revenir sur une décision produit, c'est ton arbitrage.**
- [x] **La chaîne des conséquences**, énumérée en un seul endroit et testée. Elle a trouvé
      **trois défauts** : 🔴 une campagne d'un projet supprimé référençait toujours ses cas (la
      lancer les aurait **exécutés** contre la vraie application) ; une spécification restait
      consultable par son identifiant ; la purge d'un projet échouait sur une clé étrangère
      oubliée — **le même défaut qu'un mois plus tôt, revenu un étage plus haut**.
- [x] **Carte de la logique** : où vit chaque règle, et pourquoi (`docs/LOGIQUE.md`).

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
4. **Le faux `non_conforme`** (9ᵉ cause, §5) : le banc a produit 8 verdicts « application non
   conforme » qui accusaient l'application à tort. Aucun test unitaire ne pouvait le voir — le
   code faisait exactement ce qu'on lui demandait ; c'est la **donnée** envoyée à un vrai
   navigateur qui était irrecevable. **Seule une exécution réelle pouvait le révéler.**
5. **Un défaut de l'application testée** : `<input type="date" max="date_now">` sur
   `/creance_douteux` — un placeholder de gabarit qui a fui non résolu dans le HTML livré. Trouvé
   *en passant*, par la cartographie. C'est exactement ce qu'un outil de test doit savoir dire.
6. **Une régression introduite par un correctif du jour même** (2026-07-22). La migration 17,
   censée débloquer le banc, a classé « délibérées » les Spécifications qui portaient encore un
   cas au moment où elle tournait — elle ne pouvait voir que celles *déjà* vides. Cas supprimés
   ensuite, le nettoyage ne s'est plus déclenché : **6 fantômes là où le défaut d'origine en
   produisait 1**. La suite de tests était **verte** (685 au moment du commit).

   ⚠️ **Règle qui en sort** : *une reprise de données ne classe pas sur l'état INSTANTANÉ quand
   une SIGNATURE stable existe.* Une enveloppe automatique porte le titre exact de son cas — vrai
   que le cas existe encore ou non. C'est ce que fait la migration 18.

   ⚠️ **Et une règle sur les tests eux-mêmes** : j'ai écrit un test « cycle complet » présenté
   comme celui qui manquait. Sabotage à l'appui, **il n'attrape pas ce défaut** — sur une base
   neuve la provenance est correcte dès la création. Seul le test de *reprise* le tient. **Un test
   dont on surestime la portée est pire qu'un test absent** : on croit le terrain couvert.
   Vérifier par sabotage *quel* test tombe, pas seulement *qu'il* tombe.

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
| champs cachés | cherche un champ `visible=false` | la **visibilité** du champ |
| identifiant de route | `/demande_avoir/29789` **inventé** | l'URL concrète visitée par le crawl |
| **règles de saisie** | `"TEST_REMB_CLI001"` dans un champ `\d{7}` | le `pattern` de l'attribut HTML |

⚠️ **La 9ᵉ est d'une autre nature — et c'est la plus grave.** Les huit premières font TOMBER le
scénario, avec une trace lisible : on sait qu'on a un problème. Celle-ci le laisse se dérouler
proprement jusqu'au bout, puis **conclut « l'application est non conforme » alors que
l'application a raison**. Le navigateur refuse silencieusement d'envoyer un formulaire dont un
champ viole son `pattern` ; rien n'est créé ; l'assertion de création échoue ; verdict
`non_conforme`. C'est **la donnée du test** qui était invalide.

**Un outil de test qui accuse à tort est pire qu'un outil qui ne teste rien** — il détruit la
confiance dans ses propres verdicts, y compris les justes.

Portée mesurée (2026-07-21, après ré-exploration enrichie) : **12 des 21 routes** portant un champ
requis ont au moins un motif strict — **57 % de la surface testable**. Plus de 20 champs requis
concernés (`\d{7}`, `\d{6}`, `\d{9}`, BIC `[A-Za-z0-9]{8,11}`, téléphones, montants `min=0`).

**Et deux trous d'OUTIL** — l'agent ne pouvait pas réussir, quelle que soit la consigne :

| Trou | Conséquence |
|---|---|
| Aucun step d'**upload**, `fill_field` aveugle au type `file` | 13 routes sur 37 inatteignables |
| `leave_field_empty` aveugle au `<select>` | erreur Playwright cryptique sur un scénario légitime |

⚠️ **Un piège évité de justesse** : le correctif « URL réelle » stockait `/en/achat_siege/113` —
la version **anglaise**. Il aurait fait échouer tous les steps à libellé français (« Envoyer » →
« Send »). **Mon propre correctif allait introduire la cause suivante.**

⚠️ **Un second piège, dans l'application testée elle-même** : `/creance_douteux` sert
`<input type="date" max="date_now">` — un placeholder de gabarit qui a fui **non résolu** dans le
HTML. Le navigateur ignore une borne invalide ; nous allions écrire « valeur ≤ date_now » à
l'agent, une consigne impossible à satisfaire sur un champ pourtant valide. Toute borne ni
numérique ni date est désormais **tue**. Le placeholder reste dans l'annuaire — c'est un vrai
défaut de leur portail, qu'un humain doit pouvoir voir — mais il ne descend pas dans la consigne.
**Une mesure fidèle n'oblige pas à répéter le bruit qu'elle a capté.**

⚠️ **Et une fois sur NOTRE propre outil.** Une ré-exploration lancée depuis l'interface a réécrit
l'annuaire **à l'identique** — le serveur avait encore l'ancien module de crawl en mémoire — tout
en affichant « terminée ». Mêmes 37 routes, mêmes 373 champs : **rien à l'écran ne pouvait le
trahir**. Corrigé en affichant le compteur de **règles de saisie** sur la carte du projet : routes
et champs bougent peu d'une mesure à l'autre, les règles n'existent que depuis la mesure enrichie.
Zéro règle sur un portail qui en a = mesure à refaire. *(Un compteur à zéro n'est pas affiché :
« 0 règles » se lirait « ce portail n'en a pas » au lieu de « on n'a pas mesuré ».)*

**Réflexe à garder** : avant d'améliorer un prompt, vérifier si **la donnée est déjà mesurée** —
et si l'agent a seulement l'**outil** pour l'appliquer.

**Second réflexe, ajouté par la 9ᵉ** : quand un verdict accuse l'application, se demander d'abord
si **notre donnée de test était recevable**. Un `non_conforme` n'est crédible que si la soumission
a réellement eu lieu.

---

## 6. Dette et écarts connus (assumés, pas oubliés)

- `test_case_version.spec_content` — copie legacy, à supprimer par migration dédiée.
- Colonnes `confirmation_status` / `confirmed_by` de `repair_attempt` : **plus lues ni écrites**
  (feature retirée) mais non droppées — SQLite imposerait de reconstruire la table.
- **4 scripts non commités** (`confirmation_run_9`, `probe_*`, `regeneration_preuve_contrainte`) :
  antérieurs à cette session, jamais relus — je ne commite pas du code que je n'ai pas lu.
- `CONTINUITE.md` reste **périmé au-delà du 2026-07-17** ; ce plan et `BACKLOG.md` font foi.
