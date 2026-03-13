from collections.abc import Iterable
import re


_GIF_PATTERN = re.compile(r"(GIF:[\w-]+)", re.IGNORECASE)
# Split after sentence-ending punctuation followed by whitespace
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.?!…])\s+")
# Split when …/?/! is immediately followed by uppercase (no space between)
_SENTENCE_SPLIT_NO_SPACE = re.compile(r"(?<=[?!…])(?=[A-ZÁ-Ú])")
_MAJUSCULE_SPLIT_PATTERN = re.compile(r"(?<=[a-zá-úç0-9,])\s+(?=[A-ZÁ-ÚÇ])")

# Comma followed by a transition/conjunction word — good split point for long chunks
_COMMA_TRANSITION_RE = re.compile(
    r',\s+(?=(?:'
    r'mas|porém|porem|então|entao|só|so|tipo|pois|enfim|aliás|alias|'
    r'porque|inclusive|aí|ai|daí|dai|já|ja|até|ate|ainda|agora|depois|'
    r'quando|enquanto|nem|ou'
    r')\b)',
    re.IGNORECASE,
)

# Maximum length for a single chunk before forced splitting
_MAX_CHUNK_LENGTH = 120

# Matches context-injection brackets that the LLM may regurgitate.
_CONTEXT_BRACKET_RE = re.compile(
    r'\['
    r'(?:'
        r'Contexto|Ferramentas|GIFs?\s*[Dd]ispon|Instruções|Instrucoes|'
        r'Lembretes|Estilo|Gírias|Girias|Foco|Atenção|Atencao|'
        r'INSTRUÇÕES|Contexto Pessoal|Contexto de Tempo|'
        r'[A-ZÁ-Ú][^\]]{8,}'
    r')'
    r'[^\]]*\]',
    re.IGNORECASE,
)

# Matches a "Lou:" / "Louise:" role prefix at the start of a line.
_ROLE_PREFIX_RE = re.compile(r'^\s*(?:Lou|Louise)\s*:\s*', re.IGNORECASE)

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)
_PREPOSITIONS = {"de", "da", "do", "dos", "das", "pra", "pro", "para", "no", "na", "nos", "nas", "em"}
_PROPER_JOINERS = {"the", "los", "las", "san", "santa", "são"}
_ARTICLE_CONNECTORS = {"o", "a", "os", "as", "um", "uma", "uns", "umas"}
_INTERJECTION_SPLITS = {
    "hehe",
    "haha",
    "hihi",
    "eita",
    "opa",
    "ah",
    "ai",
    "uai",
    "ixi",
    "vish",
    "aff",
    "afff",
    "hmm",
    "hmmm",
    "hmmmm",
    "humm",
    "hummm",
    "hummmm",
    "oxe",
    "oxi",
    "oba",
    "bah",
}

_DYNAMIC_INTERJECTION_PATTERN = re.compile(r"^([a-zá-úç]{2,8})([!….,]*)\s+(.*)$", re.IGNORECASE)
_INTERJECTION_VOCATIVE_PATTERN = re.compile(r"^([a-zá-úç]{1,8}),\s*(.+)$", re.IGNORECASE)
_INTERJECTION_SOLO_PATTERN = re.compile(r"^([a-zá-úç]{1,8})$", re.IGNORECASE)

_SENTENCE_STARTERS = {
    "agora",
    "hoje",
    "entao",
    "então",
    "mas",
    "quando",
    "onde",
    "enquanto",
    "porém",
    "porem",
    "entretanto",
    "depois",
    "ate",
    "até",
    "bom",
    "olha",
}

_HARD_SENTENCE_BREAKERS = {
    "sem",
    "isso",
    "essa",
    "esse",
    "essas",
    "esses",
    "assim",
    "inclusive",
    "entao",
    "então",
    "mas",
    "só",
    "so",
    "tipo",
    "pois",
    "enfim",
    "aliás",
    "bora",
    "partiu",
}

_EMPHASIS_LEADS = {
    "ta",
    "tá",
    "to",
    "tô",
    "tava",
    "tando",
    "tamo",
    "esta",
    "está",
    "esta",
    "estao",
    "estão",
    "fica",
    "ficou",
    "ficando",
    "ficar",
    "é",
    "eh",
    "foi",
    "vai",
    "segue",
    "parece",
    "pareceu",
    "tava",
}

_UPPERCASE_RESTART_TOKENS = (
    "A",
    "O",
    "As",
    "Os",
    "Esse",
    "Essa",
    "Esses",
    "Essas",
    "Este",
    "Esta",
    "Estes",
    "Estas",
    "Aquele",
    "Aquela",
    "Aqueles",
    "Aquelas",
    "Isto",
    "Isso",
    "Aquilo",
)

_ACRONYM_EXCEPTIONS = {
    "nasa",
    "html",
    "http",
    "https",
    "cpu",
    "gpu",
    "ai",
    "lol",
    "br",
    "sp",
}

_TITLE_CONNECTORS = {
    "da",
    "de",
    "do",
    "das",
    "dos",
    "vs",
    "vs.",
    "x",
    "feat",
    "ft",
    "and",
    "the",
    "of",
    "&",
    "by",
}
_TITLE_LOWER_JOINERS = _TITLE_CONNECTORS | {
    "del",
    "della",
    "van",
    "von",
    "der",
    "den",
    "para",
    "por",
}

# Matches bullet-point / numbered list patterns typical of assistant-mode output
_BULLET_LIST_RE = re.compile(r'^\s*(?:\d+[.)\-]|[-•*])\s+', re.MULTILINE)

_NAME_STOPWORDS = {"pai", "lou", "mateus", "mãe", "mae"}

# Common uppercase words that are NOT proper nouns (pronouns, articles, etc.)
# Prevent them from being title-merged with the previous chunk
_UPPERCASE_NON_TITLE_WORDS = {
    "você", "voce", "ele", "ela", "eles", "elas", "nós", "nos",
    "eu", "tu", "isso", "esse", "essa", "este", "esta", "aqui",
    "ali", "lá", "la", "já", "ja", "não", "nao", "sim", "bem",
    "muito", "mais", "menos", "tudo", "nada", "sempre", "nunca",
    "agora", "hoje", "ontem", "amanhã", "amanha", "depois",
    "quando", "onde", "como", "quem", "qual", "quanto",
}

