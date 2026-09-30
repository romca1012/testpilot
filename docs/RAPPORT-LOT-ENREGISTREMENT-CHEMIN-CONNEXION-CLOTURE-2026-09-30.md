# Rapport de clôture — chantier « Enregistrement assisté du chemin de connexion »

Ce rapport couvre le chantier ENTIER (sous-lots A à E), pas un sous-lot isolé — chacun a déjà son
propre rapport (`docs/RAPPORT-LOT-ENREGISTREMENT-SOUSLOT-{A,B,C,D,E}-2026-09-29.md`). Il répond aux
étapes 11 et 12 de la consigne originale, les deux seules qui portent sur le chantier dans son
ensemble plutôt que sur un sous-lot.

## Ce que le chantier livre, en une phrase

Une personne avec les identifiants montre UNE FOIS, dans un vrai navigateur distant piloté par
WebSocket, le chemin de clics qui franchit un écran de pré-connexion (ex. sélection de pays) ; ce
chemin est confirmé, enregistré en base par projet, puis rejoué automatiquement — sans plus jamais
solliciter personne — à chaque exploration ou run réel sur ce même projet, jusqu'à ce que
l'application change et que le rejeu échoue explicitement (jamais en silence).

## Sous-lots livrés et fusionnés dans `master`

| Sous-lot | Contenu | PR | Commit master |
|---|---|---|---|
| A | Calcul du nom accessible (AccName), y compris à travers un shadow DOM | #34 | `c9b1e83` |
| B | Jeton d'accès à usage unique pour démarrer une session live | #35 | `a755ed2` |
| C | Relais WebSocket : capture des clics réels, confirmation, fermeture garantie, timeout à deux niveaux | #38 (remplace #36) | `faaab01` |
| D | Rejeu automatique de la séquence enregistrée (exploration + exécution réelle) | #39 (remplace #37) | `8723920` |
| E | Preuve de bout en bout (étape 10) | #40 | `9834071` |
| — | Correctifs étape 12 + frontend de la session en direct | #43 (remplace #42) | `bf142d5` |

Chaque sous-lot a eu sa propre revue `verdict-reviewer` avant sa fusion individuelle — voir son
rapport dédié pour le détail des bugs trouvés et corrigés à ce niveau (shadow DOM dans A, course
clic/confirmer dans C, matching approximatif `get_by_role` dans D, notamment).

## Étape 12 — revue dédiée chantier-entier, résultat

Une revue `verdict-reviewer` supplémentaire, portant sur le diff COMPLET du chantier
(`git diff 403a0a3 origin/master`, 41 fichiers, ~3907 insertions — du premier commit de A au
dernier commit de E), a été menée spécifiquement pour chercher des problèmes qui n'apparaissent
QU'en regardant l'ensemble, pas chaque sous-lot isolément : cohérence du calcul du nom accessible
entre capture (A/C) et rejeu (D), interactions entre les différents mécanismes de fermeture d'une
session (jeton B, timeout C, `finally` de la route), et chemins d'accès croisés entre les
garde-fous de B/C/D.

**Verdict : aucun chemin vers un faux `conforme` trouvé** — l'invariant non négociable (deux axes
jamais fusionnés, échec technique jamais `conforme`) tient à l'examen du chantier entier. Deux
défauts réels trouvés, tous deux produisant un **diagnostic trompeur** (jamais un faux succès, mais
un message qui accuse la mauvaise cause) :

1. **Capture (`accname.py`, A/C) et rejeu (`page.get_by_role`, D) divergeaient** sur trois cas
   mesurés avec un vrai Chromium : priorité `title`/`placeholder` inversée, `<summary>` classé
   `button` alors que Playwright l'expose en `group`, et — trouvé par le garde-fou ajouté pour
   vérifier les deux premiers, pas par la revue initiale — un `<label for>` masqué contribue quand
   même son texte chez Playwright, contrairement à l'algorithme AccName pur qu'`accname.py`
   suivait. Chacune rendait une séquence capturée « avec succès » définitivement injouable, avec
   le message « l'application a changé » alors que c'est ce module qui se contredisait lui-même.
2. **La reconnexion en cours de scénario** (`_verifier_ou_reconnecter_session`, code préexistant
   au chantier) n'avait jamais reçu le câblage `sequence_connexion` du sous-lot D, qui ne l'avait
   branché que sur la connexion initiale du run — un diagnostic « vérifiez l'identifiant, le mot
   de passe » au lieu du rejeu attendu.

Les deux corrigés, falsifiés (retirés temporairement, rouge reproduit, restaurés, vert reconfirmé),
avec un garde-fou de non-régression ajouté (`tests/test_accname.py::_nom_via_clic` compare
désormais systématiquement, pour les 36 cas du fichier, ce que `accname.calculer()` capture à ce
que `page.get_by_role` retrouverait au rejeu). PR #42 → #43 (rebasée après la fusion indépendante
de #41, voir plus bas), fusionnée dans `master` (`bf142d5`).

