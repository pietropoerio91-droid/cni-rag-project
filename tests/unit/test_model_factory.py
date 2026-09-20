import logging

import pytest

from src.core import model_factory
from src.core.model_factory import ModelFactory, prefissi_per_modello


@pytest.fixture
def yaml_config(monkeypatch):
    monkeypatch.setattr(
        model_factory.ConfigLoader,
        "get_rag_config",
        classmethod(lambda cls: {"embedding": {"model_name": "modello-yaml"}}),
    )


def test_senza_ambiente_vale_il_yaml(yaml_config, monkeypatch):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    assert ModelFactory.resolve_embedding_model() == ("modello-yaml", "yaml")


def test_ambiente_prevale_e_viene_segnalato(yaml_config, monkeypatch, caplog):
    monkeypatch.setenv("EMBEDDING_MODEL", "modello-ambiente")
    with caplog.at_level(logging.WARNING):
        assert ModelFactory.resolve_embedding_model() == ("modello-ambiente", "ambiente")
    assert "sovrascrive" in caplog.text


def test_ambiente_uguale_al_yaml_non_avvisa(yaml_config, monkeypatch, caplog):
    monkeypatch.setenv("EMBEDDING_MODEL", "modello-yaml")
    with caplog.at_level(logging.WARNING):
        ModelFactory.resolve_embedding_model()
    assert caplog.text == ""


@pytest.mark.parametrize("nome,atteso", [
    ("intfloat/multilingual-e5-small", ("query: ", "passage: ")),
    ("paraphrase-multilingual-MiniLM-L12-v2", ("", "")),
    ("all-MiniLM-L6-v2", ("", "")),
])
def test_prefissi_per_famiglia(nome, atteso):
    assert prefissi_per_modello(nome) == atteso
