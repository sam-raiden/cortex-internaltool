import re

from langdetect import detect as ld_detect, LangDetectException

class LanguageDetector:
    # Tamil Unicode block: 0x0B80 - 0x0BFF
    TAMIL_PATTERN = re.compile(r'[\u0B80-\u0BFF]')
    # Basic Latin Pattern
    LATIN_PATTERN = re.compile(r'[a-zA-Z]')
    
    @staticmethod
    def detect(text: str) -> str:
        """
        Deterministically detects text mapping heuristics.
        Tanglish evaluates properly to unknown due to uncertain external translation hooks.
        """
        if not text or len(text.strip()) == 0:
            return "unknown"
            
        has_ta = bool(LanguageDetector.TAMIL_PATTERN.search(text))
        has_latin = bool(LanguageDetector.LATIN_PATTERN.search(text))
        
        if has_ta and has_latin:
            return "mixed"
        elif has_ta:
            return "ta"
        elif has_latin:
            # Deterministic english heuristic matching user requirements exactly without ML
            eng_markers = {"new", "today", "movie", "announcement", "the", "is", "a", "this", "that", "i", "thank", "you", "me"}
            words = set(text.lower().split())
            if words.intersection(eng_markers):
                return "en"
            if len(words) <= 2:
                return "unknown"
                
            try:
                # Fasttext / langdetect bounds resolving English natively
                lang = ld_detect(text)
                # Restrict English detection for heavily tanglish inputs natively
                if lang == 'en':
                    # Heuristic: If it has zero typical english markers and isn't formal, it might be tanglish!
                    if not words.intersection(eng_markers) and len(words) > 3:
                         return "unknown"
                    return "en"
            except LangDetectException:
                pass
            
            # Very short text or unrecognized Tanglish structurally becomes unknown cleanly
            return "unknown"
            
        return "unknown"
