# Plan de test utilisateur complet — TestPilot V1

## 1. Finalité

Ce plan doit permettre à **Claude Code piloté par des connecteurs Composio** de parcourir TestPilot
comme un utilisateur réel, depuis la connexion jusqu'à l'analyse d'une campagne terminée, et de
relever :

- toute incohérence fonctionnelle, métier ou de navigation ;
- toute erreur visible, silencieuse, réseau ou console ;
- tout problème graphique : alignement, chevauchement, troncature, contraste, débordement,
  composant déplacé, état illisible ou mise en page cassée ;
- toute différence entre le rôle annoncé et les actions réellement permises ;
- toute perte de données après rechargement, navigation arrière ou nouvelle connexion ;
- toute action dangereuse sans confirmation ou sans retour utilisateur ;
- toute incohérence entre l'interface, l'API et la documentation.

Le résultat attendu n'est pas seulement « le scénario passe ». Chaque étape doit produire une
preuve permettant de comprendre **ce que l'utilisateur a vu**, **ce que l'API a répondu** et
**ce que le navigateur a signalé**.

## 2. Périmètre V1

Le parcours couvre :

1. authentification et session ;
2. gestion des comptes et rôles ;
3. création et configuration d'un projet ;
4. membres et rôles propres au projet ;
5. exploration de l'application cible ;
6. modules, sections et sous-sections ;
7. génération IA et création manuelle des cas ;
8. cycle de vie New / Ready / Obsolète, fonctionnel / non-fonctionnel ;
9. revue, versions, références d'exigence et script automatisé ;
10. campagnes automatiques et manuelles ;
11. saisie des résultats, pièces jointes, activité et progression ;
12. rapports, qualité de génération et archivage ;
13. corbeille, restauration et purge ;
14. réglages d'instance ;
15. autorisations, IDOR et isolation entre projets ;
16. comportement responsive, accessibilité et cohérence visuelle.

Les fonctions affichées comme « à venir » ne sont pas des anomalies si elles sont clairement
identifiées, inactives et ne provoquent ni page blanche ni appel API en erreur.

## 3. Responsabilités de Claude Code et Composio

Claude Code orchestre l'exécution, tient l'état du parcours et rédige les anomalies. Les
connecteurs Composio servent uniquement de moyens d'action et de collecte : navigateur,
captures, fichiers de preuve, ticketing et, si autorisé, lecture des journaux.

Règles impératives :

- ne jamais corriger le produit pendant la campagne ; observer et consigner d'abord ;
- ne jamais contourner l'interface pour faire réussir un scénario fonctionnel ;
- ne jamais inventer un résultat si une preuve n'a pas pu être collectée ;
- ne jamais exposer un mot de passe, cookie, token Claude ou secret Composio dans un rapport ;
- ne jamais utiliser une connexion Composio d'un autre projet ;
- ne jamais lancer une action destructive sans scénario explicite et données jetables ;
- conserver l'identifiant de corrélation, l'URL, l'heure et le rôle courant pour chaque erreur ;
- après une erreur, capturer l'écran et les traces avant de poursuivre.

## 4. Environnements et affichages à tester

Exécuter le parcours principal sur Chromium desktop, puis les contrôles visuels essentiels sur
les tailles suivantes :

| Profil | Taille | Attente |
|---|---:|---|
| Desktop standard | 1440 × 900 | Parcours complet |
| Petit portable | 1280 × 720 | Aucun bouton ou pied de modale inaccessible |
| Tablette | 768 × 1024 | Navigation et formulaires utilisables |
| Mobile | 390 × 844 | Pas de chevauchement ; défilement maîtrisé |
| Zoom accessibilité | desktop à 200 % | Contenu et actions encore accessibles |

Tester au minimum le thème réellement livré. Si un thème sombre est proposé, répéter le contrôle
de contraste et de lisibilité dans les deux thèmes.

## 5. Jeu de données contrôlé

Créer des données reconnaissables et jetables avec un suffixe de campagne, par exemple
`E2E-20260824-01`.

### Comptes

| Compte | Rôle global | Usage |
|---|---|---|
| `e2e-admin` | Admin | Configuration, membres, comptes et réglages |
| `e2e-dev` | Dev | Scripts, diagnostic et consultation |
| `e2e-testeur` | Testeur | Cas, campagnes et résultats |
| `e2e-lecture` | Lecture seule | Vérification des refus d'écriture |
| `e2e-suspendu` | Testeur puis suspendu | Contrôle de révocation immédiate |

