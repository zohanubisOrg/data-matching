import re
import unicodedata


def strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", "" if value is None else str(value)).casefold()
    text = text.replace("_", " ").replace("-", " ").replace(".", " ")
    text = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    return " ".join(text.split())


def tokens(value: object) -> set[str]:
    return set(normalize_text(value).split())


def number(value: str) -> float:
    return float(value.replace(",", "."))


GERMAN_VIET_SYNONYMS: dict[str, str] = {
    "reismehl": "rice flour", "bot gao": "rice flour",
    "klebreismehl": "glutinous rice flour", "bot nep": "glutinous rice flour",
    "tapiokastarke": "tapioca flour", "bot nang": "tapioca flour",
    "maisstarke": "corn starch", "bot bap": "corn starch",
    "maismehl": "corn flour",
    "kartoffelmehl": "potato flour",
    "paniermehl": "bread crumbs",
    "mischmehl": "flour", "mehlmischung": "flour", "teigmischung": "flour",
    "rote bohnen": "red bean", "adzukibohnen": "red bean",
    "mungbohnen": "mung bean", "mungobohnen": "mung bean", "gruene bohnen": "mung bean",
    "schwarze bohnen": "black bean",
    "weisse bohnen": "white bean",
    "sojabohnen": "soybean",
    "weisser sesam": "white sesame", "schwarzer sesam": "black sesame",
    "palmzucker": "palm sugar", "duong thot not": "palm sugar",
    "tamarinde": "tamarind", "tamarindenfleisch": "tamarind", "me chua": "sour tamarind",
    "nudeln": "noodles", "nudler": "noodles", "ramyun": "ramen",
    "banh xeo": "banh xeo", "banh cuon": "banh cuon", "banh bo": "banh bo", "banh beo": "banh beo",
    "banh gio": "banh gio", "banh bot loc": "banh bot loc", "banh canh": "banh canh", "banh khot": "banh khot",
    "banh quay": "banh quay", "chao quay": "banh quay", "banh bao": "banh bao",
    "bot chien gion": "bot chien gion", "bot chien tom": "bot chien tom",
    "bap cha": "bap cha", "bot khoai": "tapioca stripe", "banh phong tom": "prawn crackers",
    "pho ga": "pho ga", "pho bo": "pho bo", "hu tieu": "hu tieu",
    "risvermicelli": "rice vermicelli", "rismel": "rice flour",
    "majsstivelse": "corn starch", "tapiokamel": "tapioca flour",
    "kylling": "chicken", "oksekod": "beef", "svinekod": "pork", "and": "duck", "rejer": "shrimp",
    "staerk": "spicy", "sterk": "spicy", "sur": "sour", "syltet": "pickled", "kopnudler": "cup noodles"
}


def translate_multilingual(text: str) -> str:
    res = text.lower().replace("-", " ").replace("_", " ")
    for src, tgt in sorted(GERMAN_VIET_SYNONYMS.items(), key=lambda x: len(x[0]), reverse=True):
        if src in res:
            res = res.replace(src, f"{src} {tgt}")
    return res


