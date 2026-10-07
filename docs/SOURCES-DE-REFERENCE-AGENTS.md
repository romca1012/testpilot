# Sources de référence — qualité des agents et des vérifications de TestPilot

Date : 2026-10-07. Statut : **source de vérité du chantier « qualité des agents »**
(`docs/PLAN-QUALITE-AGENTS-2026-10.md`). Toute décision de conception d'un outil, d'un prompt, d'une
évaluation ou d'un calcul de référence s'y rattache. En cas d'écart entre ce document et le code,
on le **signale** (CLAUDE.md §5.6), on ne l'arrondit pas.

## Comment lire ce document

- Chaque entrée dit **ce que la source établit** (paraphrase, jamais une citation longue), **où elle
  s'applique** (lot Q1–Q5) et **comment elle a été vérifiée**.
- Les résumés des pages web ont été établis le 2026-10-07 par lecture assistée : avant
  d'implémenter un détail (nom de paramètre, version d'outil, limite chiffrée), **relire la page
  source**. Les versions d'outils Anthropic (`web_search_2026…`, `code_execution_2026…`) changent.
- Quand une affirmation a pu être **vérifiée dans le code installé** (Behave), c'est écrit : cette
  vérification prime sur le résumé de la page.
- Une source n'est jamais une preuve de ce que fait TestPilot : ce sont `docs/CONTINUITE.md` §4 et
  le code qui font foi sur l'existant.

## 1. Anthropic — API et conception d'outils

