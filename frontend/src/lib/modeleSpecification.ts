// Le MODÈLE de spécification (décision du porteur, 2026-07-24 — amendement §4.2 du brief).
//
// Le brief promettait à l'origine un « formulaire structuré, pas un champ libre ». Le document
// libre a été retenu — une spécification existante s'importe, elle ne se ressaisit pas — mais avec
// une contrepartie : **l'outil dit ce qu'il attend**. Sans repère, deux specs du même auteur
// n'ont pas la même forme, et la génération part d'une matière irrégulière.
//
// ⚠️ Ce modèle est une AIDE, pas un carcan : rien ne le vérifie, rien ne le rend obligatoire.
// Le forcer reviendrait à réintroduire le formulaire rigide qu'on a écarté.
//
// Chaque rubrique existe parce que son absence a coûté quelque chose de mesuré :
//   • les DONNÉES : sans valeurs plausibles, l'agent en invente — et les inventions violaient les
//     règles de saisie réelles (9ᵉ cause, faux « non conforme ») ;
//   • les RÈGLES : elles deviennent les assertions ; sans elles, un test « passe » sans rien
//     vérifier de sérieux ;
//   • le RÉSULTAT ATTENDU : c'est le verdict, et il doit être une phrase vérifiable, pas un
//     ressenti ;
//   • les CAS PARTICULIERS : ce sont les cas d'erreur et les cas limites qu'on pourra tirer de
//     la même spécification.

export const MODELE_SPECIFICATION = `## Ce qu'on veut tester

Décrivez en une ou deux phrases la fonctionnalité, du point de vue de l'utilisateur.
Exemple : « Un employé déclare un sinistre client depuis le portail, et le service
juridique doit le retrouver dans sa liste. »

## Le parcours

1. Point de départ (quelle page, connecté en tant que qui ?)
2. Ce que l'utilisateur fait
3. Ce qu'il fait ensuite
4. Comment il valide

## Les données utilisées

Donnez des valeurs plausibles pour les informations à saisir — c'est ce qui évite que
l'outil en invente. Précisez les formats imposés que vous connaissez.
Exemple : numéro de dossier à 7 chiffres, montant en euros, pièce jointe obligatoire.

## Les règles à respecter

Ce que l'application doit faire, et ce qu'elle doit refuser.
Exemple : « Le montant ne peut pas dépasser le plafond du contrat. »
Exemple : « Sans pièce jointe, la demande doit être refusée. »

## Le résultat attendu

Une phrase de verdict, vérifiable : qu'est-ce qui prouve que ça a marché ?
Exemple : « La demande apparaît dans la liste du service juridique, au statut À traiter. »

## Cas particuliers à couvrir (facultatif)

Ce qui devrait échouer, et les valeurs limites.
Exemple : « Un montant négatif est refusé. » / « Un dossier déjà clos ne peut plus être modifié. »
`

/** Le document est-il vide, ou n'est-il que le modèle non rempli ?
 *
 *  ⚠️ Utile pour ne pas laisser partir une génération sur un formulaire vierge : un modèle
 *  intact contient des consignes, pas une spécification — l'agent générerait un test à partir
 *  de « Décrivez en une ou deux phrases… ». Le distinguer d'un vrai document est donc une
 *  garde, pas une coquetterie. */
export function estModeleNonRempli(texte: string): boolean {
  const t = (texte || '').trim()
  if (!t) return true
  return t === MODELE_SPECIFICATION.trim()
}
