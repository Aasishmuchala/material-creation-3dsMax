import re

from material_inspector.core.model import Finding, FixAction, Severity
from material_inspector.core.titles import HEADLINES, fix_sentence, group, headline

CONTRACT_IDS = (
    "R001 R002 R003 R004 R005 R006 R007 R008 R010 R011 R012 R013 R014 R015 R016 R017 R018 R020 R999 "
    "M001 M002 M003 M004 M005 M006 M007 M008 M009 M010 M012 M013 M900"
).split()


def test_every_contract_id_present():
    assert set(CONTRACT_IDS) <= set(HEADLINES)


def test_headline_copy_rules():
    for rid, (text, fix) in HEADLINES.items():
        assert not text.endswith("."), rid
        assert 0 < len(text) <= 70, rid
        assert "—" not in text + fix and "–" not in text + fix, rid
        assert not re.search(r"\b[RM]\d{3}\b", text), rid


def test_unknown_falls_back_to_message():
    f = Finding("X123", Severity.WARNING, "m", "raw message")
    assert headline(f) == "raw message"
    assert fix_sentence(f) == ""
    g = Finding("X123", Severity.WARNING, "m", "raw", fix=FixAction("k", "t", description="do it"))
    assert fix_sentence(g) == "do it"


def test_fix_sentence_and_group():
    fix = FixAction("k", "t")
    assert fix_sentence(Finding("R001", Severity.ERROR, "m", "x", fix=fix)) == "Reads it as linear data"
    assert fix_sentence(Finding("R004", Severity.ERROR, "m", "x")) == "Relink the file"
    assert fix_sentence(Finding("M008", Severity.INFO, "m", "x")) == ""
    assert group(Finding("R001", Severity.ERROR, "m", "x")) == "Will render wrong"
    assert group(Finding("R015", Severity.WARNING, "m", "x")) == "Worth a look"
    assert group(Finding("M008", Severity.INFO, "m", "x")) == "Notes"
