import re
from dataclasses import dataclass
from typing import Pattern


@dataclass(frozen=True)
class LoveTextRules:
    min_words: int
    min_emojis: int
    min_sentences: int
    sentence_min_words: int
    min_verbs: int
    count_any_emoji: bool
    emojis: tuple[str, ...]
    sad_patterns: tuple[str, ...]
    verb_re: Pattern[str]


def _count_love_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _count_love_emojis(text: str, rules: LoveTextRules) -> int:
    if rules.count_any_emoji:
        emoji_re = re.compile(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")
        return len(emoji_re.findall(text))
    return sum(text.count(e) for e in rules.emojis)


def _count_love_verbs(text: str, rules: LoveTextRules) -> int:
    return len(rules.verb_re.findall(text or ""))


def _count_love_sentences(text: str, rules: LoveTextRules) -> int:
    parts = re.split(r"[.!?]+|\n+", text)
    count = 0
    for part in parts:
        if not part.strip():
            continue
        words = re.findall(r"\b\w+\b", part)
        if len(words) < rules.sentence_min_words:
            continue
        count += 1
    if count > 0:
        return count

    words = re.findall(r"\b\w+\b", text)
    chunk = []
    for word in words:
        chunk.append(word)
        if len(chunk) >= rules.sentence_min_words:
            count += 1
            chunk = []
    return count


def love_text_ok(text: str, rules: LoveTextRules) -> bool:
    if not text:
        return False
    if _count_love_words(text) < rules.min_words:
        return False
    if _count_love_emojis(text, rules) < rules.min_emojis:
        return False
    if rules.min_sentences > 0 and _count_love_sentences(text, rules) < rules.min_sentences:
        return False
    if rules.min_verbs > 0 and _count_love_verbs(text, rules) < rules.min_verbs:
        return False
    return True
