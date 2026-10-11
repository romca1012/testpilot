# Banc d'agents web — 2026-10-11 — base-6 (lot VH-06) et base-7 (lots VH-06 + VH-07, bac à sable) comparées

Rapports bruts : `banc-agents-2026-10-11-base-6.md` (commit `8839d98`, bac à sable éteint) et `banc-agents-2026-10-11-base-7.md`
(commit `fa70e49`, `--bac-a-sable`). 30 essais sur 30 chacune, mode strict, réparation Sonnet 4.6 à 2 tentatives, mêmes 10 cas,
même modèle de génération (`claude-sonnet-4-6`). Plafonds 5,50 $ et 7 $ ; dépensé 4,61 $ et 4,98 $.

## Indicateurs (30 essais, 10 cas × 3) — mêmes formules pour toutes les campagnes

| Indicateur | base-3 | base-4 | base-5 (lot 4) | base-6 (+ lot 6) | **base-7 (+ lot 7)** |
|---|---|---|---|---|---|
| Faux verts | 0/21 | 0/21 | 0/21 | 0/21 | **0/25** |
| Faux rouges | 6/23 = 26 % | 2/19 = 11 % | 2/23 = 9 % | 1/19 = 5 % | **0/23** |
| Générations abouties | 28/30 | 28/30 | 29/30 | 27/30 | **28/30** |
| Essais qui s'exécutent sans erreur technique | 23/30 | 19/30 | 23/30 | 19/30 | **23/30** |
| Essais justes partout (saine et défauts) | 17/30 | 17/30 | 21/30 | 18/30 | **23/30** |
| Cas justes aux trois essais | 3/10 | 2/10 | 5/10 | 4/10 | **6/10** |
| Tests sans aucun step écrit à la main | — | — | — | 25/27 | **26/28** |
| Coût des générations (par génération) | 3,01 $ (0,100) | — (0,132) | 4,04 $ (0,135) | 3,87 $ (0,129) | **4,98 $ (0,166)** |
| Coût des réparations | 0,41 $ | — | 0,53 $ | 0,74 $ | **0 $** (toutes refusées par le circuit du produit) |

Échantillon petit : les intervalles de Wilson se recouvrent d'une campagne à l'autre. Ce qui sort du bruit de façon plausible :
la disparition des faux rouges depuis base-3 (6/23 → 0/23) et le passage de `panier_total_tva` de 0/3 à 3/3.

## Lecture

- **Le lot 6 seul (base-6) n'améliore pas les indicateurs.** Il atteint son but direct — 25 tests sur 27 n'ont plus aucun step
  écrit à la main, contre du code libre dans presque tous les essais non justes de base-5 — mais les erreurs techniques ne
  baissent pas (19/30 contre 23/30, dans le bruit). Les échecs se sont DÉPLACÉS du code libre vers l'usage des steps : la forme
  de la réponse de l'oracle et le libellé exact à côté d'une valeur ne sont pas connus de l'agent au moment d'écrire.
- **Le lot 7 (base-7) donne le gain attendu, sur le cas qui l'avait désigné.** `panier_total_tva` : 0/3 en base-5 et base-6
  (champ cherché sur la mauvaise page), 3/3 en base-7. `connexion_valide` 2/3 → 3/3, `client_creation_nom_limite` 1/3 → 3/3.
  Meilleure campagne depuis le début sur les essais justes partout (23/30) et sur les cas justes aux trois essais (6/10).
- **Faux verts : 0/25, faux rouges : 0/23.** Sur les sept campagnes comparables (base-2 à base-7), 0 faux vert sur 131 jeux
  concluants ; versions différentes de l'outil, donc pas un seul échantillon — mais aucune n'en a produit.
- **Coût : + 0,037 $ par génération avec le bac à sable** (0,129 → 0,166 $), soit + 29 %. Un essai n'appelle pas le modèle, mais
  chaque essai est un tour d'agent. Très loin du plafond du §9 (1 € par cas). Aucune réparation payée en base-7.
- **Gardes d'écriture** : 13 refus en base-6 (`LITTERAL_NON_OBSERVE` ×12, `ECHAPPEMENT_LITTERAL` ×1 — la garde du lot 6 a servi
  une fois), 11 en base-7. Aucun `VALEUR_TIREE_DE_L_ESSAI` : sur ce banc, l'agent n'a pas tenté de recopier une donnée vue
  à l'essai (ce qui ne prouve pas que la garde tient — elle n'a pas été sollicitée).

## Ce qui reste (7 essais non justes en base-7)

| Cas | Essais | Cause mesurée |
|---|---|---|
| `commande_persistance_serveur` | 3/3 | l'agent ne connaît pas la FORME de la réponse de l'oracle : « le champ "panier" vaut "{}" » sur un objet (×2) ; libellé cherché « CMD-[0-9]+ » au lieu de « Numéro de commande » (×1) |
| `panier_remise_arrondi` | 2/3 | génération sans essai à blanc passé (déjà 2/3 en base-6, 1/3 en base-5) |
| `commande_confirmation` | 1/3 | « l'oracle renvoie N résultats » sur une réponse qui est un objet |
| `client_creation_nom_requis` | 1/3 | tableau « clients » introuvable par ce nom sur `/clients` |

Quatre de ces sept essais tiennent à l'oracle : sa requête est déclarée, mais ni la forme de sa réponse ni ses clés ne sont
montrées à l'agent. C'est la suite logique (lot 8 : oracles tracés) — montrer à l'agent un exemple de réponse de chaque
requête d'oracle, comme l'annuaire lui montre les pages.

Relevé en base-6, à corriger avec le lot 8 : « le champ … de l'oracle … compte N élément(s) » sur un objet sort encore
`non_conforme` (constat échoué) au lieu d'un test mal posé — c'est le seul faux rouge de base-6.

## Limites de cette mesure

- Banc interne : une petite application écrite par nous, dix cas, trente essais. Elle compare deux versions à conditions
  égales ; elle ne prouve rien sur une application réelle (lot 10 : jeu mis de côté, applications jamais vues).
- Le bac à sable n'a été mesuré QUE sur ce banc, dont la remise à zéro est fiable par construction.
- La garde `VALEUR_TIREE_DE_L_ESSAI` et le point de vigilance `valeur_vue_a_l_essai` n'ont pas été exercés par ces campagnes.
