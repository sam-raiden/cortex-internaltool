import re
from typing import List

class HashtagExtractor:
    # Extracts tokens prefixed by #
    HASHTAG_PATTERN = re.compile(r'#(\w*[a-zA-Z\u0B80-\u0BFF0-9_]+\w*)')
    
    @staticmethod
    def extract_from_text(text: str) -> List[str]:
        """
        Pulls tags directly from caption raw text preserving script format natively.
        """
        if not text:
            return []
            
        tags = HashtagExtractor.HASHTAG_PATTERN.findall(text)
        # return unique preserving order
        seen = set()
        return [t for t in tags if not (t in seen or seen.add(t))]
