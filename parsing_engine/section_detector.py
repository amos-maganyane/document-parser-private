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
        sections = {}
        current_section = None
        raw_text = document.get("raw_text", "")
        
        # First try to detect sections from raw text
        logging.debug("Detecting sections from raw text...")
        lines = raw_text.split('\n')
        current_content = []
        
        # Initialize contact section with first few lines
        contact_lines = []
        for line in lines[:5]:  # First 5 lines are usually contact info
            line = line.strip()
            if line:
                contact_lines.append(line)
        
        if contact_lines:
            sections["contact"] = {
                "content": "\n".join(contact_lines),
                "position": {},
                "blocks": []
            }
        
        # Process remaining lines
        i = 5  # Start after contact section
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
                
            # Check if line is a potential section heading
            section_match = self._match_section_heading(line, self.min_heading_size)
            
            if section_match:
                logging.debug(f"Found section: {section_match} from line: {line}")
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
                
                # For skills section, include the header line as it might contain skills
                if current_section == "skills":
                    current_content.append(line)
            elif current_section:
                # For skills section, check if line contains skill indicators
                if current_section == "skills" and any(indicator in line.lower() for indicator in [
                    "languages:", "frameworks", "tools", "libraries:", "testing:", "methodologies:",
                    "software design", "architecture:", "agile", "databases:", "platforms:",
                    "programming", "development", "technologies"
                ]):
                    current_content.append(line)
                else:
                    current_content.append(line)
            
            i += 1
        
        # Save last section's content
        if current_section and current_content:
            sections[current_section]["content"] = "\n".join(current_content)
        
        # If no sections found, try to detect sections from content blocks
        if not sections or not any(s["content"].strip() for s in sections.values()):
            logging.debug("No sections found in raw text, trying content blocks...")
            sections = {}  # Reset sections
            content_blocks = document.get("content", [])
            
            if content_blocks:
                for block in content_blocks:
                    text = block.get("text", "").strip()
                    if not text:
                        continue
                    
                    # For simplified content, treat each line as potential section
                    lines = text.split('\n')
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        section_match = self._match_section_heading(line, self.min_heading_size)
                        
                        if section_match:
                            logging.debug(f"Found section: {section_match} from line: {line}")
                            current_section = section_match
                            if current_section not in sections:
                                sections[current_section] = {
                                    "content": "",
                                    "position": block.get("position", {}),
                                    "blocks": []
                                }
                            # For skills section, include the header line
                            if current_section == "skills":
                                sections[current_section]["content"] += line + "\n"
                            continue
                            
                        if current_section:
                            sections[current_section]["content"] += line + "\n"
                            if block not in sections[current_section]["blocks"]:
                                sections[current_section]["blocks"].append(block)
        
        # If still no sections found, create a default section with all content
        if not sections:
            logging.debug("No sections found, using default section...")
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
    
    def _match_section_heading(self, text: str, font_size: float) -> Optional[str]:
        """Match section heading with improved pattern matching"""
        if not text:
            return None
            
        text_lower = text.lower()
        logging.debug(f"Checking if line is section heading: {text}")
        
        # Common resume section headings
        common_sections = {
            "experience": ["experience", "work experience", "professional experience", "employment history"],
            "education": ["education", "academic background", "educational background", "academic qualifications"],
            "skills": ["technical skills", "skills", "core competencies", "professional skills"],
            "projects": ["technical projects", "projects", "project experience", "key projects"],
            "certifications": ["certifications", "certificates", "professional certifications"],
            "summary": ["summary", "professional summary", "profile", "objective"]
        }
        
        # Check for common section headings first
        for section, patterns in common_sections.items():
            if any(p.lower() == text_lower for p in patterns):
                logging.debug(f"Found exact match for common section: {section}")
                return section
        
        # Direct matches from config
        for section, section_info in self.section_rules.items():
            patterns = section_info.get("patterns", [])
            if any(p.lower() == text_lower for p in patterns):
                logging.debug(f"Found exact match for section: {section}")
                return section
                
        # Then try pattern matching with compiled patterns
        confidence_scores: Dict[str, int] = {}
        for section, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    confidence_scores[section] = confidence_scores.get(section, 0) + 1
        
        if confidence_scores:
            best_section = max(confidence_scores.items(), key=lambda x: x[1])[0]
            confidence = confidence_scores[best_section] / len(self.compiled_patterns[best_section])
            if confidence >= self.confidence_threshold:
                logging.debug(f"Found pattern match for section: {best_section} with confidence {confidence}")
                return best_section
            else:
                logging.debug(f"Section match {best_section} rejected due to low confidence: {confidence}")
        
        # Special case for headings with colon or all caps
        if text.endswith(':') or text.isupper():
            text_clean = text.rstrip(':').lower()
            # Check common sections first
            for section, patterns in common_sections.items():
                if any(p.lower() in text_clean for p in patterns):
                    logging.debug(f"Found special case match for common section: {section}")
                    return section
            # Then check config patterns
            for section, section_info in self.section_rules.items():
                patterns = section_info.get("patterns", [])
                if any(p.lower() in text_clean for p in patterns):
                    logging.debug(f"Found special case match for section: {section}")
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