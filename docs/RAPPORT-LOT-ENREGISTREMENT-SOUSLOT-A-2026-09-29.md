## Lot « Enregistrement assisté du chemin de connexion » — sous-lot A — calcul du nom accessible (AccName) — terminé (en attente de fusion)

Décisions utilisées : aucune décision `D#` du registre du chantier `docs/PLAN-FIABILITE-VERDICT-2026-09.md` — ce lot est
hors de ce chantier, donné directement par le porteur en session. Principe non négociable énoncé dans la consigne :
« aucun appel à un modèle de langage dans le chemin d'exécution qui capture ou rejoue les clics » — le calcul du nom d'un
élément cliqué est un algorithme déterministe (norme W3C AccName), jamais une décision devinée par une IA en direct.

### Ce que le sous-lot change, en clair

Deux algorithmes déterministes, purs, sans aucun appel réseau ni LLM :

1. **Calcul du nom accessible (AccName)** — lu sur la source du groupe de travail W3C (`w3c/aria`, `accname/index.html`),
   pas travaillé de mémoire : 2A (masqué non référencé) → 2B (`aria-labelledby`, récursif) → 2D (`aria-label`) → 2E
   (étiquette du langage hôte : `<label for>`, `<label>` englobant, `alt`, avec `placeholder` en repli restreint aux
   champs de saisie, HTML-AAM) → 2F/2G/2H (nom depuis le contenu, récursif) → 2I (`title`, tout dernier recours). Étape
   2C (« embedded control ») explicitement écartée : cas étroit sans usage pour un chemin de connexion.
2. **Remontée d'arbre** (point cliqué → élément interactif exploitable) — propre à ce projet, aucun jeu de tests officiel
   externe ne la couvre (les cas AccName partent toujours d'un élément déjà identifié, jamais d'un point). Un clic qui ne
   touche rien d'interactif rend une absence propre (`None`), jamais une exception — un simple clic égaré de l'utilisateur
   pendant l'enregistrement ne doit pas casser toute la session.

Ambiguïté (rôle + nom qui correspondrait à plusieurs éléments au rejeu) : réutilise le principe déjà établi de
`ElementIntrouvableError`/`_un_seul` de la bibliothèque de steps — jamais résolu en silence par « le premier trouvé ».

Le shadow DOM ouvert est percé récursivement partout où c'est nécessaire : résolution du point cliqué
(`elementFromPoint`), remontée d'ancêtre au-delà d'une frontière shadow (`getRootNode().host`), résolution d'un id
référencé par `aria-labelledby`/`label[for]` (`getRootNode().getElementById`/`querySelectorAll`, jamais `document`), et
comptage des homonymes pour la détection d'ambiguïté. Un shadow root **fermé** reste invisible par construction du
navigateur (`shadowRoot` rend `null`) — limite du web, documentée, non contournable.

### Changements

- `src/testpilot/generation/accname.py` (nouveau) — les deux algorithmes ci-dessus, module pur.
- `tests/test_accname.py` (nouveau, 34 tests, marqueur `conformance` — vrai Chromium, exclu de `pytest -q` par défaut).
- `.github/workflows/generation-quality.yml` — `test_accname.py` ajouté au job `browser-evidence` (seul job qui installe
  un vrai Chromium).

### Tests ajoutés

- 15 cas repris de web-platform-tests/wpt (`accname/name/comp_labelledby.html`, `comp_name_from_content.html`,
  `comp_host_language_label.html`, lus le 2026-09-29 via leur contenu brut sur GitHub), chacun commenté avec son fichier
  et son libellé source. Cas écartés, documentés plutôt que passés sous silence : contenu généré par CSS
  (`::before`/`::after`, compteurs, `content: attr()`), rendu bidirectionnel (RTL), `text-transform` — sans rapport avec
  un chemin de connexion, une reproduction fidèle exigerait un moteur de disposition CSS.
