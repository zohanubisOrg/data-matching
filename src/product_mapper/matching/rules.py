import re

VARIANT_SYNONYMS = {
    "ramyun": "ramen", "ramennudler": "ramen",
    "kylling": "chicken", "huhn": "chicken", "poulet": "chicken",
    "okse": "beef", "oksekod": "beef", "rind": "beef", "boeuf": "beef",
    "svin": "pork", "svinekod": "pork", "schwein": "pork", "porc": "pork",
    "rejer": "shrimp", "rej": "shrimp", "reje": "shrimp", "garnelen": "shrimp", "crevette": "shrimp",
    "fisk": "fish", "poisson": "fish",
    "grontsager": "vegetable", "groentsager": "vegetable", "gemuse": "vegetable", "legumes": "vegetable",
    "nudler": "noodles", "nudeln": "noodles",
    "ansungtangmyun": "ansung", "nongshin": "nongshim",
    "kop": "cup", "becher": "cup",
    "pakke": "pack", "pakker": "pack", "beutel": "pack",
    "staerk": "spicy", "scharf": "spicy", "pedas": "spicy",
    "soed": "sweet", "sod": "sweet", "suess": "sweet",
    "kokos": "coconut", "kokosmilch": "coconut",
    "sesam": "sesame", "loeg": "onion", "zwiebel": "onion",
    "hvidloeg": "garlic", "knoblauch": "garlic",
    "svampe": "mushroom", "pilze": "mushroom", "champignon": "mushroom",
}

VARIANT_TOKENS = {
    "apple", "lemon", "mango", "original", "classic", "chicken", "beef", "pork", "shrimp",
    "seafood", "vegetable", "kimchi", "spicy", "sweet", "hot", "mild", "garlic", "tomato",
    "coconut", "taro", "pandan", "honey", "peach", "lychee", "chilli", "chili", "onion",
    "sesame", "soy", "mushroom", "curry", "prawn", "crab", "duck", "fish", "banana",
    "ansung", "nongshim", "ramen", "cup", "pack", "durian", "pineapple"
}


def variant_tokens(text: str) -> set[str]:
    words = [VARIANT_SYNONYMS.get(w, w) for w in re.findall(r"[\w]+", text.casefold())]
    return {w for w in words if w in VARIANT_TOKENS}

