# Spécification — Validation du champ requis « Raison de la demande » (Portail des Services)

## Contexte technique

Module Odoo custom `custom_website`. Portail de développement : `http://localhost:10017`.
Modèle principal : `helpdesk.ticket` (module `helpdesk`), étendu par `custom_website`.

Ce besoin ne couvre **que la validation du champ obligatoire** du formulaire de demande de
matériel. Il ne re-teste pas le parcours complet de sélection d'accessoires.

### Champs concernés du modèle `helpdesk.ticket`

| Champ | Type | Description |
|---|---|---|
| `name` | char | Raison de la demande — **obligatoire**, jamais auto-rempli |
| `partner_name` | char | Demandeur (auto-rempli par le serveur) |
| `types_demandes` | selection | Type de demande (`new` = nouvel entrant) |
| `team_id` | many2one | Équipe « Demandes Matériel » (id 1), injectée côté serveur |

### Données existantes (réelles)

- Produit de référence : **`PC Portable HP`**, id Odoo **78**, catégorie **Ordinateurs**.

## Parcours d'accès (navigation réelle)

1. Authentification via `http://localhost:10017/web/login` (`input[name="login"]`,
   `input[name="password"]`, puis `Enter`). Odoo redirige vers `/web`.
2. Naviguer **explicitement** vers `http://localhost:10017/myservices`.
3. Cliquer l'onglet **« Ordinateurs »**, puis le produit **« PC Portable HP »**
   → `/description/78`.
4. Sur `/description/78`, cliquer le bouton **« Demander »** → affiche le formulaire de
   demande (`data-model_name="helpdesk.ticket"`).
5. Le bouton de soumission est `<a class="btn btn-primary s_website_form_send">Envoyer</a>`.
6. En cas de succès : redirection vers `/your-ticket-has-been-submitted`.
7. En cas d'échec de validation : la page reste sur le formulaire et affiche une erreur.

## Fonctionnalité : le champ « Raison de la demande » est obligatoire

**En tant qu'** employé connecté au Portail des Services
**Je veux** que le formulaire refuse une demande sans raison renseignée
**Afin de** ne jamais créer de ticket vide et inexploitable pour l'équipe Matériel

### Règle métier vérifiée

Le champ `name` est **obligatoire**. Une soumission sans ce champ **ne doit créer aucun
ticket** : le nombre total d'enregistrements du modèle `helpdesk.ticket` doit rester
**inchangé** après la tentative.

À l'inverse, une soumission avec `name` renseigné **crée exactement un** `helpdesk.ticket`
supplémentaire, avec le nom fourni.

### Scénarios attendus

- **[Nominal]** — `name` renseigné (« Demande test BDD - validation champ requis »),
  `types_demandes` = `new` → la page finale contient `/your-ticket-has-been-submitted`,
  et le nombre de `helpdesk.ticket` **augmente de 1**.
- **[Erreur]** — `name` laissé **vide** → **aucun** ticket supplémentaire créé (le nombre
  total de `helpdesk.ticket` **n'a pas augmenté**) et une erreur de validation est affichée
  dans le formulaire.
- **[Limite]** — `name` rempli avec une chaîne très longue (300 caractères) → le
  comportement doit rester cohérent : soit le ticket est créé avec le nom tronqué/complet,
  soit une erreur de validation s'affiche ; dans tous les cas, **aucun ticket partiel** ne
  doit subsister.

### Prérequis de comparaison

Le nombre d'enregistrements de `helpdesk.ticket` doit être **relevé avant** chaque action
afin de pouvoir vérifier son évolution après la soumission.