- Cas limites propres au projet : élément sans nom du tout, descendant masqué (ne contribue rien), `<label for>` masqué
  (ne contribue rien — 2A n'exempte QUE le nœud directement référencé par `aria-labelledby`).
- **Falsifiabilité de l'ambiguïté** : `test_falsifiable_deux_boutons_meme_role_et_meme_nom_leve_ElementIntrouvableError`
  (lève réellement) et son pendant `..._mais_nom_different_ne_leve_rien` (ne lève pas) — prouve que le garde-fou mord,
  pas seulement qu'il existe dans le code.
- **5 cas de remontée d'arbre volontairement généreux** (aucune couverture officielle externe) : icône imbriquée dans un
  bouton, texte imbriqué dans un lien, zone vide d'un `role="button"` sans enfant sémantique, clic qui ne touche rien
  d'interactif (`None`), conteneur purement visuel à traverser.
- **3 tests de résolution par coordonnées réelles** (clic simulé, pas un `ElementHandle` passé directement) dans un
  shadow DOM ouvert : bouton interne résolu, remontée qui ne saute pas par-dessus la frontière shadow vers un ancêtre
  extérieur, ambiguïté détectée à travers le shadow DOM.
- **2 tests de falsifiabilité supplémentaires**, trouvés en revue verdict-reviewer (deuxième passage) : `aria-labelledby`
  et `<label for>` valides mais internes à un shadow DOM, chacun vérifié rouge avant correctif (résultats exacts observés :
  `'x'` au lieu du vrai libellé, `''` au lieu du vrai libellé) puis vert après.

### Critères d'acceptation

- [x] Algorithme AccName implémenté dans l'ordre précis de la spec officielle.
- [x] ≥ 20 cas de test officiels (15 retenus, documentés, plus les cas écartés justifiés) — tous retrouvés.
- [x] Cas limites propres au projet : élément sans nom, composant personnalisé (shadow DOM), deux éléments homonymes
      (erreur explicite, jamais un choix silencieux).
- [ ] Élément dans une iframe — **non couvert** (voir Écarts ci-dessous).
- [x] Source exacte documentée (commentaires par cas + ce rapport), cas écartés justifiés.

### Mesures

- `pytest -q -m conformance tests/test_accname.py` : 34 passed (~1,7 s, vrai Chromium headless).
- `pytest -q` (suite par défaut) : `test_accname.py` entièrement désélectionné (marqueur `conformance`), aucune
  régression sur les 2882 tests par défaut du dépôt (vérifié via la suite complète lancée pour le sous-lot B, sur la
  même base de code).
- `ruff check --select E9,F63,F7,F82 src tests` : vert.
- CI GitHub (`browser-evidence`, vrai Chromium installé) : verte sur `dcc3241` (4/4 checks requis) ; re-vérification en
  cours sur `f65c61f` (dernier commit) au moment de ce rapport.
- Aucun appel LLM dans ce module — coût nul, hors périmètre du §9 du brief.

### Écarts constatés avec le plan

- **Iframe non traitée** : la consigne demande un cas limite « élément dans une iframe » — non implémenté. Une iframe
  de même origine aurait pu être percée comme un shadow root (accès direct à `contentDocument`), mais une iframe
  cross-origin est structurellement invisible depuis `page.evaluate` (barrière de sécurité du navigateur, pas une
  limite de cet algorithme) — un écran de connexion tiers logé dans une iframe cross-origin resterait donc hors de
  portée de cette remontée d'arbre. Signalé plutôt que traité en silence ; à trancher explicitement si un cas réel se
  présente (sous-lot C ou plus tard).
- **Deux bugs trouvés par le sous-agent verdict-reviewer, tous deux corrigés et vérifiés falsifiables avec un vrai
  Chromium** (voir Risques ci-dessous pour le détail complet) :
  1. Premier passage : `<label for>` masqué fuyait son texte, et le shadow DOM n'était pas percé pour
     `elementFromPoint`/la remontée d'ancêtre/le comptage d'homonymes (commit `dcc3241`).
  2. Deuxième passage : la résolution par id (`aria-labelledby`, `<label for>`) restait scopée à `document`, donc
     invisible à l'intérieur d'un shadow DOM même après le premier correctif (commit `f65c61f`).
  Dans les deux cas, le défaut produisait un **résultat plausible mais faux** (jamais une absence détectable) — le pire
  cas pour un module qui alimentera une capture/rejeu sans supervision humaine ultérieure. Chaque correctif est
  accompagné d'un test qui reproduit exactement le mauvais résultat observé avant correction.
- Code mort retiré en cours de revue : `_ROLES_NOM_DEPUIS_CONTENU` contenait des rôles (`heading`, `cell`, `gridcell`,
  `columnheader`, `rowheader`, `term`) jamais atteignables par `calculer()` (aucun ne fait partie des rôles interactifs
  que `resoudreCible` peut retourner) — retirés, même principe déjà appliqué à `legend`/`caption`.

### Risques / points à surveiller

- Élément dans une iframe cross-origin : non couvert, barrière de sécurité de la plateforme (voir Écarts).
- Un ancêtre `aria-hidden="true"` non visuellement masqué lui-même (motif rare : contenu décoratif superposé) ne serait
  pas détecté par `estMasque`, qui ne teste que l'état propre de l'élément — signalé en revue, non vérifié en pratique,
  scénario marginal.
- Ce module ne fait QUE calculer un nom/rôle à partir d'un point — il ne capture ni ne rejoue encore rien (sous-lots
  C/D, pas commencés). Sa fiabilité conditionne directement celle de tout le reste du lot : un nom silencieusement faux
  ici deviendrait un clic silencieusement faux au rejeu, sans qu'aucune couche ultérieure ne puisse le détecter.

### Suggestions hors périmètre

- Ajouter un test dédié pour une iframe de même origine (percée possible, contrairement au cas cross-origin) si un cas
  réel se présente.
