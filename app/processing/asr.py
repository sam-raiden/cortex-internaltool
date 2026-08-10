import os
import time
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass
from faster_whisper import WhisperModel

@dataclass
class ASRResult:
    text: Optional[str]
    language: Optional[str]
    duration: float
    success: bool
    error: Optional[str]
    
class ASRProvider(ABC):
    @abstractmethod
    def extract_text(self, audio_path: str) -> ASRResult:
        pass

class FasterWhisperProvider(ASRProvider):
    _model = None

    @classmethod
    def _get_model(cls) -> WhisperModel:
        if cls._model is None:
            # We explicitly enforce CPU for this POC to avoid CUDA setup dependencies in python tests
            cls._model = WhisperModel("tiny", device="cpu", compute_type="int8")
        return cls._model

    def extract_text(self, audio_path: str) -> ASRResult:
        start = time.time()
        try:
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Media file not found: {audio_path}")
                
            model = self._get_model()
            
            # Transcription executes audio stripping natively
            segments, info = model.transcribe(audio_path, beam_size=5)
            
            # Segments is a generator, so we must iterate it entirely to finish ASR
            transcript_parts = []
            for s in segments:
                transcript_parts.append(s.text.strip())
                
            duration = round((time.time() - start), 2)
            text = " ".join(transcript_parts)
            
            return ASRResult(
                text=text if text else None,
                language=info.language,
                duration=duration,
                success=True,
                error=None
            )
        except Exception as e:
            duration = round((time.time() - start), 2)
            return ASRResult(
                text=None,
                language=None,
                duration=duration,
                success=False,
                error=str(e)
            )