_SPLIT_PREFERRED_STARTERS = {
    "lembra",
    "queria",
    "quero",
    "vamos",
    "vamo",
    "bora",
    "olha",
    "pensa",
}

_COMMA_LOWERCASE_WORDS = {
    "mas",
    "mais",
    "que",
    "call",
    "boa",
    "boas",
    "bom",
    "bons",
    "só",
    "so",
    "olha",
    "ai",
    "aí",
    "pai",
    "tipo",
    "bora",
    "vamo",
    "vamos",
    "e",
    "ou",
    "pra",
    "pro",
    "porém",
    "porem",
    "então",
    "entao",
}

_QUE_LOWERCASE_WORDS = {"call", "boa", "boas", "bom", "bons"}

_DE_DESCRIPTOR_WORDS = {
    "boa",
    "boas",
    "bom",
    "bons",
    "linda",
    "lindas",
    "lindo",
    "lindos",
    "maravilhosa",
    "maravilhoso",
    "maravilhosas",
    "maravilhosos",
    "absurda",
    "absurdas",
    "absurdo",
    "absurdos",
    "doida",
    "doidas",
    "doido",
    "doidos",
    "massa",
    "top",
    "suave",
    "incrível",
    "incriveis",
    "incrivel",
    "incríveis",
    "braba",
    "brabo",
}

_QUESTION_STARTERS = {
    "cadê",
    "cade",
    "qual",
    "quais",
    "quando",
    "onde",
    "como",
    "quem",
    "que",
    "quanto",
    "quantos",
    "quantas",
}

_QUESTION_LEAD_INS = {"ai", "aí", "aii", "opa", "olha", "tipo", "eita", "aff", "oxe", "oxi", "ei", "vish"}

_QUESTION_VOCATIVES = {"pai"}

# Short affirmation/interjection words that expect a comma before the next clause
_COMMA_AFTER_SHORT_WORDS = {
    "ok", "okay", "sim", "não", "nao", "claro", "certo", "bom",
    "beleza", "tá", "ta", "tô", "to", "pronto", "enfim", "aliás",
    "alias", "verdade", "exato", "obvio", "óbvio", "pois", "aham",
    "uhum", "hmm", "hm", "ah", "oh", "putz", "vixi", "eita",
    "opa", "oxe", "uai", "ué", "ue", "mano", "real", "sério",
    "serio", "talvez", "tipo", "olha", "vish", "ata", "atá",
}

_QUESTION_PREFIX_PHRASES = (
    "por que",
    "pra que",
    "será que",
    "sera que",
)

_QUESTION_SUFFIXES = (
    "cadê",
    "cadê você",
    "cadê voce",
    "cadê vc",
    "cade",
    "cade você",
    "cade voce",
    "cade vc",
    "onde",
    "quando",
    "como",
    "qual",
    "quais",
    "tá aí",
    "ta ai",
    "tá por aí",
    "ta por ai",
    "ainda aí",
    "ainda ai",
    "me responde",
    "fala comigo",
    "pra onde",
    "por que",
    "pra que",
    "o que",
)

_QUESTION_MID_MARKERS = (
    " o que ",
    " pra que ",
    " por que ",
    " será que",
    " sera que",
    " tá aí",
    " ta ai",
    " tá por aí",
    " ta por ai",
    " cadê ",
    " cade ",
    " que horas",
)


