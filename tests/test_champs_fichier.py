"""Champs FICHIER — la cause n°1 des erreurs techniques mesurées (2026-07-21).

Mesure du taux d'erreur technique : **2 échecs sur 3** venaient de là. L'agent remplissait un
`<input type="file">` comme du texte → le navigateur refuse
(`InvalidStateError: This input element accepts a filename`).

⚠️ **L'agent ne pouvait PAS réussir** : la bibliothèque partagée n'avait aucun step d'upload, et
`fill_field` ne connaissait pas le type `file`. L'outil n'existait pas — ce n'était pas une
faiblesse de prompt. Or **13 des 37 routes du portail** ont un champ fichier, presque toujours
REQUIS : c'était donc un plafond structurel sur la fiabilité.

Le correctif a trois couches, testées ici :
1. `fill_field` reconnaît le type `file` et téléverse (plus jamais de `el.value = …`) ;
2. un step partagé `je joins un fichier au champ "…"` existe (l'agent voit la capacité) ;
3. le prompt DIT quels champs requis sont des fichiers (l'annuaire le savait, personne ne le
   transmettait).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "behave_runtime" / "steps_library"))

from testpilot.analysis.plan import TestPlan  # noqa: E402
from testpilot.generation import domain_model, prompt as pm  # noqa: E402


def _plan(routes):
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"],
                    portal_routes=routes, risks=[], connector_type="odoo", cost_usd=0.0,
                    raw_spec="SPEC", entry_url=routes[0] if routes else "")


def _modele(champs):
    return {"mesure_le": "2026-07-21", "pages": {"/form/{id}": {"champs": champs}},
            "transitions": {}, "onglets_internes": {}}


# ── Couche 1 : le helper téléverse au lieu d'écrire du texte ──────────────────

class _FauxLocator:
    def __init__(self, journal, input_type):
        self.journal = journal
        self.input_type = input_type
        self.first = self

    def set_input_files(self, chemin): self.journal.append(("upload", chemin))

    def evaluate(self, script, *a):
        # `fill_field` interroge le locator pour le tag puis le type de l'élément.
        return "input" if "tagName" in script else self.input_type

    def count(self):
        return 1  # `locate_field` : le champ existe par son attribut `name`, tel quel

    def wait_for(self, **kw):
        pass


class _FauxPage:
    """Simule un `<input type="file">`. `page.evaluate` = l'ANCIEN chemin fautif (écriture JS)."""

    def __init__(self, input_type="file"):
        self.input_type = input_type
        self.journal: list = []
        self.url = "https://exemple.test/formulaire"

    def wait_for_selector(self, *a, **kw): pass
    def locator(self, sel): return _FauxLocator(self.journal, self.input_type)
    def evaluate(self, script, *a):
        self.journal.append(("js", script))   # ← ce que le correctif doit éviter
        return None


def test_fill_field_TELEVERSE_sur_un_champ_fichier():
    """Le cœur du correctif : plus jamais `el.value = …` sur un champ fichier."""
    from _base_helpers import fill_field

    page = _FauxPage(input_type="file")
    # `resolve_field_name` interroge la page ; on court-circuite en passant un nom résoluble.
    import _base_helpers as H
    original = H.resolve_field_name
    H.resolve_field_name = lambda p, n: n
    try:
        fill_field(page, "rib_client", "rib.pdf")
    finally:
        H.resolve_field_name = original

    actions = [a for a, _ in page.journal]
    assert "upload" in actions, "un champ fichier doit être TÉLÉVERSÉ"
    assert "js" not in actions, "plus jamais d'écriture JS sur un champ fichier"


def test_le_fichier_televerse_existe_vraiment_et_n_est_pas_vide():
    """Un fichier vide (ou un .txt déguisé) peut être rejeté par une validation de type — on
    diagnostiquerait alors un faux « champ introuvable »."""
    from _base_helpers import attach_file

    page = _FauxPage()
    import _base_helpers as H
    original = H.resolve_field_name
    H.resolve_field_name = lambda p, n: n
    try:
        attach_file(page, "rib_client", "rib.pdf")
    finally:
        H.resolve_field_name = original

    chemin = Path(page.journal[0][1])
    assert chemin.exists()
    assert chemin.read_bytes().startswith(b"%PDF"), "un PDF valide, pas un fichier vide"


def test_le_nom_du_fichier_est_deduit_quand_la_valeur_n_en_est_pas_un():
    from _base_helpers import attach_file

    page = _FauxPage()
    attach_file(page, "justificatifs_mutation", "un texte quelconque")

    nom = Path(page.journal[0][1]).name
    assert nom.startswith("piece-jointe-"), "nom généré depuis le champ"
    assert nom.endswith(".pdf")


# ── Couche 2 : le step partagé existe (l'agent voit la capacité) ──────────────

def test_le_step_d_upload_est_AU_CATALOGUE():
    """Sans step au catalogue, l'agent ne peut pas savoir que la capacité existe (`0003`)."""
    from testpilot.generation import steps_library

    libelles = [s.label for s in steps_library.catalogue()]
    assert any("joins un fichier" in lb for lb in libelles), (
        "le step d'upload doit être proposé à l'agent")


