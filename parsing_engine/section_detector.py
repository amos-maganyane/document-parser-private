import re
from typing import Dict, List
import logging

class SectionDetector:
    def __init__(self, rules: Dict):
        # Handle empty rules gracefully
        self.section_rules = rules.get("patterns", {}) if rules else {}
        self.confidence_threshold = rules.get("confidence_threshold", 0.5) if rules else 0.5
        self.min_heading_size = rules.get("min_heading_size", 10) if rules else 10

                # Compile regex patterns for efficiency
        self.compiled_patterns = {}
        for section, patterns in self.section_rules.items():
            compiled = []
            for pattern in patterns:
                try:
                    compiled.append(re.compile(pattern, re.IGNORECASE))
                except re.error as e:
                    logging.error(f"Invalid regex pattern '{pattern}': {str(e)}")
            self.compiled_patterns[section] = compiled
        
    def detect_sections(self, document: Dict) -> Dict:
        sections = {}
        current_section = None
        content_blocks = document.get("content", [])
        
        for block in content_blocks:
            # Handle all block types
            text = block.get("text", "").strip()
            if not text:
                continue
                
            # Get font size with safe defaults
            font_size = self._get_dominant_font_size(block)

            if font_size < self.min_heading_size and not text.endswith(':'):
                continue
            
            # Check if this block is a section heading
            section_match = self._match_section_heading(text, font_size)
            if section_match:
                current_section = section_match
                sections[current_section] = {
                    "content": "",
                    "position": block.get("position", {}),
                    "blocks": []
                }
                continue
                
            # Add content to current section
            if current_section:
                sections[current_section]["content"] += text + "\n"
                sections[current_section]["blocks"].append(block)
        
        return {
            "sections": sections,
            "raw": document.get("raw_text", ""),
            "metadata": document.get("metadata", {})
        }
    
    def _match_section_heading(self, text: str, font_size: float) -> str:
        # Bypass font size check if we're dealing with text files
        if font_size < self.min_heading_size and not text.endswith(':'):
            return None
            
        text_lower = text.lower()
        confidence_scores = {}
        
        # Handle case where no section rules are defined
        if not self.section_rules:
            return None
            
        for section, patterns in self.section_rules.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    confidence_scores[section] = confidence_scores.get(section, 0) + 1
        
        if not confidence_scores:
            return None
            
        best_section = max(confidence_scores, key=confidence_scores.get)
        confidence = confidence_scores[best_section] / len(patterns)
        
        return best_section if confidence >= self.confidence_threshold else None
    
    def _get_dominant_font_size(self, block: Dict) -> float:
        # Handle different block formats
        if block.get("type") == "heading":
            return 14  # Force headings to be recognized
        
        if "font" in block:
            if isinstance(block["font"], dict):
                return block["font"].get("size", 10)
            return 10
            
        if "font_summary" in block and "dominant_size" in block["font_summary"]:
            return block["font_summary"]["dominant_size"]
            
        return 10  # Default size