def _clean_llm_artifacts(text: str) -> str:
    """Remove common artefacts that local LLMs leak into their output.

    This runs *before* any splitting so that noisy tokens never reach the
    chunk pipeline.  The cleaning covers:

    * Context-bracket injections the model echoes from the history
      (e.g. ``[GIFs Disponíveis: happy, lol, wow]``)
    * ``Lou:`` / ``Louise:`` role prefixes the model emits at the start
      of a line or at the very beginning.
    * Template tokens from Llama-2, ChatML, etc.
    * Stray whitespace / blank lines that remain after stripping.
    """
    if not text:
        return ""

    # 1. Strip bracketed context injections
    cleaned = _CONTEXT_BRACKET_RE.sub("", text)

    # 2. Strip per-line "Lou:" or "Louise:" role prefixes
    lines = cleaned.split("\n")
    stripped_lines: list[str] = []
    for line in lines:
        line = _ROLE_PREFIX_RE.sub("", line)
        stripped = line.strip()
        if stripped:
            stripped_lines.append(stripped)
    cleaned = "\n".join(stripped_lines)

    # 3. Remove common template tokens that may survive earlier cleaning
    for tok in ("[INST]", "[/INST]", "<<SYS>>", "<</SYS>>",
                "<s>", "</s>", "<|im_start|>", "<|im_end|>"):
        cleaned = cleaned.replace(tok, "")

    # 4. Strip bullet-point / numbered-list prefixes (assistant-mode)
    cleaned = _BULLET_LIST_RE.sub("", cleaned)

    # 5. Remove garbage lines (e.g. "- Lou", "Lou", bare role names, list bullets with just a name)
    final_lines: list[str] = []
    for ln in cleaned.split("\n"):
        ln = ln.strip()
        # Skip lines that are just "- Lou", "* Lou", "Lou", "Louise", etc.
        bare = re.sub(r'^[\-\*•]\s*', '', ln).strip()
        if bare.lower() in ('lou', 'louise', 'pai', 'mateus', ''):
            continue
        # Skip lines that look like markdown headers
        if re.match(r'^#{1,4}\s', ln):
            continue
        final_lines.append(ln)
    cleaned = "\n".join(final_lines)

    # 6. Strip stray quote marks the LLM may leak
    cleaned = re.sub(r'["\\"]+', '', cleaned)
    # Clean up leftover whitespace from removed quotes
    cleaned = re.sub(r'  +', ' ', cleaned)

    # 7. Fix broken greetings early (before splitting can fragment them)
    cleaned = _fix_broken_greetings(cleaned)

    # 8. Collapse residual whitespace
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def sanitize_and_split_response(text: str, style_terms: Iterable[str] | None = None) -> list:
    """Normalizer that mimics the legacy Lou formatter while fixing edge cases."""

    if not text:
        return []

    # --- LLM artifact pre-cleaning ---
    text = _clean_llm_artifacts(text)

    # --- Fix broken greetings BEFORE any splitting ---
    # Must run here so "Boa, Noite" → "Boa noite" before
    # _MAJUSCULE_SPLIT_PATTERN fragments on comma+uppercase.
    text = _fix_broken_greetings(text)

    if "GIF:" in text:
        return _split_gif_segments(text, style_terms=style_terms)

    cleaned = _EMOJI_PATTERN.sub("", text)
    cleaned = cleaned.strip()
    if not cleaned:
        return []

    # --- Fix missing commas after short words BEFORE splitting ---
    # Must run here so "Ok Se" → "Ok, se" before _MAJUSCULE_SPLIT_PATTERN
    # would fragment them into separate chunks.
    cleaned = _fix_comma_after_short_words_global(cleaned)

    style_tokens = _prepare_style_tokens(style_terms)

    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    rough_chunks: list[str] = []

    for line in lines:
        # First split on punctuation + whitespace, then on punctuation + uppercase (no space)
        sentence_chunks = _SENTENCE_SPLIT_PATTERN.split(line)
        expanded: list[str] = []
        for sc in sentence_chunks:
            expanded.extend(_SENTENCE_SPLIT_NO_SPACE.split(sc))
        for sentence in expanded:
            sentence = sentence.strip()
            if not sentence:
                continue
            # Split on comma + transition words ("mas", "então", etc.)
            comma_parts = _COMMA_TRANSITION_RE.split(sentence)
            for cp in comma_parts:
                cp = cp.strip()
                if not cp:
                    continue
                sub_chunks = _MAJUSCULE_SPLIT_PATTERN.split(cp)
                for chunk in sub_chunks:
                    stripped = chunk.strip()
                    if not stripped:
                        continue
                    if stripped.startswith(",") and rough_chunks:
                        rough_chunks[-1] = f"{rough_chunks[-1]} {stripped.lstrip(', ').strip()}".strip()
                    else:
                        rough_chunks.append(stripped)

    # Re-attach chunks that start with a vocative (Pai, Lou, etc.)
    # so "Boa noite," + "Pai, como vai?" becomes "Boa noite, pai, como vai?"
    rough_chunks = _merge_vocative_chunks(rough_chunks)

    # Force-split any remaining overly long chunks at natural break points
    rough_chunks = _split_long_chunks(rough_chunks)

    repaired = _merge_proper_nouns(rough_chunks)
    repaired = _merge_dangling_fragments(repaired)

    final_chunks: list[str] = []
    for chunk in repaired:
        normalized = _normalize_chunk(chunk)
        if not normalized:
            continue
        style_segments = _split_on_style_terms(normalized, style_tokens)
        for segment in style_segments:
            for emphasis_chunk in _split_uppercase_emphasis(segment):
                for restart_chunk in _split_uppercase_restart_chunks(emphasis_chunk):
                    final_chunks.extend(_split_interjection_chunk(restart_chunk, style_tokens))

    composed_chunks: list[str] = []
    for chunk in final_chunks:
        composed_chunks.extend(_split_after_question_marks(chunk))

    ensured_chunks: list[str] = []
    for segment in composed_chunks:
        ensured = _ensure_question_punctuation(segment)
        if ensured:
            ensured_chunks.append(ensured)

    return ensured_chunks


def _merge_vocative_chunks(chunks: list[str]) -> list[str]:
    """Re-attach chunks that start with a vocative like 'Pai', 'Lou', 'Mateus'.

    When _MAJUSCULE_SPLIT_PATTERN splits 'Boa noite, Pai, como vai?' into
    ['Boa noite,', 'Pai, como vai?'], this function merges them back.
    Also strips trailing commas from the left chunk after merge.
    """
    if not chunks:
        return chunks
    merged: list[str] = []
    for chunk in chunks:
        stripped = chunk.strip()
        if not stripped:
            continue
        if merged:
            first_word = _clean_token_edges(stripped.split()[0]).lower() if stripped.split() else ""
            prev = merged[-1]
            # Merge when previous chunk ends with comma and current starts with vocative
            if first_word in _NAME_STOPWORDS and prev.rstrip().endswith(","):
                merged[-1] = f"{prev} {stripped}"
                continue
        merged.append(stripped)
    # Strip any trailing commas that remain after other processing
    return [c.rstrip(",").strip() if c.endswith(",") else c for c in merged if c.strip()]


def _split_gif_segments(text: str, style_terms: Iterable[str] | None = None) -> list[str]:
    segments = _GIF_PATTERN.split(text)
    tokens: list[str] = []
    for segment in segments:
        stripped = (segment or "").strip()
        if not stripped:
            continue
        if stripped.upper().startswith("GIF:"):
            tokens.append(stripped)
        else:
            tokens.extend(sanitize_and_split_response(stripped, style_terms=style_terms))
    return tokens


def _split_long_chunks(chunks: list[str]) -> list[str]:
    """Force-split chunks that exceed _MAX_CHUNK_LENGTH at a natural break point."""
    result: list[str] = []
    for chunk in chunks:
        if len(chunk) <= _MAX_CHUNK_LENGTH:
            result.append(chunk)
            continue
        # Try splitting at comma + transition word first
        parts = _COMMA_TRANSITION_RE.split(chunk)
        if len(parts) > 1:
            result.extend(p.strip() for p in parts if p.strip())
            continue
        # Try splitting at any comma near the midpoint
        mid = len(chunk) // 2
        best_comma = -1
        for i, ch in enumerate(chunk):
            if ch == ',':
                if best_comma == -1 or abs(i - mid) < abs(best_comma - mid):
                    best_comma = i
        if best_comma > 15 and best_comma < len(chunk) - 15:
            left = chunk[:best_comma].strip()
            right = chunk[best_comma + 1:].strip()
            if left:
                result.append(left)
            if right:
                result.append(right)
            continue
        # Try splitting at a conjunction/preposition word boundary near the midpoint
        _SPLIT_WORDS = {'que', 'pra', 'pro', 'tipo', 'porque', 'ou', 'e', 'nem'}
        best_split = -1
        words_iter = re.finditer(r'\b(\w+)\b', chunk)
        for m in words_iter:
            if m.group(1).lower() in _SPLIT_WORDS and m.start() > 15 and m.start() < len(chunk) - 15:
                if best_split == -1 or abs(m.start() - mid) < abs(best_split - mid):
                    best_split = m.start()
        if best_split > 0:
            left = chunk[:best_split].strip()
            right = chunk[best_split:].strip()
            if left and right:
                result.append(left)
                result.append(right)
                continue
        # No good split point — keep as-is
        result.append(chunk)
    return result