# ── Couche 3 : le prompt DIT quels champs sont des fichiers ───────────────────

def test_le_prompt_signale_les_champs_FICHIER():
    """L'annuaire connaissait le type depuis toujours ; personne ne le transmettait."""
    modele = _modele([
        {"name": "nom", "required": True, "tag": "input", "type": "text"},
        {"name": "rib_client", "required": True, "tag": "input", "type": "file"},
    ])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "CHAMP FICHIER" in s
    assert "rib_client" in s
    assert "je joins un fichier au champ" in s, "le prompt indique LE step à employer"
    assert "InvalidStateError" in s, "il dit pourquoi écrire du texte échoue"


def test_sans_champ_fichier_aucune_alerte_inutile():
    """Pas de consigne inventée là où elle n'a pas lieu d'être (bruit = alerte tue)."""
    modele = _modele([{"name": "nom", "required": True, "tag": "input", "type": "text"}])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "CHAMP FICHIER" not in s


# ── Champs requis CACHÉS (5ᵉ occurrence du même motif) ───────────────────────

def test_un_champ_requis_CACHE_n_est_pas_demande():
    """⚠️ Mesuré le 2026-07-21 sur `/demande_avoir` : `partner_email` et `name` sont requis mais
    `visible=false` — injectés par le SERVEUR. Le prompt exigeait de remplir TOUS les champs
    requis → l'agent les cherchait dans l'interface → `TimeoutError`, échec technique.

    On ne demande QUE les champs saisissables, et on NOMME les cachés : sans ça, l'agent croirait
    la liste incomplète et tenterait de les remplir quand même."""
    modele = _modele([
        {"name": "visible_1", "required": True, "tag": "input", "type": "text", "visible": True},
        {"name": "cache_serveur", "required": True, "tag": "input", "type": "email",
         "visible": False},
    ])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "2 champs requis, dont **1 à remplir par l'interface**" in s
    assert "NE tente PAS de remplir" in s
    assert "`cache_serveur`" in s
    # Le champ caché ne doit PAS figurer dans la liste à remplir.
    liste = s.split("DOIT remplir TOUS ceux-ci :")[1].split("⚠️")[0]
    assert "cache_serveur" not in liste
    assert "visible_1" in liste


def test_sans_champ_cache_aucune_mise_en_garde_inutile():
    modele = _modele([{"name": "a", "required": True, "tag": "input", "type": "text",
                       "visible": True}])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "NE tente PAS" not in s


def test_sur_l_annuaire_REEL_les_champs_caches_de_demande_avoir_sont_ecartes():
    chemin = Path("data/domain/projet-1.json")
    if not chemin.exists():
        pytest.skip("annuaire réel absent")
    modele = json.loads(chemin.read_text(encoding="utf-8"))

    s = pm._section_champs_requis(_plan(["/demande_avoir/{id}"]), modele)

    assert "NE tente PAS de remplir" in s
    assert "`partner_email`" in s, "le champ qui a fait échouer le run doit être écarté nommément"


def test_le_type_est_expose_par_l_annuaire():
    """La donnée manquante, à la source : `formulaires_requis` n'exposait pas `type`."""
    modele = _modele([{"name": "rib", "required": True, "tag": "input", "type": "file"}])

    forms = domain_model.formulaires_requis(modele, ["/form/{id}"])

    assert forms[0]["requis"][0]["type"] == "file"


# ── Sur l'annuaire RÉEL : l'ampleur du problème ───────────────────────────────

def test_sur_l_annuaire_REEL_les_champs_fichier_sont_signales():
    chemin = Path("data/domain/projet-1.json")
    if not chemin.exists():
        pytest.skip("annuaire réel absent")
    modele = json.loads(chemin.read_text(encoding="utf-8"))

    s = pm._section_champs_requis(_plan(["/mutation/{id}"]), modele)

    assert "justificatifs_mutation" in s
    assert "CHAMP FICHIER" in s, "le champ fichier requis de /mutation doit être signalé"


# ── URL réelle vs route normalisée (6ᵉ occurrence du motif) ──────────────────

def test_le_prompt_donne_l_URL_REELLE_quand_la_route_a_un_identifiant():
    """⚠️ Mesuré le 2026-07-21 : l'agent a écrit `/demande_avoir/29789` — un identifiant INVENTÉ.
    La page ne rendait pas le formulaire → `TimeoutError` sur `partner_name`, pourtant visible.

    Les routes de l'annuaire sont NORMALISÉES (`{id}`) pour dédupliquer ; un test doit naviguer
    vers une URL RÉELLE. Le crawl connaissait l'URL concrète et la jetait."""
    modele = {"mesure_le": "2026-07-21", "transitions": {}, "onglets_internes": {},
              "pages": {"/demande_avoir/{id}": {"champs": [],
                                                "url_exemple": "/demande_avoir/12345"}}}

    s = pm._section_domaine_mesure(_plan(["/demande_avoir/{id}"]), modele)

    assert "/demande_avoir/12345" in s
    assert "n'invente JAMAIS un numéro" in s


