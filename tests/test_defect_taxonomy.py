"""§5 — projection SYMPTÔME → CAUSE RACINE (taxonomie causale), couverte en direct.

Ce module tranche la classification la plus critique du brief : c'est sur la cause
racine que ``defect_origin`` décide vrai_bug / test_a_reparer / indetermine. On vérifie
ici les trois points sensibles :

- la PRIORITÉ entre causes quand plusieurs symptômes coexistent dans un même message ;
- le DÉPARTAGE des égalités entre catégories (au niveau du cas, via la cause dominante) ;
- le REPLI vers ``unknown`` quand aucune règle ne matche clairement.
"""

from testpilot.execution.behave_result import BehaveFailure
from testpilot.verdict import defect_taxonomy as dt


def _fail(*, step="", tb="", raw="", ftype=""):
    """Fabrique un BehaveFailure minimal (scénario fixe, seuls le texte/type importent)."""
    return BehaveFailure(scenario_name="s", step_text=step, failure_type=ftype,
                         traceback_summary=tb, raw=raw)


# --- Normalisation --------------------------------------------------------------

def test_normalize_neutralise_url_nombres_et_espaces():
    out = dt.normalize_error("  Erreur   http://x/y?z=1  code 42  ")
    assert "<url>" in out
    assert "<n>" in out  # 42 -> <n>
    assert "  " not in out  # espaces compactés
    assert out == out.strip().lower()


def test_normalize_texte_vide():
    assert dt.normalize_error("") == ""
    assert dt.normalize_error(None) == ""


# --- Classification unitaire par mots-clés --------------------------------------

def test_chaque_categorie_reconnue_par_un_mot_cle():
    cas = {
        dt.MISSING_SERVER_CONTEXT: "le champ team_id reste vide",
        dt.WRONG_NAVIGATION: "405 Method Not Allowed sur la route",
        dt.WRONG_FIELD_NAME: "TimeoutError: locator introuvable",
        dt.MISSING_ROLE: "AccessError: permission denied",
        dt.ASSERTION_MISMATCH: "AssertionError: valeur attendue",
    }
    for attendu, texte in cas.items():
        assert dt.classify_failure(_fail(tb=texte)) == attendu


# --- PRIORITÉ : plusieurs symptômes dans un même message ------------------------

def test_le_signal_gagne_sur_les_mots_cles_du_message():
    """INVERSÉ PAR 0015 — et c'est tout l'objet de la décision.

    Ce test affirmait l'inverse : les mots-clés du message (« reste vide ») l'emportaient sur
    `AssertionError`. Or ce message est écrit par l'AGENT, tandis que le type d'exception est
    levé par le RUNTIME. Faire gagner le texte, c'était laisser l'agent choisir son propre
    verdict — et un vrai bug applicatif devenait `test_a_reparer` (le faux négatif de §4.4).

    Le coût est assumé : une assertion réellement due à un contexte serveur manquant sera
    désormais classée `vrai_bug` → le circuit s'arrête et un humain tranche. Sur-arrêter est la
    direction sûre ; réparer un test correct contre une application cassée ne l'est pas.
    """
    texte = "AssertionError: le champ team_id reste vide"
    assert dt.classify_failure(_fail(tb=texte)) == dt.ASSERTION_MISMATCH


def test_priorite_respecte_l_ordre_declare_de_categories():
    # Navigation (405/route) précède field-name (timeout/locator) dans CATEGORIES.
    texte = "405 Method Not Allowed — puis TimeoutError: locator"
    assert dt.classify_failure(_fail(tb=texte)) == dt.WRONG_NAVIGATION
    # Sanity : l'ordre déclaré est bien celui qu'on suppose.
    assert dt.CATEGORIES.index(dt.WRONG_NAVIGATION) < dt.CATEGORIES.index(dt.WRONG_FIELD_NAME)


def test_mots_cles_priment_sur_le_fallback_de_type():
    # failure_type="assertion" seul donnerait ASSERTION_MISMATCH ; mais le texte porte
    # un mot-clé WRONG_FIELD_NAME ("timeout") → les mots-clés priment sur le symptôme.
    f = _fail(tb="TimeoutError: element", ftype="assertion")
    assert dt.classify_failure(f) == dt.WRONG_FIELD_NAME


# --- REPLI sur le symptôme puis sur unknown -------------------------------------

