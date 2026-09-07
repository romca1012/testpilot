# Audit TestPilot avant ouverture aux équipes — 7 septembre 2026

## Décision

**Pas de feu vert pour une ouverture générale en l'état.** Le socle est réel et un pilote interne
est envisageable après levée des points ci-dessous. Installer une préproduction privée sur
Scaleway peut précéder cette levée ; accueillir les utilisateurs doit la suivre.

Périmètre : code backend/frontend, authentification, droits projet, connecteur Odoo, génération,
exécutions, file de traitements, image Docker et PostgreSQL. Cible confirmée par le porteur :
portail de services d'entreprise sous Odoo 17, copie locale dans Docker.
L'audit n'a ni déployé sur Scaleway ni modifié les données métier Odoo.

## Addendum du 7 septembre 2026 (soirée) — traitement des points 1, 2, 4 et 5

Suite directe de cet audit, avant tout déploiement. Ce qui a été livré :

1. **Mot de passe initial.** Implémenté : `must_change_password` + `password_expires_at`
   (secret temporaire 24h), middleware qui bloque toute route hors `/api/auth/password` tant que
   le drapeau est posé, `verifier_politique_mot_de_passe` (longueur + secrets prévisibles
   refusés), compare-and-swap sur le changement (`UserRepo.change_own_password`), limitation des
   tentatives, écran frontend dédié (`ForcedPasswordChangeScreen.vue`) distinct du changement
   volontaire. Migration SQLite 42 + révision Alembic `a94c6d8e2f53` (PostgreSQL) posent le
   drapeau sur les comptes existants. La variante « invitation à usage unique » proposée dans
   l'audit reste NON implémentée — le compromis retenu (secret temporaire + changement forcé)
   couvre le risque signalé.
2. **Isolation des équipes.** Un projet créé par l'API est désormais privé par défaut
   (`default_access=no_access`, créateur admin explicite du projet). **Correctif critique
   apporté à la migration initiale** : elle fermait tous les projets EXISTANTS sans compenser par
   un accès explicite — sur une base déjà en service, ç'aurait déconnecté tous les comptes de
   tous leurs projets au premier redémarrage. La migration fige maintenant l'accès implicite
   actuel en overrides explicites avant de fermer le défaut (testé : `tests/test_migration_42_password_ownership.py`).
   Un deuxième bug, distinct, faisait qu'un compte d'id `0` (le compte de test) se voyait
   attribuer `owner_id=None` (troncature Python : `0` est *falsy*) — le projet créé se retrouvait
   fermé sans AUCUN admin, y compris son créateur. Corrigé ; c'était la cause d'environ 90 échecs
   de test en cascade, tous relus et corrigés (certains attendaient l'ancien modèle « ouvert par
   défaut », désormais faux par construction).
3. **Sandbox d'exécution.** Non traité — accepté comme risque assumé pour un pilote interne à
   opérateurs de confiance, conformément à la recommandation de l'audit.
4. **Reprise des traitements.** Le job `background_job` attend désormais la capacité AVANT de se
   réclamer (`run_gated` déplacé), donc une tâche encore en file n'est plus jamais marquée
   « en cours » avant d'avoir réellement démarré. L'exploration reconstruit son entrée `_JOBS`
   en tout début de `run_exploration`, y compris lors d'un rejeu après redémarrage — le `KeyError`
   décrit dans l'audit est fermé. Un vrai test de redémarrage avec une exploration en attente
   reste à faire en recette (pas simulable en test unitaire sans lancer un vrai process).
5. **Générations simultanées.** Mitigé, pas éliminé : réservation en mémoire (`threading.Lock`)
   en plus du contrôle en base, suffisante tant que le déploiement cible tourne à un seul worker
   uvicorn (`compose.production.yml`, confirmé). Si l'architecture passe un jour à plusieurs
   workers/process, cette réservation ne suffira plus — il faudra alors la réservation en base
   que l'audit décrivait comme cible.

