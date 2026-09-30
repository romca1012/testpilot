"""`connectors/odoo_view.py` — analyse PURE d'une vue Odoo (lot 09, C9).

Les fixtures d'arch ci-dessous reprennent la structure RÉELLE mesurée sur le banc Odoo 16.0
(`sale.order`, 2026-09-30) : boutons à visibilité conditionnelle (domaine Odoo, jamais un
booléen), barre d'état, champ x2many avec sous-vue INLINÉE (jamais une vue séparée), champs
requis portés par les métadonnées `models`, pas par l'arch.
"""

from __future__ import annotations

from testpilot.connectors.odoo_view import analyser_vue, normaliser_reponse_rpc

_ARCH_MINIMAL = """<form string="Commande">
  <header>
    <button name="action_confirm" string="Confirmer" type="object"
            modifiers="{&quot;invisible&quot;: [[&quot;state&quot;, &quot;not in&quot;, [&quot;draft&quot;]]]}"/>
    <button name="action_lock" string="Verrouiller" type="object" modifiers="{&quot;invisible&quot;: true}"/>
    <button name="action_preview" string="Aperçu" type="object"/>
    <field name="state" widget="statusbar" statusbar_visible="draft,sent,sale"/>
  </header>
  <group>
    <field name="partner_id"/>
    <field name="order_line">
      <tree>
        <field name="product_id"/>
        <field name="product_uom_qty"/>
      </tree>
    </field>
  </group>
</form>"""

_GET_VIEWS_SALE_ORDER = {
    "views": {"form": {"arch": _ARCH_MINIMAL, "id": 1, "model": "sale.order"}},
    "models": {
        "sale.order": {
            "state": {"type": "selection", "required": False,
                      "selection": [["draft", "Devis"], ["sent", "Envoyé"],
                                    ["sale", "Commande"], ["done", "Verrouillé"],
                                    ["cancel", "Annulé"]]},
            "partner_id": {"type": "many2one", "required": True, "relation": "res.partner"},
            "order_line": {"type": "one2many", "required": False, "relation": "sale.order.line"},
        },
        "sale.order.line": {
            "product_id": {"type": "many2one", "required": True, "relation": "product.product"},
            "product_uom_qty": {"type": "float", "required": False},
        },
    },
}


def test_analyser_vue_distingue_les_3_etats_de_visibilite_d_un_bouton():
    """Falsifiable : mesuré sur le banc réel que la quasi-totalité des boutons d'un vrai
    formulaire portent un `invisible` CONDITIONNEL (une liste, un domaine Odoo), jamais un
    booléen — les réduire à `bool(...)` aurait classé « toujours caché » un bouton visible la
    plupart du temps (`action_confirm` ici). Les 3 états doivent rester distincts."""
    resultat = analyser_vue(_GET_VIEWS_SALE_ORDER, "sale.order", "form")

    par_nom = {b["name"]: b["invisible"] for b in resultat["boutons"]}
    assert par_nom["action_confirm"] == [["state", "not in", ["draft"]]]
    assert par_nom["action_lock"] is True
    assert par_nom["action_preview"] is False


def test_analyser_vue_rend_la_barre_d_etat_avec_ses_valeurs_visibles_et_toutes():
    resultat = analyser_vue(_GET_VIEWS_SALE_ORDER, "sale.order", "form")

    assert resultat["barre_etat"] == {
        "champ": "state",
        "valeurs_visibles": ["draft", "sent", "sale"],
        "valeurs_toutes": ["draft", "sent", "sale", "done", "cancel"],
    }


def test_analyser_vue_rend_absent_sans_widget_statusbar():
    sans_barre = {
        "views": {"form": {"arch": '<form><field name="partner_id"/></form>'}},
        "models": {"sale.order": {"partner_id": {"type": "many2one", "required": True}}},
    }
    assert analyser_vue(sans_barre, "sale.order", "form")["barre_etat"] is None


def test_analyser_vue_recense_les_sous_champs_editables_d_un_x2many():
    """La sous-vue d'un x2many est INLINÉE dans l'arch parent (mesuré sur le banc, `order_line`
    de `sale.order`) — jamais une seconde requête RPC à faire."""
    resultat = analyser_vue(_GET_VIEWS_SALE_ORDER, "sale.order", "form")

    x2many = {c["name"]: c for c in resultat["champs_x2many"]}
    assert x2many["order_line"]["relation"] == "sale.order.line"
    assert x2many["order_line"]["sous_champs"] == ["product_id", "product_uom_qty"]


def test_analyser_vue_ignore_un_champ_normal_pour_les_x2many():
    resultat = analyser_vue(_GET_VIEWS_SALE_ORDER, "sale.order", "form")
    noms = {c["name"] for c in resultat["champs_x2many"]}
    assert "partner_id" not in noms


def test_analyser_vue_liste_les_champs_requis_depuis_les_metadonnees_pas_l_arch():
    """`required` vient de `models[modele]`, jamais d'un attribut de l'arch — la vue peut très
    bien ne pas porter `required="1"` alors que le champ EST requis au niveau du modèle."""
    resultat = analyser_vue(_GET_VIEWS_SALE_ORDER, "sale.order", "form")
    assert resultat["champs_requis"] == ["partner_id"]


def test_falsifiable_un_arch_illisible_rend_une_erreur_jamais_une_exception():
    brut = {"views": {"form": {"arch": "<form><non-ferme></form>"}}, "models": {}}

    resultat = analyser_vue(brut, "sale.order", "form")

    assert resultat["erreur"]
    assert resultat["boutons"] == []


def test_falsifiable_une_vue_absente_rend_une_erreur_explicite():
    resultat = analyser_vue({"views": {}, "models": {}}, "sale.order", "form")
    assert "sale.order" in resultat["erreur"]
    assert "form" in resultat["erreur"]


# ── Repli `fields_view_get` (pré-16, ou get_views en échec) ──────────────────────────────────

def test_normaliser_reponse_rpc_reconnait_fields_view_get():
    """Forme `fields_view_get` : un seul modèle, jamais de sous-champs x2many observables — c'est
    la dégradation ASSUMÉE de ce repli, pas un bug de la normalisation."""
    brut = {"arch": _ARCH_MINIMAL, "model": "sale.order",
            "fields": {"partner_id": {"type": "many2one", "required": True}}}

    arch, modeles = normaliser_reponse_rpc(brut, "sale.order", "form")

    assert arch == _ARCH_MINIMAL
    assert modeles == {"sale.order": {"partner_id": {"type": "many2one", "required": True}}}


def test_analyser_vue_avec_repli_fields_view_get_degrade_sans_planter():
    brut = {"arch": _ARCH_MINIMAL,
            "fields": {"partner_id": {"type": "many2one", "required": True},
                      "order_line": {"type": "one2many", "required": False}}}

    resultat = analyser_vue(brut, "sale.order", "form")

    assert resultat["erreur"] == ""
    assert resultat["champs_requis"] == ["partner_id"]
    # Sous-champs du x2many INVISIBLES avec ce repli (pas de modèle "sale.order.line" fourni) :
    # `champs_x2many` reste renseigné (la relation ET le nom du champ viennent de l'arch/du
    # modèle principal), mais ses `sous_champs` sont toujours lus depuis l'arch elle-même — eux
    # ne dépendent PAS de `models`, donc restent corrects même avec ce repli.
    x2many = {c["name"]: c for c in resultat["champs_x2many"]}
    assert x2many["order_line"]["sous_champs"] == ["product_id", "product_uom_qty"]
