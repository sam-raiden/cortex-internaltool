import re
from typing import Optional

class CaptionPurifier:
    # Match patterns for OG standard prefix
    OG_PREFIX_PATTERN = re.compile(r'(?:on\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}|on\s+Instagram):\s+"([\s\S]*)$', re.IGNORECASE)
    
    @staticmethod
    def purify(raw_og_text: str) -> Optional[str]:
        """
        Safely extracts underlying Instagram textual caption skipping the canonical OG metadata prefixes.
        Handles unicode, multiline, internal quotes, and truncated payloads.
        Returns None if extraction is malformed or uncertain.
        """
        if not raw_og_text or not raw_og_text.strip():
            return None
            
        text = raw_og_text.strip()
        
        # Test Format
        m1 = CaptionPurifier.OG_PREFIX_PATTERN.search(text)
        if m1:
            extracted = m1.group(1)
            # Safe truncation mapping: canonical wrappers put `"`, if it ends with `"`, remove exactly one.
            # Instagram often appends `.` after the `"` in og:description.
            extracted = re.sub(r'"\.?$', '', extracted)
            return extracted.strip() if extracted.strip() else ""
            
        # If it doesn't match standard constraints, it's UNCERTAIN.
        # Natively mark caption extraction as uncertain rather than silently storing polluted data.
        return None