**Vérifié après ces corrections :** suite backend complète et suite frontend (244 tests) sans
régression connue ; `vue-tsc --noEmit` propre. Le détail des exécutions est dans l'historique de
session, pas reproduit ici.

**Ajout hors périmètre initial, sur demande explicite du porteur — garde-fou anti-édition
concurrente et temps réel.** Deux compléments, pas dans l'audit d'origine :

- **Édition concurrente d'un cas.** `CaseRepo.update_metier`/`update_script` acceptent désormais
  `expected_version_id` : la sauvegarde est refusée (409 `conflit_edition`) si la version consultée
  par l'écran n'est déjà plus la version courante — plus jamais de fusion silencieuse sur un
  contenu périmé quand deux comptes éditent le même cas. Câblé de bout en bout (route, écran,
  bouton « Recharger »).
- **Temps réel (SSE).** `GET /api/projects/{id}/events` diffuse aux écrans ouverts sur un projet
  qu'un cas a été créé/édité — implémentation en mémoire (`events_bus.py`), cohérente avec le
  worker unique du déploiement cible ; ne suffira plus si l'architecture passe un jour à plusieurs
  workers/process (il faudra alors un pub/sub partagé, ex. Redis). SSE choisi plutôt que WebSocket :
  un seul sens suffisait au besoin, et ça traverse les réseaux d'entreprise sans configuration
  particulière. Reste une NOTIFICATION, jamais une autorité — le garde-fou ci-dessus reste la
  vraie protection si un événement est raté. Recette manuelle à deux onglets recommandée avant
  ouverture (voir « Recette de sortie attendue »).

**Reste ouvert avant d'accueillir de vraies équipes** (recette à faire, pas du code) : le parcours
complet à deux comptes/deux projets décrit dans « Recette de sortie attendue » ci-dessous n'a pas
été rejoué manuellement après ces correctifs — seule la couverture automatisée l'a été.

## Preuves obtenues

| Vérification | Résultat et portée |
|---|---|
| Frontend Vitest | 244 tests réussis, 43 fichiers. Avertissements RouterLink dans certains montages de tests. |
| TypeScript / build Vite | Réussis. |
| Backend complet | Tentatives Windows et Linux interrompues avant terme : aucune validation complète revendiquée. Une erreur de fixture reproduite et corrigée (clé créée hors du répertoire du test). Bilan ciblé consigné en fin de document. |
| PostgreSQL 16 jetable | Toutes les migrations appliquées ; 12 tests réussis, 1 ignoré faute d'outils locaux pg_dump/pg_restore. Ne vaut pas preuve de restauration. |
| Régressions ajoutées | 5 tests réussis : préflight et création concurrente de projets. |
| Image Docker corrigée | Construction réussie avec les dépendances verrouillées. Préflight réel : harnais, écriture des fichiers générés, base SQLite jetable, stockage et lancement Chromium réussis. Ce contrôle seul n'est pas un démarrage HTTPS de production. |
| Behave dans l'image | Dry-run réel réussi, bibliothèque Odoo chargée, aucune étape indéfinie. |
| Connecteur Odoo réel | RPC : connexion et lecture du schéma res.users réussies. Navigateur : première tentative expirée à 15 s au login ; second essai réussi, portail authentifié /en/myservices, 66 liens. |

La sonde reproductible est `scripts/audit_odoo_lecture.py`. Elle utilise la configuration locale,
n'affiche pas les identifiants et ne crée aucun objet métier. L'ouverture de la page ne prouve
ni la correction des formulaires ni la réussite des campagnes.

Les tests Windows utilisent l'environnement local `.venv-v1` (complété avec la dépendance
Prometheus manquante). La construction Docker utilise `requirements.lock`. Les résultats locaux
ne remplacent donc pas une suite complète réussie avec les dépendances exactes de la release.

## Défauts corrigés dans cet audit

