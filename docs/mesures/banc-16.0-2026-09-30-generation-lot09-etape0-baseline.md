# Banc de mesure — Odoo 16.0 — 2026-09-30 — lot09-etape0-baseline

Mode : **génération** · commit `6e250d9` · image `odoo@sha256:0f36a5002a200bb1649771c2cb9403ca5392d7ac4bb23f9ad500b339df3f5a3a` · données de la mesure : `C:\Users\ROMARI~1\AppData\Local\Temp\banc_data_z68voj6s`

## Indicateurs

| Indicateur | Valeur | Échantillon | Cible |
|---|---|---|---|
| I1 — Faux PASSED | non mesuré | 0 / 0 paires (défaut, cas) | 0 faux PASSED |
| I2 — Faux FAILED | non mesuré | 0 / 0 cas sur l'instance saine | ≤ 2 % |
| I3 — Exécution au 1er passage | 73.3 % | 15 cas générés | ≥ 85 % |
| I4 — Verdict exploitable | 6.7 % | 15 cas générés | ≥ 75 % |
| I5 — Blocage bien attribué | non mesuré | 0 / 0 paires (panne, cas) | 100 % |
| I6 — Coût par nouveau cas | 0.112 $ | 15 nouveaux cas | < 1 € par cas |

« non mesuré » signifie qu'aucune observation n'a été faite (mode figé : I3, I4, I6 ne s'appliquent pas) ; ce n'est PAS zéro.

## Non mesuré

- generation / ui_onglet_formulaire : cas non généré ou dry-run non passé
- generation / ui_refus_sauvegarde : cas non généré ou dry-run non passé

## Détail par cas

| Configuration | Cas | Statut | Exécution | Fonctionnel | Cause | Durée (s) |
|---|---|---|---|---|---|---|
| generation | achat_confirmation | blocked | blocked | indetermine |  |  |
| generation | crm_opportunite | blocked | blocked | indetermine |  |  |
| generation | droit_suppression | blocked | blocked | indetermine |  |  |
| generation | facture_validation | blocked | blocked | indetermine |  |  |
| generation | portail_acces | retest | technical_error | indetermine |  |  |
| generation | projet_tache | retest | technical_error | indetermine |  |  |
| generation | stock_reception | blocked | blocked | indetermine |  |  |
| generation | ui_champ_requis | blocked | blocked | indetermine |  |  |
| generation | ui_onglet_formulaire | non mesuré |  |  |  |  |
| generation | ui_refus_sauvegarde | non mesuré |  |  |  |  |
| generation | vente_client_obligatoire | blocked | blocked | indetermine |  |  |
| generation | vente_comptage | blocked | blocked | indetermine |  |  |
| generation | vente_etat_confirme | blocked | blocked | indetermine |  |  |
| generation | vente_livraison | blocked | blocked | indetermine |  |  |
| generation | vente_total | passed | success | conforme |  |  |
