"""Appariement de steps TOLÉRANT AUX ACCENTS — un matcher Behave, pas une consigne au LLM.

POURQUOI CE MODULE EXISTE (mesuré le 2026-07-19, re-génération du cas 9). Le LLM a écrit tout le
`.feature` **sans accents** (« le modele », « est enregistre »), alors que les libellés de la
bibliothèque partagée en portent (« le modèle », « est enregistré »). Behave apparie le texte
**à l'exact** → chaque step partagé accentué devient `undefined` → le dry-run échoue en boucle →
la génération `dry_run_stalled`. Un seul tirage sans accents fait tomber tout le fichier.

C'EST BEHAVE QUI APPARIE, PAS NOTRE CODE — donc la tolérance se pose au niveau du **matcher**, là
où la comparaison a lieu. Normaliser ailleurs (dans nos steps, dans le prompt) ne changerait rien
à ce que Behave voit. Même principe que pour les champs requis : l'outil tolère, on ne compte pas
sur le LLM pour être exact.

DEUX EXIGENCES, LA SECONDE EST CRITIQUE :
  a. décider le match SANS accents (pattern et texte pliés) ;
  b. ne JAMAIS corrompre une VALEUR capturée : un champ dont la valeur est « Matériel » doit
     rester « Matériel », pas « Materiel ». Le pliage sert à DÉCIDER, jamais à altérer la donnée.

Le pliage préserve la LONGUEUR (accent précomposé → base ASCII, 1 pour 1) : c'est indispensable
pour que les indices (`spans`) restent alignés entre texte plié et texte original, et donc
qu'on puisse re-découper la valeur ACCENTUÉE d'origine.

PÉRIMÈTRE STRICT : accents/diacritiques UNIQUEMENT. Pas la casse (replier la casse ferait
collisionner des steps distincts). Pas les espaces (autre mode d'échec, non observé, et toucher
aux espaces changerait la sémantique `parse`).
"""

from __future__ import annotations

from behave.matchers import Argument, ParseMatcher

# Accents précomposés du français (+ quelques voisins) → base ASCII, 1 caractère pour 1 caractère.
# ⚠️ **Longueur préservée, volontairement** : chaque clé est un seul code point, chaque valeur
# aussi. Une forme décomposée NFD (é → e + accent combinant, puis retrait du combinant) RACCOURCIRAIT la
# chaîne et désalignerait les `spans` → on ne pourrait plus récupérer la valeur accentuée. Les
# ligatures (œ, æ) sont volontairement absentes : elles changeraient la longueur (1 → 2), et
# aucun libellé de step n'en contient.
_FOLD = str.maketrans({
    "à": "a", "á": "a", "â": "a", "ã": "a", "ä": "a", "å": "a",
    "ç": "c",
    "è": "e", "é": "e", "ê": "e", "ë": "e",
    "ì": "i", "í": "i", "î": "i", "ï": "i",
    "ñ": "n",
    "ò": "o", "ó": "o", "ô": "o", "õ": "o", "ö": "o",
    "ù": "u", "ú": "u", "û": "u", "ü": "u",
    "ý": "y", "ÿ": "y",
    "À": "A", "Á": "A", "Â": "A", "Ã": "A", "Ä": "A", "Å": "A",
    "Ç": "C",
    "È": "E", "É": "E", "Ê": "E", "Ë": "E",
    "Ì": "I", "Í": "I", "Î": "I", "Ï": "I",
    "Ñ": "N",
    "Ò": "O", "Ó": "O", "Ô": "O", "Õ": "O", "Ö": "O",
    "Ù": "U", "Ú": "U", "Û": "U", "Ü": "U",
    "Ý": "Y",
})


def fold_accents(text: str) -> str:
    """Plie les accents en préservant la longueur (1 code point → 1 code point)."""
    return text.translate(_FOLD)


class AccentTolerantParseMatcher(ParseMatcher):
    """`ParseMatcher` qui apparie sans tenir compte des accents — mais rend les valeurs capturées
    TELLES QU'ÉCRITES (accents compris).

    Sous-classe le matcher `parse` par défaut : les placeholders `{field}` et les convertisseurs
    de type `{id:d}` gardent exactement leur sémantique. On ne change que la base de comparaison.
    """

    def __init__(self, func, pattern, step_type=None, custom_types=None):
        super().__init__(func, pattern, step_type, custom_types)
        # `self.pattern` reste l'ORIGINAL (messages d'erreur, describe). Seul le PARSER, qui décide
        # le match, est reconstruit sur le pattern plié.
        if custom_types is None:
            custom_types = self.TYPE_REGISTRY
        self.parser = self.PARSER_CLASS(fold_accents(pattern), extra_types=custom_types,
                                        case_sensitive=self.CASE_SENSITIVE)

    def check_match(self, step_text):
        """Décide sur le texte PLIÉ ; reconstruit les arguments sur le texte ORIGINAL.

        Reprend la logique de `ParseMatcher.check_match`, à une différence près : la valeur d'une
        capture CHAÎNE est reprise du texte d'origine (accents préservés). Les valeurs converties
        (`:d` → int, etc.) sont laissées telles quelles — un chiffre n'a pas d'accent, aucun
        risque, et re-slicer casserait la conversion.
        """
        folded = fold_accents(step_text)
        matched = self.parser.parse(folded)
        if not matched:
            return None

        args = []
        for index, value in enumerate(matched.fixed):
            start, end = matched.spans[index]
            args.append(self._argument(step_text, folded, start, end, value))
        for name, value in matched.named.items():
            start, end = matched.spans[name]
            args.append(self._argument(step_text, folded, start, end, value, name))
        args.sort(key=lambda a: a.start)
        return args

    @staticmethod
    def _argument(step_text, folded, start, end, value, name=None):
        # Longueur préservée ⇒ [start:end] désigne le MÊME segment dans les deux textes.
        original = step_text[start:end]
        # Capture chaîne (non convertie) : on rend la valeur ACCENTUÉE d'origine, jamais la pliée.
        if isinstance(value, str) and value == folded[start:end]:
            value = original
        return Argument(start, end, original, value, name)
