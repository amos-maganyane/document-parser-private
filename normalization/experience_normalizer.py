from datetime import datetime, date
import re
import json
import os
from typing import Dict, List, Optional, Tuple, Union, Sequence
from rapidfuzz import fuzz, process
from .date_normalizer import DateNormalizer
from .skill_normalizer import SkillNormalizer
from datetime import date as date_today  
import yaml
import logging

logger = logging.getLogger(__name__)

class ExperienceNormalizer:
    def __init__(self, data_dir: str = "data/experience", patterns_path: str = "config/patterns.yaml"):
        self.date_normalizer = DateNormalizer()
        self.skill_normalizer = SkillNormalizer(ontology_path="data/ontology/skills_ontology.json", patterns_path=patterns_path)
        self.patterns = self._load_patterns(patterns_path)
        self.company_mapping = self._load_mapping(os.path.join(data_dir, "companies.json"))
        self.title_mapping = self._load_mapping(os.path.join(data_dir, "titles.json"))
        self.position_mapping = self._load_mapping(os.path.join(data_dir, "titles.json"))
        self.company_index = self._create_index(self.company_mapping)
        self.title_index = self._create_index(self.title_mapping)
        self.position_index = self._create_index(self.position_mapping)
        
        # Load normalization settings
        self.normalization_settings = self.patterns.get('experience_normalization', {})
        self.company_threshold = self.normalization_settings.get('fuzzy_match', {}).get('company_threshold', 85)
        self.title_threshold = self.normalization_settings.get('fuzzy_match', {}).get('title_threshold', 90)
        self.cleaning_patterns = self.normalization_settings.get('description_cleaning', {})
        
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
    
    def _load_patterns(self, path: str) -> Dict:
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load experience patterns: {e}")
            return {}
    
    def normalize_company(self, name: str) -> str:
        if not name:
            return ""
        
        # Clean common artifacts using patterns from config
        artifacts_pattern = self.cleaning_patterns.get('artifacts', '[^\\w\\s&.,-]')
        cleaned = re.sub(artifacts_pattern, '', name, flags=re.IGNORECASE)
        
        # Remove company suffixes from patterns
        suffixes = self.patterns.get('experience_patterns', {}).get('company_suffixes', [])
        for suffix in suffixes:
            cleaned = re.sub(
                f'\\b({suffix})\\b\\.?',
                '',
                cleaned,
                flags=re.IGNORECASE
            ).strip()
        
        # Use cleaned version for matching, but return original casing if no match
        return self._match_entity(cleaned, self.company_mapping) or name
    
    def normalize_title(self, title: str) -> str:
        if not title:
            return ""
        
        # Standardize abbreviations from patterns
        expanded = title
        title_abbrevs = self.patterns.get('experience_patterns', {}).get('title_abbreviations', {})
        
        # First pass: expand compound abbreviations (e.g., "Sr. SWE")
        for abbrev, full in title_abbrevs:
            if " " in abbrev:  # This identifies compound patterns
                pattern = abbrev.replace(" ", "\\s+")  # Allow flexible whitespace
                expanded = re.sub(f'\\b{pattern}\\b', full, expanded, flags=re.IGNORECASE)
        
        # Second pass: expand individual abbreviations
        for abbrev, full in title_abbrevs:
            if " " not in abbrev:  # This identifies single-word patterns
                # Handle optional periods in abbreviations
                pattern = abbrev.replace(".", "\\.?")  # Make periods optional
                expanded = re.sub(f'\\b{pattern}\\b', full, expanded, flags=re.IGNORECASE)
        
        # Try to match the expanded version first
        matched = self._match_entity(expanded, self.title_mapping)
        if matched:
            return matched
        
        # Try to match the original version
        matched = self._match_entity(title, self.title_mapping)
        if matched:
            return matched
        
        # If no match found, return the expanded version
        return expanded
    
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
        # Convert to Optional[str] type to match SkillNormalizer's interface
        optional_techs: List[Optional[str]] = [tech for tech in tech_list]
        normalized = self.skill_normalizer.normalize_list(optional_techs)
        # Filter out None values from result
        return [tech for tech in normalized if tech is not None]
    
    def normalize_description(self, description: str) -> str:
        """Clean and standardize job descriptions"""
        if not description:
            return ""
        
        # Remove bullet points and numbering using pattern from config
        bullet_pattern = self.cleaning_patterns.get('bullet_points', '^[\\s•\\-*]+')
        description = re.sub(bullet_pattern, '', description, flags=re.MULTILINE)
        
        # Remove excessive whitespace using pattern from config
        whitespace_pattern = self.cleaning_patterns.get('whitespace', '\\s+')
        description = re.sub(whitespace_pattern, ' ', description).strip()
        
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
    
    def calculate_duration(self, start: Union[str, date], end: Union[str, date]) -> int:
        """Calculate duration in months"""
        try:
            from dateutil.relativedelta import relativedelta
            
            # Get start date
            start_dt = None
            if isinstance(start, date):
                start_dt = start
            elif isinstance(start, str):
                start_str = self.date_normalizer.normalize(start)
                if start_str:
                    start_dt = datetime.strptime(start_str, '%Y-%m-%d').date()
            
            # Get end date
            end_dt = None
            if isinstance(end, date):
                end_dt = end
            elif isinstance(end, str):
                end_str = self.date_normalizer.normalize(end)
                if end_str:
                    end_dt = datetime.strptime(end_str, '%Y-%m-%d').date()
            
            # Use today's date for current positions
            if not end_dt:
                end_dt = date.today()
                
            if not start_dt:
                return 0
                
            if start_dt > end_dt:
                return 0
                
            delta = relativedelta(end_dt, start_dt)
            total_months = delta.years * 12 + delta.months
            
            # Add an extra month if there are remaining days
            if delta.days > 0:
                total_months += 1
                
            return total_months
        except Exception as e:
            logger.warning(f"Error calculating duration: {e}")
            return 0
            

    def _match_entity(self, text: str, mapping: Dict) -> Optional[str]:
        # Exact match
        if text in self.company_index:
            return self._get_canonical(text, mapping)
        
        # Fuzzy match with configurable thresholds
        threshold = self.company_threshold if mapping is self.company_mapping else self.title_threshold
        result = process.extractOne(
            text, 
            self.company_index if mapping is self.company_mapping else self.position_index,
            scorer=fuzz.WRatio,
            score_cutoff=threshold
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
                start_norm, end_norm = self.normalize_dates(
                    start_date if start_date else "", 
                    end_date if end_date else ""
                )
                normalized_entry["start_date"] = start_norm
                normalized_entry["end_date"] = end_norm
                
                # Calculate duration if both dates are available
                if start_norm and end_norm:
                    normalized_entry["duration_months"] = self.calculate_duration(start_norm, end_norm)
                    
            normalized.append(normalized_entry)
            
        return normalized