| Source | Ce qu'elle établit | S'applique à |
|---|---|---|
| [Sorties structurées](https://platform.claude.com/docs/en/docs/build-with-claude/structured-outputs) | `output_config.format` (schéma JSON) garantit une réponse valide ; `strict: true` sur un outil garantit des paramètres conformes. Limites : 20 outils stricts par requête, 24 paramètres optionnels, 16 types union ; `minimum/maximum/minLength` non supportés (le SDK les ajoute en description) ; 1ʳᵉ requête plus lente (compilation, cache 24 h) ; `output_config.format` invalide le cache de prompt ; traiter `stop_reason` = `refusal` / `max_tokens` explicitement | Q3 (mode strict de `write_test_plan`), Q4 (schéma du plan de vérification) |
| [Définir des outils](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools) | Les descriptions d'outils sont le facteur le plus important (≥ 3-4 phrases : quoi, quand, quand NON, limites) ; `input_examples` pour les entrées imbriquées (validés contre le schéma, ~20-200 tokens) ; regrouper les opérations proches ; préfixer les noms ; réponses « haut signal » ; demander une explication, pas un raisonnement. **`tool_choice` any/tool est refusé (400) sur Opus 5.5, Sonnet 5.5, Fable 5.1** : utiliser `auto` + `strict` | Q3, Q4 |
| [Outil d'exécution de code](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool) | Bac à sable Python/Bash **sans accès Internet**, 5 Gio de mémoire, 90 s par cellule en appel programmatique ; conteneur réutilisable (`container.id`, expire) ; gratuit lorsqu'il accompagne la recherche/lecture web ; plusieurs modèles dont Sonnet 4.6 et Haiku 4.5 (fonctions réduites sur Haiku) | Q5 (construction et test d'un calculateur) |
| [Outil de recherche web](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool) | Citations toujours actives (URL, titre, extrait ≤ 150 car., âge de la page) ; `allowed_domains` **ou** `blocked_domains` (pas les deux) ; `max_uses` ; 10 $ / 1000 recherches ; `encrypted_content` à renvoyer tel quel ; afficher les citations à un utilisateur final ; `pause_turn` à relancer | Q5 (recherche réglementaire sourcée) |
| [Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) | Méthode : prototyper, évaluer sur des tâches réalistes multi-appels, **regrouper les transcripts et faire analyser par un agent** pour améliorer les outils. Moins d'outils, plus capables ; espaces de noms ; réponses concises (~⅓ des tokens) ; pagination/troncature. Suivre : précision, appels redondants, erreurs de paramètres, tokens, temps — et ce que l'agent **omet** | Q3 (durcissement des outils), Q2 |
| [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Workflows : prompt chaining, routing, parallélisation/vote, **evaluator-optimizer**, orchestrator-workers. Principes : simplicité, transparence, soin de l'interface agent-outil | Q3, Q4 (agent critique de plan), Q5 |
| [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | Tâche / essai / évaluateur (grader) / transcript / résultat. Évaluateurs : code (rapides, objectifs), modèle (flexibles, à **calibrer** par des humains), humains (référence). **pass@k** (au moins un succès) vs **pass^k** (tous les essais). Évals de **capacité** vs de **régression**. Commencer à 20-50 tâches réelles ; tâches non ambiguës avec **solution de référence** ; jeux **équilibrés** (comportement attendu ET non attendu) ; environnement vierge par essai ; « évaluer le résultat, pas le chemin » ; lire les transcripts ; laisser un « inconnu » aux juges LLM | Q2 (banc d'agents), Q3 |

### Relecture des pages officielles pour Q3-a (2026-10-07) — confirmé, précisé, contredit

Pages relues : « Strict tool use », « Structured outputs », « Define tools » (celle-ci a changé
d'adresse : `…/agents-and-tools/tool-use/define-tools`, plus `implement-tool-use`).

- **Confirmé** : `strict: true` au niveau de la définition d'outil ; 20 outils stricts, 24 paramètres
  optionnels, 16 unions par requête ; `minLength`, `maxLength`, `minimum`, `maximum`, `multipleOf`,
  `maxItems` non supportés (400) ; `additionalProperties` doit valoir `false` ; compilation de la
  grammaire à la 1ʳᵉ requête, cache 24 h ; `output_config.format` invalide le cache de prompt ;
  `input_examples` validés contre le schéma (400 si invalide), ~20-50 tokens (simple) à ~100-200
  (imbriqué) ; `tool_choice` `any`/`tool` refusé sur Opus 5.5, Sonnet 5.5, Fable 5.1 — **et** Mythos
  5.1 (à ajouter à la liste) ; `claude-sonnet-4-6` figure parmi les modèles supportés.
- **Précisé (absent du résumé initial)** : `minItems` n'est supporté que pour **0 et 1** ; les
  propriétés sortent dans l'ordre du schéma, requises d'abord ; un schéma peut passer les trois limites
  et échouer en « Schema is too complex for compilation » (400, délai de compilation 180 s) ; ne
  changer que `name` ou `description` n'invalide pas le cache de grammaire, changer le jeu d'outils si ;
  l'API injecte un prompt système propre aux sorties structurées (« input légèrement plus élevé »,
  montant non publié) ; pas de PHI dans un nom de propriété, une `enum` ou un `pattern` ; casse des
  `enum` non garantie ; les toolsets `computer`/`browser` refusent `strict`.
- **Contredit dans le dépôt** : le commentaire de `llm/adapter.py::call_json` dit les sorties
  structurées « PAS garanties sur Sonnet 4.6 » ; la page les liste, `claude-sonnet-4-6` compris. Le repli
  (400 → parsing tolérant) reste correct et n'a pas été touché : signalé, pas arrondi.
- **Non établi par la doc** : `input_examples` combiné à `strict: true` (aucune page ne l'interdit ni ne
  le montre) ; le surcoût en tokens du mode strict. À lever par UN appel réel peu coûteux.

## 2. Playwright et Behave

| Source | Ce qu'elle établit | S'applique à |
|---|---|---|
| [Playwright — bonnes pratiques](https://playwright.dev/docs/best-practices) | Tester le comportement visible ; locators par rôle/libellé plutôt que CSS/XPath ; **assertions « web-first »** (`expect(...).to_be_visible()`) qui réessaient, jamais de lecture instantanée ; isolation des tests ; Trace Viewer en CI. Déjà appliqué par les règles 5-6 du prompt système | Q1, Q3, Q4 |
| Behave 1.3.3 — **vérifié dans `.venv-v1/Lib/site-packages/behave/model.py`** (l.1995-2014) | Un step qui lève `AssertionError` → statut `failed` ; **toute autre exception → `error`** ; `KeyboardInterrupt` → `error` + arrêt ; le message d'erreur est dans `step.error_message`. Behave sépare donc nativement échec d'assertion et erreur technique | Q1 (classification des échecs) |
| Behave 1.3.3 — **vérifié dans `model.py::Step.run` (l.1951-1984)** | **`step.match` n'existe pas** sur l'objet step : le `Match` est une variable locale transmise aux formateurs. Un hook qui a besoin de la fonction d'un step la retrouve par `context._runner.step_registry.find_match(step)`. Découvert le 2026-10-07 : une doublure de test portait l'attribut `match` et masquait le défaut, seul un vrai run Behave l'a révélé — **toute doublure de step doit reproduire les attributs RÉELS de Behave** | Q1 (hook `after_step`), tout hook futur |
| [Behave — API et hooks](https://behave.readthedocs.io/en/latest/api/) | Hooks `before_/after_` (`all`, `feature`, `scenario`, `step`, `tag`) ; statuts `untested/passed/failed/skipped/undefined` (la version installée en ajoute : `error`, `pending`, `hook_error`) ; `step.error_message` | Q1 |

**Règle d'écart** : pour Behave, ce que dit le **code installé** prime sur la page web (la page
liste moins de statuts que la version 1.3.3).

## 3. Recherches sur les oracles, les calculs et l'amélioration d'agents

| Source | Ce qu'elle établit | S'applique à |
|---|---|---|
| [TaxCalcBench](https://arxiv.org/pdf/2507.16126) | Les modèles de pointe calculent correctement **moins d'un tiers** des déclarations d'impôt fédérales, même simplifiées (mauvais barèmes, erreurs de calcul, éligibilité) | Q4, Q5 : un calcul « de mémoire » n'est jamais une référence |
| [Payroll — compréhension sémantique et cents](https://arxiv.org/pdf/2601.18012) | Bonne compréhension sur les cas simples, difficultés sur multi-juridictions, plafonds, change ; le **calcul programmé et reproductible** améliore nettement la fiabilité | Q5 |
| [Do LLMs Generate Useful Test Oracles? (ASE 2025)](https://conf.researchr.org/details/ase-2025/ase-2025-papers/10/Do-LLMs-Generate-Useful-Test-Oracles-An-Empirical-Study-with-an-Unbiased-Dataset) | 13 866 oracles postérieurs à l'entraînement : des oracles LLM efficaces (score de mutation proche d'oracles humains) mais **faibles sur les oracles complexes** ; risque de faux positifs et faux négatifs | Q1, Q4 |
| [Synedrion — agents pour du code fiscal](https://arxiv.org/pdf/2509.13471) | Un agent de **test métamorphique** produisant des contre-exemples améliore nettement la génération de code fiscal (pire cas 45 % contre 9-15 %) | Q4 (relations métamorphiques), Q5 |
| [GEPA / DSPy](https://dspy.ai/api/optimizers/GEPA) | Optimisation de prompts par **réflexion sur les traces** et frontière de Pareto (au lieu d'une note unique) ; la publication annonce mieux que MIPROv2 (+13 %) avec beaucoup moins d'essais (chiffres de l'article, non reproduits ici) | Q2/Q3 (boucle d'amélioration des prompts, sur jeu mis de côté) |
| [mon-entreprise / Publicodes (URSSAF)](https://www.data.gouv.fr/dataservices/api-mon-entreprise) | Moteur **officiel, libre (MIT) et avec API** de calcul de paie/charges pour la France | Q5 : référence pour **calibrer la méthode** avant de l'appliquer à un pays sans moteur |
| [OpenFisca-Senegal](https://github.com/openfisca/openfisca-senegal) | Marqué « hautement expérimental », issu de hackathons (~2016), barèmes non datés dans la doc visible | Q5 : **ne pas** s'en servir comme référence actuelle sans revérification des barèmes |

## 4. Ce que ces sources imposent à TestPilot (invariants du chantier)

1. **Le texte de l'agent n'est jamais une source de vérité** (CLAUDE.md §3). Un calcul de référence
   est une **fonction déterministe** dont les paramètres citent leurs sources, validée par un
   humain ; l'agent la **propose**, il ne la **juge** pas.
2. **L'agent orchestre des outils fiables** ; la garantie vient de l'outil (déterministe, testé,
   falsifiable), pas du prompt.
3. **Un pourcentage de garantie se mesure** : pass@1, pass^k, faux verts sur défauts injectés
   (« non mesuré ≠ 0 »), coût par cas — sur un banc équilibré, évaluateurs déterministes d'abord.
4. **Mesurer APRÈS avoir rendu le verdict honnête** : un verdict qui laisse passer des verts sans
   preuve gonfle tous les chiffres.
5. **Aucune régression** : chaque changement est livré avec un test de falsifiabilité et la suite
   complète reste verte (les échecs antérieurs, propres à Windows, sont connus et listés au rapport).
