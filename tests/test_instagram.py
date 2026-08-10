import pytest
from app.collectors.instagram.parser import InstagramParser

def test_extract_post_id():
    assert InstagramParser.extract_post_id_from_url("https://www.instagram.com/p/CXYZB_123/") == "CXYZB_123"
    assert InstagramParser.extract_post_id_from_url("https://www.instagram.com/reel/CXYZB_123/?igsh=abcd") == "CXYZB_123"
    assert InstagramParser.extract_post_id_from_url("https://instagram.com/p/ABC/?img_index=1") == "ABC"
    assert InstagramParser.extract_post_id_from_url("https://unrelated.com/p/xyz") == "xyz"
    assert InstagramParser.extract_post_id_from_url("https://www.instagram.com/username/") is None
