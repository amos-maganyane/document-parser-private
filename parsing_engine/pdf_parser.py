import pdfplumber
import fitz  # PyMuPDF
import re
from typing import Dict, List, Tuple, Any
from .layout_analyzer import LayoutAnalyzer
from .section_detector import SectionDetector
import logging
import yaml  # Make sure to import yaml

class PDFParser:
    def __init__(self, config: Dict):
        self.use_ocr = config.get("use_ocr", False)
        self.layout_analysis = config.get("layout_analysis", True)
        
        # Load section rules if it's a file path
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
        
    def parse(self, file_path: str) -> Dict[str, Any]:
        self.logger.debug(f"Starting PDF parsing: {file_path}")
        # First pass: Text extraction
        text_data = self._extract_text(file_path)
        self.logger.debug(f"Extracted text data: {text_data}")
        
        # Second pass: Layout analysis
        if self.layout_analysis:
            layout_data = self._analyze_layout(file_path)
            self.logger.debug(f"Layout analysis: {layout_data}")
            combined = self._integrate_layout(text_data, layout_data)
            self.logger.debug(f"Combined data: {combined}")
            result = self.section_detector.detect_sections(combined)
            self.logger.debug(f"Final sections: {result}")
            return result

        return text_data
    
    def _extract_text(self, file_path: str) -> Dict:
        parsed = {"raw_text": "", "tables": [], "metadata": {}}
        
        try:
            with pdfplumber.open(file_path) as pdf:
                parsed["metadata"] = pdf.metadata
                
                for page in pdf.pages:
                    # Extract text
                    page_text = page.extract_text(x_tolerance=1, y_tolerance=1)
                    parsed["raw_text"] += page_text + "\n\n"
                    
                    # Extract tables
                    tables = page.extract_tables()
                    for table in tables:
                        parsed["tables"].append({
                            "page": page.page_number,
                            "data": table
                        })
                    
                    # Extract images metadata
                    parsed["images"] = page.images
                    
        except Exception as e:
            logging.error(f"PDF extraction failed: {e}")
            if self.use_ocr:
                parsed = self._fallback_to_ocr(file_path)
        
        return parsed
    
    def _analyze_layout(self, file_path: str) -> Dict:
        return self.layout_analyzer.analyze(file_path)
    
    def _integrate_layout(self, text_data: Dict, layout_data: Dict) -> Dict:
        """Combine text content with layout information"""
        integrated = {
            "content": [],
            "raw_text": text_data["raw_text"],
            "metadata": text_data["metadata"]
        }
        
        # Add content blocks with layout metadata
        for block in layout_data.get("blocks", []):
            if not block.get("text", "").strip():
                continue
            
            # Get font info
            font_size = block.get("font_summary", {}).get("dominant_size", 10)
            font_name = block.get("font_summary", {}).get("dominant_font", "")
            
            # Check if heading by font characteristics
            is_heading = (
                font_size >= 12 or 
                font_name.startswith("CMBX") or
                any(word.strip().isupper() for word in block["text"].split())
            )
            
            integrated["content"].append({
                "text": block["text"],
                "type": "heading" if is_heading else "text",
                "position": block.get("bbox", []),
                "font": {
                    "size": font_size,
                    "name": font_name
                }
            })
        
        # Add tables if any
        for table in text_data.get("tables", []):
            if table.get("data"):
                integrated["content"].append({
                    "type": "table",
                    "data": table["data"],
                    "page": table["page"]
                })
        
        return integrated
    
    def _fallback_to_ocr(self, file_path: str) -> Dict:
        """Fallback to OCR when text extraction fails"""
        try:
            import pytesseract
            from PIL import Image
            import io
            
            doc = fitz.open(file_path)
            full_text = ""
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap()
                img = Image.open(io.BytesIO(pix.tobytes()))
                text = pytesseract.image_to_string(img)
                full_text += text + "\n\n"
                
            return {"raw_text": full_text, "tables": [], "metadata": {}}
            
        except ImportError:
            logging.error("OCR fallback requires pytesseract and PIL")
            return {"raw_text": "", "tables": [], "metadata": {}}