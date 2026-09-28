"""Effets vérifiés côté serveur (lot 08a, sous-lot 08c, C6) — état technique, champs numériques
avec tolérance devise, documents liés et leur état, rapport PDF généré.

Tous sur `context.last_record_ids`/`context.last_record_model` (lot 01) : ce que le dernier step
d'ouverture/création (08b) ou d'assertion (`_odoo_steps.py`) a mis en contexte — jamais un
enregistrement redécouvert au hasard.

⚠️ **NON VÉRIFIÉ SUR BANC RÉEL** — mêmes réserves que `_odoo_gestion_steps.py`/`_selecteurs.py`.
Les assertions elles-mêmes (`state`, champs lus/ comparés, `res.currency.rounding`) sont du RPC
pur, déjà du même patron que `_odoo_steps.py` (qui, lui, tourne réellement en génération depuis
plusieurs lots) — le risque est concentré sur `step_rapport_pdf_genere`, seul step de ce fichier
qui touche l'UI (menu Imprimer), non vérifié.
"""

from __future__ import annotations

import re
from pathlib import Path

from behave import then

from _base_helpers import (
    _dernier_telechargement,
    _texte_du_fichier,
    constater,
    telecharger_via,
)
from _odoo_steps import _exiger_enregistrement_en_contexte


def _record_courant(context):
    _exiger_enregistrement_en_contexte(
        context, "Aucun enregistrement en contexte. Ouvrez ou créez d'abord un document.",
        avec_modele=True)
    return context.odoo.env[context.last_record_model].browse(context.last_record_ids[0])


@then('l\'état technique de ce document est "{valeur}"')
def step_etat_technique(context, valeur):
    record = _record_courant(context)
    actuel = record.read(["state"])[0]["state"]
    constater(str(actuel) == valeur, f"État technique : attendu '{valeur}', obtenu '{actuel}'.")


def _tolerance_devise(context, model_name: str, record_id: int) -> float:
    """Demi-pas d'arrondi de la devise du document (`res.currency.rounding`, lu via son champ
    `currency_id` — convention Odoo la plus répandue). Repli 0.01 (2 décimales) si le modèle n'a
    pas de champ `currency_id`, ou en cas d'erreur RPC : une tolérance est un raffinement de
    précision, jamais un motif d'échec technique."""
    try:
        Model = context.odoo.env[model_name]
        if "currency_id" not in Model.fields_get(["currency_id"]):
            return 0.01
        valeur = Model.browse(record_id).read(["currency_id"])[0].get("currency_id")
        if not valeur:
            return 0.01
        currency_id = valeur[0] if isinstance(valeur, (list, tuple)) else valeur
        rounding = context.odoo.env["res.currency"].browse(currency_id).read(["rounding"])[0]["rounding"]
        return float(rounding) / 2
    except Exception:
        return 0.01


@then('le champ "{champ}" de ce document vaut {nombre:g}')
def step_champ_vaut_nombre(context, champ, nombre):
    record = _record_courant(context)
    actuel = record.read([champ])[0][champ]
    tolerance = _tolerance_devise(context, context.last_record_model, context.last_record_ids[0])
    constater(abs(float(actuel) - float(nombre)) <= tolerance,
             f"Champ '{champ}' : attendu {nombre} (± {tolerance}), obtenu {actuel}.")


@then('ce document a {n:d} "{modele_lie}" lié(s) par "{champ}"')
def step_a_n_lies_par_champ(context, n, modele_lie, champ):
    record = _record_courant(context)
    lies = record.read([champ])[0].get(champ) or []
    constater(len(lies) == n, f"'{champ}' : attendu {n} lié(s), obtenu {len(lies)}.")
    context.last_related_ids = list(lies)
    context.last_related_model = modele_lie


def _lies_sont_a_l_etat(context, modele: str, valeur: str) -> tuple[bool, list]:
    """Les documents de `context.last_related_ids` sont-ils tous à l'état `valeur` dans `modele` ?
    Ne consigne PAS le constat elle-même (fonction pure) : chaque `@then` appelant reste celui qui
    assertit visiblement — garde de la bibliothèque (0010, « pas de vérification creuse »)."""
    lies = getattr(context, "last_related_ids", None)
    if not lies:
        raise RuntimeError(
            "Aucun document lié en contexte. Utilisez d'abord un step "
            "'ce document a N \"modèle\" lié(s) par \"champ\"'.")
    Model = context.odoo.env[modele]
    etats = Model.browse(lies).read(["state"])
    obtenus = [e["state"] for e in etats]
    return all(e == valeur for e in obtenus), obtenus


@then('le document lié "{modele}" est à l\'état "{valeur}"')
def step_document_lie_etat(context, modele, valeur):
    ok, obtenus = _lies_sont_a_l_etat(context, modele, valeur)
    constater(ok, f"Document(s) lié(s) '{modele}' : attendu état '{valeur}', obtenu {obtenus}.")


@then("la facture liée est comptabilisée")
def step_facture_liee_comptabilisee(context):
    """Raccourci documenté de `step_document_lie_etat` : une facture Odoo « comptabilisée » a
    l'état technique `posted` (`account.move`) — jamais un libellé français deviné."""
    ok, obtenus = _lies_sont_a_l_etat(context, "account.move", "posted")
    constater(ok, f"Facture liée : attendu l'état 'posted' (comptabilisée), obtenu {obtenus}.")


@then('un rapport PDF "{nom_rapport}" est généré pour ce document')
def step_rapport_pdf_genere(context, nom_rapport):
    page = context.page
    # Ouvre le menu « Imprimer » s'il existe sous cette forme (repli silencieux : certaines vues
    # exposent directement le lien du rapport, sans sous-menu à ouvrir d'abord).
    try:
        page.get_by_role("button", name=re.compile("imprimer|print", re.IGNORECASE)).first.click(
            timeout=3000)
    except Exception:
        pass
    telecharger_via(context, nom_rapport)
    chemin = Path(_dernier_telechargement(context)["chemin"])
    donnees = chemin.read_bytes()
    constater(donnees[:4] == b"%PDF",
             f"Le rapport '{nom_rapport}' téléchargé n'est pas un PDF valide (signature absente).")
    texte = _texte_du_fichier(str(chemin))  # lève déjà si aucun texte extractible
    constater(bool(texte.strip()), f"Aucun texte extrait du rapport '{nom_rapport}'.")
