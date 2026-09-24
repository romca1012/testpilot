# Banc de mesure — Odoo 18.0 — 2026-09-24

Mode : **figé** · commit `91b2d7a` · image `odoo@sha256:478065867b945579649373aa4cca3b56f7b74daf0522e5fdf85e7d1262e11d39` · données de la mesure : `C:\Users\ROMARI~1\AppData\Local\Temp\banc_data_ov85npgl`

## Indicateurs

| Indicateur | Valeur | Échantillon | Cible |
|---|---|---|---|
| I1 — Faux PASSED | 0.0 % | 0 / 9 paires (défaut, cas) | 0 faux PASSED |
| I2 — Faux FAILED | 13.3 % | 2 / 15 cas sur l'instance saine | ≤ 2 % |
| I3 — Exécution au 1er passage | non mesuré | non mesuré cas générés | ≥ 85 % |
| I4 — Verdict exploitable | non mesuré | non mesuré cas générés | ≥ 75 % |
| I5 — Blocage bien attribué | 100.0 % | 7 / 7 paires (panne, cas) | 100 % |
| I6 — Coût par nouveau cas | non mesuré | non mesuré nouveaux cas | < 1 € par cas |

« non mesuré » signifie qu'aucune observation n'a été faite (mode figé : I3, I4, I6 ne s'appliquent pas) ; ce n'est PAS zéro.

## Écarts aux attendus

| Configuration | Cas | Attendu | Observé | Cause |
|---|---|---|---|---|
| sain | ui_champ_requis | passed | failed | assertion_mismatch |
| sain | ui_refus_sauvegarde | passed | failed | assertion_mismatch |

## Détail par cas

| Configuration | Cas | Statut | Exécution | Fonctionnel | Cause | Durée (s) |
|---|---|---|---|---|---|---|
| sain | vente_livraison | passed | success | conforme |  | 9.5 |
| sain | vente_total | passed | success | conforme |  | 4.6 |
| sain | vente_client_obligatoire | passed | success | conforme |  | 4.5 |
| sain | vente_etat_confirme | passed | success | conforme |  | 5.4 |
| sain | facture_validation | passed | success | conforme |  | 5.7 |
| sain | droit_suppression | passed | success | conforme |  | 7.6 |
| sain | ui_champ_requis | failed | success | non_conforme | assertion_mismatch | 24.2 |
| sain | ui_onglet_formulaire | passed | success | conforme |  | 19.7 |
| sain | ui_refus_sauvegarde | failed | success | non_conforme | assertion_mismatch | 17.7 |
| sain | achat_confirmation | passed | success | conforme |  | 5.0 |
| sain | stock_reception | passed | success | conforme |  | 4.7 |
| sain | crm_opportunite | passed | success | conforme |  | 4.0 |
| sain | projet_tache | passed | success | conforme |  | 4.0 |
| sain | vente_comptage | passed | success | conforme |  | 4.6 |
| sain | portail_acces | passed | success | conforme |  | 11.0 |
| defaut:vente_sans_livraison | vente_livraison | failed | success | non_conforme | assertion_mismatch | 4.2 |
| defaut:total_faux | vente_total | failed | success | non_conforme | assertion_mismatch | 4.1 |
| defaut:client_non_requis | vente_client_obligatoire | failed | success | non_conforme | assertion_mismatch | 3.9 |
| defaut:etat_bloque | vente_livraison | failed | success | non_conforme | assertion_mismatch | 4.8 |
| defaut:etat_bloque | vente_etat_confirme | failed | success | non_conforme | assertion_mismatch | 5.0 |
| defaut:facture_non_postee | facture_validation | failed | success | non_conforme | assertion_mismatch | 4.5 |
| defaut:droit_trop_large | droit_suppression | failed | success | non_conforme | assertion_mismatch | 6.4 |
| defaut:message_absent | ui_champ_requis | failed | success | non_conforme | assertion_mismatch | 18.4 |
| defaut:message_absent | ui_refus_sauvegarde | failed | success | non_conforme | assertion_mismatch | 17.6 |
| panne:odoo_arrete | vente_livraison | blocked | blocked | indetermine | precondition_non_remplie | 3.8 |
| panne:odoo_arrete | facture_validation | blocked | blocked | indetermine | precondition_non_remplie | 4.0 |
| panne:odoo_arrete | ui_champ_requis | blocked | blocked | indetermine | precondition_non_remplie | 4.0 |
| panne:mauvais_mot_de_passe | vente_livraison | blocked | blocked | indetermine | precondition_non_remplie | 2.5 |
| panne:mauvais_mot_de_passe | facture_validation | blocked | blocked | indetermine | precondition_non_remplie | 2.4 |
| panne:mauvais_mot_de_passe | ui_champ_requis | blocked | blocked | indetermine | precondition_non_remplie | 2.3 |
| panne:module_desinstalle | crm_opportunite | blocked | blocked | indetermine | precondition_non_remplie | 4.1 |
