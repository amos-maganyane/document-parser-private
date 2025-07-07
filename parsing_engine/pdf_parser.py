import pdfplumber
import fitz  # PyMuPDF
import re
from typing import Dict, List, Tuple, Any
from .layout_analyzer import LayoutAnalyzer
from .section_detector import SectionDetector
import logging
import yaml
import json
from pdfminer.high_level import extract_text
from pdfminer.layout import LAParams

# Marker imports
try:
    from marker.models import load_all_models
    from marker.convert import convert_single_pdf
    MARKER_AVAILABLE = True
except ImportError:
    MARKER_AVAILABLE = False

class PDFParser:
    def __init__(self, config: Dict):
        self.use_ocr = config.get("use_ocr", False)
        self.layout_analysis = config.get("layout_analysis", True)
        self.use_marker = config.get("use_marker", True) and MARKER_AVAILABLE

        # Load section rules
        section_rules = config.get("section_rules", {})
        if isinstance(section_rules, str):
            try:
                with open(section_rules, 'r') as f:
                    section_rules = yaml.safe_load(f)
            except Exception as e:
                logging.error(f"Failed to load section rules: {str(e)}")
                section_rules = {}
    
        self.section_detector = SectionDetector(section_rules)
        self.layout_analyzer = LayoutAnalyzer()
        self.logger = logging.getLogger(__name__)

        if self.use_marker:
            self.logger.info("Loading Marker models...")
            self.marker_model = load_all_models()
            self.logger.info("Marker models loaded.")

    def parse(self, file_path: str) -> Dict[str, Any]:
        if self.use_marker:
            return self._parse_with_marker(file_path)
        else:
            return self._parse_with_legacy(file_path)

    def _parse_with_marker(self, file_path: str) -> Dict[str, Any]:
        self.logger.debug(f"Starting PDF parsing with Marker: {file_path}")
        try:
            # Use Marker to process the PDF
            full_text, images, out_meta = convert_single_pdf(file_path, self.marker_model)

            # The output from marker is markdown text.
            # We can feed this directly to the section detector.
            # The section detector expects a specific input format, so we create it here.
            combined = {
                "content": [{
                    "text": full_text,
                    "type": "text",
                    "position": {},
                    "font": {"name": "Unknown", "size": 10}
                }],
                "raw_text": full_text,
                "metadata": out_meta
            }
            
            result = self.section_detector.detect_sections(combined)
            self.logger.debug(f"Detected sections from Marker output:\n{json.dumps(result.get('sections', {}), indent=2)}")
            return result

        except Exception as e:
            self.logger.error(f"Failed to parse PDF with Marker: {e}")
            self.logger.info("Falling back to legacy PDF parsing.")
            return self._parse_with_legacy(file_path)

    def _parse_with_legacy(self, file_path: str) -> Dict[str, Any]:
        self.logger.debug(f"Starting legacy PDF parsing: {file_path}")
        
        text_data = self._extract_text(file_path)
        if not text_data.get("raw_text", "").strip():
            self.logger.error("No text could be extracted from PDF")
            return {"raw_text": "", "sections": {}}
            
        try:
            if self.layout_analysis:
                try:
                    layout_data = self._analyze_layout(file_path)
                    combined = self._integrate_layout(text_data, layout_data)
                except Exception as e:
                    self.logger.warning(f"Layout analysis failed: {e}, falling back to text-only parsing")
                    combined = {
                        "content": [{"text": text_data["raw_text"], "type": "text", "position": {}, "font": {"name": "Unknown", "size": 10}}],
                        "raw_text": text_data["raw_text"],
                        "metadata": text_data["metadata"]
                    }
            else:
                combined = {
                    "content": [{"text": text_data["raw_text"], "type": "text", "position": {}, "font": {"name": "Unknown", "size": 10}}],
                    "raw_text": text_data["raw_text"],
                    "metadata": text_data["metadata"]
                }
            
            result = self.section_detector.detect_sections(combined)
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to parse PDF with legacy method: {e}")
            return {
                "raw_text": text_data.get("raw_text", ""),
                "sections": {},
                "metadata": text_data.get("metadata", {})
            }
    
    def _extract_text(self, file_path: str) -> Dict:
        parsed = {"raw_text": "", "tables": [], "metadata": {}, "images": []}
        
        try:
            import subprocess
            result = subprocess.run(['pdf2txt.py', file_path], capture_output=True, text=True)
            if result.stdout.strip():
                self.logger.debug(f"Text extracted with pdf2txt.py:\n{result.stdout}")
                parsed["raw_text"] = result.stdout
                
                try:
                    with pdfplumber.open(file_path) as pdf:
                        parsed["metadata"] = pdf.metadata
                except Exception as e:
                    self.logger.warning(f"Failed to extract metadata: {e}")
                
                return parsed
            
            self.logger.warning("pdf2txt.py extracted no text, trying pdfplumber")
            with pdfplumber.open(file_path) as pdf:
                parsed["metadata"] = pdf.metadata
                self.logger.debug(f"PDF metadata: {pdf.metadata}")
                
                for page in pdf.pages:
                    try:
                        self.logger.debug(f"Processing page {page.page_number}")
                        page_text = page.extract_text(x_tolerance=3, y_tolerance=3)
                        if page_text:
                            self.logger.debug(f"Page {page.page_number} text:\n{page_text}")
                            parsed["raw_text"] += page_text + "\n\n"
                        else:
                            self.logger.warning(f"No text extracted from page {page.page_number}")
                        
                        try:
                            tables = page.extract_tables()
                            for table in tables:
                                if table:
                                    parsed["tables"].append({
                                        "page": page.page_number,
                                        "data": table
                                    })
                                    self.logger.debug(f"Table found on page {page.page_number}: {table}")
                        except Exception as table_err:
                            self.logger.warning(f"Table extraction failed: {table_err}")
                            
                    except Exception as page_err:
                        self.logger.warning(f"Page extraction failed: {page_err}")
                        continue
            
            if not parsed["raw_text"].strip():
                self.logger.warning("pdfplumber extracted no text, trying PyMuPDF")
                doc = fitz.open(file_path)
                
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    self.logger.debug(f"Processing page {page_num + 1} with PyMuPDF")
                    
                    try:
                        text_page = page.get_textpage()
                        page_text = text_page.extractText()
                        if page_text:
                            self.logger.debug(f"Page {page_num + 1} text:\n{page_text}")
                            parsed["raw_text"] += page_text + "\n\n"
                        else:
                            self.logger.warning(f"No text extracted from page {page_num + 1}")
                    except Exception as e:
                        self.logger.warning(f"Failed to extract text from page {page_num + 1}: {e}")
            
            if not parsed["raw_text"].strip() and self.use_ocr:
                self.logger.info("No text extracted with any method, falling back to OCR")
                parsed = self._fallback_to_ocr(file_path)
                    
        except Exception as e:
            self.logger.error(f"PDF extraction failed: {e}")
            if self.use_ocr:
                parsed = self._fallback_to_ocr(file_path)
        
        return parsed
    
    def _analyze_layout(self, file_path: str) -> Dict:
        return self.layout_analyzer.analyze(file_path)
    
    def _integrate_layout(self, text_data: Dict, layout_data: Dict) -> Dict:
        integrated = {
            "content": [],
            "raw_text": text_data["raw_text"],
            "metadata": text_data["metadata"]
        }
        
        for block in layout_data.get("text_blocks", []):
            if not block.get("text", "").strip():
                continue
            
            font_size = block.get("font", {}).get("size", 10)
            font_name = block.get("font", {}).get("name", "")
            
            is_heading = (
                font_size >= 12 or 
                font_name.startswith("CMBX") or
                any(word.strip().isupper() for word in block["text"].split())
            )
            
            integrated["content"].append({
                "text": block["text"],
                "type": "heading" if is_heading else "text",
                "position": block.get("position", {}),
                "font": {
                    "size": font_size,
                    "name": font_name
                }
            })
        
        for table in text_data.get("tables", []):
            if table.get("data"):
                integrated["content"].append({
                    "type": "table",
                    "data": table["data"],
                    "page": table["page"]
                })
        
        return integrated
    
    def _fallback_to_ocr(self, file_path: str) -> Dict:
        try:
            import pytesseract
            from PIL import Image
            import io
            
            doc = fitz.open(file_path)
            full_text = ""
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                mat = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                text = pytesseract.image_to_string(img)
                full_text += text + "\n\n"
                
            return {"raw_text": full_text, "tables": [], "metadata": {}}
            
        except ImportError:
            logging.error("OCR fallback requires pytesseract and PIL")
            return {"raw_text": "", "tables": [], "metadata": {}}