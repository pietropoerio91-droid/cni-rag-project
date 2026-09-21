import pytest

from src.governance import pii_filter as modulo
from src.governance.pii_filter import PIIFilter


def _config(monkeypatch, valore):
    monkeypatch.setattr(modulo.ConfigLoader, "get_rag_config", classmethod(lambda cls: valore))


def test_senza_indicazioni_il_filtro_e_attivo(monkeypatch):
    _config(monkeypatch, {})
    assert PIIFilter.from_config().enabled is True


def test_la_configurazione_puo_disattivarlo(monkeypatch):
    _config(monkeypatch, {"governance": {"pii_filter": {"enabled": False}}})
    assert PIIFilter.from_config().enabled is False


def test_attivo_maschera_email_e_telefono():
    out = PIIFilter(enabled=True).filter("Scrivi a segreteria@cni.it o chiama +39.06.6976701")
    assert "segreteria@cni.it" not in out and "6976701" not in out


def test_disattivato_lascia_il_testo_invariato():
    testo = "segreteria@cni.it, telefono +39.06.6976701, codice fiscale 80057570584"
    assert PIIFilter(enabled=False).filter(testo) == testo


def test_limite_noto_il_codice_fiscale_dell_ente_viene_letto_come_telefono():
    # Documenta il motivo per cui il filtro e' disattivato su un corpus pubblico.
    assert "80057570584" not in PIIFilter(enabled=True).filter("Il codice fiscale del CNI e' 80057570584.")
