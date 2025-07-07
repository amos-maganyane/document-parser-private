import re
from typing import Dict, List, Optional
import logging

class SectionDetector:
    def __init__(self, rules: Dict):
        # Handle both direct and nested patterns
        if "detection_rules" in rules:
            detection_rules = rules["detection_rules"]
        else:
            detection_rules = rules

        # Get patterns and settings
        patterns = detection_rules.get("patterns", {})
        self.section_rules = patterns.get("sections", {})  # Get nested section patterns
        self.confidence_threshold = detection_rules.get("settings", {}).get("confidence_threshold", 0.5)
        self.min_heading_size = detection_rules.get("settings", {}).get("min_heading_size", 10)

        # Compile regex patterns for efficiency
        self.compiled_patterns = {}
        for section, section_info in self.section_rules.items():
            compiled = []
            patterns = section_info.get("patterns", [])
            for pattern in patterns:
                try:
                    compiled.append(re.compile(pattern, re.IGNORECASE))
                except re.error as e:
                    logging.error(f"Invalid regex pattern '{pattern}': {str(e)}")
            self.compiled_patterns[section] = compiled
        
    def detect_sections(self, document: Dict) -> Dict:
        sections = {
            "contact": {"content": "", "position": {}, "blocks": []},
            "summary": {"content": "", "position": {}, "blocks": []},
            "skills": {"content": "", "position": {}, "blocks": []},
            "education": {"content": "", "position": {}, "blocks": []},
            "experience": {"content": "", "position": {}, "blocks": []},
            "projects": {"content": "", "position": {}, "blocks": []},
            "certifications": {"content": "", "position": {}, "blocks": []}
        }
        current_section = None
        raw_text = document.get("raw_text", "")
        
        logging.debug("Detecting sections from raw text...")
        lines = raw_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            section_match = self._match_section_heading(line)
            
            if section_match:
                logging.debug(f"Found section: {section_match} from line: {line}")
                current_section = section_match
                sections[current_section]["content"] += line + "\n"
            elif self._contains_date_pattern(line):
                # If a date pattern is found, and we are not already in experience or education,
                # assume it's an experience entry. This is a heuristic.
                if current_section not in ["experience", "education"]:
                    current_section = "experience" # Default to experience if date found
                    logging.debug(f"Inferred section: {current_section} from line with date pattern: {line}")
                sections[current_section]["content"] += line + "\n"
            elif current_section:
                # Append content to the current section
                sections[current_section]["content"] += line + "\n"
        
        # Clean up empty sections and add blocks if available
        content_blocks = document.get("content", [])
        for section_name, section_data in sections.items():
            if not section_data["content"].strip() and content_blocks:
                # Attempt to populate from content blocks if raw text detection failed for a section
                for block in content_blocks:
                    text = block.get("text", "").strip()
                    if not text:
                        continue
                    
                    section_match = self._match_section_heading(text)
                    if section_match == section_name:
                        sections[section_name]["content"] += text + "\n"
                        
                        if block not in sections[section_name]["blocks"]:
                            sections[section_name]["blocks"].append(block)
            elif section_data["content"].strip() and not section_data["blocks"]:
                # If content was found from raw_text but no blocks, try to associate
                # This part is a simplification; a more robust solution would map blocks during initial parsing
                for block in content_blocks:
                    if block.get("text", "").strip() in section_data["content"]:
                        if block not in sections[section_name]["blocks"]:
                            sections[section_name]["blocks"].append(block)

        # Fallback: if still no sections, put everything in a default 'content' section
        if not any(s["content"].strip() for s in sections.values()):
            logging.debug("No sections found, using default section 'content'...")
            sections["content"] = {
                "content": raw_text,
                "position": {},
                "blocks": document.get("content", [])
            }
        
        logging.debug(f"Detected sections: {list(sections.keys())}")
        return {
            "sections": sections,
            "raw_text": raw_text,
            "metadata": document.get("metadata", {})
        }
    
    def _match_section_heading(self, text: str) -> Optional[str]:
        """Match section heading with improved pattern matching"""
        if not text:
            return None
            
        text_lower = text.lower()
        logging.debug(f"Checking if line is section heading: {text}")
                
        # Try pattern matching with compiled patterns
        for section, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    logging.debug(f"Found pattern match for section: {section} from line: {text}")
                    return section
        
        # Special case for headings with colon or all caps
        if text.endswith(':') or text.isupper():
            text_clean = text.rstrip(':')
            for section, patterns in self.compiled_patterns.items():
                for pattern in patterns:
                    if pattern.search(text_clean):
                        logging.debug(f"Found special case match for section: {section} from line: {text}")
                        return section
        
        return None
    
    def _get_dominant_font_size(self, block: Dict) -> float:
        # This function is no longer used for section detection based on font size.
        # Keeping it for potential future use or if other parts of the system rely on it.
        if block.get("type") == "heading":
            return 14  # Force headings to be recognized
        
        if "font" in block:
            if isinstance(block["font"], dict):
                return block["font"].get("size", 10)
            return 10
            
        if "font_summary" in block and "dominant_size" in block["font_summary"]:
            return block["font_summary"]["dominant_size"]
            
        return 10  # Default size

    def _contains_date_pattern(self, text: str) -> bool:
        # Regex to find common date patterns (e.g., Jan 2020 - Dec 2021, 2020 - Present)
        date_patterns = [
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s*[-–]\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}|Present|Current)\b",
            r"\b\d{4}\s*[-–]\s*(?:\d{4}|Present|Current)\b",
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b"
        ]
        for pattern in date_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False