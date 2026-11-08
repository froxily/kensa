from pathlib import Path

def test_archive_name():
    assert Path('archive').name == 'archive'

def test_suffix():
    assert Path('notes.txt').suffix == '.txt'

def test_parent():
    assert Path('archive/notes.txt').parent.name == 'archive'
