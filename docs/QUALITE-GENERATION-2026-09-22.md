# Qualité de génération — évaluation du 22 septembre 2026

## Résultat observé avant correction

Source : base SQLite locale `data/testpilot.db`, ouverte en lecture seule ; uniquement les
exécutions `first_run`, hors exécutions encore en attente. Cet échantillon historique de
7 exécutions ne permet pas de généraliser à tous les projets ou à la production.

| Mesure | Résultat |
|---|---:|
| Premiers passages enregistrés | 7 |
| Exécutions sans erreur technique | 3 / 7 (42,9 %) |
| Erreurs techniques | 4 / 7 (57,1 %) |
| Données invalides parmi les exécutions sans erreur technique | 2 / 3 |
| Verdict métier conforme ou non conforme | 1 / 7 (14,3 %) |
| Premiers passages du 22 septembre | 3 erreurs techniques / 3 |

Le taux technique ne suffit pas à qualifier l'utilité d'un test : une donnée refusée
n'apporte pas la même preuve qu'un verdict métier. Un test qui détecte un défaut réel
(`non_conforme`) reste une réussite d'exécution et un verdict exploitable.

## Constats et corrections

- Les artefacts des exécutions 155 et 190 montrent des échecs de navigation sur
  `Surveys` et `Helpdesk / All Tickets`. La traduction de menus et les sous-menus
  supposés sont des risques observés, pas seulement des hypothèses.
- L'exploration Odoo perdait la hiérarchie : seuls le libellé et le modèle étaient
  conservés. Elle conserve désormais `menu_path` lorsque l'arbre le permet, en gardant
  les feuilles homonymes sous des parents différents. Les anciennes cartographies
  restent compatibles ; une nouvelle exploration est nécessaire pour les enrichir.
- Le prompt distingue maintenant libellé simple et chemin mesuré. Il demande aussi
  l'observation de la vue : un champ RPC ne prouve pas la présence du champ dans l'UI.
- Le smoke-check signale les chemins non étayés, même lorsque l'application ne comporte
  aucune page de portail cartographiée. Cet avis utilise le circuit existant de relecture
  et de correction ; il reste non bloquant, car la cartographie peut être incomplète.
- L'écriture Gherkin parse le contenu avant de remplacer le fichier et refuse les
  scénarios sans étapes et les plans de scénario sans exemples, y compris lorsqu'un
  autre scénario valide les masque.
- La boucle de génération transmet les diagnostics utiles de Behave (imports, parsing,
  etc.). Le garde-fou de stagnation distingue désormais les causes d'échec différentes.

Ces changements complètent les modifications de résolution adaptative déjà présentes
au début de l'intervention. Ils ne modifient pas les verdicts pour rendre les tests verts.

## Mesure reproductible

```powershell
python scripts/audit_generation_quality.py --db data/testpilot.db
```

Ce script n'importe pas la configuration, ne migre pas la base, ne contacte aucun
service et ne lit aucun secret. Il sépare réussite technique et verdict métier exploitable,
exclut les rejeux et distingue l'absence de mesure d'un taux nul.

## Limites et critère de validation réelle

Les chiffres ci-dessus sont un état initial, pas une amélioration mesurée après correction.
Les tests automatisés du dépôt vérifient les contrats et les régressions ; les contrôles
Behave à blanc vérifient le parsing et la résolution, pas les parcours UI de l'application.
Aucune nouvelle campagne métier réelle ni génération avec le fournisseur LLM n'a été
lancée lors de cette intervention.

Pour mesurer la réussite du premier passage après déploiement : réexplorer avec le compte
et la langue réellement utilisés à l'exécution ; générer de nouvelles versions sur un corpus
représentatif (nominal, refus attendu, champs requis, relations, portail et back-office) ;
exécuter chaque version une seule fois en conservant séparément les éventuelles réparations.
Rapporter les deux taux, les causes d'échec, le coût et la taille de l'échantillon.
Une cible de 100 % sur ce corpus est vérifiable ; une garantie universelle de perfection
ne l'est pas. La dérive UI, les droits, les données et la disponibilité restent à mesurer.

## Vérifications effectuées

- 195 tests ciblés réussis : génération, régénération, smoke-check, prompt, qualité,
  exploration Odoo, réparation, lint des assertions et harnais Behave.
- Contrôles statiques critiques Ruff (`E9,F63,F7,F82`) réussis et `git diff --check` propre.
  Le lint étendu signale encore des règles de style et de modernisation du code existant ;
  il n'est pas déclaré entièrement vert.
- La suite globale de 2 022 tests sélectionnés a été interrompue au profit de la suite
  ciblée : elle n'est pas déclarée validée. Les tests de conformité contre des applications
  publiques ne font pas partie de cette vérification.
- Sur ce poste, le lanceur `.venv/Scripts/python.exe` ne démarrait pas. Les vérifications
  ont utilisé Python 3.12 fourni par Codex avec les dépendances existantes de `.venv`,
  sans réinstallation ni changement des dépendances du projet.
