import pytest
from reviewer.parser import parse_pass, extract_json, ParseError


SOURCE = "Первое предложение. Второе.\n\nВторой абзац."


def test_extract_json_from_fenced_block():
    raw = 'text before\n```json\n{"findings":[]}\n```\ntext after'
    assert extract_json(raw) == {"findings": []}


def test_extract_json_missing_raises():
    with pytest.raises(ParseError):
        extract_json("no json here")


def test_parse_pass_valid_finding():
    raw = '```json\n{"findings":[{"quote":"Первое предложение.","paragraph":1,"sentence":1,"category":"facts","defect":"x","fix":"y"}]}\n```'
    findings, hall = parse_pass(raw, "p1", SOURCE, max_paragraph=2)
    assert len(findings) == 1
    assert findings[0].quote == "Первое предложение."
    assert hall == 0


def test_parse_pass_hallucinated_quote_excluded():
    raw = '```json\n{"findings":[{"quote":"Нет такого текста.","paragraph":1,"sentence":1,"category":"facts","defect":"x","fix":"y"}]}\n```'
    findings, hall = parse_pass(raw, "p1", SOURCE, max_paragraph=2)
    assert findings == []
    assert hall == 1


def test_parse_pass_wrong_category_dropped():
    raw = '```json\n{"findings":[{"quote":"Первое предложение.","paragraph":1,"sentence":1,"category":"reader","defect":"x","fix":"y"}]}\n```'
    findings, hall = parse_pass(raw, "p1", SOURCE, max_paragraph=2)
    assert findings == []


def test_parse_pass_out_of_range_dropped():
    raw = '```json\n{"findings":[{"quote":"Первое предложение.","paragraph":99,"sentence":1,"category":"facts","defect":"x","fix":"y"}]}\n```'
    findings, _ = parse_pass(raw, "p1", SOURCE, max_paragraph=2)
    assert findings == []


def test_parse_pass_dedupes_within_pass():
    item = '{"quote":"Второй абзац.","paragraph":2,"sentence":null,"category":"logic","defect":"a","fix":"b"}'
    raw = f'```json\n{{"findings":[{item},{item}]}}\n```'
    findings, _ = parse_pass(raw, "p2", SOURCE, max_paragraph=2)
    assert len(findings) == 1