1. **Mode strict de production absent de TestPilot.** `TESTPILOT_PRODUCTION=true` était placé sur
   PostgreSQL dans `compose.production.yml`. Il est maintenant placé sur le service applicatif ;
   les validations de configuration et la protection d'origine conditionnées par ce mode s'appliquent.
2. **Harnais d'exécution absent de l'image.** `Dockerfile` copie désormais `behave_runtime/` et
   crée son répertoire `generated/` avec les droits de `pwuser`. Le préflight refuse maintenant un
   harnais incomplet ou un répertoire de génération non inscriptible.
3. **Réponse erronée en cas de créations concurrentes.** `api/routes/projects.py` utilisait
   `SELECT MAX(id)` après insertion. Il renvoie maintenant l'identifiant de sa propre insertion.
   Le test intercale une autre création avant la réponse et vérifie que celle-ci reste correcte.
4. **Isolation du test API sur une installation neuve.** Sa fixture redirige désormais aussi
   `DATA_DIR` vers le répertoire du test, empêchant la création de `.secret_key` dans les données
   de l'instance. Le garde-fou n'est pas désactivé.

## Points à traiter avant l'ouverture

### 1. Mot de passe initial : changement obligatoire absent

Le stockage des mots de passe utilisateur est déjà haché et salé (PBKDF2-SHA256, 600 000
itérations). L'admin ne peut pas relire le mot de passe depuis l'API. Cependant il choisit le
mot de passe initial et peut en imposer un nouveau lors d'une réinitialisation : il le connaît
donc tant que l'utilisateur ne le change pas. `api/routes/auth.py` permet le changement volontaire,
mais ne limite pas une première session à cette opération et accepte le même ancien/nouveau secret.
La révocation des sessions lors d'un changement existe déjà.

**Proposition minimale, à implémenter avant les premiers comptes d'équipe :**

- Champ serveur `must_change_password`, positionné à la création et après réinitialisation admin,
  y compris pour l'administrateur d'amorçage. Migration des comptes existants dont l'origine du
  mot de passe ne peut pas être garantie.
- Secret initial aléatoire temporaire, durée limitée, transmis par un canal approprié. Après
  authentification, seuls consultation de session, changement de mot de passe et déconnexion
  sont autorisés. Le serveur doit bloquer les autres API : une fenêtre obligatoire côté écran
  seule serait contournable.
- Nouveau secret différent du temporaire ; mise à jour du hash, levée du drapeau et révocation
  des anciennes sessions atomiques. Aucun secret dans les logs, emails de notification ou réponses API.
- Politique partagée serveur/interface : actuellement l'écran annonce 8 caractères et le profil
  production en exige au moins 12. Recommandation : 15 caractères en authentification par mot de
  passe seul, phrases de passe et gestionnaires autorisés, refus des secrets courants/compromis,
  longueur maximale acceptée d'au moins 64, limitation des tentatives. Pas de changement périodique
  arbitraire ni d'obligation de combinaison majuscules/chiffres/symboles.
- Tests avec de vraies sessions : accès bloqué avant changement, ancien secret inutilisable,
  réinitialisation admin réactivant l'obligation, lecture seule pouvant sécuriser son compte,
  expiration, concurrence et validation identique dans l'écran et l'API.

La politique proposée s'appuie sur [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html).
Il s'agit d'une recommandation de conception, pas d'une certification de conformité.

**Variante préférable :** invitation à usage unique et expiration courte permettant à
l'utilisateur de définir directement son premier mot de passe. L'admin ne choisit alors aucun
mot de passe utilisateur. Cette variante nécessite un canal d'invitation fiable. SSO/MFA pourront
suivre pour un pilote interne restreint ; l'appropriation du mot de passe ne doit pas attendre.
La présente intervention propose ce parcours mais ne l'implémente pas.

### 2. Isolation des équipes : les projets sont ouverts par héritage

