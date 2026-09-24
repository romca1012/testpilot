# Banc de mesure — Odoo 17.0 — 2026-09-24 — avant-lots-01-03

Mode : **figé** · commit `42fa613` · image `odoo@sha256:8779f8157ddcc37b84014c94646073f46fd4ad776b7a5d95fc3b0dc73a24a8fa` · données de la mesure : `C:\Users\ROMARI~1\AppData\Local\Temp\banc_data_hl783fpd`

## Indicateurs

| Indicateur | Valeur | Échantillon | Cible |
|---|---|---|---|
| I1 — Faux PASSED | 0.0 % | 0 / 8 paires (défaut, cas) | 0 faux PASSED |
| I2 — Faux FAILED | 0.0 % | 0 / 13 cas sur l'instance saine | ≤ 2 % |
| I3 — Exécution au 1er passage | non mesuré | non mesuré cas générés | ≥ 85 % |
| I4 — Verdict exploitable | non mesuré | non mesuré cas générés | ≥ 75 % |
| I5 — Blocage bien attribué | 0.0 % | 0 / 7 paires (panne, cas) | 100 % |
| I6 — Coût par nouveau cas | non mesuré | non mesuré nouveaux cas | < 1 € par cas |

« non mesuré » signifie qu'aucune observation n'a été faite (mode figé : I3, I4, I6 ne s'appliquent pas) ; ce n'est PAS zéro.

## Écarts aux attendus

| Configuration | Cas | Attendu | Observé | Cause |
|---|---|---|---|---|
| panne:odoo_arrete | vente_livraison | blocked | retest | unknown |
| panne:odoo_arrete | facture_validation | blocked | retest | unknown |
| panne:odoo_arrete | ui_champ_requis | blocked | retest | unknown |
| panne:mauvais_mot_de_passe | vente_livraison | blocked | retest | unknown |
| panne:mauvais_mot_de_passe | facture_validation | blocked | retest | unknown |
| panne:mauvais_mot_de_passe | ui_champ_requis | blocked | retest | unknown |
| panne:module_desinstalle | crm_opportunite | blocked | failed | assertion_mismatch |

## Détail par cas

| Configuration | Cas | Statut | Exécution | Fonctionnel | Cause | Durée (s) |
|---|---|---|---|---|---|---|
| sain | vente_livraison | passed | success | conforme |  | 4.1 |
| sain | vente_total | passed | success | conforme |  | 3.9 |
| sain | vente_client_obligatoire | passed | success | conforme |  | 3.6 |
| sain | vente_etat_confirme | passed | success | conforme |  | 4.6 |
| sain | facture_validation | passed | success | conforme |  | 6.6 |
| sain | droit_suppression | passed | success | conforme |  | 5.6 |
| sain | ui_champ_requis | passed | success | conforme |  | 11.0 |
| sain | achat_confirmation | passed | success | conforme |  | 4.6 |
| sain | stock_reception | passed | success | conforme |  | 4.9 |
| sain | crm_opportunite | passed | success | conforme |  | 3.8 |
| sain | projet_tache | passed | success | conforme |  | 3.8 |
| sain | vente_comptage | passed | success | conforme |  | 4.0 |
| sain | portail_acces | passed | success | conforme |  | 9.5 |
| defaut:vente_sans_livraison | vente_livraison | failed | success | non_conforme | assertion_mismatch | 4.3 |
| defaut:total_faux | vente_total | failed | success | non_conforme | assertion_mismatch | 4.5 |
| defaut:client_non_requis | vente_client_obligatoire | failed | success | non_conforme | assertion_mismatch | 4.0 |
| defaut:etat_bloque | vente_livraison | failed | success | non_conforme | assertion_mismatch | 4.2 |
| defaut:etat_bloque | vente_etat_confirme | failed | success | non_conforme | assertion_mismatch | 5.8 |
| defaut:facture_non_postee | facture_validation | failed | success | non_conforme | assertion_mismatch | 3.9 |
| defaut:droit_trop_large | droit_suppression | failed | success | non_conforme | assertion_mismatch | 5.4 |
| defaut:message_absent | ui_champ_requis | failed | success | non_conforme | assertion_mismatch | 14.2 |
| panne:odoo_arrete | vente_livraison | retest | technical_error | indetermine | unknown | 4.0 |
| panne:odoo_arrete | facture_validation | retest | technical_error | indetermine | unknown | 4.0 |
| panne:odoo_arrete | ui_champ_requis | retest | technical_error | indetermine | unknown | 3.7 |
| panne:mauvais_mot_de_passe | vente_livraison | retest | technical_error | indetermine | unknown | 2.0 |
| panne:mauvais_mot_de_passe | facture_validation | retest | technical_error | indetermine | unknown | 2.2 |
| panne:mauvais_mot_de_passe | ui_champ_requis | retest | technical_error | indetermine | unknown | 2.2 |
| panne:module_desinstalle | crm_opportunite | failed | success | non_conforme | assertion_mismatch | 5.7 |
