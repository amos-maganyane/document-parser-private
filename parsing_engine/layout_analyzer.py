import fitz  # PyMuPDF
from typing import Dict, List
import logging

class LayoutAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def analyze(self, file_path: str) -> Dict:
        doc = fitz.open(file_path)
        layout = {
            "text_blocks": [],
            "fonts": {},
            "images": []
        }
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            page_layout = self._analyze_page(page, page_num)
            
            # Add page blocks to global list
            layout["text_blocks"].extend(page_layout["blocks"])
            
            # Aggregate font statistics
            for font_info in page_layout["fonts"]:
                font_key = f"{font_info['name']}_{font_info['size']}"
                layout["fonts"][font_key] = layout["fonts"].get(font_key, 0) + font_info["count"]
            
            # Add images
            layout["images"].extend(page_layout["images"])
        
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
        
        try:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                        
                    block_text += text + " "
                    
                    # Extract font details
                    font = span.get("font", "")
                    if isinstance(font, str):
                        font_name = font
                    elif isinstance(font, dict):
                        font_name = font.get("name", "Unknown")
                    else:
                        font_name = "Unknown"
                        
                    # Extract size with fallbacks
                    size = span.get("size", None)
                    if size is None:
                        # Try alternative size fields
                        size = span.get("font_size", span.get("fontSize", 10))
                    try:
                        font_size = float(size)
                    except (TypeError, ValueError):
                        font_size = 10
                    
                    font_key = f"{font_name}_{font_size}"
                    font_details[font_key] = {
                        "name": font_name,
                        "size": font_size,
                        "count": font_details.get(font_key, {}).get("count", 0) + len(text)
                    }
                block_text += "\n"  # Add newline after each line
                
        except Exception as e:
            self.logger.warning(f"Error processing text block: {e}")
            # Return basic block info without font details
            return {
                "text": block_text.strip() or block.get("text", ""),
                "position": {
                    "bbox": block.get("bbox", [0, 0, 0, 0]),
                    "page": block.get("page", 0)
                },
                "font": {
                    "name": "Unknown",
                    "size": 10
                },
                "fonts": []
            }
        
        # Get dominant font info
        font_summary = self._summarize_fonts(font_details)
        
        return {
            "text": block_text.strip(),
            "position": {
                "bbox": block.get("bbox", [0, 0, 0, 0]),
                "page": block.get("page", 0)
            },
            "font": {
                "name": font_summary.get("dominant_font", "Unknown"),
                "size": font_summary.get("dominant_size", 10)
            },
            "fonts": [
                {"name": details["name"], "size": details["size"], "count": details["count"]}
                for details in font_details.values()
            ]
        }
    
    def _summarize_fonts(self, font_details: Dict) -> Dict:
        if not font_details:
            return {}
        
        # Find the most common font by character count
        dominant = max(font_details.values(), key=lambda x: x["count"])
        
        # Calculate average size for similar fonts
        sizes = []
        for details in font_details.values():
            if details["name"] == dominant["name"]:
                sizes.extend([details["size"]] * details["count"])
        
        avg_size = sum(sizes) / len(sizes) if sizes else dominant["size"]
        
        return {
            "dominant_font": dominant["name"],
            "dominant_size": avg_size,
            "font_variants": len(font_details)
        }