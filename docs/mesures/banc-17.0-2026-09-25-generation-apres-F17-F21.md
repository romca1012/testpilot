# Banc de mesure — Odoo 17.0 — 2026-09-25 — apres-F17-F21

Mode : **génération** · commit `763d528` · image `odoo@sha256:8779f8157ddcc37b84014c94646073f46fd4ad776b7a5d95fc3b0dc73a24a8fa` · données de la mesure : `C:\Users\ROMARI~1\AppData\Local\Temp\banc_data_lp0uo98l`

## Indicateurs

| Indicateur | Valeur | Échantillon | Cible |
|---|---|---|---|
| I1 — Faux PASSED | non mesuré | 0 / 0 paires (défaut, cas) | 0 faux PASSED |
| I2 — Faux FAILED | non mesuré | 0 / 0 cas sur l'instance saine | ≤ 2 % |
| I3 — Exécution au 1er passage | 33.3 % | 15 cas générés | ≥ 85 % |
| I4 — Verdict exploitable | 33.3 % | 15 cas générés | ≥ 75 % |
| I5 — Blocage bien attribué | non mesuré | 0 / 0 paires (panne, cas) | 100 % |
| I6 — Coût par nouveau cas | 0.101 $ | 15 nouveaux cas | < 1 € par cas |

« non mesuré » signifie qu'aucune observation n'a été faite (mode figé : I3, I4, I6 ne s'appliquent pas) ; ce n'est PAS zéro.

## Non mesuré

- generation / ui_champ_requis : cas non généré ou dry-run non passé

## Détail par cas

| Configuration | Cas | Statut | Exécution | Fonctionnel | Cause | Durée (s) |
|---|---|---|---|---|---|---|
| generation | achat_confirmation | retest | technical_error | indetermine |  |  |
| generation | crm_opportunite | retest | technical_error | indetermine |  |  |
| generation | droit_suppression | retest | technical_error | indetermine |  |  |
| generation | facture_validation | retest | technical_error | indetermine |  |  |
| generation | portail_acces | passed | success | conforme |  |  |
| generation | projet_tache | retest | technical_error | indetermine |  |  |
| generation | stock_reception | retest | technical_error | indetermine |  |  |
| generation | ui_champ_requis | non mesuré |  |  |  |  |
| generation | ui_onglet_formulaire | passed | success | conforme |  |  |
| generation | ui_refus_sauvegarde | passed | success | conforme |  |  |
| generation | vente_client_obligatoire | retest | technical_error | indetermine |  |  |
| generation | vente_comptage | passed | success | conforme |  |  |
| generation | vente_etat_confirme | retest | technical_error | indetermine |  |  |
| generation | vente_livraison | retest | technical_error | indetermine |  |  |
| generation | vente_total | passed | success | conforme |  |  |