def test_fallback_sur_le_type_quand_aucun_mot_cle():
    # Texte vide → pas de mot-clé possible → projection du symptôme sur la cause.
    assert dt.classify_failure(_fail(ftype="permission")) == dt.MISSING_ROLE
    assert dt.classify_failure(_fail(ftype="ui_timeout")) == dt.WRONG_FIELD_NAME
    assert dt.classify_failure(_fail(ftype="odoo_data")) == dt.MISSING_SERVER_CONTEXT
    assert dt.classify_failure(_fail(ftype="odoorpc")) == dt.WRONG_NAVIGATION


def test_unknown_quand_type_inconnu_et_aucun_mot_cle():
    assert dt.classify_failure(_fail(ftype="something_new")) == dt.UNKNOWN


def test_unknown_quand_texte_neutre_et_type_absent():
    # Message présent mais sans aucun mot-clé, et pas de symptôme exploitable.
    f = _fail(tb="opération terminée sans détail exploitable")
    assert dt.classify_failure(f) == dt.UNKNOWN


# --- Garde contre les collisions de sous-chaîne (incident CI 2026-09-15) --------
#
# Le garde d'ordre 0009 (`test_case_order.py`) cherchait « position » par containment
# (`"position" in texte`) et se déclenchait à tort sur « supposition ». Même défaut de fond,
# ici : `_KEYWORDS` matchait par containment avant ce correctif — « attendu » aurait été
# reconnu dans « inattendu », qui n'a pourtant rien à voir avec une comparaison attendu/obtenu.

def test_mot_cle_ne_matche_pas_a_l_interieur_d_un_autre_mot():
    texte = "un comportement inattendu, sans lien avec une comparaison quelconque"
    assert dt.classify_failure(_fail(tb=texte)) == dt.UNKNOWN


def test_aucun_mot_cle_ne_matche_quand_il_est_englobe_par_des_lettres():
    """Garde systématique, pas seulement le cas « attendu »/« inattendu » : entourer N'IMPORTE
    QUEL mot-clé de lettres quelconques ne doit jamais produire son propre classement — sinon
    le containment nu serait toujours présent ailleurs dans la table."""
    for category, kws in dt._KEYWORDS.items():
        for kw, pattern in zip(kws, dt._KEYWORD_PATTERNS[category]):
            if not (kw[0].isalpha() and kw[-1].isalpha()):
                continue  # mots-clés à ponctuation en bout (aucun ici aujourd'hui, garde future)
            texte = f"xx{kw}xx"
            assert not pattern.search(texte), f"{kw!r} matche à tort dans {texte!r}"


# --- Agrégation : comptage et cause dominante -----------------------------------

def test_classify_failures_compte_et_omet_les_zeros():
    failures = [
        _fail(tb="AccessError: forbidden"),          # MISSING_ROLE
        _fail(tb="AccessError: permission denied"),  # MISSING_ROLE
        _fail(tb="AssertionError: attendu 0"),       # ASSERTION_MISMATCH
    ]
    counts = dt.classify_failures(failures)
    assert counts == {dt.MISSING_ROLE: 2, dt.ASSERTION_MISMATCH: 1}
    # Les catégories à zéro n'apparaissent jamais.
    assert dt.WRONG_NAVIGATION not in counts


def test_dominant_par_majorite_simple():
    failures = [
        _fail(tb="AccessError: forbidden"),          # MISSING_ROLE
        _fail(tb="AccessError: permission denied"),  # MISSING_ROLE
        _fail(tb="AssertionError: attendu 0"),       # ASSERTION_MISMATCH
    ]
    assert dt.dominant_category(failures) == dt.MISSING_ROLE


def test_dominant_departage_egalite_par_priorite():
    # Une occurrence chacune : WRONG_FIELD_NAME et MISSING_ROLE sont à égalité (1-1).
    # CATEGORIES place WRONG_FIELD_NAME avant MISSING_ROLE → il gagne le départage.
    failures = [
        _fail(tb="TimeoutError: locator absent"),  # WRONG_FIELD_NAME
        _fail(tb="AccessError: forbidden"),        # MISSING_ROLE
    ]
    assert dt.dominant_category(failures) == dt.WRONG_FIELD_NAME
    assert dt.CATEGORIES.index(dt.WRONG_FIELD_NAME) < dt.CATEGORIES.index(dt.MISSING_ROLE)


def test_dominant_none_sans_echec():
    assert dt.dominant_category([]) is None
    assert dt.dominant_category(None) is None


def test_dominant_unknown_quand_tout_est_indetermine():
    failures = [_fail(ftype="mystere"), _fail(tb="rien de parlant ici")]
    assert dt.dominant_category(failures) == dt.UNKNOWN
