import re


TOPICS = {
    "семейное": r"\b(?:семейн\w*|детск\w*|для детей|для всей семьи)\b",
    "кукольный театр": r"\bкукол\w*|\bкукольн\w*",
    "сказка": r"\bсказ(?:к|оч)\w*",
    "мастер-класс": r"\bмастер[-\s]класс\w*",
    "музыка": r"\b(?:музык\w*|оркестр\w*|концерт\w*)",
    "краеведение": r"\b(?:краевед\w*|история башкортостана)",
    "танцы": r"\b(?:тан[ецц]\w*|хореограф\w*|балет\w*)",
    "интерактив": r"\bинтерактив\w*",
}


def event_tags(title, description, category, age, free, existing=()):
    text = f"{title} {description}".casefold().replace("ё", "е")
    tags = [category, f"{age}+"]
    if free:
        tags.append("бесплатно")
    tags.extend(label for label, pattern in TOPICS.items() if re.search(pattern, text))
    return list(dict.fromkeys([*tags, *(tag.strip()[:300] for tag in existing if tag.strip())]))[:40]
