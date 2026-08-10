from typing import List
from app.processing.models import ContentSource

class TextAssembler:
    @staticmethod
    def assemble(sources: List[ContentSource]) -> str:
        """
        Assembles robust content sources into a single raw deterministic string payload.
        Order conceptually: Caption -> OCR -> Transcript -> Hashtags.
        """
        blocks = []
        # Sort or strictly assemble based on semantic block rules
        for src in sources:
            if src.text and src.text.strip():
                blocks.append(src.text.strip())
        
        return "\n\n".join(blocks)
