# testing/unit_tests/parsing_engine/test_layout_analyzer.py

import unittest
from unittest.mock import MagicMock, patch, call
import fitz  # PyMuPDF
from parsing_engine.layout_analyzer import LayoutAnalyzer

class TestLayoutAnalyzer(unittest.TestCase):
    def setUp(self):
            self.analyzer = LayoutAnalyzer()
            self.mock_doc = MagicMock(spec=fitz.Document)
            self.mock_page = MagicMock(spec=fitz.Page)
            
            # Setup mock document structure
            self.mock_doc.__len__.return_value = 2
            self.mock_doc.load_page.side_effect = [self.mock_page, self.mock_page]
            
            # Setup mock page structure
            self.page_dict_1 = {
                "width": 600,
                "height": 800,
                "blocks": [
                    self._create_text_block(bbox=(0, 0, 600, 100), spans=[
                        {"text": "Heading 1", "font": "Arial-Bold", "size": 16},
                        {"text": " content", "font": "Arial", "size": 12}
                    ]),
                    self._create_image_block(bbox=(0, 100, 300, 200)),
                    self._create_text_block(bbox=(0, 200, 600, 300), spans=[
                        {"text": "Paragraph text", "font": "Times-Roman", "size": 10}
                    ])
                ]
            }
            
            self.page_dict_2 = {
                "width": 600,
                "height": 800,
                "blocks": [
                    self._create_text_block(bbox=(0, 0, 600, 50), spans=[
                        {"text": "Footer text", "font": "Arial", "size": 8}
                    ])
                ]
            }

            self.mock_page.get_text.side_effect = [self.page_dict_1, self.page_dict_2]

    def _create_text_block(self, bbox, spans):
        """Create a mock text block dictionary"""
        return {
            "type": 0,
            "bbox": bbox,
            "lines": [{"spans": spans}]
        }

    def _create_image_block(self, bbox):
        """Create a mock image block dictionary"""
        return {
            "type": 1,
            "bbox": bbox,
            "width": bbox[2] - bbox[0],
            "height": bbox[3] - bbox[1]
        }

    @patch("parsing_engine.layout_analyzer.fitz.open")
    def test_analyze(self, mock_fitz_open):
        # Setup
        mock_fitz_open.return_value = self.mock_doc
        
        # Execute
        layout = self.analyzer.analyze("dummy.pdf")
        
        # Verify document structure
        self.assertEqual(len(layout["pages"]), 2)
        self.assertEqual(len(layout["fonts"]), 4)  # 4 unique font keys
        
        # Verify page 1 structure
        page1 = layout["pages"][0]
        self.assertEqual(page1["page"], 0)
        self.assertEqual(page1["width"], 600)
        self.assertEqual(page1["height"], 800)
        # TEXT BLOCKS ONLY (image block is separate)
        self.assertEqual(len(page1["blocks"]), 2)  # FIXED: Only text blocks
        self.assertEqual(len(page1["fonts"]), 3)    # From two text blocks
        self.assertEqual(len(page1["images"]), 1)   # One image block
        
        # Verify page 2 structure
        page2 = layout["pages"][1]
        self.assertEqual(page2["page"], 1)
        self.assertEqual(len(page2["blocks"]), 1)
        
        # Verify font aggregation
        self.assertIn("Arial-Bold_16", layout["fonts"])
        self.assertIn("Times-Roman_10", layout["fonts"])
        self.assertEqual(layout["fonts"]["Arial-Bold_16"], len("Heading 1"))

    def test_analyze_page(self):
        # Execute
        page_layout = self.analyzer._analyze_page(self.mock_page, 0)
        
        # Verify
        self.assertEqual(page_layout["page"], 0)
        self.assertEqual(page_layout["width"], 600)
        self.assertEqual(page_layout["height"], 800)
        # TEXT BLOCKS ONLY
        self.assertEqual(len(page_layout["blocks"]), 2)  # FIXED
        self.assertEqual(len(page_layout["fonts"]), 3)
        self.assertEqual(len(page_layout["images"]), 1)

        # Verify block processing
        text_block = page_layout["blocks"][0]
        self.assertEqual(text_block["text"], "Heading 1 content")
        self.assertEqual(text_block["bbox"], (0, 0, 600, 100))
        self.assertEqual(text_block["font_summary"]["dominant_font"], "Arial-Bold")
        self.assertEqual(text_block["font_summary"]["dominant_size"], 16)
        self.assertEqual(text_block["font_summary"]["font_variants"], 2)
        
        image_block = page_layout["images"][0]
        self.assertEqual(image_block["bbox"], (0, 100, 300, 200))
        self.assertEqual(image_block["width"], 300)
        self.assertEqual(image_block["height"], 100)

    def test_process_text_block(self):
        # Setup
        block = self.page_dict_1["blocks"][0]
        
        # Execute
        processed = self.analyzer._process_text_block(block)
        
        # Verify
        self.assertEqual(processed["text"], "Heading 1 content")
        self.assertEqual(processed["bbox"], (0, 0, 600, 100))
        self.assertEqual(len(processed["fonts"]), 2)
        
        # Verify font details
        fonts = {f"{f['name']}_{f['size']}": f for f in processed["fonts"]}
        self.assertEqual(fonts["Arial-Bold_16"]["count"], len("Heading 1"))
        self.assertEqual(fonts["Arial_12"]["count"], len(" content"))
        
        # Verify summary
        summary = processed["font_summary"]
        self.assertEqual(summary["dominant_font"], "Arial-Bold")
        self.assertEqual(summary["dominant_size"], 16)
        self.assertEqual(summary["font_variants"], 2)

    def test_summarize_fonts(self):
        # Setup
        font_details = {
            "font1": {"name": "Arial", "size": 12, "count": 100},
            "font2": {"name": "Arial-Bold", "size": 12, "count": 150},
            "font3": {"name": "Times", "size": 10, "count": 50}
        }
        
        # Execute
        summary = self.analyzer._summarize_fonts(font_details)
        
        # Verify
        self.assertEqual(summary["dominant_font"], "Arial-Bold")
        self.assertEqual(summary["dominant_size"], 12)
        self.assertEqual(summary["font_variants"], 3)
    
    def test_summarize_fonts_empty(self):
        summary = self.analyzer._summarize_fonts({})
        self.assertEqual(summary, {})
    
    @patch("parsing_engine.layout_analyzer.fitz.open")
    def test_empty_document(self, mock_fitz_open):
        # Setup empty document
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 0
        mock_fitz_open.return_value = mock_doc
        
        # Execute
        layout = self.analyzer.analyze("empty.pdf")
        
        # Verify
        self.assertEqual(layout, {
            "pages": [],
            "fonts": {},
            "images": []
        })
    
    @patch("parsing_engine.layout_analyzer.fitz.open")
    def test_page_with_no_blocks(self, mock_fitz_open):
        # Setup page with no blocks
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_page = MagicMock()
        mock_page.get_text.return_value = {
            "width": 600,
            "height": 800,
            "blocks": []
        }
        mock_doc.load_page.return_value = mock_page
        mock_fitz_open.return_value = mock_doc
        
        # Execute
        layout = self.analyzer.analyze("blank.pdf")
        
        # Verify
        page = layout["pages"][0]
        self.assertEqual(page["blocks"], [])
        self.assertEqual(page["fonts"], [])
        self.assertEqual(page["images"], [])
    
    def test_text_block_with_empty_spans(self):
        # Setup block with empty spans
        block = {
            "type": 0,
            "bbox": (0, 0, 100, 100),
            "lines": [
                {"spans": []},
                {"spans": [{"text": " ", "font": "Arial", "size": 12}]}
            ]
        }
        
        # Execute
        processed = self.analyzer._process_text_block(block)
        
        # Verify
        self.assertEqual(processed["text"], " ")
        self.assertEqual(len(processed["fonts"]), 1)
        self.assertEqual(processed["fonts"][0]["count"], 1)
    
    def test_font_aggregation_across_pages(self):
        # Setup two pages with same fonts
        with patch("parsing_engine.layout_analyzer.fitz.open") as mock_fitz_open:
            mock_fitz_open.return_value = self.mock_doc
            
            # Execute
            layout = self.analyzer.analyze("multi_page.pdf")
            
            # Verify font counts are aggregated
        self.assertEqual(layout["fonts"]["Arial_8"], 11)
        # Arial_12: " content" (8 chars)
        self.assertEqual(layout["fonts"]["Arial_12"], 8)

if __name__ == "__main__":
    unittest.main()