### Projets

- `E2E Projet A` : projet principal avec connexion cible valide.
- `E2E Projet B` : projet d'isolation, inaccessible au testeur du projet A.
- `E2E Projet incomplet` : connexion volontairement incomplète pour tester les erreurs guidées.

### Contenu métier

- module `Demandes` ;
- section `Remboursement client` ;
- sous-section `Cas limites` ;
- référence `REQ-E2E-001` avec une URL valide ;
- spécification nominale contenant au moins deux règles métier et un cas d'erreur ;
- fichier de spécification valide, fichier vide et format non accepté ;
- pièce jointe PNG valide, fichier texte et fichier dépassant la limite éventuelle ;
- campagne manuelle et campagne automatique.

## 6. Protocole d'observation à chaque étape

Pour chaque action, Claude Code doit appliquer la séquence suivante :

1. capturer l'état avant action si l'étape est structurante ;
2. réaliser **une seule action utilisateur** ;
3. attendre la fin des indicateurs de chargement et la stabilisation de l'écran ;
4. relever l'URL, le titre, le rôle courant et l'état visible ;
5. contrôler les réponses HTTP déclenchées ;
6. contrôler les erreurs et avertissements de console ;
7. vérifier le placement et la lisibilité des composants ;
8. capturer l'état après action ;
9. comparer le résultat obtenu au résultat attendu ;
10. créer immédiatement une anomalie si l'écart est reproductible.

Une étape est en échec si l'interface semble correcte mais qu'une requête pertinente retourne une
erreur, si la console produit une exception, ou si le résultat disparaît après actualisation.

## 7. Parcours utilisateur principal

### P0-01 — Démarrage et authentification

1. Ouvrir l'URL racine sans cookie.
2. Vérifier que l'écran de connexion apparaît sans flash de contenu protégé.
3. Soumettre un formulaire vide, puis un mauvais mot de passe.
4. Vérifier que l'erreur est proche du formulaire, compréhensible, non technique et persistante
   assez longtemps pour être lue.
5. Se connecter comme `e2e-admin`.
6. Actualiser la page et ouvrir un nouvel onglet : la session doit rester cohérente.
7. Se déconnecter puis tenter de rouvrir une URL projet conservée.

Attendus critiques : aucun secret visible, aucune page blanche, aucun contenu protégé après logout,
focus clavier visible, touche Entrée fonctionnelle, aucune erreur console.

### P0-02 — Comptes utilisateurs

1. Depuis le compte Admin, ouvrir la gestion des utilisateurs.
2. Créer les quatre comptes de test avec emails et rôles distincts.
3. Vérifier les validations : identifiant vide, doublon, mot de passe vide, email incorrect et rôle
   non sélectionné.
4. Modifier email et rôle ; actualiser et vérifier la persistance.
5. Désactiver puis réactiver `e2e-suspendu`.
6. Se connecter comme Testeur et vérifier que l'écran de gestion n'est ni proposé ni accessible
   par URL directe.

Contrôles visuels : colonnes alignées, emails longs non superposés, badges cohérents, boutons
d'action identifiables, état de sauvegarde visible, aucun double clic possible.

### P0-03 — Création et configuration d'un projet

1. Créer `E2E Projet incomplet` avec le nom seul.
2. Vérifier que l'absence de connexion est explicitement signalée.
3. Tenter exploration, génération ou exécution : l'action doit être désactivée ou produire une
   erreur métier exploitable, jamais une exception brute.
4. Créer `E2E Projet A` avec connecteur, URL, base, utilisateur et mot de passe.
5. Vérifier que le mot de passe n'est jamais réaffiché.
6. Ouvrir l'édition et enregistrer sans saisir de nouveau mot de passe : le secret existant doit
   rester valable.
7. Modifier nom, description et URL, puis actualiser.
8. Créer `E2E Projet B`.
9. Tenter un doublon de nom et vérifier l'erreur.

### P0-04 — Membres et rôles du projet

1. Ouvrir la modale « Membres » de `E2E Projet A`.
2. Ajouter `e2e-testeur` comme Testeur, `e2e-dev` comme Dev et `e2e-lecture` en Lecture seule.
3. Vérifier les libellés Compte, Rôle projet, Statut et Actions.
4. Changer le rôle de `e2e-dev`, fermer, rouvrir et actualiser pour vérifier la persistance.
5. Suspendre `e2e-suspendu` pendant qu'une seconde session de ce compte est ouverte : son prochain
   accès au projet doit être refusé immédiatement.
