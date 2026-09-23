---
description: Lot 12 — Valeurs de champ écrites sans avoir été observées : masque de saisie (C10), référence relationnelle inexistante (C10)
---

# Lot 12 — Valeurs observées (C10)

Lis `CLAUDE.md` puis C10 de `docs/PLAN-FIABILITE-VERDICT-2026-09.md`, et le rapport de campagne
`docs/mesures/campagne-lot01-2026-09-23.md`. Décision requise : aucune. Dépend du lot 11 (F7/F8
d'abord, ce sont des statuts faux). Branche : `lot-12-valeurs-observees`.

## Pourquoi

Deux défauts de même cause racine, mesurés en campagne réelle : l'agent écrit une valeur qu'il
**invente** plutôt qu'une valeur **observée**. Un masque de saisie sur `numero_facture1` a
transformé silencieusement la valeur inventée sur 3 essais sur 8 (cas 99, 101, 126) ; un produit
halluciné (« PC Portable HP ») absent du catalogue réel a fait échouer le cas 13. Le correctif
many2one déjà fait (`inspect_schema` annonce qu'un champ relationnel se SÉLECTIONNE, ne se
RENSEIGNE pas) est le bon modèle : une valeur saisie doit avoir été vue, jamais devinée.

## Avant de coder

Lis `src/testpilot/generation/valeur_conforme.py`, `src/testpilot/generation/regles_apprises.py`,
les `RefusMesure`/`refus_mesures` de `_base_helpers.py`, et le correctif many2one déjà fait
(`src/testpilot/generation/tools/inspect.py`, `inspect_schema`). **Propose un plan avant
d'implémenter** : ne crée pas un second mécanisme parallèle à l'apprentissage existant
(`regles_apprises.py` mémorise déjà des règles de champ apprises par projet — vérifie si le
masque de saisie s'y intègre naturellement plutôt que d'ajouter un nouveau fichier de mémoire).

## Masques de saisie (#4, C10)

1. Pendant l'exploration/inspection d'un formulaire, relève pour chaque champ : `pattern`,
   `maxlength`, `inputmode`, `placeholder`, et les indices de masque (`data-mask`, `inputmask` ou
   équivalent). Relève aussi jusqu'à 3 valeurs existantes du champ via RPC (`query_data` ou
   l'outil d'inspection déjà disponible), sans lire de donnée sensible au-delà du format
   (anonymise/tronque si le champ contient une donnée personnelle).
2. À l'exécution, après chaque `fill_field`, relis la valeur réellement retenue par le champ (le
   mécanisme existe déjà partiellement : `_verifier_valeur_retenue`, `_base_helpers.py`). Si elle
   diffère de la valeur saisie :
   - consigne la transformation (saisi → obtenu) dans le sidecar des refus mesurés
     (`RefusMesure`/`refus_mesures`, même mécanisme que les refus serveur) ;
   - lève `DonneeRefuseeError` avec les DEUX valeurs (déjà fait pour ce message précis — vérifie
     si le sidecar de mesure existe déjà pour ce cas ou doit être ajouté) — ne laisse jamais le
     scénario continuer avec une donnée silencieusement modifiée.
3. La génération (prompt/outils) reçoit le format observé pour ce champ (exemples réels relevés +
   transformation apprise d'un run précédent, via le mécanisme d'apprentissage existant) plutôt
   que d'inventer un format.

## Références inexistantes (#2, C10)

1. Toute valeur de champ relationnel (many2one) ou d'option de liste (select/radio) écrite dans un
   `.feature` est vérifiée au `smoke_check` par `name_search` (Odoo) ou les options réellement
   relevées pendant l'inspection — jamais laissée passer sans vérification jusqu'à l'exécution
   réelle.
2. Si la valeur est absente, `smoke_check` refuse en listant les 5 valeurs réelles les plus
   proches (recherche approximative sur le libellé), pour que l'agent corrige sans deviner à
   nouveau à l'aveugle.

## Tests exigés

- Doublure de masque : une valeur écrite « FAC-TEST-001 » relue comme « 001 » lève
  `DonneeRefuseeError` AU STEP DE SAISIE (`fill_field`), pas plus tard dans le scénario.
- Produit/référence absent : `smoke_check` refuse AVANT tout run réel, avec les valeurs réelles
  les plus proches dans le message.
- Garde anti-régression : un champ dont la valeur saisie est fidèlement retenue ne déclenche rien
  (pas de faux positif sur un champ sans masque).

## Mesure (avant/après)

Rejoue les cas 99, 101, 126 et 13 : une génération neuve (pas un rejeu de l'ancien Gherkin), un
seul run physique chacun (`TESTPILOT_QUALIFICATION=1`, comme la campagne du 23/09). Rapporte la
réussite au premier passage et le coût, avant (campagne du 23/09,
`docs/mesures/campagne-lot01-2026-09-23.md`) → après (ce lot).

## Critères d'acceptation

- [ ] Les cas 99, 101, 126 et 13 rejoués ne reproduisent plus le même défaut (masque non observé /
      référence hallucinée) — mesuré, pas seulement en tests unitaires.
- [ ] `python -m pytest -q` et ruff critique verts.
- [ ] Le coût par cas reste sous le plafond §9 (< 1 €).

## Interdits

- Créer un second mécanisme de mémoire de règles apprises parallèle à `regles_apprises.py` sans
  justifier explicitement pourquoi l'existant ne convient pas.
- Toucher à `defect_taxonomy.py` ou `status.py` (lot 02).

Termine par le rapport au format de `CLAUDE.md` §10 et lance le sous-agent `verdict-reviewer`.
