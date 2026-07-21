# Spécification — Création d'une demande de remboursement (Portail des Services)

## Contexte technique

Portail Odoo `custom_website` : `http://localhost:10017`. Modèle `helpdesk.ticket`.
Formulaire visé : `/remboursement/{id}`.

## Besoin

Vérifier qu'un utilisateur connecté peut créer une demande de remboursement en renseignant tous les champs
obligatoires, et que l'enregistrement est bien créé après soumission.

## Champs obligatoires (mesurés sur le formulaire réel)

- `partner_name`
- `partner_email`
- `name`
- `code_client1`
- `nom_client`
- `montant_remboursement`
- `motif` — valeurs : , avoir, double_regl_virement_errone, acompte_yes__no_prestation
- `nom_banque`
- `iban_client`
- `bic_client`
- `rib_client`
- `nom_prenom`

## Parcours

1. Se connecter au portail.
2. Ouvrir le formulaire `/remboursement/{id}`.
3. Renseigner tous les champs obligatoires ci-dessus avec des valeurs plausibles.
4. Soumettre le formulaire.
5. Vérifier qu'un nouvel enregistrement `helpdesk.ticket` a été créé.
