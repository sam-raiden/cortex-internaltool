import re
import unicodedata

class TextNormalizer:
    URL_PATTERN = re.compile(r'https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)')
    
    @staticmethod
    def normalize(text: str) -> str:
        """
        Deterministically canonicalize raw string retaining emojis, tamil slang, hashtags.
        - Removes URLs seamlessly.
        - Normalizes Unicode string blocks.
        - Collapses repeated whitespacing/newlines.
        """
        if not text:
            return ""
            
        # 1. Unicode normalisation (NFC)
        text = unicodedata.normalize('NFC', text)
        
        # 2. Strip URLs (they pollute embedding engines conceptually)
        text = TextNormalizer.URL_PATTERN.sub('', text)
        
        # 3. Collapse whitespaces and excessive newlines
        text = re.sub(r'\s+', ' ', text)
        
        # 4. Strip boundary whitespaces
        return text.strip()