`api/access.py::_role_effectif_projet_legacy` retombe sur le rôle global lorsqu'aucun accès
spécifique n'est défini. `role_effectif_projet` calcule la projection `project_member`, mais
renvoie finalement la résolution historique. Un utilisateur sans affectation explicite peut
donc avoir accès à un projet. Ce n'est pas une isolation fermée par défaut.

Avant le pilote : définir chaque projet en `no_access` par défaut puis attribuer explicitement
un administrateur et les groupes autorisés. Vérifier les accès directs aux cas, résultats,
rapports, pièces jointes et scripts avec deux vraies équipes. À terme, unifier le modèle et
créer les projets fermés par défaut, sans perdre la gestion d'accès par l'admin d'instance.
Les contrôles d'accès existants ne constituent pas une isolation matérielle entre clients.

### 3. Python exécuté avec les droits et secrets du serveur

`execution/behave_runner.py::_subprocess_env` transmet tout `os.environ` au sous-processus.
Le code des steps peut être généré par l'IA ou édité par un Dev de projet. Il s'exécute sous le
même utilisateur système, avec accès au stockage et potentiellement aux secrets de la base,
des sessions et de l'API IA. Un dossier temporaire distinct et un contrôle AST de quelques
imports ne sont pas un bac à sable ; les imports Python s'exécutent même pendant un dry-run.

Avant des équipes non mutuellement fiables : worker isolé par exécution, variables autorisées
explicitement, aucun secret applicatif global, volume limité au test courant, réseau limité à
la cible de recette et quotas CPU/mémoire/temps. Pour un pilote interne provisoire, les personnes
autorisées à fournir du code exécutable doivent être considérées comme opérateurs de confiance.
Cette restriction doit être assumée ; elle ne résout pas le risque du code généré.

### 4. Reprise des traitements : garantie partielle

La file `background_job` est persistante et son payload est chiffré. Mais `run_job` marque une
tâche `running` avant d'attendre le sémaphore dans `run_gated`. Une tâche encore en attente de
capacité peut donc être classée « interrompue » après redémarrage sans avoir réellement commencé.
La promesse « toutes les tâches en attente reprennent » doit être corrigée ou l'ordre révisé.

L'exploration stocke son état dans `_JOBS`. Après redémarrage, `run_exploration` accède à
`_JOBS[job_id]` sans le reconstruire ; une tâche durable d'exploration rejouée peut lever `KeyError`,
y compris après avoir écrit sa cartographie. Persister/reconstruire cet état et tester un vrai
redémarrage avec une exploration en attente et une campagne active avant ouverture.

### 5. Générations simultanées : risque de collision de fichiers

`generation_service.unique_feature_slug` cherche un nom disponible en base, puis la génération
écrit dans le dossier global `GENERATED_DIR` avant persistance finale. Deux générations de cas
au même titre dans des projets distincts peuvent réserver le même nom sans verrou atomique.
Le risque est déduit de cette séquence ; aucune corruption de données réelles n'a été provoquée.
Utiliser un identifiant technique unique réservé avant génération et un dossier propre au job ;
tester deux générations simultanées portant le même titre.

## Ce que les fonctionnalités font réellement

