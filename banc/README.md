# Banc de mesure de la fiabilité du verdict (lot 04)

Une instance Odoo de RÉFÉRENCE jetable, dont on CONNAÎT les défauts : on peut alors affirmer qu'un statut est vrai (ou
faux) au lieu de le croire. Le banc rend **I1 (faux PASSED)** et **I5 (blocage bien attribué)** mesurables, donc chaque
lot suivant prouvable.

⚠️ **Jamais sur une instance client.** Les défauts du module `tp_bugs_injectes` sont faits pour se tromper ; le script
de mesure refuse tout hôte qui n'est pas local.

## Démarrer

```bash
scripts/banc_init.sh 17.0              # ou .\scripts\banc_init.ps1 -Version 17.0 sous Windows ; ≈ 7 min la première fois
python scripts/banc_mesure.py --version 17.0     # mode figé : coût nul, aucun LLM (≈ 12 min)
docker compose -f compose.banc.yml down -v       # effacer le banc
```

Versions : `16.0`, `17.0`, `18.0` (Community, données de démo, images figées **par digest** dans `banc/images.env`).
Port dédié : `18069` (`BANC_PORT`), lié à `127.0.0.1` seulement. Comptes : `admin / admin`, `banc_commercial`
(Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur + Stock + Facturation) — mots de passe jetables.

## Ce que contient le banc

| Chemin | Rôle |
|---|---|
| `compose.banc.yml`, `banc/images.env` | PostgreSQL + Odoo, images par digest, volume jetable |
| `scripts/banc_init.sh` / `.ps1` | crée la base `banc`, installe les modules de D9 et `tp_bugs_injectes`, `odoo neutralize`, comptes, `fr_FR` |
| `banc/odoo_addons/tp_bugs_injectes/` | 7 défauts activables un par un (`ir.config_parameter` `tp_bug.<code>` = `1`), inactifs par défaut, avec leurs tests Odoo |
| `banc/cas_figes/` | 15 cas écrits à la main (feature + steps), tenant lieu de versions approuvées — mode `figé` |
| `specs/banc/*.md` | les 15 specs correspondantes — mode `génération` |
| `specs/banc/attendus.yaml` | le statut attendu de chaque cas, instance saine / sous chaque défaut / sous chaque panne — **écrit par un humain** |
| `scripts/banc_mesure.py` | rejoue les cas et calcule I1–I6 ; sortie Markdown + JSON dans `docs/mesures/` |
| `scripts/banc_projet.py` | crée (idempotent) le projet TestPilot « Banc Odoo <version> » et l'explore |
| `scripts/banc_generation.py` | mode `génération` (LLM, plafond de coût obligatoire) |
| `.github/workflows/banc.yml` | nocturne + manuel + PR touchant le banc ; matrice 16.0 / 17.0 / 18.0 ; mode figé seulement |

## Les défauts et les pannes

| Défaut (`tp_bug.<code>`) | Effet |
|---|---|
| `vente_sans_livraison` | confirmer un devis ne crée pas de bon de livraison |
| `total_faux` | `amount_total` d'une commande de vente décalé de 1 % |
| `client_non_requis` | `partner_id` optionnel sur la commande de vente |
| `etat_bloque` | `action_confirm` laisse l'état `draft` sans erreur |
| `facture_non_postee` | la validation de facture ne passe pas en `posted` |
| `droit_trop_large` | `banc_commercial` peut supprimer une commande confirmée |
| `message_absent` | aucun message d'erreur visible sur un champ requis vide (masqué côté interface) |

| Panne | Mise en place | Attendu |
|---|---|---|
| `odoo_arrete` | `docker compose stop odoo` | `blocked` |
| `mauvais_mot_de_passe` | mot de passe erroné pour le compte du projet | `blocked` |
| `module_desinstalle` | état du module `crm` passé à `uninstalled` (le step de Contexte lit cet état ; pas de désinstallation physique — voir le rapport) | `blocked` |

## Règles de mesure

- **« Non mesuré » n'est pas « zéro »** : un indicateur sans observation vaut `non mesuré`.
- **Les attendus ne se déduisent jamais d'un run.** Si un run contredit un attendu, c'est un constat à instruire.
- **Une mesure ne modifie jamais `data/`** : elle tourne sur un dossier de données jetable (chemin dans la sortie).
- **Ne pas lancer la suite pytest et une mesure en même temps** sur le même poste.
- Ne jamais publier les indicateurs d'une mesure partielle (`--configs` est réservé à la mise au point).

## Constats du banc sur la bibliothèque de steps (Odoo 17.0 Community)

