import os
import re
from typing import Dict, List
import logging

class TextParser:
    def __init__(self, config: Dict = None):
        self.config = config or {}
        # Ensure section rules exist
        self.section_rules = self.config.get("section_rules", {})
        
class TextParser:
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.section_rules = self.config.get("section_rules", {})
        
    def parse(self, file_path: str) -> Dict:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            
            document = {
                "raw_text": raw_text,
                "content": self._structure_content(raw_text),
                "metadata": self._extract_metadata(file_path),
                "tables": [],
                "images": []
            }
            return document
        except Exception as e:
            logging.error(f"Text parsing failed: {str(e)}")
            return {
                "raw_text": "",
                "content": [],
                "metadata": self._extract_metadata(file_path, error=True),
                "tables": [],
         
                "images": []
            }
    
    def _structure_content(self, raw_text: str) -> List[Dict]:
        lines = raw_text.split('\n')
        blocks = []
        current_block = []
        
        # Enhanced pattern with word boundaries
        heading_pattern = (
            r'^\s*(CONTACT(\s*INFO)?|(PROFESSIONAL\s+)?SUMMARY|PROFILE|OBJECTIVE|'
            r'(WORK|PROFESSIONAL|EMPLOYMENT)\s+EXPERIENCE|EXPERIENCE|'
            r'CAREER\s+(HISTORY|PATH)|(ACADEMIC\s+)?EDUCATION|QUALIFICATIONS|DEGREES|'
            r'TRAINING|CERTIFICATIONS?|(TECHNICAL\s+)?SKILLS|COMPETENCIES|EXPERTISE|'
            r'(KEY\s+)?PROJECTS|PORTFOLIO|PERSONAL\s+DETAILS|ABOUT\s+ME'
            r')\s*:?\s*$'
        )
        
        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                if current_block:
                    blocks.append(self._create_text_block("\n".join(current_block)))
                    current_block = []
                continue
                
            # Only consider lines that exactly match the heading pattern
            if re.match(heading_pattern, stripped_line, re.IGNORECASE):
                if current_block:
                    blocks.append(self._create_text_block("\n".join(current_block)))
                    current_block = []
                blocks.append(self._create_heading_block(stripped_line))
            else:
                current_block.append(line)
        
        if current_block:
            blocks.append(self._create_text_block("\n".join(current_block)))
            
        return blocks
    
    def _create_text_block(self, text: str) -> Dict:
        return {
            "text": text,
            "type": "text",
            "position": {"x": 0, "y": 0},
            "font": {"size": 11, "name": "Arial"}
        }
    
    def _create_heading_block(self, text: str) -> Dict:
        return {
            "text": text,
            "type": "heading",
            "position": {"x": 0, "y": 0},
            "font": {"size": 14, "name": "Arial"}
        }
    
    def _extract_metadata(self, file_path: str, error: bool = False) -> Dict:
        try:
            return {
                "format": "text",
                "file_name": os.path.basename(file_path),
                "file_size": os.path.getsize(file_path) if not error else 0
            }
        except:
            return {
                "format": "text",
                "file_name": os.path.basename(file_path),
                "file_size": 0
            }