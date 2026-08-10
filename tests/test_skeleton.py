import os

def test_project_structure():
    assert os.path.exists("app")
    assert os.path.exists("config")
    assert os.path.exists("scripts")
    assert os.path.exists("tests")
    assert os.path.exists("output")
    assert os.path.exists("migrations")
