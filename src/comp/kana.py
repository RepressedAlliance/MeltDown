"""Hepburn romaji to hiragana, for karaoke syllables (`{\\k}` tags) that have to be set in Japanese type."""

_BASE = {
    "a": "あ", "i": "い", "u": "う", "e": "え", "o": "お",
    "ka": "か", "ki": "き", "ku": "く", "ke": "け", "ko": "こ",
    "ga": "が", "gi": "ぎ", "gu": "ぐ", "ge": "げ", "go": "ご",
    "sa": "さ", "shi": "し", "si": "し", "su": "す", "se": "せ", "so": "そ",
    "za": "ざ", "ji": "じ", "zi": "じ", "zu": "ず", "ze": "ぜ", "zo": "ぞ",
    "ta": "た", "chi": "ち", "ti": "ち", "tsu": "つ", "tu": "つ", "te": "て", "to": "と",
    "da": "だ", "di": "ぢ", "du": "づ", "de": "で", "do": "ど",
    "na": "な", "ni": "に", "nu": "ぬ", "ne": "ね", "no": "の",
    "ha": "は", "hi": "ひ", "fu": "ふ", "hu": "ふ", "he": "へ", "ho": "ほ",
    "ba": "ば", "bi": "び", "bu": "ぶ", "be": "べ", "bo": "ぼ",
    "pa": "ぱ", "pi": "ぴ", "pu": "ぷ", "pe": "ぺ", "po": "ぽ",
    "ma": "ま", "mi": "み", "mu": "む", "me": "め", "mo": "も",
    "ya": "や", "yu": "ゆ", "yo": "よ",
    "ra": "ら", "ri": "り", "ru": "る", "re": "れ", "ro": "ろ",
    "wa": "わ", "wo": "を", "n": "ん", "nn": "ん",
}
for _c, _k in (("k", "き"), ("g", "ぎ"), ("n", "に"), ("h", "ひ"), ("b", "び"), ("p", "ぴ"), ("m", "み"),
               ("r", "り")):
    _BASE.update({_c + "ya": _k + "ゃ", _c + "yu": _k + "ゅ", _c + "yo": _k + "ょ"})
_BASE.update({"sha": "しゃ", "shu": "しゅ", "sho": "しょ", "cha": "ちゃ", "chu": "ちゅ", "cho": "ちょ",
              "ja": "じゃ", "ju": "じゅ", "jo": "じょ"})


def to_hiragana(romaji):
    """One karaoke syllable (or a few) in Hepburn: longest match first, a doubled consonant as a small tsu,
    "n" before a consonant or at the end as ん. Unknown letters are dropped."""
    s = "".join(ch for ch in romaji.lower() if ch.isalpha())
    out, i = [], 0
    while i < len(s):
        if i + 1 < len(s) and s[i] == s[i + 1] and s[i] not in "aiueon":
            out.append("っ")
            i += 1
            continue
        if s[i] == "n" and (i + 1 == len(s) or s[i + 1] not in "aiueoy"):
            out.append("ん")
            # "nn" (as karaoke files often write ん): both letters are this one kana unless a vowel follows
            i += 2 if s[i + 1:i + 2] == "n" and s[i + 2:i + 3] not in tuple("aiueoy") else 1
            continue
        for n in (3, 2, 1):
            if s[i:i + n] in _BASE:
                out.append(_BASE[s[i:i + n]])
                i += n
                break
        else:
            i += 1
    return "".join(out)