def _prepare_style_tokens(style_terms: Iterable[str] | None) -> list[str]:
    if not style_terms:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for term in style_terms:
        cleaned = _normalize_style_term(term)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    normalized.sort(key=len, reverse=True)
    return normalized


def _normalize_style_term(term: str | None) -> str:
    if not term:
        return ""
    cleaned = re.sub(r"\s+", " ", term.strip())
    return cleaned.lower()


def _split_on_style_terms(text: str, style_tokens: list[str]) -> list[str]:
    if not text or not style_tokens:
        return [text] if text else []
    lowered = text.lower()
    split_points: set[int] = set()
    for token in style_tokens:
        token_len = len(token)
        if token_len == 0:
            continue
        start = 0
        while start < len(text):
            idx = lowered.find(token, start)
            if idx == -1:
                break
            before_char = text[idx - 1] if idx > 0 else " "
            after_index = idx + token_len
            after_char = text[after_index] if after_index < len(text) else " "
            if idx > 0 and _is_style_boundary_char(before_char) and _is_style_boundary_char(after_char):
                split_points.add(idx)
            start = idx + max(1, token_len)
    if not split_points:
        return [text]
    ordered_points = sorted(split_points)
    segments: list[str] = []
    last_index = 0
    for point in ordered_points:
        if point <= last_index:
            continue
        segment = text[last_index:point].strip()
        if segment:
            segments.append(segment)
        last_index = point
    tail = text[last_index:].strip()
    if tail:
        segments.append(tail)
    return segments if segments else [text]


def _is_style_boundary_char(char: str) -> bool:
    if not char:
        return True
    if char.isspace():
        return True
    return char in ",.;!?…:()[]{}'\"-—"


def _clean_token_edges(token: str) -> str:
    if not token:
        return ""
    return re.sub(r"^[^0-9A-Za-zÁ-Úá-úçÇ]+|[^0-9A-Za-zÁ-Úá-úçÇ]+$", "", token)


def _match_dynamic_interjection(text: str) -> list[str] | None:
    snippet = text.strip()
    if not snippet:
        return None
    match = _DYNAMIC_INTERJECTION_PATTERN.match(snippet)
    if not match:
        return None
    word, punctuation, tail = match.groups()
    tail = (tail or "").strip()
    if not tail:
        return None
    if punctuation and "," in punctuation:
        return None
    if not _looks_like_dynamic_interjection(word or ""):
        return None
    head = f"{word}{punctuation or ''}".strip()
    return [head, tail]


def _looks_like_dynamic_interjection(word: str) -> bool:
    if not word:
        return False
    lower = word.lower()
    if lower in _INTERJECTION_SPLITS:
        return True
    if len(lower) <= 6 and re.search(r"(.)\1{2,}", lower):
        return True
    if len(lower) <= 6 and re.search(r"([aeiouáéíóú])\1+$", lower):
        return True
    dynamic_prefixes = ("hum", "hmm", "aff", "ah", "oxe", "oxi", "bah", "eita", "opa")
    if any(lower.startswith(prefix) for prefix in dynamic_prefixes):
        return True
    return False


def _extract_title_like_run(tokens: list[str]) -> list[str]:
    run: list[str] = []
    started = False
    for token in tokens:
        cleaned = _clean_token_edges(token)
        if not cleaned:
            continue
        lower = cleaned.lower()
        if cleaned.isdigit():
            run.append(cleaned)
            started = True
            continue
        if lower in _TITLE_LOWER_JOINERS:
            if started:
                run.append(lower)
                continue
            break
        if cleaned[0].isupper():
            run.append(cleaned)
            started = True
            continue
        break
    if run and any(part[0].isupper() or part.isdigit() for part in run):
        return run
    return []


def _should_force_merge_title(previous: str, current: str) -> bool:
    prev = previous.rstrip()
    curr = current.strip()
    if not prev or not curr:
        return False
    curr_tokens = curr.split()
    if not curr_tokens:
        return False
    first = _clean_token_edges(curr_tokens[0]).lower()
    if first and first in _SENTENCE_STARTERS:
        return False
    if first and first in _UPPERCASE_NON_TITLE_WORDS:
        return False
    title_run = _extract_title_like_run(curr_tokens)
    if not title_run:
        return False
    first_word = _clean_token_edges(curr_tokens[0]).lower()
    if first_word in _SPLIT_PREFERRED_STARTERS:
        return False
    if any(part.isdigit() for part in title_run):
        return True
    return len(title_run) >= 2


def _merge_proper_nouns(chunks: list[str]) -> list[str]:
    merged: list[str] = []
    for chunk in chunks:
        if merged and _should_merge_with_previous(merged[-1], chunk):
            merged[-1] = f"{merged[-1]} {chunk}".strip()
        else:
            merged.append(chunk)
    return merged


def _merge_dangling_fragments(chunks: list[str]) -> list[str]:
    merged: list[str] = []
    for index, chunk in enumerate(chunks):
        candidate = chunk
        if merged:
            candidate = _build_title_candidate(chunks, index)
        if merged and _looks_like_dangling_fragment(merged[-1], candidate):
            merged[-1] = f"{merged[-1]} {chunk}".strip()
        else:
            merged.append(chunk)
    return merged


def _build_title_candidate(chunks: list[str], start_index: int) -> str:
    combined: list[str] = []
    title_started = False
    max_window = 3
    for offset in range(start_index, min(len(chunks), start_index + max_window)):
        token = chunks[offset].strip()
        if not token:
            break
        words = token.split()
        if not words:
            break
        first_clean = _clean_token_edges(words[0])
        if not first_clean:
            break
        lower_first = first_clean.lower()
        if lower_first in _SENTENCE_STARTERS and not title_started:
            break
        if first_clean[0].isupper() or first_clean.isdigit():
            combined.append(token)
            title_started = True
            continue
        if title_started and (lower_first in _TITLE_LOWER_JOINERS or first_clean.isdigit()):
            combined.append(token)
            continue
        break
    return " ".join(combined).strip() if combined else chunks[start_index]