Le banc a déjà trouvé des limites de la bibliothèque, consignées dans le rapport du lot 04 : `je navigue vers le menu
Odoo` ouvre `/web#action=menu`, qui n'existe pas sur 17.0 Community ; les steps de lecture `le champ … est égal à`
échouent sur une facture (`browse().read()` d'odoorpc et sérialisation de la réponse Odoo 17).

## Application web locale à défauts injectables (banc d'agents web, lot Q2-b)

Le banc Odoo ci-dessus ne sert que le connecteur `odoo`. Pour le connecteur `web` générique, `banc/app_web/` est une
petite boutique en mémoire (connexion, produits + recherche, clients, panier avec TVA 18 % et remise, commandes) dont on
connaît le comportement SAIN et six défauts activables un par un : `total_faux`, `validation_absente`,
`message_erreur_absent`, `etat_non_enregistre`, `filtre_ignore`, `login_accepte_tout` (`banc/app_web/defauts.py`).
But : mesurer si un test GÉNÉRÉ détecte un défaut (faux vert) sans accuser l'application saine (faux rouge).

```bash
python -m banc.app_web.serveur                          # application saine ; affiche l'URL (port libre, 127.0.0.1)
python -m banc.app_web.serveur --defauts total_faux     # ou TP_DEFAUTS=total_faux,filtre_ignore
curl -X POST http://127.0.0.1:<port>/__reset            # état remis à zéro (les défauts restent)
curl http://127.0.0.1:<port>/__etat                     # vérification INDÉPENDANTE : commandes, panier, enregistrements
curl -X POST http://127.0.0.1:<port>/__defauts -d '{"defauts": ["filtre_ignore"]}'   # bascule à chaud
```

- **Loopback uniquement** : tout hôte d'écoute non bouclage est refusé au démarrage ; les routes `/__*` refusent un
  client ou un en-tête `Host` non bouclage. `/__etat` ne révèle jamais les défauts actifs.
- Compte de test fixe et jetable, déclaré dans `specs/banc_local/apps.yaml` (jamais un secret réel).
- Les 10 specs sont dans `specs/banc_local/`, les attendus dans `specs/banc_local/attendus.yaml`.
- **Règle d'honnêteté des attendus** : `attendus.yaml` est écrit AVANT tout run contre l'application, chaque statut est
  justifié par la lecture de la spec et de la description du défaut, et il n'est JAMAIS modifié après coup pour faire
  passer une mesure. Un run qui contredit un attendu est un constat à instruire (le cas généré, le défaut ou le
  verdict) ; si un défaut n'est détecté par aucune spec, on AJOUTE la spec qui le couvre, on ne retire pas le défaut.
- Tests de l'application : `python -m pytest -q tests/test_app_banc_web.py` (HTTP réel sur loopback, aucun navigateur).

## Orchestrateur du banc d'agents web (lot Q2-d)

`scripts/banc_agents.py` mesure si un test GÉNÉRÉ détecte un défaut de l'application locale ci-dessus sans accuser l'application
saine. Pour chaque spec de `specs/banc_local/` et chaque essai (k) : une génération sur l'application saine (seul poste de coût
LLM), puis le MÊME test (empreintes sha256 consignées) joué sur la saine et sur chaque défaut listé par `attendus.yaml`,
l'application étant réinitialisée entre deux jeux. Sortie : `docs/mesures/banc-agents-<date>.{md,json}` (pass@1, pass^k, faux
verts, faux rouges, non concluants à part, coût en USD et EUR, intervalles de Wilson, « non mesuré » quand n = 0).

```bash
python scripts/banc_agents.py --a-sec                              # défaut : valide la configuration et affiche le budget ; aucun LLM, aucun navigateur
python scripts/banc_agents.py --reel --plafond-cout 5 --essais 3   # ⚠️ LLM + navigateur RÉELS : accord du porteur, jamais en CI
```

- `--reel` exige `--plafond-cout` (dollars), refuse tout hôte non bouclage et `ODOO_ENV=prod`, et affiche le budget avant de commencer.
  Le plafond est appliqué EN AMONT (arrêt avant l'essai qui le dépasserait, code de sortie 3).
- Un attendu incohérent (cas sans attendu sur la saine, code de défaut inconnu, polarité impossible) est REFUSÉ au chargement,
  jamais ignoré en silence. `attendus.yaml` n'est jamais modifié pour faire passer une mesure.
- Codes de sortie : 0 rien à signaler ; 1 au moins un faux vert ; 2 configuration invalide ; 3 campagne incomplète, porte « faux
  verts » non mesurée ou test joué différent du test généré.
- Estimation d'une campagne réelle (10 cas × k = 3 = 30 générations) : ≈ 4,5 $ avec 0,15 $ par génération. Cette valeur est une borne
  prudente tirée des campagnes ODOO (0,100 à 0,124 $ par cas, `docs/mesures/banc-*-generation*.json`) : le coût sur le connecteur
  web n'est PAS mesuré.
- Tests : `python -m pytest -q tests/test_banc_agents.py` (doublures uniquement ; HTTP sur bouclage pour l'application locale).
