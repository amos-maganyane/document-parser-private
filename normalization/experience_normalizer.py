from datetime import datetime
import re
import json
import os
from typing import Dict, List, Optional, Tuple
from rapidfuzz import fuzz, process
from .date_normalizer import DateNormalizer
from .skill_normalizer import SkillNormalizer
from datetime import date as date_today  

class ExperienceNormalizer:
    def __init__(self, data_dir: str = "data/experience"):
        self.date_normalizer = DateNormalizer()
        self.skill_normalizer = SkillNormalizer(os.path.join(data_dir, "skills_ontology.json"))
        self.company_mapping = self._load_mapping(os.path.join(data_dir, "companies.json"))
        self.title_mapping = self._load_mapping(os.path.join(data_dir, "titles.json"))
        self.company_index = self._create_index(self.company_mapping)
        self.title_index = self._create_index(self.title_mapping)
        
    def _load_mapping(self, file_path: str) -> Dict:
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _create_index(self, mapping: Dict) -> List[str]:
        index = set()
        for canonical, variants in mapping.items():
            index.add(canonical)
            for variant in variants:
                index.add(variant)
        return list(index)
    
    def normalize_company(self, name: str) -> str:
        if not name:
            return ""
        
        # Clean common artifacts
        cleaned = re.sub(r'[^\w\s&.,-]', '', name, flags=re.IGNORECASE)
        cleaned = re.sub(
            r'\b(Inc|Incorporated|Corp|Corporation|Co|Company|Ltd|Limited|LLC|Group)\b\.?', 
            '', 
            cleaned, 
            flags=re.IGNORECASE
        ).strip()
        
        # Use cleaned version for matching, but return original casing if no match
        return self._match_entity(cleaned, self.company_mapping) or name
    
    def normalize_title(self, title: str) -> str:
        if not title:
            return ""
        
        # Standardize abbreviations
        expanded = title
        replacements = [
            (r'\bSr\.?\b', 'Senior'),
            (r'\bJr\.?\b', 'Junior'),
            (r'\bMgr\.?\b', 'Manager'),
            (r'\bDir\.?\b', 'Director'),
            (r'\bVP\.?\b', 'Vice President'),
            (r'\bPM\b', 'Project Manager'),
            (r'\bSWE\b', 'Software Engineer'),
            (r'\bSDE\b', 'Software Development Engineer'),
        ]
        
        for pattern, replacement in replacements:
            expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)
        
        # Try to match the expanded version first
        matched = self._match_entity(expanded, self.title_mapping)
        if matched:
            return matched
        
        # If no match with expanded version, try original
        return self._match_entity(title, self.title_mapping) or title

    
    def normalize_dates(self, start_date: str, end_date: str) -> Tuple[Optional[str], Optional[str]]:
        normalized_start = None
        normalized_end = None
        
        try:
            if start_date:
                normalized_start = self.date_normalizer.normalize(start_date)
        except Exception:
            pass
            
        try:
            if end_date:
                normalized_end = self.date_normalizer.normalize(end_date)
        except Exception:
            pass
            
        return normalized_start, normalized_end
    
    def normalize_technologies(self, tech_list: List[str]) -> List[str]:
        """Normalize technology names using skill ontology"""
        return self.skill_normalizer.normalize_list(tech_list)
    
    def normalize_description(self, description: str) -> str:
        """Clean and standardize job descriptions"""
        if not description:
            return ""
        
        # Remove bullet points and numbering
        description = re.sub(r'^[\s•\-*]+', '', description, flags=re.MULTILINE)
        
        # Remove excessive whitespace
        description = re.sub(r'\s+', ' ', description).strip()
        
        # Capitalize first letter
        if description:
            description = description[0].upper() + description[1:]
        
        return description
    
    def _get_canonical(self, variant: str, mapping: Dict) -> str:
        """Get canonical name from variant"""
        for canonical, variants in mapping.items():
            if variant == canonical or variant in variants:
                return canonical
        return variant
    
    def calculate_duration(self, start: str, end: str) -> int:
        """Calculate duration in months"""
        try:
            from dateutil.relativedelta import relativedelta
            start_dt = self.date_normalizer.normalize(start, return_date=True)
            end_dt = self.date_normalizer.normalize(end, return_date=True)
            
            # Use date_today.today() instead of datetime.now().date()
            if end_dt is None:
                end_dt = date_today.today()
                
            if not start_dt or not end_dt:
                return 0
                
            if start_dt > end_dt:
                return 0
                
            delta = relativedelta(end_dt, start_dt)
            return delta.years * 12 + delta.months
        except:
            return 0
            

    def _match_entity(self, text: str, mapping: Dict) -> Optional[str]:
        # Exact match
        if text in self.company_index:
            return self._get_canonical(text, mapping)
        
        # Fuzzy match
        result = process.extractOne(
            text, 
            self.company_index if mapping is self.company_mapping else self.title_index,
            scorer=fuzz.WRatio,
            score_cutoff=85 if mapping is self.company_mapping else 90
        )
        
        if result:
            match, score, _ = result
            return self._get_canonical(match, mapping)
        return None
    
    def normalize(self, experience_entries: List[Dict]) -> List[Dict]:
        """Normalize a list of experience entries"""
        if not isinstance(experience_entries, list):
            return []
            
        normalized = []
        for entry in experience_entries:
            if not isinstance(entry, dict):
                continue
                
            normalized_entry = {
                "company": self.normalize_company(entry.get("company", "")),
                "position": self.normalize_title(entry.get("position", "")),
                "description": self.normalize_description(entry.get("description", "")),
                "technologies": self.normalize_technologies(entry.get("technologies", [])),
            }
            
            # Normalize dates if present
            start_date = entry.get("start_date")
            end_date = entry.get("end_date")
            if start_date or end_date:
                start_norm, end_norm = self.normalize_dates(start_date, end_date)
                normalized_entry["start_date"] = start_norm
                normalized_entry["end_date"] = end_norm
                
                # Calculate duration if both dates are available
                if start_norm:
                    normalized_entry["duration_months"] = self.calculate_duration(start_date, end_date)
                    
            normalized.append(normalized_entry)
            
        return normalized