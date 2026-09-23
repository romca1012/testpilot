---
description: Lot 10 — Campagne de mesure complète et mise à jour de la documentation
---

# Lot 10 — Mesure finale et clôture du chantier

Lis `CLAUDE.md` et tout le plan. Dépend de tous les lots. Branche : `lot-10-cloture`.

## Travail

1. Banc (lot 04), versions 16.0, 17.0, 18.0 : mode `figé` puis mode `génération` (plafond de coût
   explicite). Conformité web (`-m conformance`) et Odoo (`-m conformance_odoo`).
2. Rapport `docs/QUALITE-GENERATION-<date>.md`, même structure et même discipline que celui du
   2026-09-22 : ligne de base (lot 04) → résultat, I1 à I6, échantillon, coût, causes d'échec
   restantes classées, limites. Aucun chiffre sans sa commande de reproduction.
3. Mets à jour :
   - `docs/ARCHITECTURE.md` : axe exécution `blocked`, confiance, profils d'instance, oracle,
     outils de l'agent, banc ;
   - `docs/CONTINUITE.md` §4 : proposer (sans l'acter) les invariants nouveaux — « pas de
     `conforme` sans constat », « un `failed` vient d'un `Alors` », « un vert par repli est
     qualifié » — pour validation du porteur ;
   - `docs/ONBOARDING.md` : lancer le banc, lancer une campagne stricte ;
   - le tableau de suivi du plan (statuts, dates, liens vers les rapports).
4. Liste des écarts restants et proposition de chantier suivant, **sans** l'entamer.

## Critères d'acceptation

- [ ] I1 = 0 et I5 = 100 % sur les trois versions, ou écart expliqué cas par cas.
- [ ] Chaque indicateur publié avec échantillon et commande.
- [ ] Documentation cohérente avec le code (le sous-agent `verdict-reviewer` le vérifie).

Rapport au format `CLAUDE.md` §10.