Une seconde passe de `verdict-reviewer`, sur ce même correctif ET sur le frontend construit dans la
foulée (voir plus bas), a trouvé et fait corriger deux bloquants supplémentaires, propres au
frontend cette fois (état non réinitialisé entre deux sessions ; confirmation optimiste sans
attendre l'accusé serveur) — détail dans
`docs/RAPPORT-LOT-ENREGISTREMENT-CHANTIER-CORRECTIFS-FRONTEND-2026-09-30.md`.

## Frontend — l'écran qui manquait (au-delà des étapes 11/12)

Signalé comme limite n°4 ci-dessous puis construit dans la foulée : jusqu'ici, aucun écran humain
n'existait pour cette fonctionnalité — seule façon de l'utiliser, parler directement le protocole
HTTP + WebSocket. Un écran complet (flux vidéo cliquable avec mise à l'échelle affiché→réel, chemin
capturé, confirmer/recommencer/annuler) a été construit et fusionné dans la même PR que les
correctifs de l'étape 12 (#43, `bf142d5`) — détail complet dans le rapport dédié cité ci-dessus.
Cette limite n°4 ne s'applique donc plus telle quelle : elle est corrigée, pas seulement notée.

## Étape 11 — limites connues, écrites noir sur blanc

### Les trois limites annoncées par la consigne d'origine

1. **Cette solution suppose qu'une personne soit disponible au moment de l'enregistrement.** Rien
   dans ce chantier n'automatise la découverte d'un chemin de connexion inédit — la première fois
   qu'un projet rencontre un écran de pré-connexion, quelqu'un avec les identifiants du projet doit
   ouvrir une session live et cliquer à travers, une fois. Sans ça, l'exploration et les runs
   restent bloqués sur cet écran exactement comme avant ce chantier.
2. **Un enregistrement ne se met pas à jour tout seul si l'application change d'interface.** Le
   rejeu (sous-lot D) échoue explicitement (`SequenceConnexionObsoleteError`) dès qu'un élément
   enregistré ne se retrouve plus — jamais une tentative silencieuse de deviner autre chose à la
   place — mais quelqu'un doit alors refaire l'enregistrement à la main. Aucune détection
   proactive d'une interface qui a changé n'existe : on l'apprend seulement au prochain rejeu.
3. **Les captchas restent hors de portée**, comme pour tout le reste du projet (aucun sous-lot de
   ce chantier n'a tenté de les contourner).

### Limites supplémentaires, trouvées en construisant les sous-lots (déjà dans leurs rapports respectifs, rassemblées ici)

4. ~~**Aucun frontend construit (sous-lot C).**~~ **Corrigée** (2026-09-30, PR #43) — un écran
   complet existe désormais (`frontend/src/pages/LiveSession.vue`), accessible par-projet
   (`effective_role`, plancher `dev`, connecteur web) depuis la navigation `CasesShell.vue`.
5. ~~**Coordonnées de clic non mises à l'échelle (sous-lot C).**~~ **Corrigée** en construisant
   l'écran (PR #43) : le relais vidéo transmet la taille RÉELLE du viewport distant, l'image
   affichée peut être plus petite — `LiveSession.vue::surClic` convertit désormais les coordonnées
   affichées en coordonnées réelles avant d'envoyer un clic, falsifié (vérifié rouge sans la
   conversion, vert avec).
6. **Un clic ambigu pendant l'enregistrement ne bloque pas la session (sous-lot C).** Si un clic ne
   résout à aucun élément unique, l'étape est simplement absente de la liste capturée — signalé au
   client (`clic_ambigu`) mais pas empêché. Une personne qui enregistre sans lire attentivement la
   liste avant de confirmer pourrait valider une séquence **incomplète** sans s'en rendre compte
   sur le moment (elle serait détectée seulement plus tard, au rejeu, si l'étape manquante était
   nécessaire pour franchir l'écran).
7. **Le message d'erreur d'une séquence obsolète (sous-lot D) ne dit pas CE QUI a changé** sur la
   page — seulement le rôle et le nom enregistrés qui ne s'y retrouvent plus. La personne qui
   refait l'enregistrement doit comparer elle-même avec ce qu'elle voit.
8. **`session_injectee` exclue du rejeu sur la base d'une hypothèse non vérifiée sur une
   application réelle (sous-lot D)** : le rejeu est sauté pour cette stratégie d'authentification
   en supposant que l'écran intercalé ne réapparaît jamais une fois authentifié via
   `storage_state`. Si cette hypothèse s'avérait fausse pour une application réelle donnée, le
   diagnostic « session valide » serait silencieusement erroné pour ce cas précis — écrit
   explicitement dans le code et les tests (`behave_runtime/steps_library/_base_helpers.py`), pas
   découvert seulement ici.
9. **Iframe cross-origin non traitée (sous-lot A).** Un écran de pré-connexion logé dans une
   iframe de provenance différente du reste de la page échapperait structurellement au calcul du
   nom accessible (barrière de sécurité du navigateur, pas une limite de l'algorithme lui-même) —
   ni capturable ni rejouable tel quel.

## Ce qui reste, au-delà de ce chantier

- Un écran pour consulter/relancer un enregistrement déjà confirmé (aujourd'hui, seul
  `project_login_recordings` en base en garde la trace — aucun écran ne l'affiche après coup).
- Test dédié pour la gate d'accès de `CasesShell.vue` (voir le rapport correctifs+frontend) —
  suggestion hors périmètre, pas un manque introduit par ce chantier (les entrées de navigation
  existantes au même plancher n'en ont pas non plus).
- Le lot 08b/08d et les audits similaires ont déjà établi le motif « échec bruyant plutôt que
  repli silencieux » que ce chantier suit ; aucune régression de ce principe n'a été introduite ici
  (confirmé par les revues sous-lot par sous-lot, la revue chantier-entier de l'étape 12, ET la
  revue du frontend qui a suivi).

## Mesure finale

`python -m pytest -q` sur `origin/master` (commit `bf142d5`, après fusion des correctifs
chantier-entier et du frontend) : 2916 passed, 16 skipped, exit 0 — aucune régression sur
l'ensemble du chantier. `npm test -- --run` (frontend) : 359 passed.