def _should_merge_with_previous(previous: str, current: str) -> bool:
    current = current.strip()
    previous = previous.rstrip()
    if not previous or not current:
        return False
    if not current[0].isupper():
        return False
    # Common pronouns/adverbs that start with uppercase after a split should NOT be merged
    curr_first_word = current.split()[0]
    curr_first_clean = _clean_token_edges(curr_first_word).lower()
    if curr_first_clean in _UPPERCASE_NON_TITLE_WORDS:
        return False
    prev_last_word = previous.split()[-1]
    prev_token = prev_last_word.lower()
    if prev_token in _PREPOSITIONS:
        return True
    if prev_last_word.lower() in _PROPER_JOINERS:
        return True
    if _looks_like_title_stitch(previous, current):
        return True
    if _looks_like_compound_title_bridge(previous, current):
        return True
    if _should_merge_short_fragment(previous, current):
        return True
    return False


def _looks_like_title_stitch(previous: str, current: str) -> bool:
    prev = previous.rstrip()
    curr = current.strip()
    if not prev or not curr:
        return False
    if prev[-1] in ".?!…":
        return False
    prev_words = prev.split()
    if not prev_words:
        return False
    prev_last = _clean_token_edges(prev_words[-1])
    curr_words = curr.split()
    if not prev_last or not curr_words:
        return False
    curr_first = _clean_token_edges(curr_words[0])
    if not curr_first:
        return False
    if prev_last.lower() in _NAME_STOPWORDS or curr_first.lower() in _NAME_STOPWORDS:
        return False
    # Common pronouns/adverbs should NOT be treated as title words
    if curr_first.lower() in _UPPERCASE_NON_TITLE_WORDS:
        return False
    if not prev_last[0].isupper() or not curr_first[0].isupper():
        return False
    if len(curr_words) == 1:
        return True
    lookahead = curr_words[1:3]
    for token in lookahead:
        cleaned = _clean_token_edges(token)
        if not cleaned:
            continue
        if cleaned[0].islower() or cleaned.lower() in _TITLE_LOWER_JOINERS:
            return True
    return False


def _looks_like_compound_title_bridge(previous: str, current: str) -> bool:
    prev_tokens = previous.split()
    curr_tokens = current.split()
    if not prev_tokens or not curr_tokens:
        return False
    # If the first word of current is a common pronoun/adverb, never merge
    first_curr = _clean_token_edges(curr_tokens[0]).lower()
    if first_curr in _UPPERCASE_NON_TITLE_WORDS:
        return False
    window = [*prev_tokens[-3:], *curr_tokens[:3]]
    if not window:
        return False
    started = False
    uppercase_hits = 0
    run: list[str] = []
    for raw in window:
        token = _clean_token_edges(raw)
        if not token:
            continue
        lower = token.lower()
        # Skip non-title words from counting as title parts
        if lower in _UPPERCASE_NON_TITLE_WORDS:
            if started:
                break
            continue
        if token[0].isupper() or token.isdigit():
            run.append(token)
            uppercase_hits += 1
            started = True
            continue
        if started and lower in _TITLE_LOWER_JOINERS:
            run.append(lower)
            continue
        if started:
            break
    if uppercase_hits < 2 or len(run) < 2:
        return False
    if run[-1].lower() in _TITLE_LOWER_JOINERS:
        return False
    return True


def _looks_like_dangling_fragment(previous: str, current: str) -> bool:
    prev = previous.rstrip()
    curr = current.strip()
    if not prev or not curr:
        return False
    if prev[-1] in ".?!…":
        return False
    if _should_force_merge_title(prev, curr):
        return True
    # Coloned titles like "Detroit: Become" should merge with continuation words
    if ":" in prev:
        head, tail = prev.rsplit(":", 1)
        tail_words = tail.strip().split()
        if tail.strip() and len(tail_words) <= 2:
            first_curr = curr.split()[0]
            if first_curr and first_curr[0].isupper():
                return True
    prev_last = prev.split()[-1]
    if not prev_last:
        return False
    # Se a frase anterior termina com um artigo e a próxima começa em maiúscula, deve unir
    if prev_last.lower() in _ARTICLE_CONNECTORS and curr.split()[0][0].isupper():
        return True
    if not prev_last[0].isupper():
        return False
    curr_words = curr.split()
    if not curr_words:
        return False
    starter_token = curr_words[0].rstrip(",.!?…").lower()
    if starter_token and starter_token in _SPLIT_PREFERRED_STARTERS:
        return False
    if starter_token in _HARD_SENTENCE_BREAKERS:
        return False
    if len(curr_words) <= 3 and curr_words[0][0].isupper():
        return True
    if _looks_like_title_stitch(prev, curr):
        return True
    if _looks_like_compound_title_bridge(prev, curr):
        return True
    if _should_merge_short_fragment(prev, curr):
        return True
    first_token = curr_words[0]
    if first_token.endswith(",") and first_token[0].isupper():
        return True
    return False


# Fix greetings where the model inserts stray commas / quotes: "Boa, noite" → "Boa noite"
_BROKEN_GREETING_RE = re.compile(
    r'\b(Bo[am])[\s,"\']*(dia|tarde|noite)\b',
    re.IGNORECASE,
)


def _fix_broken_greetings(text: str) -> str:
    """Normalize common Portuguese greetings that the model may break with commas.

    Handles: 'Boa, noite' → 'Boa noite', 'Boa, Noite' → 'Boa noite',
             'Bom, dia' → 'Bom dia', etc.
    """
    def _repl(m: re.Match) -> str:
        prefix = m.group(1).capitalize()  # "Boa" or "Bom" (normalise case)
        period = m.group(2).lower()       # "dia", "tarde", "noite"
        return f"{prefix} {period}"
    return _BROKEN_GREETING_RE.sub(_repl, text)


