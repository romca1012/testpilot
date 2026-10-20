"""Les pages HTML de l'application web du banc (lot Q2-b).

Pourquoi ce soin. Le test sera généré par un agent qui INSPECTE la page comme sur un vrai site : il faut donc des
`<label>` reliés à leurs champs, des rôles accessibles (`navigation`, `main`, `alert`, `status`), des tableaux avec
légende et en-têtes, des messages d'erreur DANS le DOM. Les formulaires portent `novalidate` malgré `required` : sans
cela le navigateur bloquerait lui-même la soumission d'un champ vide et le serveur ne verrait jamais le cas (le défaut
`validation_absente` serait alors inobservable) — beaucoup de sites font ce choix pour afficher leurs propres messages.
La longueur maximale n'est PAS portée par `maxlength` (le navigateur tronquerait la saisie et le refus ne se
produirait jamais) : elle figure dans un texte d'aide relié au champ.

Fonctions pures : elles reçoivent des données déjà prêtes et rendent du HTML ; aucune ne lit l'état serveur.
"""

from __future__ import annotations

from html import escape as _e
from typing import Iterable

from .calcul import (
    AGE_MAX,
    NOM_CLIENT_MAX,
    QUANTITE_MAX,
    TAUX_TVA,
    Produit,
    formater_montant,
    formater_pourcentage,
)

_STYLE = """
body{font-family:system-ui,sans-serif;margin:0;color:#1d2330;background:#f6f7f9}
header{background:#1d2330;color:#fff;padding:.6rem 1.2rem;display:flex;gap:1.2rem;align-items:center;flex-wrap:wrap}
header a{color:#fff}
header .session{margin-left:auto}
main{max-width:52rem;margin:1.2rem auto;padding:0 1rem}
table{border-collapse:collapse;width:100%;background:#fff;margin:1rem 0}
caption{text-align:left;font-weight:600;padding:.4rem 0}
th,td{border:1px solid #cfd4dc;padding:.4rem .6rem;text-align:left}
.champ{margin:.8rem 0}
label{display:block;font-weight:600;margin-bottom:.2rem}
input{padding:.35rem;min-width:14rem}
input[type=number]{min-width:5rem;width:5rem}
button{padding:.4rem .9rem}
.erreur{color:#a1180f;font-weight:600}
.succes{color:#0b6b2c;font-weight:600}
.aide{color:#5a6475;font-size:.9rem}
.sr-only{position:absolute;left:-9999px}
"""

_NAV = (
    ("/produits", "Produits"),
    ("/clients", "Clients"),
    ("/panier", "Panier"),
    ("/commandes", "Commandes"),
    ("/acces", "Contrôle d'accès"),
)


def _page(titre: str, corps: str, *, identifiant: str | None = None) -> str:
    """Le gabarit commun : titre de document, navigation (si connecté), zone principale."""
    if identifiant is None:
        entete = '<header><span>Boutique de test</span></header>'
    else:
        liens = "".join(f'<a href="{href}">{_e(nom)}</a>' for href, nom in _NAV)
        entete = (
            f'<header><span>Boutique de test</span><nav aria-label="Navigation principale">{liens}</nav>'
            f'<p class="session">Connecté en tant que <strong>{_e(identifiant)}</strong></p>'
            '<form method="post" action="/deconnexion"><button type="submit">Se déconnecter</button></form></header>'
        )
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(titre)} — Boutique de test</title><style>{_STYLE}</style></head>"
        f"<body>{entete}<main>{corps}</main></body></html>"
    )


def connexion(erreur: str | None = None, identifiant: str = "") -> str:
    alerte = f'<p id="erreur-connexion" class="erreur" role="alert">{_e(erreur)}</p>' if erreur else ""
    corps = (
        "<h1>Connexion</h1>"
        f"{alerte}"
        '<form method="post" action="/connexion" novalidate>'
        '<div class="champ"><label for="identifiant">Identifiant</label>'
        f'<input type="text" id="identifiant" name="identifiant" autocomplete="username" required '
        f'aria-required="true" value="{_e(identifiant)}"></div>'
        '<div class="champ"><label for="mot-de-passe">Mot de passe</label>'
        '<input type="password" id="mot-de-passe" name="mot_de_passe" autocomplete="current-password" required '
        'aria-required="true"></div>'
        '<button type="submit">Se connecter</button></form>'
    )
    return _page("Connexion", corps)