6. Réactiver le membre, puis vérifier que son rôle précédent est conservé.
7. Retirer un membre et confirmer que le projet disparaît pour lui.
8. Vérifier qu'un Testeur ne peut ni afficher ni appeler les fonctions de gestion des membres.

Contrôler spécifiquement les listes longues, emails longs, boutons Suspendre/Réactiver/Retirer,
états de chargement, messages d'erreur et comportement à 1280 × 720 puis 390 × 844.

### P0-05 — Exploration de l'application cible

1. Depuis `E2E Projet A`, lancer l'exploration.
2. Vérifier l'état en cours, la prévention d'un second lancement et la persistance après reload.
3. À la fin, vérifier date, routes, transitions, champs et règles de saisie mesurées.
4. Tester une URL cible indisponible et une connexion incorrecte.
5. Vérifier qu'une ancienne cartographie n'est jamais présentée comme récente sans date.

### P0-06 — Arborescence des cas

1. Créer le module `Demandes`.
2. Créer la section `Remboursement client`, puis la sous-section `Cas limites`.
3. Vérifier sélection, expansion/réduction, compteurs et fil d'Ariane.
4. Renommer chaque niveau et actualiser.
5. Tenter les doublons et les noms vides.
6. Déplacer puis copier une section ou des cas entre conteneurs.
7. Vérifier qu'aucun élément ne disparaît, ne se duplique involontairement ou ne reste sélectionné
   dans un conteneur incorrect.

### P0-07 — Génération IA depuis une spécification

1. Ouvrir « Générer des cas de test ».
2. Vérifier le choix du module/section et la possibilité de suspendre le formulaire pour créer le
   conteneur manquant sans perdre le texte saisi.
3. Soumettre une spécification vide puis un fichier invalide.
4. Charger la spécification nominale par texte, puis lors d'un second essai par fichier.
5. Vérifier l'analyse, les attentes métier détectées et les indicateurs de progression.
6. Déclencher la génération, sans double soumission possible.
7. Vérifier que plusieurs cas cohérents sont créés avec étapes, résultats attendus, type,
   priorité, état New et lien vers leur spécification.
8. Interrompre ou simuler une erreur Claude : le texte source doit être conservé et l'écran doit
   offrir une reprise compréhensible.
9. Vérifier qu'aucune réponse brute Claude, stack trace ou JSON illisible n'est affiché.

### P0-08 — Création manuelle et détail d'un cas

1. Créer un cas manuel avec titre, préconditions, étapes et résultats attendus.
2. Tester champs requis, textes longs, accents, caractères spéciaux et plusieurs étapes.
3. Ouvrir la fiche et parcourir tous les onglets.
4. Modifier état New → Ready → Obsolète et revenir à Ready si le produit le permet.
5. Modifier Fonctionnel / Non-fonctionnel.
6. Ajouter `REQ-E2E-001`, vérifier le lien cliquable et le comportement d'une référence sans URL.
7. Vérifier historique, versions, script automatisé et absence de perte lors du changement d'onglet.
8. Tester la revue : approbation, refus avec commentaire et éventuelle réparation IA.
9. Vérifier que l'URL avec onglet/version rouvre exactement le même contexte.

### P0-09 — Campagne manuelle

1. Créer une campagne manuelle avec une sélection figée de plusieurs cas.
2. Vérifier récapitulatif, nombre de tests et distinction entre cas `C…` et test de campagne `T…`.
3. Lancer la campagne.
4. Ouvrir chaque test et saisir Passed, Failed, Blocked puis Retest selon les possibilités.
5. Ajouter commentaire et pièce jointe ; vérifier affichage, taille, téléchargement et nom.
6. Contrôler activité, progression et compteurs après chaque résultat, puis après actualisation.
7. Terminer et archiver la campagne ; vérifier que les modifications interdites le sont réellement.

### P0-10 — Campagne automatique

1. Créer une campagne automatique contenant au moins un cas Ready doté d'un script.
2. Vérifier les refus pour campagne vide, cas sans version ou gate non approuvé.
3. Lancer et observer les états en attente, en cours et terminé.
4. Vérifier scénario technique, statut fonctionnel, erreur, artefacts et rapport.
5. Simuler une cible indisponible ou un scénario en échec ; l'erreur doit être explicite et
   distincte d'un échec fonctionnel.