def _normalize_chunk(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return ""
    normalized = normalized.replace("...", "…")
    normalized = normalized.replace(".", "")
    normalized = normalized.replace("'", "")
    normalized = normalized.replace('"', '')  # strip stray quotes
    normalized = normalized.replace("!?", "?")
    normalized = normalized.replace("?!", "?")
    normalized = normalized.replace("!", "")
    # --- Fix broken greetings: "Boa, noite" → "Boa noite", etc. ---
    normalized = _fix_broken_greetings(normalized)
    # --- Fix spacing around punctuation ---
    normalized = re.sub(r",\s*\?", "?", normalized)       # "Boa, ?" → "Boa?"
    normalized = re.sub(r"\s+\?", "?", normalized)         # "Boa ?" → "Boa?"
    normalized = re.sub(r"\s+,", ",", normalized)          # " ," → ","
    normalized = re.sub(r",\s+", ", ", normalized)         # normalise after comma
    normalized = re.sub(r"\s{2,}", " ", normalized)         # collapse whitespace
    normalized = _normalize_comma_followups(normalized)
    normalized = _normalize_que_followups(normalized)
    normalized = _normalize_de_tao_clause(normalized)
    normalized = _normalize_de_descriptor_clause(normalized)
    normalized = _cleanup_soft_pause_commas(normalized)
    normalized = _normalize_pai_reference(normalized)
    normalized = _apply_interjection_fallback(normalized)
    normalized = _fix_comma_after_short_words(normalized)
    normalized = _normalize_short_titlecase_words(normalized)
    normalized = _ensure_sentence_capitalization(normalized)
    return normalized


def _split_interjection_chunk(text: str, style_tokens: list[str]) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    for token in _INTERJECTION_SPLITS:
        if lowered.startswith(token + " "):
            head, tail = text[: len(token)], text[len(token):].strip()
            if tail:
                return _compose_interjection_segments(head.strip(), tail)
    style_match = _match_style_prefix(text, style_tokens)
    if style_match:
        return _compose_interjection_segments(style_match[0], style_match[1])
    dynamic = _match_dynamic_interjection(text)
    if dynamic:
        return _compose_interjection_segments(dynamic[0], dynamic[1])
    return [text]


def _match_style_prefix(text: str, style_tokens: list[str]) -> list[str] | None:
    if not text or not style_tokens:
        return None
    stripped = text.lstrip()
    leading_ws = len(text) - len(stripped)
    lowered = stripped.lower()
    for token in style_tokens:
        token_len = len(token)
        if token_len == 0:
            continue
        if not lowered.startswith(token):
            continue
        boundary_index = leading_ws + token_len
        if boundary_index >= len(text):
            return None
        next_char = text[boundary_index]
        if not _is_style_boundary_char(next_char):
            continue
        head = text[:boundary_index].strip()
        tail = text[boundary_index:].strip()
        if head and tail:
            return [head, tail]
    return None


def _split_uppercase_emphasis(text: str) -> list[str]:
    snippet = (text or "").strip()
    if not snippet:
        return []
    if " " not in snippet:
        return [snippet]
    tokens = snippet.split()
    segments: list[str] = []
    buffer: list[str] = []
    prev_lower = ""
    for index, token in enumerate(tokens):
        buffer.append(token)
        cleaned = _clean_token_edges(token)
        next_clean = _clean_token_edges(tokens[index + 1]) if index + 1 < len(tokens) else ""
        if (
            buffer
            and _should_break_after_emphasis(prev_lower, cleaned)
            and _looks_like_sentence_restart(next_clean)
        ):
            segments.append(" ".join(buffer).strip())
            buffer = []
        prev_lower = cleaned.lower() if cleaned else ""
    if buffer:
        segments.append(" ".join(buffer).strip())
    return [segment for segment in segments if segment]


def _split_uppercase_restart_chunks(text: str) -> list[str]:
    snippet = (text or "").strip()
    if not snippet:
        return []
    pattern = re.compile(r"\b(" + "|".join(_UPPERCASE_RESTART_TOKENS) + r")\b")
    split_points: list[int] = []
    last_accepted = 0
    for match in pattern.finditer(snippet):
        start = match.start()
        if start == 0 or start == last_accepted:
            continue
        prev_char = snippet[start - 1]
        if prev_char in ".?!…:\n;-":
            continue
        prefix_slice = snippet[:start].rstrip()
        if not prefix_slice:
            continue
        prev_word = _clean_token_edges(prefix_slice.split()[-1])
        if not prev_word or not prev_word.islower():
            continue
        tail = snippet[match.end():].lstrip()
        if not tail:
            continue
        next_word = _clean_token_edges(tail.split()[0])
        if not next_word or not next_word[0].isupper():
            continue
        split_points.append(start)
        last_accepted = start
    if not split_points:
        return [snippet]
    segments: list[str] = []
    last_index = 0
    for point in split_points:
        segment = snippet[last_index:point].strip()
        if segment:
            segments.append(segment)
        last_index = point
    tail_segment = snippet[last_index:].strip()
    if tail_segment:
        segments.append(tail_segment)
    return segments


def _should_break_after_emphasis(prev_lower: str, current_token: str) -> bool:
    if not prev_lower or prev_lower not in _EMPHASIS_LEADS:
        return False
    if not current_token or len(current_token) < 4:
        return False
    if not current_token.isupper():
        return False
    if current_token.lower() in _ACRONYM_EXCEPTIONS:
        return False
    return True


def _looks_like_sentence_restart(token: str) -> bool:
    if not token:
        return False
    lower = token.lower()
    if lower in _ARTICLE_CONNECTORS or lower in _SENTENCE_STARTERS or lower in _HARD_SENTENCE_BREAKERS:
        return True
    if len(token) >= 2 and token[0].isupper() and token[1:].islower():
        return True
    if len(token) == 1 and token.isupper():
        return True
    return False


def _format_interjection_sentence(head: str, tail: str) -> str:
    head_clean = (head or "").strip()
    tail_clean = (tail or "").strip()
    if not head_clean:
        return tail_clean
    if not tail_clean:
        return head_clean
    head_clean = re.sub(r"[!….,]+$", "", head_clean)
    formatted_head = head_clean[:1].upper() + head_clean[1:].lower() if head_clean else head_clean
    stripped_tail = tail_clean.lstrip()
    if stripped_tail and stripped_tail[0] in ",;:—-":
        stripped_tail = stripped_tail[1:].lstrip()
    if stripped_tail and stripped_tail[0].isalpha():
        stripped_tail = stripped_tail[0].lower() + stripped_tail[1:]
    if stripped_tail:
        return f"{formatted_head}, {stripped_tail}"
    return formatted_head


def _split_after_question_marks(text: str) -> list[str]:
    snippet = (text or "").strip()
    if not snippet:
        return []
    if "?" not in snippet:
        return [_ensure_sentence_capitalization(snippet)]
    segments: list[str] = []
    buffer: list[str] = []
    for char in snippet:
        buffer.append(char)
        if char == "?":
            segment = "".join(buffer).strip()
            if segment:
                segments.append(_ensure_sentence_capitalization(segment))
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        segments.append(_ensure_sentence_capitalization(tail))
    return segments


def _ensure_sentence_capitalization(text: str) -> str:
    if not text:
        return ""
    stripped = text.lstrip()
    leading_ws = text[: len(text) - len(stripped)]
    if stripped and stripped[0].islower():
        stripped = stripped[0].upper() + stripped[1:]
    return f"{leading_ws}{stripped}".strip()


def _fix_comma_after_short_words(text: str) -> str:
    """Insert missing comma after short interjection/affirmation words.

    Fixes patterns like 'Ok Se é normal' → 'ok, se é normal'.
    Only acts when a recognised short word is immediately followed by a space
    and an uppercase letter that clearly starts a new clause (not a proper noun).
    """
    if not text or len(text) < 4:
        return text
    # Pattern: (short_word)(space)(Uppercase rest)
    # We only fix when the uppercase word is NOT a known proper noun / name
    _PROPER_NOUNS = {"pai", "mateus", "lou", "louise", "deus", "brasil", "são"}
    match = re.match(r'^([A-Za-zÀ-ÿ]+)\s+([A-ZÀ-Ú])(.*)$', text)
    if not match:
        return text
    first_word = match.group(1)
    upper_char = match.group(2)
    rest = match.group(3)
    if first_word.lower() not in _COMMA_AFTER_SHORT_WORDS:
        return text
    # Check if the next word is a proper noun (don't lowercase those)
    next_word_match = re.match(r'^([A-Za-zÀ-ÿ]+)', upper_char + rest)
    next_word = next_word_match.group(1).lower() if next_word_match else ""
    if next_word in _PROPER_NOUNS:
        return text
    # Already has comma — don't double
    if first_word.endswith(','):
        return text
    return f"{first_word}, {upper_char.lower()}{rest}"


def _fix_comma_after_short_words_global(text: str) -> str:
    """Apply comma-after-short-word fix across the entire text, not just at the start.

    Handles patterns like "ok Se é normal" → "ok, se é normal" anywhere in the text,
    including after newlines.
    """
    if not text or len(text) < 4:
        return text
    _PROPER_NOUNS = {"pai", "mateus", "lou", "louise", "deus", "brasil", "são"}

    def _replacer(m: re.Match) -> str:
        word = m.group(1)
        if word.lower() not in _COMMA_AFTER_SHORT_WORDS:
            return m.group(0)
        upper_char = m.group(2)
        rest_start = m.group(3) if m.lastindex >= 3 else ""
        # Extract the full next word to check for proper nouns
        next_full = re.match(r'^([A-Za-zÀ-ÿ]+)', upper_char + rest_start)
        if next_full and next_full.group(1).lower() in _PROPER_NOUNS:
            return m.group(0)
        return f"{word}, {upper_char.lower()}{rest_start}"

    # Match: (short_word)(space)(Uppercase)(rest until next space or end)
    return re.sub(
        r'\b([A-Za-zÀ-ÿ]+)\s+([A-ZÀ-Ú])(\S*)',
        _replacer,
        text,
    )


def _normalize_pai_reference(text: str) -> str:
    if "Pai" not in text:
        return text
    source_text = text
    def _repl(match: re.Match) -> str:
        start = match.start()
        if source_text[:start].strip():
            return "pai"
        return "Pai"
    return re.sub(r"\bPai\b", _repl, text)


def _apply_interjection_fallback(text: str) -> str:
    match = _match_dynamic_interjection(text)
    if not match:
        return text
    head, tail = match
    segments = _compose_interjection_segments(head, tail)
    if not segments:
        return text
    if len(segments) == 1:
        return segments[0]
    return ", ".join(segment.strip() for segment in segments if segment.strip())


def _compose_interjection_segments(head: str, tail: str) -> list[str]:
    head_clean = (head or "").strip()
    tail_clean = _trim_interjection_tail(tail or "")
    if not head_clean and not tail_clean:
        return []
    if not head_clean:
        return [tail_clean] if tail_clean else []
    formatted_head = head_clean[:1].upper() + head_clean[1:].lower()
    if not tail_clean:
        return [formatted_head]
    vocative_match = _INTERJECTION_VOCATIVE_PATTERN.match(tail_clean)
    if vocative_match:
        vocative = vocative_match.group(1)
        if _looks_like_vocative_target(vocative):
            remainder = vocative_match.group(2).strip()
            segments = [_join_interjection_vocative(formatted_head, vocative)]
            if remainder:
                segments.append(remainder)
            return segments
    solo_match = _INTERJECTION_SOLO_PATTERN.match(tail_clean)
    if solo_match and _looks_like_vocative_target(solo_match.group(1)):
        return [_join_interjection_vocative(formatted_head, solo_match.group(1))]
    return [f"{formatted_head}, {tail_clean}"]


def _trim_interjection_tail(text: str) -> str:
    snippet = (text or "").lstrip()
    while snippet and snippet[0] in ",;:—-":
        snippet = snippet[1:].lstrip()
    return snippet


def _join_interjection_vocative(head: str, vocative: str) -> str:
    formatted_head = (head or "").strip()
    normalized_vocative = (vocative or "").strip()
    if not normalized_vocative:
        return formatted_head
    return f"{formatted_head} {normalized_vocative.lower()}".strip()


def _looks_like_vocative_target(word: str) -> bool:
    token = (word or "").strip().lower()
    if not token:
        return False
    if token in _NAME_STOPWORDS:
        return True
    if not token.isalpha():
        return False
    return len(token) <= 4


def _looks_like_short_titlecase(word: str) -> bool:
    if not word:
        return False
    if len(word) > 4:
        return False
    if not word[0].isupper():
        return False
    if not word[1:].islower():
        return False
    if not re.fullmatch(r"[A-Za-z]+", word):
        return False
    return word.lower() not in _NAME_STOPWORDS


def _should_merge_short_fragment(previous: str, current: str) -> bool:
    prev = (previous or "").rstrip()
    curr = (current or "").strip()
    if not prev or not curr:
        return False
    if prev[-1] in ".?!…":
        return False
    curr_tokens = curr.split()
    if len(curr_tokens) != 1:
        return False
    cleaned = _clean_token_edges(curr_tokens[0])
    if not _looks_like_short_titlecase(cleaned):
        return False
    prev_last = _clean_token_edges(prev.split()[-1])
    if not prev_last:
        return False
    return prev_last.islower()


def _normalize_short_titlecase_words(text: str) -> str:
    if not text:
        return ""
    parts = re.findall(r"\s+|\S+", text)
    prev_word = ""
    for index, part in enumerate(parts):
        if part.isspace():
            continue
        cleaned = _clean_token_edges(part)
        sentence_break = bool(re.search(r"[.?!…]$", part))
        if (
            cleaned
            and _looks_like_short_titlecase(cleaned)
            and prev_word
            and prev_word.islower()
        ):
            parts[index] = _replace_word_with_case(part, cleaned.lower())
        if cleaned:
            prev_word = cleaned.lower()
        if sentence_break:
            prev_word = ""
    return "".join(parts)


def _replace_word_with_case(token: str, replacement: str) -> str:
    if not token:
        return token
    start = 0
    end = len(token)
    while start < end and not token[start].isalnum():
        start += 1
    while end > start and not token[end - 1].isalnum():
        end -= 1
    if start >= end:
        return token
    return f"{token[:start]}{replacement}{token[end:]}"


def _ensure_question_punctuation(text: str) -> str:
    snippet = (text or "").strip()
    if not snippet:
        return ""
    if snippet.endswith("?"):
        return snippet
    if not _looks_like_question_sentence(snippet):
        return snippet
    trimmed = snippet.rstrip(".!…")
    return f"{trimmed}?"


def _looks_like_question_sentence(text: str) -> bool:
    snippet = (text or "").strip()
    if not snippet:
        return False
    if "?" in snippet:
        return True
    lowered = snippet.lower()
    tokens = [_clean_token_edges(token) for token in lowered.split()]
    tokens = [token for token in tokens if token]
    if not tokens:
        return False
    stripped_tokens = _strip_question_prefixes(tokens)
    if not stripped_tokens:
        return False
    stripped_joined = " ".join(stripped_tokens)
    if _starts_with_question_phrase(stripped_joined):
        return True
    first = stripped_tokens[0]
    if first in _QUESTION_STARTERS:
        if first == "que" and len(stripped_tokens) == 1:
            return False
        if first == "que" and len(stripped_tokens) >= 2 and stripped_tokens[1] in _QUE_LOWERCASE_WORDS:
            return False
        return True
    base = " ".join(tokens).rstrip(".!…")
    if any(base.endswith(suffix.strip()) for suffix in _QUESTION_SUFFIXES):
        return True
    if any(marker in lowered for marker in _QUESTION_MID_MARKERS):
        return True
    return False


def _strip_question_prefixes(tokens: list[str]) -> list[str]:
    if not tokens:
        return []
    index = 0
    total = len(tokens)
    while index < total and tokens[index] in _QUESTION_LEAD_INS:
        index += 1
    while index < total and tokens[index] in _QUESTION_VOCATIVES:
        index += 1
    return tokens[index:]


def _starts_with_question_phrase(text: str) -> bool:
    snippet = (text or "").strip()
    if not snippet:
        return False
    for phrase in _QUESTION_PREFIX_PHRASES:
        if snippet == phrase or snippet.startswith(f"{phrase} "):
            return True
    return False


def _normalize_comma_followups(text: str) -> str:
    if "," not in text:
        return text
    pattern = re.compile(r",\s+(" + "|".join(sorted(_COMMA_LOWERCASE_WORDS, key=len, reverse=True)) + r")\b", re.IGNORECASE)
    return pattern.sub(lambda m: f", {m.group(1).lower()}", text)


def _normalize_que_followups(text: str) -> str:
    if " que " not in text.lower():
        return text
    pattern = re.compile(r"(\b[qQ]ue\s+)(" + "|".join(_QUE_LOWERCASE_WORDS) + r")\b", re.IGNORECASE)
    return pattern.sub(lambda m: f"{m.group(1)}{m.group(2).lower()}", text)


def _normalize_de_tao_clause(text: str) -> str:
    pattern = re.compile(r"(de\s+t[ãa]o\s+)([A-ZÁ-ÚÇ][\wá-úç]+)(,\s+que)", re.IGNORECASE)
    return pattern.sub(lambda m: f"{m.group(1)}{m.group(2).lower()} que", text)


def _normalize_de_descriptor_clause(text: str) -> str:
    if not text:
        return ""
    pattern = re.compile(r"\b(de|da|do|dos|das)\s+([A-ZÁ-ÚÇ][\wá-úç]+)")

    def _repl(match: re.Match) -> str:
        prefix = match.group(1)
        word = match.group(2)
        lowered = word.lower()
        if lowered not in _DE_DESCRIPTOR_WORDS:
            return match.group(0)
        if word.isupper():
            return match.group(0).lower()
        if word[1:].islower():
            return f"{prefix} {lowered}"
        return match.group(0)

    return pattern.sub(_repl, text)


def _cleanup_soft_pause_commas(text: str) -> str:
    text = re.sub(r"(olha\s+s[óo]),\s+", lambda m: f"{m.group(1)} ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(call),\s+(é)\b", lambda m: f"{m.group(1)} {m.group(2)}", text, flags=re.IGNORECASE)
    return text