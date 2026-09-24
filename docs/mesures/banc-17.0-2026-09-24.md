# Banc de mesure — Odoo 17.0 — 2026-09-24

Mode : **figé** · commit `2b319c6` · image `odoo@sha256:8779f8157ddcc37b84014c94646073f46fd4ad776b7a5d95fc3b0dc73a24a8fa` · données de la mesure : `C:\Users\ROMARI~1\AppData\Local\Temp\banc_data_1_f9z377`

## Indicateurs

| Indicateur | Valeur | Échantillon | Cible |
|---|---|---|---|
| I1 — Faux PASSED | 0.0 % | 0 / 8 paires (défaut, cas) | 0 faux PASSED |
| I2 — Faux FAILED | 0.0 % | 0 / 13 cas sur l'instance saine | ≤ 2 % |
| I3 — Exécution au 1er passage | non mesuré | non mesuré cas générés | ≥ 85 % |
| I4 — Verdict exploitable | non mesuré | non mesuré cas générés | ≥ 75 % |
| I5 — Blocage bien attribué | 100.0 % | 7 / 7 paires (panne, cas) | 100 % |
| I6 — Coût par nouveau cas | non mesuré | non mesuré nouveaux cas | < 1 € par cas |

« non mesuré » signifie qu'aucune observation n'a été faite (mode figé : I3, I4, I6 ne s'appliquent pas) ; ce n'est PAS zéro.

## Détail par cas

| Configuration | Cas | Statut | Exécution | Fonctionnel | Cause | Durée (s) |
|---|---|---|---|---|---|---|
| sain | vente_livraison | passed | success | conforme |  | 5.2 |
| sain | vente_total | passed | success | conforme |  | 4.7 |
| sain | vente_client_obligatoire | passed | success | conforme |  | 4.2 |
| sain | vente_etat_confirme | passed | success | conforme |  | 4.7 |
| sain | facture_validation | passed | success | conforme |  | 4.4 |
| sain | droit_suppression | passed | success | conforme |  | 6.0 |
| sain | ui_champ_requis | passed | success | conforme |  | 14.8 |
| sain | achat_confirmation | passed | success | conforme |  | 5.7 |
| sain | stock_reception | passed | success | conforme |  | 5.0 |
| sain | crm_opportunite | passed | success | conforme |  | 4.2 |
| sain | projet_tache | passed | success | conforme |  | 6.2 |
| sain | vente_comptage | passed | success | conforme |  | 5.9 |
| sain | portail_acces | passed | success | conforme |  | 7.0 |
| defaut:vente_sans_livraison | vente_livraison | failed | success | non_conforme | assertion_mismatch | 4.2 |
| defaut:total_faux | vente_total | failed | success | non_conforme | assertion_mismatch | 4.1 |
| defaut:client_non_requis | vente_client_obligatoire | failed | success | non_conforme | assertion_mismatch | 3.8 |
| defaut:etat_bloque | vente_livraison | failed | success | non_conforme | assertion_mismatch | 3.9 |
| defaut:etat_bloque | vente_etat_confirme | failed | success | non_conforme | assertion_mismatch | 6.3 |
| defaut:facture_non_postee | facture_validation | failed | success | non_conforme | assertion_mismatch | 4.0 |
| defaut:droit_trop_large | droit_suppression | failed | success | non_conforme | assertion_mismatch | 6.4 |
| defaut:message_absent | ui_champ_requis | failed | success | non_conforme | assertion_mismatch | 15.8 |
| panne:odoo_arrete | vente_livraison | blocked | blocked | indetermine | precondition_non_remplie | 3.8 |
| panne:odoo_arrete | facture_validation | blocked | blocked | indetermine | precondition_non_remplie | 3.8 |
| panne:odoo_arrete | ui_champ_requis | blocked | blocked | indetermine | precondition_non_remplie | 3.7 |
| panne:mauvais_mot_de_passe | vente_livraison | blocked | blocked | indetermine | precondition_non_remplie | 2.3 |
| panne:mauvais_mot_de_passe | facture_validation | blocked | blocked | indetermine | precondition_non_remplie | 2.8 |
| panne:mauvais_mot_de_passe | ui_champ_requis | blocked | blocked | indetermine | precondition_non_remplie | 3.2 |
| panne:module_desinstalle | crm_opportunite | blocked | blocked | indetermine | precondition_non_remplie | 3.4 |