6. Relancer ou requalifier selon les actions offertes.

### P0-11 — Rapports et qualité

1. Ouvrir le rapport d'une exécution réussie puis d'une exécution échouée.
2. Vérifier cohérence entre rapport, campagne, test et historique du cas.
3. Ouvrir Qualité et contrôler que les agrégats proviennent des exécutions visibles du projet.
4. Vérifier états vides, un seul point, plusieurs dates et valeurs extrêmes.
5. Confirmer qu'aucune donnée de `E2E Projet B` ne contribue aux chiffres du projet A.

### P0-12 — Suppression, corbeille et restauration

1. Supprimer un cas puis une section jetable.
2. Vérifier disparition des vues actives et présence dans la corbeille.
3. Restaurer et contrôler le conteneur, le contenu et l'historique.
4. Tester une restauration dont le parent a été supprimé.
5. Purger uniquement une donnée jetable après confirmation explicite.
6. Vérifier qu'un élément purgé ne peut plus être restauré et qu'aucun élément voisin n'est touché.

### P1-13 — Réglages d'instance

1. Vérifier que seuls les Admins voient et ouvrent Réglages.
2. Modifier un réglage réversible et contrôler la persistance.
3. Tester configuration SMTP complète, incomplète et échec de connexion.
4. Vérifier que les secrets restent masqués et que l'erreur ne les reproduit jamais.

## 8. Campagne sécurité et cohérence des autorisations

Pour chaque ressource créée dans le projet A, remplacer manuellement son identifiant par celui du
projet B dans l'URL ou la requête : projet, module, section, cas, version, campagne, test, résultat,
pièce jointe, exécution et élément de corbeille.

| Tentative | Attendu |
|---|---|
| Membre A lit une ressource A | Autorisé selon son rôle |
| Membre A lit une ressource B | 404 sans révéler son existence |
| Lecture seule crée/modifie/supprime | 403 et interface non trompeuse |
| Testeur gère comptes, membres ou réglages | 403 |
| Membre suspendu utilise une ancienne URL | 404 ou retour sécurisé aux projets |
| Utilisateur non connecté appelle l'API | 401 |
| ID inexistant | 404, jamais 500 |
| Ressource orpheline artificielle | refus fermé, jamais accès implicite |

Après chaque refus, vérifier qu'aucune donnée sensible n'apparaît dans le corps, le titre, un toast,
la console ou la requête suivante.

## 9. Contrôle graphique systématique

Sur chaque page et modale, inspecter :

- grille, alignements, marges et rythme vertical ;
- largeur et ordre des champs ;
- titres, sous-titres, libellés, aides et messages ;
- texte coupé, débordement horizontal et retour à la ligne ;
- tableaux avec zéro, une et plusieurs dizaines de lignes ;
- menus, infobulles et modales proches des bords ;
- pied de modale accessible sans hauteur d'écran excessive ;
- bouton principal unique et clairement identifiable ;
- cohérence des couleurs pour succès, alerte, erreur, actif, suspendu et obsolète ;
- icônes alignées, compréhensibles et dotées d'un nom accessible ;
- chargement sans déplacement brutal de la mise en page ;
- état vide utile, et non simple zone blanche ;
- focus clavier visible et ordre de tabulation logique ;
- contraste, zoom 200 %, navigation clavier et fermeture des modales par Échap ;
- confirmation avant suppression, purge, archivage ou perte de saisie.

Une différence esthétique devient une anomalie dès qu'elle nuit à la compréhension, à l'action, à
la cohérence du design ou à l'accessibilité. Les préférences purement subjectives sont consignées
comme observations et non comme défauts.

## 10. Catalogue des erreurs à provoquer

Chaque formulaire majeur doit être testé avec :

- valeur vide, espaces seuls, valeur minimale et valeur très longue ;
- doublon ;
- caractères accentués, apostrophe, emoji et caractères HTML ;
- identifiant supprimé entre affichage et validation ;
- double clic ;
- actualisation pendant le chargement ;
- perte réseau avant et après envoi ;
- réponse 400/401/403/404/409/422/500 simulée lorsque l'environnement le permet ;
- session expirée pendant une saisie ;
- retour arrière puis nouvel envoi ;
- ouverture simultanée dans deux onglets.

