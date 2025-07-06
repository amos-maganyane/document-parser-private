import re
import json
import os
import logging
from typing import Dict, List, Optional, Tuple, Any
from rapidfuzz import fuzz, process
from .date_normalizer import DateNormalizer
import yaml
from datetime import datetime

logger = logging.getLogger(__name__)

class EducationNormalizer:
    def __init__(self, data_dir: str = "data/education", patterns_path: str = "config/patterns.yaml"):
        self.date_normalizer = DateNormalizer()
        self.patterns = self._load_patterns(patterns_path)
        self.institution_mapping = self._load_mapping(os.path.join(data_dir, "institutions.json"))
        self.degree_mapping = self._load_mapping(os.path.join(data_dir, "degrees.json"))
        self.field_mapping = self._load_mapping(os.path.join(data_dir, "fields.json"))
        self.institution_index = self._create_index(self.institution_mapping)
        self.degree_index = self._create_index(self.degree_mapping)

    def _load_patterns(self, path: str) -> Dict:
        try:
            with open(path, 'r') as f:
                patterns = yaml.safe_load(f)
                return patterns.get('education_patterns', {})
        except Exception as e:
            logger.warning(f"Failed to load education patterns: {e}")
            return {}

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
            return "Unknown"
        
        # Clean name using patterns
        clean_name = re.sub(r'[^\w\s&.,-]', '', name, flags=re.IGNORECASE)
        clean_name = clean_name.replace('.', '')
        
        # Remove institution indicators from patterns
        indicators = '|'.join(self.patterns.get('institution_indicators', []))
        if indicators:
            clean_name = re.sub(
                f'\\b({indicators})\\b\\.?',
                '',
                clean_name,
                flags=re.IGNORECASE
            ).strip()
        
        if not clean_name:
            return "Unknown"
        
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
        
        # Return "Unknown" for unmatched institutions
        return "Unknown"
    
    
    def normalize_degree(self, degree: str) -> str:
        """Normalize degree names"""
        if not degree or not isinstance(degree, str):
            return ""
        
        clean_degree = re.sub(r'[^\w\s]', '', degree)
        
        # Apply degree patterns from config
        for pattern in self.patterns.get('degree_indicators', []):
            clean_degree = re.sub(
                f'\\b({pattern})\\b',
                lambda m: self._expand_degree_abbreviation(m.group()),
                clean_degree,
                flags=re.IGNORECASE
            )
        
        clean_degree = re.sub(r'\bMasters\b', 'Master', clean_degree, flags=re.IGNORECASE)
        clean_degree = re.sub(r'\bAdmin\b', 'Administration', clean_degree, flags=re.IGNORECASE)
        clean_degree = re.sub(r'\bin\b', 'of', clean_degree, flags=re.IGNORECASE)
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

    def _expand_degree_abbreviation(self, abbrev: str) -> str:
        """Expand degree abbreviations based on common patterns"""
        expansions = {
            'BS': 'Bachelor of Science',
            'BA': 'Bachelor of Arts',
            'MS': 'Master of Science',
            'MA': 'Master of Arts',
            'MBA': 'Master of Business Administration',
            'PhD': 'Doctor of Philosophy'
        }
        clean_abbrev = re.sub(r'\.', '', abbrev.upper())
        return expansions.get(clean_abbrev, abbrev)
    
    
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
    
    
    def normalize_dates(self, start_date: Optional[str], end_date: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """Normalize date strings to consistent format"""
        def parse_date(date_str: Optional[str]) -> Optional[str]:
            if not date_str:
                return None
            try:
                # Try to parse various date formats
                for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%B %Y", "%b %Y", "%Y"]:
                    try:
                        dt = datetime.strptime(date_str.strip(), fmt)
                        return dt.strftime("%Y-%m-%d")  # Return consistent format
                    except ValueError:
                        continue
                return date_str  # Return original if no format matches
            except Exception:
                return date_str
        
        return parse_date(start_date), parse_date(end_date)
    
    
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
    
    def normalize(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize education entries with proper field extraction"""
        normalized = []
        for entry in entries:
            # Extract basic fields
            institution = entry.get("institution", "")
            degree = entry.get("degree", "")
            field = entry.get("field_of_study", "")
            description = entry.get("description", "")
            
            # Extract and normalize dates
            start_date = entry.get("start_date", "")
            end_date = entry.get("end_date", "")
            start_norm, end_norm = self.normalize_dates(start_date, end_date)
            
            # Extract achievements from description
            achievements = []
            description_lines = description.split('\n')
            achievement_lines = []
            in_achievements = False
            
            for line in description_lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check for achievement section markers
                if any(marker in line.lower() for marker in [
                    "achievements:", "accomplishments:", "awards:", "honors:",
                    "academic achievements", "notable achievements"
                ]):
                    in_achievements = True
                    continue
                
                # Check for bullet points or numbered achievements
                if line.startswith('•') or line.startswith('-') or re.match(r'^\d+\.', line):
                    achievement = line.lstrip('•- ').strip()
                    if achievement:
                        achievements.append(achievement)
                        continue
                
                # If in achievements section, add non-bullet points too
                if in_achievements:
                    achievements.append(line)
                else:
                    achievement_lines.append(line)
            
            # If no explicit achievements found, look for achievement-like statements
            if not achievements:
                for line in achievement_lines:
                    # Look for achievement indicators
                    if any(indicator in line.lower() for indicator in [
                        "awarded", "received", "achieved", "earned", "graduated",
                        "dean's list", "honor roll", "distinction", "cum laude",
                        "gpa", "grade", "score", "rank", "medal", "prize",
                        "scholarship", "fellowship", "grant"
                    ]):
                        achievements.append(line)
            
            # Ensure we have at least one achievement
            if not achievements:
                achievements = ["Successfully completed coursework and requirements"]
            
            normalized.append({
                "institution": institution,
                "degree": degree,
                "field_of_study": field,
                "start_date": start_norm or "",
                "end_date": end_norm or "",
                "description": "\n".join(achievement_lines),
                "achievements": achievements
            })
        
        return normalized