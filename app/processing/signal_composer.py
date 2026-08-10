import re
import difflib
from typing import List, Dict, Tuple, Optional
from datetime import datetime

from app.models.schema import ContentSource, ProcessedSignal
from app.processing.caption_purifier import CaptionPurifier
from app.processing.normalizer import TextNormalizer
from app.processing.language_detector import LanguageDetector

class SourceQualityEvaluator:
    """Evaluates the structural strength and value of independent content streams"""
    
    @staticmethod
    def evaluate(sources: List[ContentSource]) -> str:
        if not sources:
            return "INSUFFICIENT"
            
        has_caption = False
        has_asr = False
        has_ocr = False
        
        valid_lengths = []
        
        for s in sources:
            text = s.raw_text or ""
            text = text.strip()
            
            # Simple Emoji / Short string check bounding signals 
            if len(text) < 4 and not any(c.isalnum() for c in text):
                continue
                
            if s.source_type == "CAPTION" and len(text) > 10:
                has_caption = True
            elif s.source_type == "ASR" and len(text) > 10:
                has_asr = True
            elif s.source_type == "OCR" and len(text) > 10:
                has_ocr = True
                
            valid_lengths.append(len(text))
            
        if not valid_lengths:
            return "INSUFFICIENT"
            
        if has_caption and (has_asr or has_ocr):
            return "HIGH"
        elif has_caption:
            return "MEDIUM"
        elif has_asr:
            return "MEDIUM"
        elif has_ocr:
            return "LOW"
            
        return "INSUFFICIENT"

class SignalTextComposer:
    def __init__(self):
        self.purifier = CaptionPurifier()
        self.normalizer = TextNormalizer()
        self.detector = LanguageDetector()
    
    def calculate_similarity(self, a: str, b: str) -> float:
        """Deterministic overlap overlap token matching natively"""
        if not a or not b:
            return 0.0
        matcher = difflib.SequenceMatcher(None, a.lower(), b.lower())
        return matcher.ratio()
        
    def compose(self, post_id: int, sources: List[ContentSource]) -> ProcessedSignal:
        quality = SourceQualityEvaluator.evaluate(sources)
        
        if quality == "INSUFFICIENT":
            # Still record insufficient signals minimally
            return ProcessedSignal(
                post_id=post_id,
                canonical_text="",
                language="unknown",
                signal_quality="INSUFFICIENT",
                processing_status="INSUFFICIENT_SIGNAL",
                source_metadata={"source_ids": [s.id for s in sources]}
            )
            
        # Prioritize
        caption_source = None
        asr_source = None
        ocr_source = None
        
        for s in sources:
            if s.source_type == "CAPTION":
                caption_source = s
            elif s.source_type == "ASR":
                asr_source = s
            elif s.source_type == "OCR":
                ocr_source = s
                
        canonical_parts = []
        retained_sources = []
        
        # Base processing
        base_text = ""
        if caption_source and caption_source.raw_text:
            purified = self.purifier.purify(caption_source.raw_text)
            if purified is None:
                purified = caption_source.raw_text
                
            base_text = self.normalizer.normalize(purified)
            canonical_parts.append(base_text)
            retained_sources.append(caption_source.id)
                
        # Deduplication Overlap Check
        if asr_source and asr_source.raw_text:
            asr_text = self.normalizer.normalize(asr_source.raw_text)
            if asr_text:
                if not canonical_parts:
                    canonical_parts.append(asr_text)
                    retained_sources.append(asr_source.id)
                else:
                    sim = self.calculate_similarity(canonical_parts[0], asr_text)
                    if sim >= 0.65:
                        if len(asr_text) > len(canonical_parts[0]):
                            canonical_parts[0] = asr_text
                            retained_sources.append(asr_source.id)
                    else:
                        canonical_parts.append(asr_text)
                        retained_sources.append(asr_source.id)
                        
        if ocr_source and ocr_source.raw_text:
            ocr_text = self.normalizer.normalize(ocr_source.raw_text)
            if ocr_text:
                if not canonical_parts:
                    canonical_parts.append(ocr_text)
                    retained_sources.append(ocr_source.id)
                else:
                    max_sim = max([self.calculate_similarity(p, ocr_text) for p in canonical_parts])
                    if max_sim >= 0.65:
                        for i, p in enumerate(canonical_parts):
                            if self.calculate_similarity(p, ocr_text) >= 0.65 and len(ocr_text) > len(p):
                                canonical_parts[i] = ocr_text
                                retained_sources.append(ocr_source.id)
                    elif max_sim >= 0.2:
                        canonical_parts.append(ocr_text)
                        retained_sources.append(ocr_source.id)
                    
        canonical_text = " ".join(canonical_parts).strip()
        language = self.detector.detect(canonical_text)
        
        return ProcessedSignal(
            post_id=post_id,
            canonical_text=canonical_text,
            language=language,
            signal_quality=quality,
            processing_status="COMPOSED",
            processor_version="v3_stage8",
            source_metadata={
                "all_source_ids": [s.id for s in sources],
                "retained_source_ids": retained_sources
            }
        )
