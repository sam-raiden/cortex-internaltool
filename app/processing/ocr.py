import os
import time
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass

import pytesseract
from PIL import Image

@dataclass
class OCRResult:
    text: Optional[str]
    confidence: Optional[float]
    language: Optional[str]
    success: bool
    error: Optional[str]

class OCRProvider(ABC):
    @abstractmethod
    def extract_text(self, image_path: str) -> OCRResult:
        pass

class TesseractOCRProvider(OCRProvider):
    def __init__(self, tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        
    def extract_text(self, image_path: str) -> OCRResult:
        if not os.path.exists(image_path):
            return OCRResult(text=None, confidence=None, language=None, success=False, error="Image not found")
            
        try:
            # We configure tesseract to detect cleanly and map Tamil / English explicitly
            img = Image.open(image_path)
            
            # Use PSM 3 (Fully automatic page segmentation) and map tam+eng
            text = pytesseract.image_to_string(img, lang="tam+eng")
            
            # Pytesseract confidence requires image_to_data mapping, which is heavier.
            # We fulfill the API but default confidence to None if simple Extraction succeeds 
            # Or we can natively map data arrays. For POC, text is sufficient.
            
            return OCRResult(
                text=text.strip() if text else None,
                confidence=None,
                language="tam+eng",
                success=True,
                error=None
            )
        except Exception as e:
            return OCRResult(text=None, confidence=None, language=None, success=False, error=str(e))
