# Spécification — Demande de Matériel via le Portail des Services (AXENEO)

## Contexte technique

Cette fonctionnalité est implémentée dans le module Odoo custom `custom_website`.
Le portail est accessible à l'URL `https://myservices.sapian.fr/` (production) ou
`http://localhost:10017` (développement).

Le modèle principal est `helpdesk.ticket` (module `helpdesk`) avec des champs étendus par `custom_website`.

### Modèle `helpdesk.ticket`

| Champ | Type | Description |
|---|---|---|
| `name` | char | Raison de la demande (obligatoire — doit être rempli dans le test) |
| `stage_id` | many2one | Étape du ticket — `Ouvert` (id=21) pour les nouvelles demandes (team_id=1 "Demandes Matériel") |
| `product` | many2one | Produit principal demandé (`product.template`) |
| `product_variant` | many2one | Variante du produit (`product.product`) |
| `product_accessory_ids` | many2many | Accessoires sélectionnés (`product.product`) |
| `fonction_materiel` | selection | Fonction du demandeur |
| `types_demandes` | selection | Type de demande (nouvel entrant / remplacement) |
| `partner_id` | many2one | Demandeur (lié à l'utilisateur connecté) |
| `type_commande` | selection | Type de commande (défaut=`'None'`) — ne pas confondre avec Python `None` |

### Modèle `product.accessory.relation`

Lie un produit principal à ses accessoires disponibles dans le portail.

| Champ | Type | Description |
|---|---|---|
| `product_id` | many2one | Produit principal |
| `accessory_id` | many2one | Accessoire |
| `is_accessory_checked` | boolean | Coché par défaut dans l'interface |

### Données existantes (exemples réels)

**Produit de référence pour les tests :**
- Nom : `PC Portable HP`
- ID Odoo : 78
- Catégorie produit : `Ordinateur` (id=7)
- Accessoires disponibles :
  - `BITEN2` (coché par défaut = True)
  - `Port TV` (coché par défaut = True)

**Autre produit avec accessoires :**
- Nom : `PC Portable HP 14" (VIP)`
- ID Odoo : 104
- Accessoires : `BITEN2`, `Port TV`, `HP 16Go DDR5 5600 SODIMM Memory`, `BISAP 6` (tous cochés par défaut)

---

## Fonctionnalité : Demande de Matériel

**En tant qu'** employé connecté au Portail des Services  
**Je veux** soumettre une demande de matériel informatique  
**Afin d'** obtenir l'équipement nécessaire à mon activité

### Flux utilisateur dans l'interface portail (navigation réelle)

URL d'entrée (dev) : `http://localhost:10017/myservices`

**Important** : après login via `/web/login`, Odoo redirige vers `/web` (backend).
Il faut naviguer explicitement vers `/myservices` après authentification.
Ne pas utiliser `/shop` (c'est la Boutique e-commerce, pas les demandes de matériel).

Chemin de navigation étape par étape :
1. `GET http://localhost:10017/web/login` — formulaire de connexion
2. Remplir `input[name="login"]` et `input[name="password"]`, puis `Enter`
3. Après redirection vers `/web`, aller sur `http://localhost:10017/myservices`
4. La page `/myservices` affiche 4 onglets : **Téléphonie**, **Périphériques**, **Ordinateurs**, **Accessoires**
5. Cliquer sur l'onglet correspondant à la catégorie du produit (ex: **"Ordinateurs"**)
6. Cliquer sur le nom du produit (ex: `PC Portable HP`) → redirige vers `/description/{id}`
7. Sur `/description/{id}` :
   - Si le produit a des accessoires : bouton `<a class="btn btn-primary buttonRequestWithAccessories" id="{id}">Demander</a>`
   - Ce bouton déclenche un POST JavaScript vers `/product/{id}/accessories` avec les `accessory_ids` sélectionnés
   - Si pas d'accessoires : lien `<a href="/formulaire/{product_id}">Demander</a>`
8. Le POST `/product/{id}/accessories` rend le template `custom_website.formulaire_portail_service1` avec le formulaire `data-model_name="helpdesk.ticket"`
9. Le formulaire contient :
   - Champ `name` (Raison de la demande) — **obligatoire, doit être rempli par le test** (`data-fill-with="undefined"` = pas d'auto-remplissage)
   - Champ `partner_name` (auto-rempli = nom de l'utilisateur)
   - Champ `partner_email` (auto-rempli = email de l'utilisateur)
   - Champ `types_demandes` (sélection : "nouvel entrant" / "remplacement matériel")
   - Champ `fonction_materiel` (sélection)
   - Checkbox `request_for_other` (boolean, visible) et `is_not_adr_agence` (boolean, visible)
   - Checkbox `product_accessory_ids` (cachées `style="display:none"`, pré-cochées `checked="checked"`)
   - Bouton submit : `<a class="btn btn-primary s_website_form_send">Envoyer</a>`
10. À la soumission : le formulaire POST vers `/website/form/` et crée le `helpdesk.ticket`
11. En cas de succès : redirection vers `/your-ticket-has-been-submitted`
12. En cas d'échec : la page reste sur le formulaire avec des erreurs

**Modèle créé** : `helpdesk.ticket` (team_id=1 "Demandes Matériel")

### Règles pour les steps de formulaire

1. **Toujours remplir le champ `name`** ("Raison de la demande") avant de soumettre — il est obligatoire et non auto-rempli
2. **Ne jamais sélectionner les checkboxes des accessoires sur la page formulaire** : elles sont cachées et pré-cochées. Les sélectionner via `input[type='checkbox']` cocherait les booléens visibles (`request_for_other`, `is_not_adr_agence`) et casserait le formulaire
3. **Pour identifier le ticket créé** : utiliser un filtrage par `id > <max_id_avant_test>` pour éviter de confondre avec d'anciens tickets
4. **Stage attendu** : le ticket est créé avec `stage_id = Ouvert` (id=21, pas "Nouveau" id=1)

### Vérifications en base après soumission

- Un enregistrement `helpdesk.ticket` est créé avec :
  - `stage_id.name = 'Ouvert'` (étape par défaut pour la team "Demandes Matériel")
  - `product.name = <nom_du_produit>` (produit principal, stocké dans le champ `product`)
  - `partner_id` = utilisateur connecté

---

## Scénarios à générer

### Nominal — Demande avec un ordinateur portable et accessoires par défaut

- Pré-condition : le produit `PC Portable HP` (id=78) existe dans `product.template` (catégorie `Ordinateur` id=7)
- Action :
  1. Naviguer vers `/en/myservices`
  2. Cliquer sur l'onglet **"Ordinateurs"**
  3. Sélectionner `PC Portable HP` dans la liste
  4. Cliquer sur **"Demander"** (bouton `.buttonRequestWithAccessories` car accessoires existent)
  5. **Remplir le champ `name`** (Raison de la demande) avec une valeur de test
  6. Cliquer "Envoyer" (`.s_website_form_send`)
- Résultat attendu :
  - Un `helpdesk.ticket` est créé avec `stage_id = Ouvert` et `product.name = 'PC Portable HP'`
  - Aucun ticket en double pour la même raison

### Erreur — Tentative de soumission sans sélectionner de produit

- Action :
  1. Naviguer vers `/en/myservices`
  2. Cliquer sur l'onglet **"Ordinateurs"**
  3. Accéder directement à l'URL `/en/product/0/accessories` (ID 0 = invalide)
  4. Cliquer "Envoyer"
- Résultat attendu :
  - Aucun `helpdesk.ticket` n'est créé (vérifier que le nombre total n'a pas augmenté)
  - Une erreur de validation est affichée (`.alert-danger` ou équivalent)

### Limite — Demande avec produit ayant le maximum d'accessoires

- Note : Ce scénario peut révéler un bug métier (le produit `PC Portable HP 14" (VIP)` avec 4 accessoires peut ne pas créer de ticket). Si le formulaire ne crée pas de ticket, c'est un problème Odoo à corriger dans le module, pas un bug de test.
- Pré-condition : le produit `PC Portable HP 14" (VIP)` (id=104) existe dans `product.template` avec 4 accessoires
- Action :
  1. Naviguer vers `/en/myservices`
  2. Cliquer sur l'onglet **"Ordinateurs"**
  3. Sélectionner `PC Portable HP 14" (VIP)` dans la liste
  4. Cliquer sur **"Demander"**
  5. **Remplir le champ `name`** (Raison de la demande) avec une valeur de test
  6. Cliquer "Envoyer"
- Résultat attendu :
  - Un `helpdesk.ticket` est créé avec `stage_id = Ouvert`
  - Les accessoires sont associés (déjà pré-cochés dans le formulaire après le POST)
  - Aucune erreur de limite ("limite" ou "maximum" dans les messages d'erreur)

---

## Contraintes importantes pour la génération de tests

1. **Module à vérifier** : `custom_website` (pas `website_portal`, pas `purchase`)
2. **Modèle cible** : `helpdesk.ticket` (pas `equipment.order` — la gestion du parc IT est backend)
3. **Pas de step de vérification du modèle `equipment.order`** : ce modèle n'est pas utilisé par le portail
4. **URL d'entrée pour les tests UI** : `http://localhost:10017/myservices` — PAS `/shop`, PAS juste `http://localhost:10017`
5. **Séquence de navigation obligatoire** : login → goto `/myservices` → onglet catégorie → produit → `/description/{id}` → bouton "Demander" → `/product/{id}/accessories` (POST JS) ou `/formulaire/{id}` (GET)
6. **Onglets sur /myservices** : "Téléphonie", "Périphériques", "Ordinateurs", "Accessoires" (textes exacts)
7. **Teardown** : les enregistrements `helpdesk.ticket` créés doivent être supprimés via `register_created(context, 'helpdesk.ticket', id)`
8. **Ne pas utiliser `equipment.order`** : le portail crée exclusivement des `helpdesk.ticket` (team "Demandes Matériel")
9. **Le formulaire utilise `data-model_name="helpdesk.ticket"`** : le ticket créé a `stage_id = Ouvert` (id=21), pas "Nouveau" (id=1)
10. **OdooRPC API** : `search()` retourne une liste d'IDs — toujours utiliser `browse(id).read([field])` pour lire les champs, jamais `.read()` directement sur le résultat de `search()`
11. **Champ `name` obligatoire** : toujours remplir `name` avec une valeur de test avant de soumettre le formulaire
12. **Accessoires déjà pré-cochés** : ne PAS sélectionner les accessoires sur la page formulaire (ils sont cachés et pré-remplis). Les sélectionner tous via `input[type='checkbox']` cocherait les booléens visibles du formulaire
13. **Identifier les nouveaux tickets** : enregistrer le max ID de `helpdesk.ticket` avant l'action, puis filtrer par `("id", ">", max_id)` pour éviter les faux positifs avec d'anciens tickets
14. **Stage "Refusé" possible** : s'il existe d'anciens tickets pour le même produit avec `stage_id = "Refusé"`, ne pas les confondre avec le nouveau ticket créé par le test