| Promesse | État constaté / limite |
|---|---|
| Gestion des projets, cas, sections, campagnes | Implémentée, avec historique, rôles et tests. La séparation des équipes dépend de la configuration des accès. |
| Test manuel | Saisie des étapes, résultat, commentaire et pièces jointes implémentée. Le résultat reste une déclaration du testeur ; TestPilot ne peut pas prouver à lui seul que le geste humain a eu lieu. |
| Génération IA | Analyse, rédaction métier, pause humaine, génération technique et validation présents. Qualité et coût réels non remesurés dans cet audit ; aucun taux de succès garanti. |
| Automatiser un cas manuel | Pipeline présent, dépend du connecteur, de la cartographie, de l'IA et des assertions produites. |
| Exécution automatique | Behave/Playwright réels, dry-run préalable, verdicts, traces et réparations bornées. Reste à valider sur des soumissions métier représentatives. |
| Verdict honnête | Séparation technique/fonctionnelle et classification des refus implémentées. Une assertion erronée peut toujours donner un verdict erroné : la revue métier reste nécessaire. |
| Connecteurs applicatifs | Odoo uniquement. La bibliothèque generic n'est pas un connecteur universel. Aucun connecteur Jira/SAP/Salesforce complet démontré. |
| Exploration | Crawl déterministe Odoo, cartographie par projet. Ni preuve exhaustive de couverture ni actualisation automatique ; reprise après panne à corriger. |
| Automatisation de gestion | Enchaînement des traitements déclenchés par l'utilisateur ; pas de scheduler de campagnes applicatif. Les références Jira sont des liens, pas une synchronisation. |
| Notifications | SMTP implémenté, configuration et destinataire nécessaires ; aucun email envoyé pour cet audit. Livraison réelle non validée. |
| Sauvegardes | Scripts présents ; restauration complète PostgreSQL + artefacts + clé de chiffrement à prouver. Un volume Docker persistant n'est pas une sauvegarde. |

## Recette de sortie attendue

1. Deux équipes, deux projets fermés, comptes Admin/Testeur/Lecture seule : tentative d'accès
   transversal par écran ET URL/API, révocation et changement de rôle immédiats.
2. Première connexion et réinitialisation : aucun accès métier avant appropriation du secret.
3. Sur Odoo 17 de recette : demande valide, champ requis vide, valeur métier refusée, erreur
   technique, lecture seule, puis vérification de l'objet réellement créé et nettoyage contrôlé.
4. Un cas créé manuellement et renseigné avec preuve ; un cas généré depuis une spec, corrigé
   par l'humain, automatisé et exécuté dans une campagne. Comparer verdict et réalité Odoo.
5. Plusieurs lancements simultanés, mêmes titres entre projets, saturation et redémarrage :
   aucun fichier partagé accidentellement, statut bloqué ou double effet métier.
6. Préproduction Scaleway privée : HTTPS, secrets externes distincts, PostgreSQL, worker unique
   tant que l'architecture le requiert, quotas, supervision et restauration d'une sauvegarde
   complète sur une instance séparée. Vérifier le portail depuis le réseau du serveur déployé.

Les écritures Odoo représentatives, le parcours IA complet, la charge cible et la restauration
restent des critères de sortie, pas des résultats déjà acquis. Aucun feu vert Scaleway n'est
déduit des seuls tests unitaires.

## Bilan final des vérifications ciblées

- **166 tests backend critiques réussis** en 217,68 s : comptes/mots de passe/sessions,
  accès par projet et routes profondes, groupes, saisie manuelle, campagnes, connecteur Odoo,
  connexion du runtime, tâches durables, sécurité du déploiement, préflight et création concurrente.
- **11 tests API réussis** en 19,52 s après correction de la fixture, avec un répertoire de
  données neuf. Ils vérifient le passage relecture → exécution → résultat → rapport avec un
  exécuteur simulé ; ce ne sont pas des soumissions réelles au portail.
- **12 tests PostgreSQL réussis, 1 ignoré**, sur une base jetable migrée, arrêtée et supprimée
  après vérification. Les bases existantes sont conservées.
- **244 tests frontend réussis**, type-check et build réussis.
- Image finale : construction, préflight Chromium et dry-run Behave réussis.
- `git diff --check` réussi. Aucun déploiement, commit ou publication effectué.

Les 5 tests de régression/préflight initialement annoncés sont inclus dans les 166 ; ne pas les
additionner une seconde fois. Les suites complètes interrompues ne sont pas comptées dans ce bilan.
Les blocages exposés dans cet audit restent ouverts malgré la réussite des tests existants.
