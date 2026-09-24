---
description: Lot 11 — Faux verdicts trouvés en campagne réelle : refus déclenché hors soumission (F7), assertion sur message deviné (F8), comptage réécrit par l'agent (F9)
---

# Lot 11 — Faux verdicts de soumission (F7, F8, F9)

Lis `CLAUDE.md` puis F7/F8 de `docs/PLAN-FIABILITE-VERDICT-2026-09.md`, et le rapport de campagne
`docs/mesures/campagne-lot01-2026-09-23.md`. Décision requise : aucune. Branche : `lot-11-faux-verdicts-soumission`.

## Pourquoi

Deux faux statuts trouvés en validant le lot 01 sur une campagne réelle (10 cas, projet 1 et 12) :
un test qui n'a rien soumis est accusé d'avoir des données invalides (F7, cas 95), et un test dont
l'application a correctement refusé la saisie est déclaré `non_conforme` parce que le message
affiché diffère d'un texte deviné par l'agent (F8, cas 97). Les deux sont des **statuts faux** —
le défaut le plus grave du chantier (CLAUDE.md §4) — donc traités avant le lot 12, plus fréquent
mais moins grave (une erreur technique, jamais un mensonge sur le verdict).

## À lire d'abord

- `behave_runtime/steps_library/_base_helpers.py` : `verifier_soumission_non_bloquee`,
  `_refus_par_le_navigateur`, `click_first_actionable`, `click_button`, `diagnostic_soumission`,
  `_refus_serveur`, `lever_donnee_refusee`, `DonneeRefuseeError`.
  `.local-preview/qualification/pilote-lot01-projet1-20260923/pilote-p1-c95-i1-20260923/` et
  `.../pilote-p1-c97-i1-20260923/` (artefacts de la campagne, `execution/execution.behave.json`
  pour le message d'erreur exact de chaque cas).
- `src/testpilot/generation/smoke_check.py`, `src/testpilot/generation/prompts/system_prompt.md`
  (Règle 6 ou équivalent sur les assertions de message).
- `tests/test_soumission_bloquee.py`, `tests/test_refus_champ_teste.py`,
  `tests/test_diagnostic_soumission.py`, `tests/test_reponse_serveur_3a.py` (gardes existantes à
  ne pas casser).

## F7 — Le refus ne se déclenche que sur une vraie soumission

1. `verifier_soumission_non_bloquee` (appelé par `click_button`) ne doit s'appliquer QUE si le
   clic est une **soumission**, établie par un signal runtime — jamais par le libellé du bouton :
   - un événement `submit` du formulaire capturé autour du clic, ou
   - le bouton cliqué a `type="submit"` (ou équivalent Odoo `.o_form_button_save` documenté),  ou
   - une requête réseau POST/PUT capturée dans la fenêtre du clic (le mécanisme de capture de
     `context.reponse_formulaire` existe déjà pour Odoo — vérifie s'il est réutilisable ici).
2. Un clic de navigation (changement d'URL en GET, onglet, lien, étape intermédiaire d'un
   formulaire multi-écrans type « Demande de mutation ») ne déclenche JAMAIS le diagnostic de
   refus, même si des champs HTML invalides existent ailleurs sur la page à ce moment-là.
3. Documente dans la docstring la distinction observée en campagne réelle (cas 95 : le clic sur
   « Demande de mutation » n'est pas un envoi, c'est une étape de navigation qui révèle le
   sous-formulaire — les champs invalides détectés à ce moment appartiennent à une section pas
   encore atteinte du formulaire).

## F8 — Un message attendu doit avoir été observé, pas deviné

1. Un constat de refus (`Alors` qui affirme un message précis) doit se fonder sur : (a) un signal
   runtime que l'application a refusé (élément `[role=alert]` visible, ou champ marqué invalide,
   ou absence de création prouvée par le comptage du lot 01) — **et**, au maximum, (b) UN fragment
   de message, qui doit avoir été **OBSERVÉ pendant la génération** (`attempt_form_submission` ou
   l'équivalent d'inspection de page) et figurer dans les champs vérifiés / la provenance de la
   génération — jamais un texte que l'agent invente ou paraphrase de mémoire.
2. `smoke_check.py` : ajoute une garde qui signale tout texte attendu dans un `Alors` qui n'a pas
   été observé pendant la génération, en réutilisant le circuit de relecture existant (même
   patron que les autres gardes de `smoke_check`).
3. Prompt système : une règle courte (un exemple, pas un paragraphe) rappelant qu'un message
   attendu doit venir d'une observation réelle, jamais d'un texte deviné — sans faire grossir le
   prompt au-delà du seuil déjà mesuré pour ce fichier.

## F9 — L'agent ne recompte jamais lui-même (ajouté le 2026-09-24)

`write_steps_file` refuse (régime bloquant, comme le transport interdit) tout step généré qui
appelle `search_count`, ou `len()` d'un `search`/`read`/`search_read`, sur `context.odoo.env` —
détection par AST (`_forbidden_recount`). Le message de refus renvoie aux steps du catalogue du
lot 01. Le prompt (Règle 3) et l'ancien message de refus, qui recommandaient `search_count([])`,
sont corrigés. Parcours en lecture seule des versions en base : lister, ne pas modifier.

## Tests exigés

- F7 : reproduis le cas 95 en doublure (context/page factices). Montre qu'il produit
  `DonneeRefuseeError` sur le code ACTUEL (avant ce lot) et ne le produit plus après — sur un clic
  de navigation qui révèle des champs pas encore remplis. Les tests existants de refus navigateur
  (`test_soumission_bloquee.py`, `test_refus_champ_teste.py`) restent verts sans changer leurs
  assertions.
- F8 : reproduis le cas 97 en doublure. Avec un message réel différent du message deviné dans le
  cas de test, le verdict n'est plus `non_conforme` À TORT (soit le smoke-check bloque avant
  l'exécution, soit le constat se limite au signal + fragment réellement observé). Les tests
  existants de `test_diagnostic_soumission.py`/`test_reponse_serveur_3a.py` restent verts.

## Critères d'acceptation

- [ ] Le cas 95 rejoué (nouvelle génération, un seul run) ne produit plus `donnee_invalide` à
      tort sur un clic de navigation intermédiaire.
- [ ] Le cas 97 rejoué ne produit plus `non_conforme` à tort quand l'application refuse
      correctement avec un message différent du texte deviné.
- [ ] `python -m pytest -q` et ruff critique verts.

## Interdits

- Toucher à `defect_taxonomy.py` ou `status.py` (lot 02).
- Affaiblir la détection d'un VRAI refus applicatif (une soumission réellement bloquée doit
  continuer à lever `DonneeRefuseeError`/le constat `non_conforme` adapté).

Termine par le rapport au format de `CLAUDE.md` §10 et lance le sous-agent `verdict-reviewer`.
