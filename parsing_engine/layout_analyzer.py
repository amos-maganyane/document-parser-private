import fitz  # PyMuPDF
from typing import Dict, List

class LayoutAnalyzer:
    def analyze(self, file_path: str) -> Dict:
        doc = fitz.open(file_path)
        layout = {
            "pages": [],
            "fonts": {},
            "images": []
        }
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            page_layout = self._analyze_page(page, page_num)
            layout["pages"].append(page_layout)
            
            # Aggregate font statistics
            for font_info in page_layout["fonts"]:
                font_key = f"{font_info['name']}_{font_info['size']}"
                layout["fonts"][font_key] = layout["fonts"].get(font_key, 0) + font_info["count"]
        
        return layout
    
    def _analyze_page(self, page, page_num: int) -> Dict:
        page_dict = page.get_text("dict")
        layout = {
            "page": page_num,
            "width": page_dict["width"],
            "height": page_dict["height"],
            "blocks": [],
            "fonts": [],
            "images": []
        }
        
        # Process text blocks
        for block in page_dict["blocks"]:
            if block["type"] == 0:  # Text block
                block_info = self._process_text_block(block)
                layout["blocks"].append(block_info)
                layout["fonts"].extend(block_info["fonts"])
            
            elif block["type"] == 1:  # Image block
                layout["images"].append({
                    "bbox": block["bbox"],
                    "width": block["width"],
                    "height": block["height"]
                })
        
        return layout
    
    def _process_text_block(self, block: Dict) -> Dict:
        block_text = ""
        font_details = {}
        
        for line in block["lines"]:
            for span in line["spans"]:
                block_text += span["text"]
                # Capture font details
                font_key = f"{span['font']}_{span['size']}"
                font_details[font_key] = {
                    "name": span["font"],
                    "size": span["size"],
                    "count": font_details.get(font_key, {}).get("count", 0) + len(span["text"])
                }
        
        return {
            "text": block_text,
            "bbox": block["bbox"],
            "font_summary": self._summarize_fonts(font_details),
            "fonts": list(font_details.values())
        }
    
    def _summarize_fonts(self, font_details: Dict) -> Dict:
        if not font_details:
            return {}
        
        dominant = max(font_details.values(), key=lambda x: x["count"])
        return {
            "dominant_font": dominant["name"],
            "dominant_size": dominant["size"],
            "font_variants": len(font_details)
        }