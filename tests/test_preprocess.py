from reviewer.preprocess import number_text, normalize, strip_markers


def test_number_text_basic():
    txt = "First sentence. Second one.\n\nSecond paragraph here."
    numbered, index = number_text(txt)
    assert "[Paragraph 1]" in numbered
    assert "[1.1]" in numbered and "[1.2]" in numbered
    assert "[Paragraph 2]" in numbered
    assert index[1] == ["First sentence.", "Second one."]
    assert index[2] == ["Second paragraph here."]


def test_normalize_quotes_and_spaces():
    assert normalize("  «Тест» ") == '"тест"'
    assert normalize("a  b\tc") == "a b c"


def test_strip_markers_roundtrip():
    txt = "One. Two.\n\nThree."
    numbered, _ = number_text(txt)
    stripped = strip_markers(numbered)
    assert "[Paragraph" not in stripped
    assert "One." in stripped and "Three." in stripped