def produits(identifiant: str, trouves: Iterable[Produit], recherche: str, erreur: str | None = None) -> str:
    trouves = list(trouves)
    alerte = f'<p class="erreur" role="alert">{_e(erreur)}</p>' if erreur else ""
    lignes = "".join(
        f'<tr><th scope="row">{_e(p.nom)}</th><td>{formater_montant(p.prix)}</td><td>'
        '<form method="post" action="/panier/ajouter" novalidate>'
        f'<input type="hidden" name="produit" value="{p.ident}">'
        f'<label class="sr-only" for="qte-{p.ident}">Quantité de {_e(p.nom)}</label>'
        f'<input type="number" id="qte-{p.ident}" name="quantite" value="1" min="1" max="{QUANTITE_MAX}">'
        f'<button type="submit" aria-label="Ajouter {_e(p.nom)} au panier">Ajouter</button></form></td></tr>'
        for p in trouves
    )
    if trouves:
        resume = f'<p id="compteur" role="status">{len(trouves)} produit{"s" if len(trouves) > 1 else ""} affiché{"s" if len(trouves) > 1 else ""}</p>'
        tableau = (
            '<table><caption>Liste des produits</caption><thead><tr><th scope="col">Produit</th>'
            '<th scope="col">Prix unitaire</th><th scope="col">Panier</th></tr></thead>'
            f"<tbody>{lignes}</tbody></table>"
        )
    else:
        resume = f'<p id="compteur" role="status">Aucun produit ne correspond à « {_e(recherche)} ».</p>'
        tableau = ""
    corps = (
        "<h1>Produits</h1>"
        f"{alerte}"
        '<form role="search" method="get" action="/produits">'
        '<div class="champ"><label for="recherche">Rechercher un produit</label>'
        f'<input type="search" id="recherche" name="q" value="{_e(recherche)}"></div>'
        '<button type="submit">Rechercher</button></form>'
        f"{resume}{tableau}"
    )
    return _page("Produits", corps, identifiant=identifiant)


def panier(
    identifiant: str,
    lignes: list[dict],
    totaux: dict,
    remise_saisie: str,
    erreur: str | None = None,
) -> str:
    """`lignes` : dicts {ident, nom, prix, quantite, total} ; `totaux` : dict de `Decimal` déjà finaux (défaut inclus)."""
    alerte = f'<p class="erreur" role="alert">{_e(erreur)}</p>' if erreur else ""
    vide = '<p id="panier-vide" role="status">Votre panier est vide.</p>' if not lignes else ""
    if lignes:
        corps_lignes = "".join(
            f'<tr><th scope="row">{_e(ligne["nom"])}</th><td>{formater_montant(ligne["prix"])}</td><td>'
            f'<label class="sr-only" for="qte-{ligne["ident"]}">Quantité de {_e(ligne["nom"])}</label>'
            f'<input type="number" id="qte-{ligne["ident"]}" name="quantite_{ligne["ident"]}" value="{ligne["quantite"]}" '
            f'min="0" max="{QUANTITE_MAX}"></td><td>{formater_montant(ligne["total"])}</td></tr>'
            for ligne in lignes
        )
        tableau = (
            '<table><caption>Contenu du panier</caption><thead><tr><th scope="col">Produit</th>'
            '<th scope="col">Prix unitaire</th><th scope="col">Quantité</th><th scope="col">Total de la ligne</th>'
            f"</tr></thead><tbody>{corps_lignes}</tbody></table>"
        )
    else:
        tableau = ""
    pct = formater_pourcentage(totaux["remise_pct"])
    recap = (
        '<table><caption>Récapitulatif</caption><tbody>'
        f'<tr><th scope="row">Sous-total HT</th><td>{formater_montant(totaux["sous_total"])}</td></tr>'
        f'<tr><th scope="row">Remise ({pct} %)</th><td>{formater_montant(totaux["remise"])}</td></tr>'
        f'<tr><th scope="row">Total HT après remise</th><td>{formater_montant(totaux["total_ht"])}</td></tr>'
        f'<tr><th scope="row">TVA ({formater_pourcentage(TAUX_TVA)} %)</th><td>{formater_montant(totaux["tva"])}</td></tr>'
        f'<tr><th scope="row">Total TTC</th><td>{formater_montant(totaux["total_ttc"])}</td></tr>'
        "</tbody></table>"
    )
    corps = (
        "<h1>Panier</h1>"
        f"{alerte}{vide}"
        '<form method="post" action="/panier/mettre-a-jour" novalidate>'
        f"{tableau}"
        '<div class="champ"><label for="remise">Remise (%)</label>'
        f'<input type="text" id="remise" name="remise" inputmode="decimal" value="{_e(remise_saisie)}"></div>'
        '<button type="submit">Recalculer</button></form>'
        f"{recap}"
        '<form method="post" action="/commande/confirmer">'
        '<button type="submit">Valider la commande</button></form>'
    )
    return _page("Panier", corps, identifiant=identifiant)


def clients(identifiant: str, enregistrements: list[dict]) -> str:
    if enregistrements:
        lignes = "".join(
            f'<tr><th scope="row">{_e(c["nom"])}</th><td>{_e(c["ville"])}</td></tr>' for c in enregistrements
        )
        liste = (
            '<table><caption>Liste des clients</caption><thead><tr><th scope="col">Nom</th>'
            f'<th scope="col">Ville</th></tr></thead><tbody>{lignes}</tbody></table>'
        )
    else:
        liste = '<p id="aucun-client" role="status">Aucun client.</p>'
    corps = '<h1>Clients</h1><p><a href="/clients/nouveau">Nouveau client</a></p>' + liste
    return _page("Clients", corps, identifiant=identifiant)