def test_pas_d_exemple_pour_une_route_SANS_identifiant():
    """Une route fixe (`/myservices`) n'a pas besoin d'exemple — le bruit dilue le signal."""
    modele = {"mesure_le": "2026-07-21", "transitions": {}, "onglets_internes": {},
              "pages": {"/myservices": {"champs": [], "url_exemple": "/myservices"}}}

    s = pm._section_domaine_mesure(_plan(["/myservices"]), modele)

    assert "URL réelle" not in s


def test_l_URL_d_exemple_n_impose_JAMAIS_une_locale():
    """⚠️ Piège évité de justesse (2026-07-21) : le crawl arrive souvent sur la version anglaise
    (`/en/achat_siege/113`). Y envoyer un test ferait échouer TOUS les steps à libellé français
    — « Envoyer » devient « Send ». Mon propre correctif d'URL aurait introduit la cause suivante.

    On garde l'identifiant concret (la seule chose qui manquait) sans imposer de locale."""
    modele = {"mesure_le": "2026-07-21", "transitions": {}, "onglets_internes": {},
              "pages": {"/achat_siege/{id}": {"champs": [],
                                              "url_exemple": "/achat_siege/113"}}}

    s = pm._section_domaine_mesure(_plan(["/achat_siege/{id}"]), modele)

    assert "/achat_siege/113" in s
    assert "/en/" not in s, "aucune URL d'exemple ne doit imposer une locale"


def test_l_annuaire_REEL_ne_contient_aucune_URL_localisee():
    chemin = Path("data/domain/projet-1.json")
    if not chemin.exists():
        pytest.skip("annuaire réel absent")
    modele = json.loads(chemin.read_text(encoding="utf-8"))

    localisees = [r for r, i in modele["pages"].items()
                  if (i.get("url_exemple") or "").startswith(("/en/", "/fr/"))]

    assert not localisees, f"URL d'exemple localisées : {localisees[:5]}"


# ── Laisser vide un <select> (8ᵉ cause mesurée) ──────────────────────────────

class _FauxSelect:
    """Un `<select>` : `fill()` y lève l'erreur Playwright qu'on veut éviter."""

    def __init__(self, journal, valeurs):
        self.journal = journal
        self.valeurs = valeurs
        self.first = self

    def evaluate(self, script, *a):
        if "tagName" in script:
            return "select"
        if "options" in script:
            return self.valeurs
        return ""

    def select_option(self, v): self.journal.append(("select_option", v))
    def fill(self, *a, **kw): raise AssertionError("fill() ne doit JAMAIS être appelé sur un select")

    def count(self): return 1  # `locate_field` : le champ existe par son attribut `name`
    def wait_for(self, **kw): pass


class _PageSelect:
    def __init__(self, valeurs):
        self.journal: list = []
        self.valeurs = valeurs
        self.url = "https://exemple.test/formulaire"

    def wait_for_selector(self, *a, **kw): pass
    def locator(self, sel): return _FauxSelect(self.journal, self.valeurs)
    def evaluate(self, *a, **kw): return None


def test_laisser_vide_un_SELECT_choisit_son_option_vide():
    """⚠️ Mesuré le 2026-07-21 (`sinistre_client`) : `leave_field_empty` faisait `fill("")` sur un
    `<select>` → « Element is not an <input>… », erreur cryptique qui fait échouer techniquement
    un scénario légitime. Même famille que les champs fichier : un type d'élément ignoré."""
    import _base_helpers as H

    page = _PageSelect(["", "paris", "lyon"])
    original = H.resolve_field_name
    H.resolve_field_name = lambda p, n: n
    try:
        H.leave_field_empty(page, "agence")
    finally:
        H.resolve_field_name = original

    assert page.journal == [("select_option", "")], "on sélectionne l'option vide"


def test_un_select_SANS_option_vide_le_dit_clairement():
    """Sans option vide, le champ NE PEUT PAS être laissé vide. On le dit, plutôt que de laisser
    une erreur de bas niveau qu'on diagnostiquerait en « champ introuvable ».

    ⚠️ `ElementIntrouvableError`, pas `AssertionError` (correctif 2026-09-14, cas C45) : ce défaut
    est TECHNIQUE (la forme du champ ne permet pas ce que le test demande), jamais une preuve que
    l'application se comporte mal — voir `defect_taxonomy._EXCEPTION_TO_CAUSE`."""
    import _base_helpers as H

    page = _PageSelect(["paris", "lyon"])
    original = H.resolve_field_name
    H.resolve_field_name = lambda p, n: n
    try:
        with pytest.raises(H.ElementIntrouvableError, match="ne peut pas"):
            H.leave_field_empty(page, "agence")
    finally:
        H.resolve_field_name = original


def test_le_prompt_INTERDIT_de_vider_un_champ_requis_en_nominal():
    modele = _modele([{"name": "agence", "required": True, "tag": "select", "type": "",
                       "visible": True}])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "Mais UNIQUEMENT là" in s
