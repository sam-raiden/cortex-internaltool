import pytest
from app.models.schema import ContentSource
from app.processing.signal_composer import SignalTextComposer, SourceQualityEvaluator
from app.processing.embeddings import EmbeddingProvider

def test_source_quality_evaluator():
    # Empty
    assert SourceQualityEvaluator.evaluate([]) == "INSUFFICIENT"
    
    # Just emoji
    assert SourceQualityEvaluator.evaluate([
        ContentSource(source_type="CAPTION", raw_text="😂")
    ]) == "INSUFFICIENT"
    
    # OCR ONLY
    assert SourceQualityEvaluator.evaluate([
        ContentSource(source_type="OCR", raw_text="Some background signs today")
    ]) == "LOW"
    
    # CAPTION ONLY
    assert SourceQualityEvaluator.evaluate([
        ContentSource(source_type="CAPTION", raw_text="Here is a valid caption for the post")
    ]) == "MEDIUM"
    
    # CAPTION + ASR
    assert SourceQualityEvaluator.evaluate([
        ContentSource(source_type="CAPTION", raw_text="Here is a valid caption for the post"),
        ContentSource(source_type="ASR", raw_text="vijay announces new things")
    ]) == "HIGH"

def test_canonical_composition():
    composer = SignalTextComposer()
    
    caption_txt = "Vijay announces TVK district meeting #TVKVijay"
    ocr_txt = "TVK DISTRICT MEETING"
    asr_txt = "Vijay will meet district secretaries tomorrow"
    
    sources = [
        ContentSource(source_type="CAPTION", raw_text=caption_txt, id=1),
        ContentSource(source_type="OCR", raw_text=ocr_txt, id=2),
        ContentSource(source_type="ASR", raw_text=asr_txt, id=3)
    ]
    
    signal = composer.compose(post_id=99, sources=sources)
    
    # The ASR adds new info "district secretaries tomorrow"
    # But the OCR is heavily overlapping with caption, so it should be skipped
    assert "district secretaries tomorrow" in signal.canonical_text
    # Should maintain hashtag
    assert "#TVKVijay" in signal.canonical_text
    
    # Check retained Source IDs - OCR (2) should be excluded
    metadata = signal.source_metadata
    assert 1 in metadata["retained_source_ids"]
    assert 3 in metadata["retained_source_ids"]
    
def test_multilingual_preservation():
    composer = SignalTextComposer()
    mixed = "தமிழக அரசியல் குறித்து Vijay இன்று பேசினார்"
    
    signal = composer.compose(post_id=99, sources=[
        ContentSource(source_type="CAPTION", raw_text=mixed, id=1)
    ])
    
    assert signal.language == "mixed"
    assert "தமிழக அரசியல் குறித்து Vijay" in signal.canonical_text
    
@pytest.fixture(scope="session")
def embedding_provider():
    return EmbeddingProvider()

def test_embedding_dimensions_and_normalized(embedding_provider):
    vec = embedding_provider.embed("Testing standard vector outputs")
    
    assert len(vec) == 384
    # Ensure it's not all zeros
    assert sum(v * v for v in vec) > 0.9  # Normalized L2 should equal ~1.0

def test_multilingual_semantic_similarity(embedding_provider):
    # Validating Tamil/English semantic clustering properly
    t1 = "விஜய் தமிழக அரசியல் குறித்து பேசினார்"
    t2 = "தமிழக அரசியல் பற்றி விஜய்யின் பேச்சு"
    t3 = "சென்னை நகரில் கனமழை பெய்தது"
    
    vec1 = embedding_provider.embed(t1)
    vec2 = embedding_provider.embed(t2)
    vec3 = embedding_provider.embed(t3)
    
    # Calculate Cosine similarity
    import numpy as np
    def cos_sim(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        
    sim_1_2 = cos_sim(vec1, vec2)
    sim_1_3 = cos_sim(vec1, vec3)
    
    # A and B should be Semantically similar
    assert sim_1_2 > sim_1_3
    assert sim_1_2 > 0.6
