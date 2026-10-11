# Plan — Verdict qui ne ment pas, tests sans erreur technique après génération

Date : 2026-10-08. Statut : **en cours** — D23, D24, D25, D27, D28 validées par le porteur le 2026-10-08 ; D29 à D32 validées le 2026-10-09 ; D26 en attente.
Sources : `docs/AUDIT-VERDICT-ET-GENERATION-2026-10-08.md` (trous V1-V10, contrôles T1-T10, biais du banc) ;
`reports/Agent de test honnête et fiable.md` (recherche, plan en 9 étapes) ; campagnes `docs/mesures/banc-agents-2026-10-0*`.
Ce plan **remplace l'ordre** de Q3 (reste) et Q4 de `PLAN-QUALITE-AGENTS-2026-10.md` ; Q5 (atelier de calcul) vient après.
Règles de travail inchangées (CLAUDE.md) : un lot = une branche = des commits atomiques ; test de falsifiabilité pour toute
vérification ; aucune fusion ni poussée sans accord.

## 1. Objectif et ce qui sera garanti

**Objectif.** Pour n'importe quelle application web (Odoo ou générique) testée après connexion : (1) un verdict qui ne ment
jamais — aucun `conforme` sans preuve liée à l'application et au critère ; (2) des tests qui s'exécutent sans erreur technique
dès la première génération, sans régénération ; (3) moins de 1 € par cas.

**Ce qui est garanti par construction** (démontrable par des tests, indépendant du LLM) à la fin du plan :
- G1 — un `conforme` repose sur au moins une vérification **exécutée, liée à l'application, et qui a déjà prouvé qu'elle
  peut échouer** ; sinon le verdict dit `indeterminé` ou « preuve faible » ;
- G2 — aucun libellé, champ, bouton, attribut ou appel réseau **non observé** n'entre dans un test livré ;
- G3 — une réparation ne peut ni toucher une vérification, ni faire passer un vert non relu pour un résultat ;
- G4 — un problème d'environnement (connexion, session, oracle injoignable, crédits) ne devient jamais `conforme` ni
  `non conforme`.

**Ce qui reste seulement mesuré et borné** (honnêteté : aucun outil ne peut le garantir à 100 %) : la justesse d'une spec
ambiguë, l'absence de faux vert « en général », l'instabilité d'un système asynchrone, la dérive de l'application, le
non-déterminisme du LLM. Ces risques sont **bornés** par un intervalle de confiance publié (lot 1) et **affichés** au porteur
(verdict à trois valeurs + niveau de preuve).

**Critère de fin du plan** (décision D27) — sur un jeu de cas mis de côté, dont une application jamais vue :
borne haute des faux verts < 2 % ; borne haute des erreurs techniques au premier run < 2 % ; une seule génération par cas
accepté ; coût mesuré < 1 € par cas ; 100 % des `conforme — preuve forte` adossés à un défaut injecté qu'ils ont détecté.

## 2. Décisions à prendre avant de commencer

