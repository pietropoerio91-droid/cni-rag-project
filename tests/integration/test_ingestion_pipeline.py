import pytest

from src.governance.public_data_filter import PublicDataFilter
from src.governance.quality_check import QualityChecker
from src.ingestion.cleaner import TextCleaner


class TestIngestionPipeline:
    def test_clean_remove_boilerplate(self):
        cleaner = TextCleaner()
        text = "Contenuto principale.\nTutti i diritti riservati.\nCookie Policy.\nAltro contenuto."
        result = cleaner.clean(text)
        assert "Tutti i diritti riservati" not in result
        assert "Cookie Policy" not in result
        assert "Contenuto principale" in result
        assert "Altro contenuto" in result

    def test_clean_normalize_whitespace(self):
        cleaner = TextCleaner()
        text = "Parola1\n\n\n\nParola2\n\nParola3"
        result = cleaner.clean(text)
        assert "\n\n\n" not in result

    def test_public_filter_allows_public_url(self):
        pf = PublicDataFilter()
        assert pf.is_public("https://www.cni.it/chi-siamo", "contenuto pubblico")

    def test_public_filter_blocks_private_url(self):
        pf = PublicDataFilter()
        assert not pf.is_public("https://www.cni.it/wp-admin", "contenuto")

    def test_public_filter_blocks_denied_keywords(self):
        pf = PublicDataFilter()
        assert not pf.is_public("https://www.cni.it/test", "questo documento è riservato")

    def test_quality_check_empty(self):
        qc = QualityChecker()
        ok, issues = qc.check("")
        assert not ok
        assert any("Empty" in i for i in issues)

    def test_quality_check_too_short(self):
        qc = QualityChecker()
        ok, issues = qc.check("Corto")
        assert not ok

    def test_quality_check_valid(self):
        qc = QualityChecker()
        text = (
            "Il Consiglio Nazionale degli Ingegneri promuove la formazione continua "
            "dei propri iscritti attraverso corsi accreditati e seminari tecnici. "
            "Gli iscritti all'albo devono maturare un numero minimo di crediti "
            "formativi professionali ogni anno per mantenere l'iscrizione attiva. "
            "La normativa vigente stabilisce l'obbligo di aggiornamento professionale "
            "continuo per tutti gli ingegneri operanti sul territorio nazionale."
        )
        ok, issues = qc.check(text)
        assert ok, issues
