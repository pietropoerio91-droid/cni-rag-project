import pytest

from src.rag.query_classifier import QueryClassifier


@pytest.fixture
def classifier():
    return QueryClassifier()


def test_classify_normativa(classifier):
    result = classifier.classify("Qual è la normativa vigente per gli ingegneri?")
    assert result == "normativa"


def test_classify_organi(classifier):
    result = classifier.classify("Chi è il presidente del CNI?")
    assert result == "organi"


def test_classify_formazione(classifier):
    result = classifier.classify("Quanti CFP servono per l'aggiornamento?")
    assert result == "formazione"


def test_classify_generico(classifier):
    result = classifier.classify("Come sta il tempo oggi?")
    assert result == "generico"


def test_classify_contatti(classifier):
    result = classifier.classify("Qual è l'indirizzo email del CNI?")
    assert result == "contatti"


def test_classify_case_insensitive(classifier):
    result = classifier.classify("NORME E REGOLAMENTI")
    assert result == "normativa"
