import re
from typing import Dict, List
import logging

class SectionDetector:
    def __init__(self, rules: Dict):
        # Handle both direct and nested patterns
        if "detection_rules" in rules:
            detection_rules = rules["detection_rules"]
        else:
            detection_rules = rules

        # Get patterns and settings
        self.section_rules = detection_rules.get("patterns", {})
        self.confidence_threshold = detection_rules.get("confidence_threshold", 0.5)
        self.min_heading_size = detection_rules.get("min_heading_size", 10)

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
        raw_text = document.get("raw_text", "")
        
        # First try to detect sections from content blocks
        content_blocks = document.get("content", [])
        if content_blocks:
            for block in content_blocks:
                text = block.get("text", "").strip()
                if not text:
                    continue
                    
                font_size = self._get_dominant_font_size(block)
                section_match = self._match_section_heading(text, font_size)
                
                if section_match:
                    current_section = section_match
                    sections[current_section] = {
                        "content": "",
                        "position": block.get("position", {}),
                        "blocks": []
                    }
                    continue
                    
                if current_section:
                    sections[current_section]["content"] += text + "\n"
                    sections[current_section]["blocks"].append(block)
        
        # If no sections found, try to parse from raw text
        if not sections and raw_text:
            lines = raw_text.split('\n')
            current_content = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Check if line is a potential section heading
                section_match = self._match_section_heading(line, 12)  # Default size for raw text
                
                if section_match:
                    # Save previous section's content if exists
                    if current_section and current_content:
                        sections[current_section]["content"] = "\n".join(current_content)
                    
                    current_section = section_match
                    current_content = []
                    sections[current_section] = {
                        "content": "",
                        "position": {},
                        "blocks": []
                    }
                elif current_section:
                    current_content.append(line)
            
            # Save last section's content
            if current_section and current_content:
                sections[current_section]["content"] = "\n".join(current_content)
        
        return {
            "sections": sections,
            "raw": raw_text,
            "metadata": document.get("metadata", {})
        }
    
    def _match_section_heading(self, text: str, font_size: float) -> str:
        """Match section heading with improved pattern matching"""
        # Skip empty text
        if not text:
            return None
            
        text_lower = text.lower()
        
        # Direct matches first (case-insensitive)
        for section, patterns in self.section_rules.items():
            if any(p.lower() == text_lower for p in patterns):
                return section
                
        # Then try pattern matching
        confidence_scores = {}
        for section, patterns in self.section_rules.items():
            for pattern in patterns:
                try:
                    if re.search(pattern, text_lower, re.IGNORECASE):
                        confidence_scores[section] = confidence_scores.get(section, 0) + 1
                except re.error:
                    continue
        
        if confidence_scores:
            best_section = max(confidence_scores, key=confidence_scores.get)
            confidence = confidence_scores[best_section] / len(self.section_rules[best_section])
            if confidence >= self.confidence_threshold:
                return best_section
        
        # Special case for headings with colon
        if text.endswith(':'):
            text_without_colon = text[:-1].lower()
            for section, patterns in self.section_rules.items():
                if any(p.lower() in text_without_colon for p in patterns):
                    return section
        
        return None
    
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