| ID | Question | Recommandation | Bloque |
|---|---|---|---|
| D23 | Rétablir la relecture humaine obligatoire des `Alors` (aujourd'hui une version sans avertissement est approuvée d'office) ? | **Oui**, jusqu'à la fin du lot 2 ; ensuite approbation automatique seulement si tous les contrôles bloquants sont passés | Lot 2 |
| D24 | Les contrôles « littéral observé » refusent l'écriture et renvoient l'agent corriger dans la même génération ? | **Oui** (refus bloquant, message qui donne la valeur observée) | Lot 5 |
| D25 | Le repli LLM à l'exécution (résolution adaptative) est coupé par défaut en campagne et dans le banc ; en produit, un vert obtenu par repli n'est jamais « preuve forte » ? | **Oui** | Lots 1, 4 |
| D26 | L'outil peut-il **exécuter** pendant la génération (avant la relecture), sur une instance bac à sable remise à zéro ? | **Oui sous conditions** : instance déclarée « bac à sable » dans le projet, remise à zéro avant chaque enregistrement, jamais sur une instance de production (garde `ODOO_ENV=prod` intacte) | Lot 7 |
| D27 | Seuils de fin du plan (§1) | **Oui** tels quels | Lot 10 |
| D28 | Nouvelles valeurs affichées : confiance `après réparation`, niveau de preuve `forte`/`faible` | **Oui** (migration SQLite + Alembic + `schema_sa` + libellés FR serveur et frontend) | Lots 3, 8 |
| D29 | Un constat échoué dans un scénario passé (échec avalé par le test) | **`indeterminé`**, cause `constat_echoue_ignore` (prolonge D16) | Lot 2 — appliquée le 2026-10-08, **validée le 2026-10-09** |
| D30 | La correction automatique (avant tout run) peut-elle modifier une vérification et rester approuvée d'office ? Conflit : le plan dit « même gel que la réparation » ; la décision du porteur du 2026-09-16 dit « elle corrige et s'auto-approuve » (elle sert justement à renforcer une assertion creuse) | Recommandation : **garder l'auto-approbation** quand la correction ne fait que renforcer (une vérification creuse → une vérification qui lit l'application, déjà exigé par les gardes VH-02), **la refuser** si elle supprime ou modifie une vérification déjà réelle. En attendant : comportement du 2026-09-16 conservé, la modification est écrite en tête du résumé de version | Lot 3 point 6 — **validée le 2026-10-09**, appliquée (voir « D30 à D32 appliquées ») |
| D31 | Éditer le métier (`résultat attendu`, étapes) sans régénérer garde l'ancien Gherkin approuvé d'office (amendement §4.3 du 2026-07-21) : le cas peut sortir `conforme` contre une attente qui n'est plus testée | Recommandation : si `résultat attendu` ou les étapes changent, la nouvelle version **reste à relire** (ou propose une régénération) ; titre/préconditions seuls : approbation d'office conservée. Déjà fait (revue) : un code RÉPARÉ non relu n'est jamais approuvé d'office par une édition du métier | Lot 3 point 4 — **validée le 2026-10-09**, appliquée |
| D32 | Un refus serveur (valeur rejetée) est appris d'office et le résolveur l'évite ensuite (§5bis n°1) : si le refus est un bug de l'application, il est contourné au run suivant | Recommandation : apprendre, mais marquer la règle « à confirmer » et ne pas l'appliquer à une valeur conforme à la spec tant qu'un humain ne l'a pas confirmée | Lot 3 point 5 — **validée le 2026-10-09**, appliquée |
| D33 | D25 dit « repli LLM coupé par défaut en campagne ». Dans le produit, la seule option existante (campagne « stricte », D5) coupe AUSSI la réparation automatique : l'activer par défaut supprimerait la réparation de toutes les campagnes, ce que D25 ne dit pas | Recommandation : une option séparée « sans repli adaptatif » (colonne de `test_run` — migration SQLite + Alembic + `schema_sa`), cochée par défaut ; en attendant, un vert obtenu par repli reste « à confirmer » (confiance `auto_resolue`), jamais un vert ordinaire | Lot 4 point 5 — **validée le 2026-10-10**, appliquée (migration 60, Alembic `c9f4a2d6e813`, option « Sans repli par l'IA » cochée par défaut, branche `lot-vh04b-d33`) |
| D34 | Garde de session (lot 4) : une application qui REDIRIGE vers sa page de connexion un utilisateur connecté mais SANS DROIT (ex. l'admin Django) donne `bloqué`, alors que c'est le comportement attendu d'un test de droits | Recommandation : garder `bloqué` par défaut (une session perdue est le cas le plus fréquent et le plus grave) ; un test de droits l'écrit avec le step dédié « l'action … est refusée » (Odoo) ou ouvre la page de connexion lui-même | Lot 4 — **validée le 2026-10-10** (aucun changement de code : `bloqué` conservé) |

Statut des décisions (2026-10-09) : **D23, D24, D25, D27, D28 validées** par le porteur le 2026-10-08 ; **D29, D30, D31, D32 validées** le 2026-10-09 (recommandations retenues telles quelles) ; **D26 en attente** (environnements de test remis à zéro).

## 3. Les lots

Ordre : **mesurer juste** (1), **fermer le mensonge** (2-4), **fermer l'erreur technique** (5-7), **prouver** (8),
**réparer sans tricher** (9), **conclure** (10). Les lots 2-4 et 5-6 peuvent avancer en parallèle (fichiers différents).
Chaque lot se termine par sa preuve d'acceptation ; aucune mesure payante n'est lancée sans le lot 1.

### Lot 1 — Un banc qui mesure juste (instrument)

But : décider sur des chiffres, pas sur du bruit. **Rien d'autre ne peut être déclaré réussi sans ce lot.**

1. **Corriger le biais connu** : les jeux du banc tournent en mode strict (`TESTPILOT_QUALIFICATION`/mode strict posés pour
   chaque exécution) — aujourd'hui le repli LLM à l'exécution a pu rattraper des tests (audit §5.2). Test : un jeu dont le
   seul moyen de passer est le repli doit sortir `technical_error`.
2. **Agrandir** : 30 à 50 cas sur au moins 3 applications — la boutique locale (existante), l'instance Odoo de référence du
   lot 04 (`compose.banc.yml`, `banc_mesure.py`), et une seconde application web locale de structure différente. Un jeu
   **mis de côté** (dont une application jamais montrée pendant la mise au point), utilisé seulement pour la mesure finale.
3. **Défauts injectés génériques** (≥ 150 occasions indépendantes) : en plus des défauts propres à chaque application, des
   « mutations extrêmes » applicables à toute application via un proxy local — avaler les écritures, neutraliser un bouton
   d'enregistrement, figer un montant, supprimer un message d'erreur.
4. **Statistique** : intervalles groupés par cas, comparaisons **appariées** et entrelacées dans la même campagne, indicateurs :
   erreurs techniques au premier run, borne des faux verts, faux rouges, pass^k, coût par cas accepté, **générations par cas
   accepté**.
5. **Deux chemins mesurés** : génération brute (actuel) et chemin du produit (avec contrôles d'après-génération).

Acceptation : campagne `base-4` publiée avec ses intervalles ; le biais 1 démontré corrigé par test ; coût affiché avant
départ. Coût : ~10 à 15 $ par campagne complète. Effort : moyen.

### Lot 2 — Un constat doit prouver quelque chose (V1, V2, V9, V10)

But : qu'aucun `conforme` ne repose sur une vérification vide.

1. `constater` refuse une condition qui n'est pas un booléen ou un nombre (Locator, méthode non appelée, objet → erreur
   technique, jamais un vert). Test de falsifiabilité : `constater(page.locator(".x"))` ne peut plus donner `conforme`.
2. Garde AST **bloquante** à l'écriture : la condition d'un `constater` doit dépendre d'une lecture de l'application
   (`context.page`, oracle, RPC en lecture) ; refus des tautologies, des valeurs fixées par le test, d'un alias ou d'une
   redéfinition de `constater`.
3. Tout constat échoué (`ok:false`) dans un scénario passé → `indeterminé` ; la garde « `except` qui avale » gère les tuples.
4. Interdire dans le code généré les écritures RPC (`write`/`create`/`unlink`/appels de méthode) hors préparation `@given`
   listée ; liste blanche d'imports ; refus de `getattr`/`exec`/`eval`/`open`/`__dict__`/`_runner` ; le sidecar des constats
   devient inaccessible au code généré.
5. D23 appliquée : relecture humaine des `Alors` obligatoire jusqu'à la fin du lot.

Acceptation : un test de falsifiabilité par trou (V1, V9, V10 et chaque contournement listé dans l'audit) ; suite verte ;
revue `verdict-reviewer`. Coût LLM : 0. Effort : moyen.

### Lot 3 — Réparation et cycle de vie honnêtes (V3, V4, V5 + moyennes)

1. Gel **mécanique** des `Alors`, `Examples` et du corps des `@then` pendant une réparation (comparaison AST du `.feature`
   et des steps ; seules les deux exceptions documentées passent).
2. Le résultat d'une version non approuvée n'est jamais écrit comme résultat du cas ; confiance `après réparation` (D28).
3. Un échec sous un `Alors` (assertion ou élément absent) ne déclenche jamais la réparation : `indeterminé` + décision humaine ;
   un `assertion_mismatch` dans le run bloque la réparation.
4. Édition du métier : un `résultat attendu` modifié impose régénération ou relecture ; plus d'approbation automatique d'une
   version issue d'une version non relue.
5. Un refus serveur n'est **appris** qu'après confirmation humaine (sinon un bug est contourné au run suivant).
6. L'agent de correction passe par le même gel des `Alors` que la réparation.

Acceptation : tests de falsifiabilité (une réparation qui touche un `Alors` est refusée ; un vert de version non relue
n'apparaît pas dans la liste ; un bug « élément absent » n'est pas réparé). Migration complète si D28. Coût : 0. Effort : moyen.

### Lot 4 — Des vérifications partagées solides (V7, V8, oracle, ground_truth)

1. `page_affiche_texte` : correspondance exacte par défaut (mot entier, casse), cible ancrée sur la zone de contenu et sur ce
   qui est apparu **après** la dernière action ; `validation_error_inline` : erreur liée au formulaire ou au champ visé et
   apparue après la soumission ; scénario négatif : soumission **prouvée** (requête capturée) et refus sur le champ visé ;
   existence Odoo cloisonnée (`id > max_id` ou jeton de tentative) ; `action refusée` = `AccessError` uniquement.
2. Garde de session avant chaque `Alors` : page de connexion détectée → `bloqué` (G4).
3. Oracle : forme de réponse validée (un objet d'erreur n'est pas « 1 résultat »), requêtes paramétrables par scénario,
   erreur HTTP de l'oracle → `indeterminé` (jamais réparation) ; comparaisons typées.
4. `ground_truth` calculé à partir des constats réellement faits (plus de « vérifié serveur » d'office pour Odoo).
5. D25 : repli LLM coupé par défaut en campagne ; tout palier de résolution (y compris le repli de clic par sous-chaîne)
   consigné ; un vert par repli n'est jamais « preuve forte » ; les libellés appris restent des hypothèses.

Acceptation : un test de falsifiabilité par step durci (chacun échoue sur l'application qui se comporte mal, sur un vrai
Chromium) ; aucun step partagé n'a de vérification « n'importe où dans la page ». Coût : 0. Effort : moyen à gros.

### Lot 5 — Aucun littéral non observé (T1, T2, T4, T5, T6, T7, T9)

But : fermer, sans LLM, 8 des 9 erreurs techniques observées dans `base-3`.

1. **Source de vérité** : l'annuaire de l'application (`data/domain/projet-<id>.json` : champs, libellés, boutons, liens, par
   route) + les inspections de la session (fusionnées toutes dans `verified_fields`, correction de `react_loop.py:163`).
2. **Contrôle bloquant à l'écriture** (D24) dans `write_feature_file`, `write_test_plan` et `write_steps_file` : tout champ,
   bouton, libellé cité existe **à l'identique** sur la route courante ; sinon refus avec l'orthographe observée.
3. Annuaire injecté dans le prompt (noms ET libellés par route), y compris dans le banc.
4. Refus AST : `page.request`, `fetch`/XHR dans `evaluate`, `goto` hors origine, `context.X` non posé par le runtime ou un step
   antérieur, lecture de secrets ; mot de passe saisi ∉ métier validé ; forme JSON de l'oracle injectée et chemins validés.
5. Outils d'inspection : redirection signalée (la page de connexion vue en session connectée), un champ par élément (pas un
   par `name`), texte visible distinct du nom accessible (fait) ; prompt sans exemples CSS ni consigne « ASCII » ambiguë ;
   CSS libre et `:has-text` interdits dans le code généré.

Acceptation **sans dépenser** : rejouer les contrôles sur les 30 tests déjà générés de `base-3` → ils doivent signaler les 8
erreurs attendues et **0** refus sur les tests justes. Puis une campagne de génération (lot 1) : erreurs techniques au premier
run divisées et bornées. Coût : 0 pour la validation, ~10 $ pour la campagne. Effort : petit à moyen.

### Lot 6 — Plus de code libre (T3, T8)

1. Steps manquants, chacun avec son test de falsifiabilité : saisir/cliquer **dans la ligne contenant** « X » ; lire la valeur
   affichée à côté d'un libellé ; texte selon un motif ; relever une valeur puis la réutiliser ; oracle « la liste contient un
   élément où … ».
2. Suivi de route par scénario : `j'ouvre la page` fixe la route, un lien suit son `href`, une action qui soumet rend la route
   inconnue ; un littéral cité sur une route inconnue est refusé.
3. Cible : 100 % des steps des tests générés issus de la bibliothèque sur le banc ; le code libre devient une exception
   explicite et relue.

Acceptation : part de code libre sur la campagne suivante ; les 4 erreurs en code libre de `base-3` impossibles à reproduire.
Coût : 0 + une campagne. Effort : moyen.

### Lot 7 — Exécuter puis écrire (T10, si D26)

But : fermer **par construction** ce que l'annuaire ne peut pas connaître (page d'arrivée après une soumission, état après une
action).

1. Mode d'enregistrement sur instance bac à sable remise à zéro : l'agent choisit un step de la bibliothèque et un élément
   **observé** (référence de l'arbre d'accessibilité courant), l'outil l'exécute dans un vrai navigateur, puis écrit le step
   à partir de l'élément réellement touché (rôle + nom accessible calculés) et de l'état observé après l'action.
2. Un step dont l'action échoue n'est pas écrit ; l'agent reçoit le fait observé (page, éléments présents).
3. Les valeurs **attendues** des `Alors` ne sont jamais tirées de l'observation (règle du lot 8) : on enregistre les actions,
   pas les verdicts.
4. Rejeu sans LLM ensuite (le test livré est du Behave déterministe).

Acceptation : sur le banc, erreurs techniques au premier vrai run (après relecture) < 2 % borne haute ; coût mesuré ~0,1 $
par cas. Coût : une campagne. Effort : gros.

### Lot 8 — Oracles tracés jusqu'à la spec et certifiés (V6, G1)

1. Chaque valeur attendue porte sa **source** : `spec` (citation de la phrase du critère) ou `observé` ; une valeur observée ne
   justifie jamais `conforme` au premier run ; un écart spec/observé va à un humain, jamais résolu en faveur de l'observé.
2. **Certificat de falsifiabilité par critère** : un `Alors` n'obtient « preuve forte » que s'il a déjà échoué sur un défaut
   injecté qui viole son critère (mutations extrêmes du lot 1 réutilisées en produit sur bac à sable).
3. Verdict affiché : `conforme — preuve forte` / `conforme — preuve faible` / `indéterminé` / `non conforme` (D28).
4. Oracle HTTP utilisé en **différentiel** (l'action par l'interface et la lecture serveur doivent concorder) ; catalogue de
   relations génériques (créer puis rechercher retrouve l'objet ; annuler restaure l'état).
5. Vote de plusieurs LLM : seulement pour **signaler** un oracle douteux, jamais pour décider.

Acceptation : 100 % des « preuve forte » adossés à un défaut détecté ; faux verts bornés < 2 % sur le jeu mis de côté.
Coût : exécutions supplémentaires sans LLM. Effort : moyen à gros.

### Lot 9 — Réparation bornée et revérifiée (G3)

1. Diagnostic avant réparation (écart de page, réseau, console, session, données) ; réparation **de l'adressage seulement**
   (locator, attente), relocalisation déterministe d'abord (empreinte multi-attributs enregistrée au lot 7), LLM seulement
   pour départager.
2. Livrée en diff relu ; un test réparé doit **refaire échouer** les défauts injectés qu'il détectait, sinon `indeterminé`.
3. Mesure inédite : régressions réelles injectées (bouton supprimé, validation retirée) → la réparation doit échouer
   bruyamment au lieu de « réparer ». Taux de régressions masquées publié.

Acceptation : taux de régressions masquées = 0 sur les régressions injectées ; aucun faux rouge créé par une réparation
adoptée. Coût : ~0,05 $ par tentative. Effort : moyen.

### Lot 10 — Mesure de clôture et amélioration continue

1. Campagne sur le jeu mis de côté (application jamais vue) avec les critères D27.
2. Boucle d'amélioration : analyse des échecs (20-50 transcriptions), une règle codée par mode d'échec, propositions de
   modification validées en comparaison appariée ; mémoire d'interaction n'admettant que des faits validés par le runtime.
3. Activation (ou abandon) des interrupteurs restés éteints (mode strict des outils, descriptions V2, règles du connecteur)
   selon la mesure.

Acceptation : critères D27 atteints, ou écart publié avec sa cause. Coût : ~15 $.

## 4. Enchaînement, coûts, risques

| Phase | Lots | Garantie obtenue à la sortie | Coût LLM estimé |
|---|---|---|---|
| Mesurer juste | 1 | décisions sur des chiffres fiables | 10-15 $ |
| Fermer le mensonge | 2, 3, 4 | G1 partiel, G3 partiel, G4 | 0 |
| Fermer l'erreur technique | 5, 6, 7 | G2 | 0 (validation sur `base-3`) + 2 campagnes ~20 $ |
| Prouver | 8 | G1 complet | 0 (exécutions) |
| Réparer sans tricher | 9 | G3 complet | faible |
| Conclure | 10 | critères D27 vérifiés | ~15 $ |
| **Total** | | | **≈ 50-65 $** de mesures, exécution sans LLM ensuite |

Risques et parades :
- **Contrôles trop stricts** qui refusent des tests justes → chaque contrôle du lot 5 est validé sur les 19 tests justes de
  `base-3` avant activation (0 refus à tort exigé).
- **Steps partagés durcis** qui créent des faux rouges → test de falsifiabilité dans les deux sens (échoue sur l'application
  fautive, passe sur la saine).
- **Bac à sable indisponible** chez un client (lot 7) → le lot 5 + 6 reste la protection ; « page d'arrivée inconnue » donne
  un refus à l'écriture, pas un test cassé.
- **Spec ambiguë** → jamais résolue par l'agent : signalée au porteur (lot 8).
- **Coût** → exécution sans LLM ; cache de prompt ; Sonnet seulement là où la mesure l'a justifié (réparation).

## 5. Première semaine proposée

1. Décisions D23-D28.
2. Lot 1, point 1 (biais du repli LLM dans le banc) — petit, immédiat.
3. Lot 2 points 1 et 3 (`constater` typé, `ok:false` → `indeterminé`) — petits, ferment le trou le plus grave.
4. Lot 5 validé **hors ligne** sur les 30 tests de `base-3` (aucune dépense).
5. Ensuite seulement : agrandissement du banc et première campagne `base-4`.

## 6. Suivi

| Lot | Statut | Date | Preuve |
|---|---|---|---|
| VH-01 (point 1) | les bancs (agents et Odoo) jouent en mode strict | 2026-10-08 | `tests/test_banc_mode_strict.py` (échouait avant) |
| VH-02 (points 1 et 3) | `constater` refuse une condition toujours vraie (`ConstatInvalideError` → `broken_test_code`) ; un constat échoué dans un scénario passé → `indetermine` (`constat_echoue_ignore`, libellé FR serveur + frontend) ; la garde `except` voit les tuples. Points 2, 4, 5 à faire | 2026-10-08 | `tests/test_constats_qui_prouvent.py` (10 échecs sur 26 avant) |
| VH-05 (validation hors ligne) | module pur `generation/litteraux_observes.py` + `scripts/valider_litteraux_hors_ligne.py` ; **pas encore branché** sur les outils d'écriture | 2026-10-08 | `tests/test_litteraux_observes.py` ; validation ci-dessous |
| VH-04 (partiel) | vérifications partagées solides : oracle (erreur HTTP → indéterminé, objet non comptable, comparaisons typées), garde de session avant chaque `Alors`, texte exact, erreur de validation ciblée, soumission prouvée, Odoo (refus de droits, existence cloisonnée), « vérifié côté serveur » par les constats, paliers de clic, banc (refus à l'écriture, règle de réparation du produit). D25 en campagne produit : fait (D33, branche `lot-vh04b-d33`) | 2026-10-10 | `tests/test_vh04_*.py` (dont 5 fichiers sur vrai Chromium, ajoutés au contrôle `browser-evidence`) |
| VH-06 (partiel) | steps manquants (saisie dans une ligne, valeur à côté d'un libellé, motif à partie fixe, relevé réutilisé, liste d'oracle), code libre compté par le banc, deux gardes d'écriture désignées par base-5 ; 7 faux verts et 1 faux rouge de la première version trouvés par la revue et fermés avant tout commit. Point 2 (route inconnue = refus) non fait | 2026-10-11 | `tests/test_vh06_steps_manquants.py` (bout en bout Chromium + Behave), `test_vh06_gardes_ecriture.py`, `test_vh06_code_libre.py` |

### Validation hors ligne de VH-05 sur les 30 tests de `base-3` (aucune dépense)

Résultat brut : 4 erreurs techniques signalées sur 5, 5 signalements sur des tests que le rejeu comptait « exécutés ».
Examen des 5 : `connexion_refusee` ×3 et `connexion_valide` essai 2 citent `username`/`password` (vrais noms : `identifiant`,
`mot_de_passe`). **Rejoués en mode strict sans clé API**, ils sortent `technical_error` (« Champ 'username' introuvable ») :
leur « conforme » de `base-3` venait du repli LLM à l'exécution (biais confirmé, corrigé par VH-01). `commande_persistance_serveur`
essai 1 fait un `fetch` direct vers l'oracle : pratique interdite, signalement juste.

Bilan corrigé : **8 erreurs techniques réelles signalées sur 9**, **0 refus à tort** sur les 18 tests justes. La seule
manquée (`client_creation_nom_limite` essai 3 : bouton cherché sur la page d'arrivée d'un envoi de formulaire) demande le lot 7.
Conséquence pour les chiffres de `base-3` : le pass@1 d'exécution réel est plus bas que publié (au moins 4 tests de connexion
comptés à tort comme exécutés).

### Revue `verdict-reviewer` de la semaine 1 (2026-10-08) et suites données

- **Bloquant corrigé** : un refus de `constater` avalé par le code du test (helper non décoré, `except Exception`/`TypeError`)
  ne laissait aucune trace et le scénario pouvait sortir `conforme`. Désormais le refus consigne un constat ÉCHOUÉ avant de lever
  (rattrapé par V10 → `indetermine`), la garde `except` couvre `TypeError`/`ConstatInvalideError`, et ces noms sont réservés au
  socle. Test de bout en bout : `test_falsifiable_un_refus_avale_par_le_test_ne_peut_pas_donner_conforme`.
- **Corrigé** : une date Odoo (`datetime.date`, `False` si vide) était refusée à tort ; message de refus rendu exact
  (« ne prouve rien » au lieu de « jamais fausse », vrai aussi pour `ElementHandle | None`).
- **Écart au plan, assumé et renvoyé au point 2 du lot 2** : `constater` accepte encore texte, liste, tuple et dictionnaire ;
  `constater(page.url)`, `constater(True)` ou un tuple non vide restent toujours vrais. Seule la garde AST (point 2 : la condition
  doit dépendre d'une lecture de l'application) fermera ces cas. La ligne VH-02 du suivi ne doit pas être lue comme « V1 fermé ».
- **Nouvelle cause** `constat_echoue_ignore` (« Une vérification a échoué sans faire échouer le test ») : décision **D29**,
  prolongement de D16 (un constat raté dans un scénario passé n'est jamais racheté). Texte en base, aucune migration.
- **Preuve de VH-01** : le test vérifie la transmission du mode strict ; le critère « un test sauvé par le repli sort
  `technical_error` » est prouvé par le rejeu strict de `connexion_refusee` essai 1 (§ validation ci-dessus).
- **À traiter avant de brancher VH-05 en refus bloquant (D24)** : `get_by_text`/`get_by_role(name=…)` comparés aux seuls champs et
  boutons (un titre « Merci » serait refusé à tort) ; paramètres de Plan du scénario (`<champ>`) ; `response.request` (observation
  réseau légitime, utile au lot 4) signalé à tort ; échantillon de validation de 18 tests justes, à élargir.
- **À surveiller** : tant que le lot 3 (gel des `Alors` en réparation) n'est pas livré, une erreur `ConstatInvalideError` part en
  réparation, et l'agent pourrait la « corriger » par une tautologie.

### Lot VH-02 terminé et VH-05 branché (2026-10-08)

- **VH-02 point 2 (V1)** — garde BLOQUANTE `CONSTAT_SANS_LECTURE` dans `write_steps_file` : la condition d'un `constater*` doit
  dépendre d'une lecture de l'application (`context.page`/`odoo`/oracle, ou une variable qui en vient — point fixe par AST) ;
  refus d'une constante, d'une tautologie (`a == a`), d'une condition faite des seules valeurs du Gherkin ou de `context.table`,
  et de toute redéfinition, réaffectation ou import renommé de `constater`.
- **VH-02 point 4 (V9)** — `ACTION_PAR_RPC` : aucune écriture RPC (`create`/`write`/`unlink`/actions) dans un `@when`/`@then`
  (permise dans un `@given` de préparation) ; `PYTHON_INTERDIT` : imports en liste blanche (`behave`, `_base_helpers`, `features`,
  `playwright`, modules standard sans effet de bord), `exec`/`eval`/`open`/`__import__`…, `getattr` à nom calculé, `_runner`,
  `__dict__`… refusés.
- **Calibrage** : aucun des 29 fichiers de steps générés de `base-3` n'est refusé par ces gardes ; 3 exemples de tests existants
  contenaient eux-mêmes un constat qui ne lisait rien — corrigés pour lire la page, sans toucher à ce qu'ils affirment.
- **VH-02 point 5 (D23)** : les contrôles étant désormais BLOQUANTS à l'écriture et ARMÉS de la même façon pour la génération,
  la correction et la réparation (`litteraux_observes.brancher_controles`, corrigé après la 2e revue : correction et réparation
  écrivaient sans les contrôles des littéraux), l'approbation automatique ne concerne plus qu'une version qui les a tous passés.
  Restent hors de ces contrôles : les éditions manuelles et les versions métier recopiées (`repositories.py`, `cases.py`) —
  à traiter avant de considérer D23 levée.
  V1 n'est pas fermé à 100 % : la garde est de forme (le runtime garde le dernier mot) ; les lots 4 et 8 la complètent.
- **VH-05 branché (D24)** : `write_feature_file` (donc aussi `write_test_plan`) refuse un champ ou un bouton jamais observé sur la
  page courante (connecteur web avec annuaire) en donnant le nom observé ; `write_steps_file` refuse le réseau direct et un
  `context.X` inventé ou secret (tous connecteurs), les sélecteurs par texte libre et les libellés non observés (web). Ce que
  l'agent inspecte pendant la génération compte comme observé. Corrigés avant branchement (revue) : titres non jugés,
  paramètres de Plan du scénario ignorés, `response.request` permis, page absente = indication seulement.
- **Prompt** : la consigne « le reste reste en ASCII » précise que les libellés de l'application se recopient à l'identique.
- **Non fait** : connecteur Odoo (l'annuaire ne relève pas le back-office — refus à tort probables) ; suivi de la page d'arrivée
  après une soumission (lot 7) ; textes attendus des `Alors` (l'annuaire ne relève pas les textes).

### 2e revue `verdict-reviewer` (2026-10-08) et suites données

- **Bloquants corrigés** : `constater(condition=True)` et les arguments déballés sont jugés ; une valeur que le test range lui-même
  dans `context` n'est une lecture que si TOUTES ses affectations lisent l'application (point fixe sur tout le fichier) ; un
  attribut non écrit par le test n'est une lecture que s'il est posé par le harnais.
- **Refus à tort corrigés** : helper qui reçoit `context`, `getattr(context, "<attribut du harnais>")`, drapeau rempli sous un
  `if`/`for` qui lit l'application, `.append`/`.update`, affectation indicée, fonction imbriquée jugée avec ses propres paramètres ;
  `from __future__`, `calendar`, `zoneinfo`, `dateutil`, `logging`, `copy` permis.
- **Action par RPC** : alias suivis, et dans un `@when`/`@then` un objet Odoo ne sert qu'à lire (liste blanche : search, read,
  browse…) — `action_confirm`, `button_confirm`, `write`… refusés quel que soit le chemin.
- **`getattr`** vers `_runner` ou un secret refusé ; la règle `contexte` des littéraux voit aussi `getattr(context, "…")`.
- **Correction et réparation** armées comme la génération (annuaire + attributs du harnais).
- **Limites assumées** (garde de forme) : `constater(context.page is not None and a == a.strip())` ou un helper local trivial
  accompagné d'un vrai constat passent encore ; le runtime et les lots 4 et 8 complètent. Odoo non calibré pour les littéraux
  (annuaire inactif hors web) ; 2 refus `CONSTAT_SANS_LECTURE` mesurés par la revue sur l'ancien corpus Odoo local portaient sur
  un attribut `current_record_id` jamais posé par le harnais — refus justifié (le test lisait un attribut inexistant).
- **Coût (§9)** : le prompt gagne deux lignes ; les refus peuvent ajouter des tours d'agent — à mesurer à la prochaine campagne.

### Lot VH-03 — état au 2026-10-09

| Point | Statut | Preuve |
|---|---|---|
| 1. Gel des vérifications en réparation | **fait**, gel TOTAL (aucune exception d'adressage, revue) : `Alors`, Exemples, Contexte ; fonctions `@then`/`@step` par décorateur ; aucune nouvelle vérification ; helpers, constantes et `context.X` écrits par un `Quand` et lus par une vérification ; référence = version de la base | `tests/test_gel_verifications.py` |
| 2. Résultat d'une version réparée non relue | **fait** : confiance `apres_reparation` (migration 59, Alembic `b7e3c1a9d405`), jamais le résultat du cas (run ET erreur), `last_verdict_version_id` corrigé | `tests/test_confiance_apres_reparation.py` |
| 3. Échec sous un `Alors` | **fait côté circuit** : jamais de réparation (confirmation humaine) ; une assertion en échec n'importe où arrête. Le verdict reste `technical_error` (pas `indeterminé`) : choix assumé, un échec technique n'est jamais `conforme` | `tests/test_circuit_alors.py` |
| 4. Édition du métier | **fait** : un code réparé non relu n'est plus approuvé d'office (revue) ; D31 : changer le résultat attendu ou les étapes laisse la version à relire et le cas se lit « Retest » jusqu'au prochain run | `tests/test_attente_metier_changee.py` |
| 5. Refus appris | **fait** (D32) : un refus d'une valeur citée par le métier attend une décision humaine, il n'est pas appliqué d'ici là | `tests/test_refus_cites_par_le_metier.py` |
| 6. Gel pour la correction | **fait** (D30) : approuvée d'office seulement si elle renforce ; sinon à relire | `tests/test_correction_ne_fait_que_renforcer.py` |

Limites assumées : une vérification d'un helper de la BIBLIOTHÈQUE n'est pas concernée (code du socle, hors génération) ; le gel
compare des empreintes d'AST, un renommage de variable dans un `@then` est refusé (sévère, jamais laxiste).

### D30 à D32 appliquées (2026-10-09, branche `lot-vh03b-d30-d31-d32`)

Décisions validées par le porteur le 2026-10-09, recommandations retenues telles quelles.

- **D30 — la correction automatique ne fait que renforcer.** Une vérification de la version d'origine est « creuse » si elle
  avale l'échec (`except` large) ou si toutes ses affirmations (`constater*`, `assert`) ne lisent rien de l'application ;
  dans le doute (un `expect`, un helper de la bibliothèque ou du fichier, des arguments déballés), elle est réelle
  (`write.verifications_creuses`). La correction peut réécrire une vérification creuse ; tout autre changement de ce que le
  test vérifie (vérification réelle, `Alors`, Exemples, scénario, nouvelle vérification) est un point de vigilance
  `verification_affaiblie_par_correction` : la version corrigée reste à relire. La décision du 2026-09-16 (la correction
  s'auto-approuve) reste vraie pour ce qu'elle visait : renforcer une assertion creuse.
- **D31 — changer ce qu'un cas doit prouver.** Éditer le résultat attendu ou les étapes d'un cas qui a déjà un test ne
  l'approuve plus d'office (titre et préconditions : amendement §4.3 inchangé) ; point de vigilance `attente_metier_changee`.
  L'étiquette de lecture du cas passe de « Réussi » à « Retest » tant que son dernier résultat vient d'une version au métier
  différent (`status.statut_du_cas`, même règle en SQL pour le filtre, testée sur toutes les combinaisons). Le run garde son
  verdict : seule l'étiquette du cas change, aucun run n'est masqué (décision 0016 (iii)). Approuver ne suffit pas à
  revenir au vert : seul un run sur la nouvelle attente le peut.
- **D32 — un refus de ce que le métier demande attend un humain.** Le runner reçoit le métier validé de la version jouée (titre,
  préconditions, étapes, résultat attendu, spec — texte humain, jamais le Gherkin ni le code). Un refus dont la valeur y est
  citée (sans casse ni accents, frontières de mot, 3 caractères au moins) est enregistré `a_confirmer` ; il n'est appliqué
  ni par le résolveur ni dans les formats montrés à l'agent tant qu'un humain n'a pas tranché sur l'écran « Cas à relire »
  (« règle de l'application » l'apprend, « bug » ne l'apprend jamais). Tout autre refus reste appris d'office : §5bis n°1
  du brief est amendé pour ce seul cas (note datée dans le brief). Limite assumée : une valeur reformulée par le métier
  (« 15/03/2027 » contre « 2027-03-15 ») n'est pas reconnue.


#### Revue `verdict-reviewer` de D30-D32 (2026-10-09) et suites données

Deux points bloquants, reproduits par la revue puis fermés (`tests/test_revue_d30_d32.py` : 8 tests sur 9 échouaient
sans les correctifs ; le 9e prouve un branchement déjà commité) :
- **B1** — une seconde édition du métier (titre seul) approuvait d'office une version restée à relire (attente changée D31,
  correction à relire D30) : le test de l'ancienne attente ressortait `conforme`. Désormais l'édition du métier n'approuve
  jamais d'office une version qui porte un test non approuvé, quel qu'en soit l'auteur (`review_gate.test_non_relu`), et le
  point de vigilance D30 suit le test recopié (jugé sur la version qui a écrit le test).
- **B2** — une écriture `context.X` ajoutée par la correction dans une fonction creuse (un `@step` d'action) échappait au gel :
  les clés des vérifications gelées sont prises sur la référence pour les deux côtés.

À corriger, fait : **C1** une exécution non clôturée (`not_executed`) ne compte plus comme « dernier résultat » (elle
faisait repasser au vert un cas « Retest », pour toujours si le run était tué) — `last_verdict_version_id` en hérite ;
**C2** test du branchement run → runner du métier (D32) ; **C3** classement « creuse » plus prudent (`raise`, appel
inconnu qui reçoit `context` ou une valeur lue) ; **C4** registre et brief commités. En plus : `global`/`nonlocal` refusés
à l'écriture (réaffecter un helper lu par une vérification sans toucher la liaison de module comparée par le gel).

Remarques retenues comme limites ou suites, non traitées ici :
- D30 alourdit la relecture : une correction d'assertion qui lisait déjà l'application (`len(x) >= 0`) est désormais à
  relire — à mesurer au banc. Une correction peut toujours changer un `Soit`/`Quand` et rester approuvée (sémantique du
  gel de VH-03, hors D30).
- `steps_modifies`/`feature_modifiee` rendent « aucun écart » sur un code illisible (les gardes d'écriture le refusent en amont).
- D32 : reconnaissance par citation textuelle — « 10 » ou « 15 » (moins de 3 caractères) ne sont jamais reconnus, des mots
  courants de la spec peuvent mettre en attente des refus de valeurs fabriquées (sens prudent). Piste : marquer l'origine de
  la valeur (résolveur ou Gherkin) dans le sidecar des refus. Le CLI et le banc ne transmettent pas le métier : tout y reste
  appris d'office. Une décision `rejetee` sortie des 500 dernières lignes du fichier redemande l'humain.
- D31 : deux sous-requêtes de plus par lecture de cas (coût à surveiller sur un gros projet) ; l'écran affiche « Retest »
  sans en donner la raison sur la liste (le point de vigilance l'explique sur la fiche).

### Lot VH-04 — vérifications partagées solides (2026-10-10, branche `lot-vh04-steps-solides`) — **partiel**

| Point du plan | Fait | Preuve (falsifiable) |
|---|---|---|
| Oracle (3) | erreur HTTP de l'oracle → `oracle_en_erreur` (exécution réussie, fonctionnel indéterminé, jamais réparée) ; « renvoie N résultats » ou « vaut … » sur un objet/une liste → test mal posé (`ReponseOracleNonComptableError`), plus jamais un `non_conforme` (faux rouge mesuré base-2 et base-4) ; comparaisons typées (12.0 = « 12 », true = « true », sans élargir) | `test_vh04_oracle_navigateur.py`, `test_oracle_steps.py` (attendu changé délibérément) |
| Adresse relative (mesure base-4) | `base_url` = adresse du projet sur le contexte du navigateur : `page.goto("/__etat")` vise l'application (2 erreurs techniques en base-4) | bout en bout Chromium (échoue sans : « Cannot navigate to invalid URL ») |
| Garde de session (2, V8, G4) | page de connexion atteinte par redirection, sans mot de passe saisi par le test, session du harnais intacte → `bloqué` au premier constat de l'`Alors` (mesuré : une exception dans `before_step` n'est pas classée `bloqué` par Behave 1.3.3) ; Odoo couvert (revue, B3) ; application monopage : seulement si la page affichée est le document redirigé (revue) | `test_vh04_garde_session.py` (bout en bout : sans la garde, l'absence constatée sortait `conforme`), `test_vh04_garde_session_odoo.py` |
| Texte exact (1, V7) | mot entier, casse respectée, un nombre n'est ni un morceau d'un plus grand nombre ni la partie entière d'un décimal ; candidats visibles selon Playwright puis texte RENDU (casse libre sous `text-transform`) ; plus jamais une option de liste ni un conteneur de hauteur nulle (revue, B1) ; l'absence garde la lecture large | `test_vh04_texte_exact.py` (bout en bout) |
| Erreur de validation (1, V7) | un message visible (ni lien, ni bouton, ni libellé, ni menu, ni bouton d'envoi) ou un champ marqué invalide ; tous les candidats lus (revue, B2) | `test_vh04_validation_et_negatif.py` (Chromium) |
| Scénario négatif (1, V7) | « n'a pas augmenté » exige une SOUMISSION observée après le relevé : requête d'envoi (sur Odoo, un appel d'écriture — `web_save`, `create`, bouton —, jamais un `onchange` en POST) ou refus du navigateur horodaté ; sinon `indéterminé` | idem |
| Odoo (1, V7) | « l'action est refusée » : seul un refus de DROITS (`AccessError`/`AccessDenied`, nom transmis par le serveur ou en tête du message) ; méthode privée refusée comme erreur du test ; « … existe » cherché parmi les enregistrements apparus après le relevé, et un enregistrement antérieur → non concluant (ni vert, ni accusation) | `test_vh04_odoo.py` |
| `ground_truth` (4) | « vérifié côté serveur » seulement si chaque scénario a un constat sous un `Alors` qui a lu le serveur (oracle, ou lecture RPC observée pendant le step) — plus d'office pour Odoo ; note d'explication reformulée | `test_vh04_verifie_serveur.py`, 3 attendus historiques changés délibérément |
| D25 (5) | paliers de clic consignés (`clic` / `clic_sous_chaine`) | `test_vh04_palier_clic.py` |
| Banc (mesure base-4) | chaque refus d'une garde d'écriture consigné et compté par essai ; le banc ne paie plus une réparation que le circuit du produit refuse | `test_vh04_banc.py` |
| Signaux réservés (revue, point 9) | garde de session, source `rpc`, soumission observée : interdits aux steps générés | `test_vh04_banc.py` |

**Écarts au plan, assumés et à arbitrer :**
- **D25 en campagne produit** : fait après validation de D33 (2026-10-10) — option `sans_repli` de la campagne, cochée par défaut (campagnes existantes comprises), qui coupe le SEUL repli adaptatif ; second essai et réparation restent actifs. Prouvé : `tests/test_d33_sans_repli.py`, `frontend/src/__tests__/AddTestRunForm.sansRepli.spec.ts`.
- **« Ancré sur ce qui est apparu après la dernière action » non fait** (texte et erreur de validation) : une validation rendue par
  le SERVEUR s'affiche au chargement de la page de réponse et serait refusée — faux rouges sur les formulaires les plus courants.
  Le critère « aucune vérification n'importe où dans la page » n'est donc pas atteint : un texte identique ailleurs dans la page
  (menu, en-tête) suffit encore.
- **Erreur de validation non rattachée au champ visé** (même raison : beaucoup d'applications affichent un bandeau global).
- **Requêtes d'oracle non paramétrables par scénario** : renvoyé au lot 8 (oracles tracés jusqu'à la spec).

**Limites assumées (garde de session)** : un refus de droits par redirection vers la connexion donne `bloqué` (D34) ; une
redirection encore en cours au moment de l'`Alors`, une redirection en JavaScript ou des cookies réécrits à chaque réponse
(Laravel) désactivent la garde (comportement d'avant) ; une application monopage qui affiche son formulaire de connexion sans
navigation n'est pas vue. **Source `rpc`** : toute lecture du serveur pendant le step compte, même sans rapport avec la condition
— n'affecte que l'étiquette `ground_truth`, jamais le statut. **Contexte du navigateur** : `base_url` le rend différent de celui de
l'exploration pour les seules adresses relatives. **Coût (§9)** : la docstring ajoutée au step « la page affiche le texte » entre
dans le catalogue du prompt (~25 jetons), aucun appel LLM ajouté.

### Lot VH-06 — plus de code libre (2026-10-11, branche `lot-vh06-suivi-de-route`) — **partiel**

Mesure qui l'a désigné (`docs/mesures/banc-agents-2026-10-10-base-5-bilan.md`) : les 9 essais non justes de base-5 viennent
presque tous de code écrit à la main par l'agent (repères Playwright, oracle interrogé à la main) ; un faux rouge vient d'un
Gherkin portant la séquence d'échappement d'un caractère au lieu du caractère.

| Point du plan | Fait | Preuve (falsifiable) |
|---|---|---|
| Steps manquants (1) | « je renseigne "<champ>" avec "<valeur>" dans la ligne contenant "<texte>" » ; « la valeur affichée pour "<libellé>" est "<valeur>" » (valeur entière, relue jusqu'au délai) ; « la page affiche un texte de la forme "<motif>" » (partie fixe d'au moins 3 caractères exigée, motif validé par le navigateur) ; « je relève la valeur affichée pour "<libellé>" comme "<nom>" » puis `{relevé:nom}` ; « la liste "<chemin>" de l'oracle "<requête>" contient un élément dont "<clé>" est "<valeur>" » | `tests/test_vh06_steps_manquants.py` : chaque step réussit sur la bonne page et échoue sur la mauvaise, sur Chromium ; 12 scénarios dans le vrai Behave |
| Code libre mesuré (3) | le banc compte les FONCTIONS de step écrites par le test (colonne « Steps écrits à la main », section « Code libre ») ; Règle 9 du prompt, exemples neutres | `tests/test_vh06_code_libre.py` |
| Gardes d'écriture (mesure base-5) | `ECHAPPEMENT_LITTERAL` (séquence `\uXXXX` dans le Gherkin, hors commentaire et motif) ; `context.oracle` interrogé à la main refusé, quel que soit le récepteur, import privé de `_base_helpers` compris ; `RELEVE_INVALIDE` (jeton mal écrit ou relevé absent du scénario) | `tests/test_vh06_gardes_ecriture.py` |

**Revue `verdict-reviewer` du 2026-10-11 — verdict BLOQUANT, traité avant tout commit.** La première version n'avait jamais été
exécutée ; ses 55 tests passaient et ne couvraient pas ces cas. Reproduits par la revue dans le vrai Behave, puis fermés :

| Défaut reproduit | Suite donnée |
|---|---|
| B1 — « ne contient aucun élément dont … » vert dès que la clé ne se lit pas (clé inventée, casse) | forme négative **retirée** (hors plan) ; la forme positive lève un test mal posé si aucun élément ne porte la clé |
| B2 — jeton mal écrit (`{releve:x}`) laissé tel quel : une absence devenait vraie | erreur du test à la substitution ; refus à l'écriture ; garde AU CONSTAT pour tout step qui ne substitue pas |
| B3 — auto-référence : valeur relevée comparée à l'écran d'où elle vient | sous un `Alors` qui lit l'écran, un relevé n'est utilisable qu'après une action (deux relevés ne sont pas une action) ; contre l'oracle, toujours |
| B4 — un en-tête de colonne pris pour un libellé (rendait l'en-tête voisin) | un `th` d'en-tête de colonne n'a pas de valeur par voisinage |
| B5 — motif sans partie fixe (`\d+`, `.+`) vrai sur toute page | partie fixe d'au moins 3 caractères, lue dans l'arbre de l'expression |
| B6 — case à cocher / bouton radio : `value` constante (« on ») | pas de valeur affichée pour ces types |
| B7 — motif valide en Python, illisible par le navigateur → `non_conforme` sur page saine | validé dans le navigateur avant la recherche : erreur du test |
| Saisie dans la mauvaise ligne sans erreur (ligne sans champ → tableau entier) | la zone doit être UNE ligne ; texte en mot entier, casse respectée |
| Valeur lue une seule fois (total recalculé en retard → faux rouge) | relue jusqu'au délai |
| Balisages non lus (`<td><strong>`, « Libellé : `<strong>` », texte après le libellé) | lus ; le texte qui suit passe avant l'élément qui suit |
| Exemples du prompt = données du banc (fuite qui aurait faussé base-6) | exemples neutres, test qui l'interdit |
| `context.releves` posable par un step généré | nom privé, réservé au socle |
| Contournements de la garde d'oracle (alias, lambda, import privé) | fermés |

**Écarts au plan, assumés :**
- **Point 2 (« un littéral cité sur une route inconnue est refusé ») non fait.** Le suivi de route existe depuis VH-05 avec la règle
  inverse, choisie pour ne jamais refuser à tort : route inconnue → le littéral doit exister quelque part dans l'application.
  La page d'arrivée après une soumission, que l'annuaire ne peut pas connaître, est l'objet du lot 7.
- **Cible « 100 % des steps issus de la bibliothèque » non mesurée** : il faut une campagne (base-6).
- **`{relevé:nom}`** est un mécanisme de gabarit dans le Gherkin, absent du registre des décisions : à faire acter (voir D35).
- Le champ cité par « … dans la ligne contenant … » n'est pas confronté à l'annuaire (D24) : il est résolu par préfixe dans la
  ligne (« Quantité » pour « Quantité de X »), ce qu'un contrôle à l'identique refuserait à tort.

**Limites assumées :** une valeur suivie d'une précision (`<dd>129,51 € <small>dont TVA</small></dd>`) est lue en entier ;
un relevé peut capturer une valeur en cours de chargement (« … ») ; `{relevé:}` après une action reste une vérification de
STABILITÉ, pas de justesse — la source de chaque valeur attendue (`spec` / `observé`) est l'objet du lot 8 ; un chemin Windows
du type `C:\ufaca…` dans un Gherkin serait refusé à tort par `ECHAPPEMENT_LITTERAL`.
**Coût (§9)** : prompt système +1 217 caractères (27 996 → 29 213), catalogue générique 60 → 67 phrases — de l'ordre de 600
jetons d'entrée par appel, en cache après le premier ; coût par cas à mesurer en base-6 (`scripts/mesure_cout_cas.py`).

