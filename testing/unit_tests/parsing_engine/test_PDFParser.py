# testing/unit_tests/parsing_engine/test_pdf_parser.py

import pytest
from unittest.mock import MagicMock, patch, ANY
from parsing_engine.pdf_parser import PDFParser
import pdfplumber
import fitz
import logging

class TestPDFParser:
    @pytest.fixture
    def mock_config(self):
        return {
            "use_ocr": False,
            "layout_analysis": True,
            "section_rules": {}
        }

    @pytest.fixture
    def parser(self, mock_config):
        return PDFParser(mock_config)

    @patch("pdfplumber.open")
    def test_extract_text_success(self, mock_pdf_open, parser):
        # Setup mock PDF
        mock_pdf = MagicMock()
        mock_pdf.metadata = {"author": "Test Author"}
        
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page text"
        mock_page.extract_tables.return_value = [["Table data"]]
        mock_page.images = [{"name": "img1.png"}]
        mock_page.page_number = 1
        
        mock_pdf.pages = [mock_page]
        mock_pdf_open.return_value.__enter__.return_value = mock_pdf

        # Execute
        result = parser._extract_text("dummy.pdf")
        
        # Verify
        assert result["raw_text"] == "Page text\n\n"
        assert result["metadata"] == {"author": "Test Author"}
        assert result["tables"] == [{"page": 1, "data": ["Table data"]}]
        assert result["images"] == [{"name": "img1.png"}]

    @patch("pdfplumber.open")
    def test_extract_text_with_ocr_fallback(self, mock_pdf_open, mock_config):
        # Setup to throw exception and enable OCR
        mock_config["use_ocr"] = True
        parser = PDFParser(mock_config)
        mock_pdf_open.side_effect = Exception("PDF error")
        
        with patch("fitz.open") as mock_fitz, \
             patch("PIL.Image.open") as mock_pil, \
             patch("pytesseract.image_to_string") as mock_ocr:
            
            # Setup OCR mocks
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 1
            mock_page = MagicMock()
            mock_pix = MagicMock()
            mock_pix.tobytes.return_value = b"image_data"
            mock_page.get_pixmap.return_value = mock_pix
            mock_doc.load_page.return_value = mock_page
            mock_fitz.return_value = mock_doc
            mock_ocr.return_value = "OCR text"
            
            # Execute
            result = parser._extract_text("dummy.pdf")
            
            # Verify OCR was used
            assert result["raw_text"] == "OCR text\n\n"
            mock_ocr.assert_called_once()

    @patch("pdfplumber.open")
    def test_extract_text_failure_no_ocr(self, mock_pdf_open, parser):
        # Setup to throw exception without OCR
        mock_pdf_open.side_effect = Exception("PDF error")
        
        # Execute
        result = parser._extract_text("dummy.pdf")
        
        # Verify
        assert result["raw_text"] == ""
        assert result["tables"] == []
        assert "metadata" in result

    def test_analyze_layout(self, parser):
        # Setup
        mock_layout = {"pages": [{"page": 1}]}
        parser.layout_analyzer.analyze = MagicMock(return_value=mock_layout)
        
        # Execute
        result = parser._analyze_layout("dummy.pdf")
        
        # Verify
        assert result == mock_layout
        parser.layout_analyzer.analyze.assert_called_once_with("dummy.pdf")

    def test_integrate_layout(self, parser):
        # Setup input data
        text_data = {
            "raw_text": "Full text",
            "metadata": {"author": "Test"},
            "tables": [{"page": 1, "data": "table"}]
        }
        
        layout_data = {
            "text_blocks": [
                {"text": "Block1", "position": [0, 0], "font": "Arial"}
            ]
        }
        
        # Execute
        result = parser._integrate_layout(text_data, layout_data)
        
        # Verify
        assert result["raw_text"] == "Full text"
        assert result["metadata"] == {"author": "Test"}
        assert len(result["content"]) == 2
        assert result["content"][0] == {
            "text": "Block1",
            "type": "text",
            "position": [0, 0],
            "font": "Arial"
        }
        assert result["content"][1] == {
            "type": "table",
            "data": "table",
            "page": 1
        }

    @patch.object(PDFParser, "_extract_text")
    @patch.object(PDFParser, "_analyze_layout")
    @patch.object(PDFParser, "_integrate_layout")
    def test_parse_with_layout(
        self, 
        mock_integrate, 
        mock_analyze, 
        mock_extract,
        parser
    ):
        # Setup mocks
        mock_extract.return_value = {"raw_text": "text"}
        mock_analyze.return_value = {"layout": "data"}
        mock_integrate.return_value = {"integrated": "data"}
        
        # Mock section detector with correct structure
        expected_result = {
            "sections": {
                "summary": {"content": "text"},
                "experience": {"content": "data"}
            },
            "raw": "text",
            "metadata": {}
        }
        parser.section_detector.detect_sections = MagicMock(return_value=expected_result)
        
        # Execute
        result = parser.parse("dummy.pdf")
        
        # Verify
        assert result == expected_result
        mock_extract.assert_called_once_with("dummy.pdf")
        mock_analyze.assert_called_once_with("dummy.pdf")
        mock_integrate.assert_called_with({"raw_text": "text"}, {"layout": "data"})
        parser.section_detector.detect_sections.assert_called_with({"integrated": "data"})

    @patch.object(PDFParser, "_extract_text")
    def test_parse_without_layout(self, mock_extract, mock_config):
        # Disable layout analysis
        mock_config["layout_analysis"] = False
        parser = PDFParser(mock_config)
        
        # Setup mock
        mock_extract.return_value = {"raw_text": "text"}
        
        # Execute
        result = parser.parse("dummy.pdf")
        
        # Verify
        assert result == {"raw_text": "text"}
        mock_extract.assert_called_once_with("dummy.pdf")

    @patch("pdfplumber.open")
    def test_table_extraction(self, mock_pdf_open, parser):
        # Setup mock PDF with tables
        mock_pdf = MagicMock()
        mock_pdf.metadata = {}
        
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_page.extract_tables.return_value = [
            [["Header1", "Header2"], ["Data1", "Data2"]],
            [["Single"]]
        ]
        mock_page.page_number = 1
        mock_pdf.pages = [mock_page]
        mock_pdf_open.return_value.__enter__.return_value = mock_pdf

        # Execute
        result = parser._extract_text("dummy.pdf")
        
        # Verify
        assert len(result["tables"]) == 2
        assert result["tables"][0] == {
            "page": 1,
            "data": [["Header1", "Header2"], ["Data1", "Data2"]]
        }
        assert result["tables"][1] == {
            "page": 1,
            "data": [["Single"]]
        }

    @patch("pdfplumber.open")
    def test_multiple_page_extraction(self, mock_pdf_open, parser):
        # Setup mock PDF with multiple pages
        mock_pdf = MagicMock()
        mock_pdf.metadata = {}
        
        # Create two pages
        page1 = MagicMock()
        page1.extract_text.return_value = "Page1"
        page1.page_number = 1
        
        page2 = MagicMock()
        page2.extract_text.return_value = "Page2"
        page2.page_number = 2
        
        mock_pdf.pages = [page1, page2]
        mock_pdf_open.return_value.__enter__.return_value = mock_pdf

        # Execute
        result = parser._extract_text("dummy.pdf")
        
        # Verify
        assert result["raw_text"] == "Page1\n\nPage2\n\n"

    def test_ocr_fallback_without_dependencies(self, mock_config, caplog):
        # Setup to throw exception and enable OCR
        mock_config["use_ocr"] = True
        parser = PDFParser(mock_config)
        
        with patch("pdfplumber.open", side_effect=Exception("PDF error")), \
             patch("fitz.open") as mock_fitz:
            
            # Simulate import error
            with patch.dict("sys.modules", {"pytesseract": None, "PIL": None}):
                # Execute
                result = parser._extract_text("dummy.pdf")
                
                # Verify
                assert "OCR fallback requires pytesseract and PIL" in caplog.text
                assert result["raw_text"] == ""

    def test_empty_pdf_handling(self, parser):
        # Setup
        parser._extract_text = MagicMock(return_value={
            "raw_text": "", 
            "tables": [],
            "metadata": {}
        })
        
        # Mock layout analyzer to avoid file access
        parser.layout_analyzer.analyze = MagicMock(return_value={"pages": []})
        
        # Mock section detector with correct structure
        mock_section_result = {
            "sections": {},  # Change from [] to {}
            "raw": "",
            "metadata": {}
        }
        parser.section_detector.detect_sections = MagicMock(return_value=mock_section_result)
        
        # Execute
        result = parser.parse("empty.pdf")
        
        # Verify
        assert result == mock_section_result