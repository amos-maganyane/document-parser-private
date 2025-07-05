import re
import json
import os
import logging
from typing import Dict, List, Optional, Tuple
from rapidfuzz import fuzz, process
from .date_normalizer import DateNormalizer

logger = logging.getLogger(__name__)

class EducationNormalizer:
    def __init__(self, data_dir: str = "data/education"):
        self.date_normalizer = DateNormalizer()
        self.institution_mapping = self._load_mapping(os.path.join(data_dir, "institutions.json"))
        self.degree_mapping = self._load_mapping(os.path.join(data_dir, "degrees.json"))
        self.field_mapping = self._load_mapping(os.path.join(data_dir, "fields.json"))
        self.institution_index = self._create_index(self.institution_mapping)
        self.degree_index = self._create_index(self.degree_mapping)
        
    def _load_mapping(self, file_path: str) -> Dict:
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
            logger.warning(f"Mapping file not found: {file_path}")
            return {}
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading mapping file {file_path}: {str(e)}")
            return {}
        
    
    def _create_index(self, mapping: Dict) -> List[str]:
        index = []
        for canonical, variants in mapping.items():
            index.append(canonical)
            index.extend(variants)
        return list(set(index))
    
    
    def normalize_institution(self, name: str) -> str:
        """Normalize educational institution name"""
        if not name or not isinstance(name, str):
            return ""
        
        clean_name = re.sub(r'[^\w\s&.,-]', '', name, flags=re.IGNORECASE)
        clean_name = clean_name.replace('.', '')
        clean_name = re.sub(
            r'\b(University|College|Institute|School|Univ|Coll|Inst|Sch)\b\.?', 
            '', 
            clean_name, 
            flags=re.IGNORECASE
        ).strip()
        
        if not clean_name:
            return name
        
        if clean_name in self.institution_index:
            return self._get_canonical(clean_name, self.institution_mapping)
        
        result = process.extractOne(
            clean_name, 
            self.institution_index, 
            scorer=fuzz.WRatio,
            score_cutoff=85
        )
        
        if result:
            match, score, _ = result
            return self._get_canonical(match, self.institution_mapping)
        return clean_name
    
    
    def normalize_degree(self, degree: str) -> str:
            """Normalize degree names"""
            if not degree or not isinstance(degree, str):
                return ""
            
            clean_degree = re.sub(r'[^\w\s]', '', degree)
            clean_degree = re.sub(
                r'\b(B\.?S\.?|BSc|B\.?Sc)\b', 
                'Bachelor of Science', 
                clean_degree, 
                flags=re.IGNORECASE
            )
            clean_degree = re.sub(
                r'\b(B\.?A\.?)\b', 
                'Bachelor of Arts', 
                clean_degree, 
                flags=re.IGNORECASE
            )
            clean_degree = re.sub(
                r'\b(M\.?S\.?|MSc|M\.?Sc)\b', 
                'Master of Science', 
                clean_degree, 
                flags=re.IGNORECASE
            )
            clean_degree = re.sub(
                r'\b(M\.?B\.?A\.?)\b', 
                'Master of Business Administration', 
                clean_degree, 
                flags=re.IGNORECASE
            )
            clean_degree = re.sub(
                r'\b(Ph\.?D\.?|DPhil)\b', 
                'Doctor of Philosophy', 
                clean_degree, 
                flags=re.IGNORECASE
            )
            
            clean_degree = re.sub(r'\bMasters\b', 'Master', clean_degree, flags=re.IGNORECASE)
            clean_degree = re.sub(r'\bAdmin\b', 'Administration', clean_degree, flags=re.IGNORECASE)
            clean_degree = re.sub(r'\bin\b', 'of', clean_degree, flags=re.IGNORECASE)
            clean_degree = clean_degree.strip()
            
            clean_degree = re.sub(r'\bDegree\b$', '', clean_degree, flags=re.IGNORECASE).strip()
            
            if not clean_degree:
                return degree
            
            if clean_degree in self.degree_index:
                return self._get_canonical(clean_degree, self.degree_mapping)
            
            result = process.extractOne(
                clean_degree, 
                self.degree_index, 
                scorer=fuzz.WRatio,
                score_cutoff=85
            )
            
            if result:
                match, score, _ = result
                return self._get_canonical(match, self.degree_mapping)
            return clean_degree
    
    
    def normalize_field(self, field: str) -> str:
        """Normalize field of study"""
        if not field or not isinstance(field, str):
            return ""
        
        clean_field = re.sub(r'\bCS\b', 'Computer Science', field, flags=re.IGNORECASE)
        clean_field = re.sub(r'\bEE\b', 'Electrical Engineering', clean_field, flags=re.IGNORECASE)
        clean_field = re.sub(r'\bCE\b', 'Computer Engineering', clean_field, flags=re.IGNORECASE)
        clean_field = re.sub(r'\bMIS\b', 'Management Information Systems', clean_field, flags=re.IGNORECASE)
        
        clean_field = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean_field)
        
        if not clean_field:
            return field
        
        for canonical, variants in self.field_mapping.items():
            if clean_field.lower() == canonical.lower():
                return canonical
            if any(clean_field.lower() == v.lower() for v in variants):
                return canonical
        return clean_field
    
    
    def _get_canonical(self, variant: str, mapping: Dict) -> str:
        """Get canonical name from variant"""
        if not variant:
            return ""
        for canonical, variants in mapping.items():
            if variant == canonical or variant in variants:
                return canonical
        return variant
    
    
    def normalize_dates(self, start_date: str, end_date: str) -> Tuple[Optional[str], Optional[str]]:
        """Normalize education dates to ISO format"""
        return (
            self.date_normalizer.normalize(start_date),
            self.date_normalizer.normalize(end_date)
        )
    
    
    def normalize_gpa(self, gpa_str: str) -> Optional[float]:
        """Normalize GPA values"""
        if not gpa_str or not isinstance(gpa_str, str):
            return None
            
        match = re.search(r'\b(\d\.\d{1,2})\b', gpa_str)
        if not match:
            # Try pattern for GPAs at start/end of string
            match = re.search(r'^(\d\.\d{1,2})\b|\b(\d\.\d{1,2})$', gpa_str.strip())
            
        # Skip if followed by scale indicator
        if match and re.search(r'out\s+of|on|scale|scale\b', gpa_str, re.IGNORECASE):
            return None
            
        if match:
            try:
                # Use the first non-empty match group
                value = match.group(1) or match.group(2)
                return float(value)
            except (ValueError, TypeError):
                return None
        return None
    
    def normalize(self, education_entries: List[Dict]) -> List[Dict]:
        """Normalize a list of education entries"""
        if not isinstance(education_entries, list):
            return []
            
        normalized = []
        for entry in education_entries:
            if not isinstance(entry, dict):
                continue
                
            normalized_entry = {
                "institution": self.normalize_institution(entry.get("institution", "")),
                "degree": self.normalize_degree(entry.get("degree", "")),
                "field_of_study": self.normalize_field(entry.get("field_of_study")),
                "description": entry.get("description", ""),
            }
            
            # Normalize dates if present
            start_date = entry.get("start_date")
            end_date = entry.get("end_date")
            if start_date or end_date:
                start_norm, end_norm = self.normalize_dates(start_date, end_date)
                normalized_entry["start_date"] = start_norm
                normalized_entry["end_date"] = end_norm
                
            # Add GPA if present
            gpa_str = entry.get("gpa")
            if gpa_str:
                normalized_entry["gpa"] = self.normalize_gpa(gpa_str)
                
            normalized.append(normalized_entry)
            
        return normalized