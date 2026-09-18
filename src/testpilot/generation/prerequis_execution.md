# Prérequis à vérifier avant une exécution

État au 18 septembre 2026 — proposition pour revue humaine (backlog 1.1).
Une génération ou un dry-run vert ne prouve pas que ces prérequis sont satisfaits.
Le dry-run vérifie le parsing et les steps ; seule une observation de la cible
établit la session, les droits, les libellés et les contraintes de données.

## Checklist de relecture

| Point | Preuve à recueillir sur la cible du projet | Si la preuve manque | Garde du dépôt |
|---|---|---|---|
| Session stable | Avec le compte de test, ouvrir le formulaire réel de connexion, terminer le SSO si présent, atteindre la page authentifiée puis une page protégée. Consigner URL et capture sans secret. | Prérequis non vérifié ; ne pas qualifier le scénario métier de conforme. | `test_step_login_portal_delegue_a_playwright_login_corrige`, `test_step_navigate_url_delegue_aussi_si_page_vierge`, `test_aucun_doublon_local_de_playwright_login_ne_subsiste` |
| Surface et droits | Vérifier que le menu demandé existe avec ce compte, sur le portail ou le back-office effectivement attendu. | Vérifier la surface et les droits avant de modifier le scénario ou de conclure à un défaut applicatif. | `test_navigate_menu_part_du_selecteur_d_applications_back_office`, `test_navigation_helper_et_step_restent_identiques_apres_divergence_mesuree` |
| Langue | Lire la langue du compte et les libellés visibles ; les comparer aux libellés utilisés par le scénario. La langue Gherkin `fr` ne prouve pas celle de l’interface. | Signaler le décalage ; ne pas inventer une traduction ni changer la langue du compte automatiquement. | `test_langue_des_libelles_mesures_conservee_sans_traduction_devinee` préserve les libellés. Leur correspondance avec la cible reste une vérification humaine. |
| Données | Observer les options, champs requis et contraintes réelles ; distinguer données nominales et valeurs invalides volontairement testées. Après soumission, lire le refus effectif ou vérifier l’état créé. | Conserver le refus et sa capture ; ne pas confondre un jeu de données rejeté avec un bug applicatif. | `test_un_AUTRE_champ_invalide_non_couvert_est_toujours_signale`, `test_le_champ_laisse_vide_par_le_scenario_lui_meme_ne_leve_RIEN`, `test_GARDE_le_resolveur_ne_reproduit_pas_une_valeur_deja_refusee` |

## Faits à l’origine de ces contrôles

- **Connexion SSO, staging Sapian, résultat 1, 18 septembre** : le crawl disposait du correctif du formulaire replié, mais le step conservait un doublon non corrigé. Timeout de 15 secondes documenté dans [la garde de délégation](../../../tests/test_odoo_steps_login_delegue.py). Le step appelle désormais le helper commun.
- **Menu Parc IT, staging, 18 septembre** : recherche depuis la racine du portail alors que le menu est dans le back-office ; le résultat 3 utilise `/` comme séparateur, non reconnu auparavant. Les gardes vérifient la racine et les deux séparateurs.
- **Divergence encore reproduite localement le 18 septembre** : `navigate_menu` visitait la racine et cherchait `Parc IT / Générer des équipements` comme un seul libellé ; `step_navigate_menu` visitait `/web#action=menu` et effectuait deux clics. Aucun appel de ce helper n’a été trouvé dans les versions de la base locale. La délégation à une seule implémentation évite que le prochain appel réintroduise ce défaut.
- **Données, exécution locale 146** : SIREN de huit chiffres refusé, trace `DonneeRefuseeError` dans `scenario_result`, capture `01-error.png`, mais `execution.error_message` vide. Les scénarios négatifs doivent garder leur intention ; les autres données restent contrôlées (voir [les tests de refus intentionnel](../../../tests/test_refus_champ_teste.py)).
- **Langue** : aucun contrôle automatique de concordance entre langue du compte et scénario n’a été trouvé dans les connecteurs et la bibliothèque de steps au 18 septembre. Ce point reste explicitement manuel ; aucune divergence de langue réelle n’est affirmée sans observation.

## Validation reproductible

```powershell
.\.venv-v1\Scripts\python.exe -m pytest tests/ -q -k "odoo_steps_login_delegue or refus_champ_teste or resolveur_evite_les_refus or transport_refus"
```

Les tests utilisent des doubles pour la navigation et les refus : ils protègent
le contrat du code, sans certifier une session Odoo réelle. La revue doit relever
pour chaque cible : projet, compte (sans secret), date, URL/surface, libellés observés,
et références de l’exécution et des captures lorsqu’elles existent.

**À approuver par le porteur** : ces quatre prérequis, la distinction des scénarios
négatifs et le contrôle humain de langue tant qu’aucune garde réelle n’est implémentée.
Aucun nouveau blocage automatique des exécutions n’est ajouté par cette checklist.