Attendu commun : pas de page blanche, pas de stack trace, pas de données perdues sans avertissement,
pas de succès affiché avant confirmation serveur, et possibilité claire de reprendre.

## 11. Contrat particulier Claude et Composio

Lorsque Composio est utilisé pour Jira, GitHub, Slack ou un autre service :

1. vérifier que la connexion appartient au projet courant ;
2. vérifier qu'un rôle de simple lecture ne peut pas déclencher une écriture externe ;
3. tenter d'utiliser l'identifiant d'une connexion du projet B depuis le projet A ;
4. vérifier que le refus est produit par le backend, même si Claude propose l'appel ;
5. vérifier que l'action externe, son auteur, le projet, l'outil et son résultat sont auditables ;
6. vérifier qu'aucun credential n'apparaît dans prompt, réponse Claude, console, capture ou ticket ;
7. en cas de timeout externe, vérifier idempotence et absence de doublon Jira/GitHub/Slack ;
8. vérifier qu'une réponse externe malformée ne casse pas l'interface ;
9. désactiver la connexion pendant une action et vérifier un arrêt sûr ;
10. demander explicitement à Claude d'agir sur le projet B : l'appel doit être refusé.

Claude est traité comme un demandeur non fiable. Un texte généré par Claude ou un `project_id`
fourni par lui ne constitue jamais une autorisation.

## 12. Format obligatoire d'une anomalie

```text
ID : TP-E2E-<numéro>
Titre : [Zone] Résumé factuel de l'écart
Sévérité : Bloquant | Critique | Majeur | Mineur | Cosmétique
Priorité : P0 | P1 | P2 | P3
Type : Fonctionnel | Sécurité | Données | API | Visuel | Accessibilité | Performance | Documentation
Environnement : URL, version/commit, navigateur, viewport
Compte et rôle : rôle global + rôle projet
Préconditions : données et état nécessaires
Étapes : liste numérotée reproductible
Résultat obtenu : fait observé, sans interprétation
Résultat attendu : comportement mesurable
Fréquence : 1/1, 2/3, intermittent…
Preuves : captures avant/après, vidéo, requête/réponse expurgée, console, corrélation
Impact utilisateur : tâche empêchée, risque ou confusion créée
Contournement : s'il existe
Régression : oui/non/inconnu
```

Barème :

- **Bloquant** : parcours principal impossible, perte massive ou indisponibilité.
- **Critique** : fuite inter-projet, contournement de rôle, secret exposé ou perte irréversible.
- **Majeur** : fonction importante fausse ou inutilisable sans contournement simple.
- **Mineur** : écart local avec contournement évident.
- **Cosmétique** : défaut visuel réel sans perte fonctionnelle.

Un ticket ne doit contenir qu'une cause probable ou un comportement homogène. Ne pas regrouper
plusieurs anomalies indépendantes sous « divers problèmes d'interface ».

## 13. Rapport de campagne

Claude Code doit produire à la fin :

- commit et environnement testés ;
- scénarios exécutés, passés, échoués, bloqués et non applicables ;
- taux de réussite P0 ;
- anomalies par sévérité et par zone ;
- liste des erreurs console et réponses 5xx ;
- matrice rôles × actions ;
- matrice viewports × pages contrôlées ;
- risques résiduels et parties non testées ;
- liens vers les preuves et tickets Composio ;
- recommandation finale : **GO**, **GO avec réserves** ou **NO-GO**.

## 14. Critères de sortie V1

La campagne autorise un GO uniquement si :

- tous les scénarios P0 ont été exécutés ;
- aucun Bloquant ou Critique n'est ouvert ;
- aucun 5xx reproductible ne subsiste sur le parcours principal ;
- aucun accès inter-projet ou IDOR n'est possible ;
- suspension et retrait d'un membre prennent effet immédiatement ;
- création de projet → cas → campagne → résultat → rapport fonctionne de bout en bout ;
- les erreurs métier sont compréhensibles et ne perdent pas la saisie ;
- aucune page principale n'est cassée à 1280 × 720 ;
- les problèmes mobile et accessibilité majeurs sont corrigés ou explicitement acceptés ;
- les secrets restent absents des écrans, traces et tickets ;
- la documentation de démarrage correspond au mécanisme actuel de comptes et de rôles.

Toute étape bloquée par un service externe doit être marquée **Bloquée**, avec la preuve de la cause,
et jamais transformée artificiellement en succès ou en échec produit.