def client_formulaire(
    identifiant: str,
    nom: str = "",
    ville: str = "",
    erreur_nom: str | None = None,
    *,
    afficher_message: bool = True,
) -> str:
    """`afficher_message=False` : le refus a eu lieu mais le message (et le marquage d'erreur) est retiré — défaut
    `message_erreur_absent`. Le formulaire est alors réaffiché tel quel, sans aucun élément d'erreur."""
    refuse = erreur_nom is not None and afficher_message
    decrit = "aide-nom erreur-nom" if refuse else "aide-nom"
    invalide = ' aria-invalid="true"' if refuse else ""
    message = f'<p id="erreur-nom" class="erreur" role="alert">{_e(erreur_nom)}</p>' if refuse else ""
    corps = (
        "<h1>Nouveau client</h1>"
        '<form method="post" action="/clients/nouveau" novalidate>'
        '<div class="champ"><label for="nom">Nom du client</label>'
        f'<input type="text" id="nom" name="nom" required aria-required="true" aria-describedby="{decrit}"'
        f'{invalide} value="{_e(nom)}">'
        f'<small id="aide-nom" class="aide">Obligatoire, {NOM_CLIENT_MAX} caractères au maximum.</small>{message}</div>'
        '<div class="champ"><label for="ville">Ville</label>'
        f'<input type="text" id="ville" name="ville" value="{_e(ville)}"></div>'
        '<button type="submit">Enregistrer</button></form>'
    )
    return _page("Nouveau client", corps, identifiant=identifiant)


def acces_formulaire(identifiant: str, client: str = "", age: str = "", erreur: str | None = None) -> str:
    """Contrôle d'accès (IT-3e) : un client, un âge ; la réponse est donnée sur la page suivante."""
    decrit = "aide-age erreur-age" if erreur else "aide-age"
    invalide = ' aria-invalid="true"' if erreur else ""
    message = f'<p id="erreur-age" class="erreur" role="alert">{_e(erreur)}</p>' if erreur else ""
    corps = (
        "<h1>Contrôle d'accès</h1>"
        '<form method="post" action="/acces" novalidate>'
        '<div class="champ"><label for="client">Nom du client</label>'
        f'<input type="text" id="client" name="client" value="{_e(client)}"></div>'
        '<div class="champ"><label for="age">Âge</label>'
        f'<input type="text" id="age" name="age" inputmode="numeric" aria-describedby="{decrit}"{invalide} value="{_e(age)}">'
        f'<small id="aide-age" class="aide">En années, de 0 à {AGE_MAX}.</small>{message}</div>'
        '<button type="submit">Vérifier l\'accès</button></form>'
    )
    return _page("Contrôle d'accès", corps, identifiant=identifiant)


def acces_resultat(identifiant: str, client: str, autorise: bool, message_refus: str) -> str:
    if autorise:
        texte = f"Bienvenue, {client} !" if client else "Bienvenue !"
        reponse = f'<p id="resultat-acces" class="succes" role="status">{_e(texte)}</p>'
    else:
        reponse = f'<p id="resultat-acces" class="erreur" role="alert">{_e(message_refus)}</p>'
    corps = "<h1>Résultat du contrôle</h1>" + reponse + '<p><a href="/acces">Nouveau contrôle</a></p>'
    return _page("Résultat du contrôle", corps, identifiant=identifiant)


def client_cree(identifiant: str, nom: str) -> str:
    corps = (
        "<h1>Client créé</h1>"
        f'<p class="succes" role="status">Le client « {_e(nom)} » a été créé.</p>'
        '<p><a href="/clients">Voir la liste des clients</a></p>'
    )
    return _page("Client créé", corps, identifiant=identifiant)


def commande_confirmee(identifiant: str, commande: dict) -> str:
    corps = (
        "<h1>Commande confirmée</h1>"
        f'<p class="succes" role="status">Numéro de commande : <strong id="numero-commande">{_e(commande["numero"])}'
        "</strong></p>"
        f'<p>Total TTC : {formater_montant(commande["total_ttc"])}</p>'
        '<p><a href="/produits">Continuer mes achats</a></p>'
    )
    return _page("Commande confirmée", corps, identifiant=identifiant)


def commandes(identifiant: str, liste: list[dict]) -> str:
    if liste:
        lignes = "".join(
            f'<tr><th scope="row">{_e(c["numero"])}</th><td>{formater_montant(c["total_ttc"])}</td></tr>'
            for c in liste
        )
        corps_liste = (
            '<table><caption>Liste des commandes</caption><thead><tr><th scope="col">Numéro</th>'
            f'<th scope="col">Total TTC</th></tr></thead><tbody>{lignes}</tbody></table>'
        )
    else:
        corps_liste = '<p id="aucune-commande" role="status">Aucune commande.</p>'
    return _page("Commandes", "<h1>Commandes</h1>" + corps_liste, identifiant=identifiant)


def introuvable(identifiant: str | None) -> str:
    return _page("Page introuvable", "<h1>Page introuvable</h1><p>Cette page n'existe pas.</p>", identifiant=identifiant)
