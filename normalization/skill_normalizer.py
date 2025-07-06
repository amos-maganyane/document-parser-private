# normalization/skill_normalizer.py
import json
from rapidfuzz import fuzz, process
from typing import Dict, List, Optional
import logging
import re
import yaml

logger = logging.getLogger(__name__)

class SkillNormalizer:
    def __init__(self, ontology_path: str, patterns_path: str = "config/patterns.yaml", threshold: int = 80):
        self.ontology = self._load_ontology(ontology_path)
        self.patterns = self._load_patterns(patterns_path)
        self.threshold = threshold
        self.skill_index = self._create_skill_index()
        self.lower_index = {s.lower(): s for s in self.skill_index}  # Case-insensitive lookup
        
    def _load_ontology(self, path: str) -> Dict:
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            raise e
    
    def _load_patterns(self, path: str) -> Dict:
        try:
            with open(path, 'r') as f:
                patterns = yaml.safe_load(f)
                return patterns.get('skill_patterns', {})
        except Exception as e:
            logger.warning(f"Failed to load skill patterns: {e}")
            return {}
    
    def _create_skill_index(self) -> List[str]:
        index = []
        for canonical, variants in self.ontology.items():
            if canonical not in index:
                index.append(canonical)
            for variant in variants:
                if variant not in index:
                    index.append(variant)
        return index
    
    def normalize(self, skill: Optional[str]) -> Optional[str]:
        """Normalize a single skill"""
        logger.debug(f"Normalizing skill: {skill}")
        if skill is None or not isinstance(skill, str):
            return None
        if skill == "":
            return ""
        # Preserve pure whitespace input
        if not skill.strip():
            return skill

        # Remove category labels using configured patterns
        for label in self.patterns.get('category_labels', []):
            skill = re.sub(f'^{label}:\\s*', '', skill)
        skill = re.sub(r'\([^)]*\)', '', skill)  # Remove parentheticals
        skill = skill.strip()
        
        # Case-insensitive exact match
        if skill.lower() in self.lower_index:
            original_case = self.lower_index[skill.lower()]
            return self._get_canonical(original_case)
        
        # Try fuzzy matching
        result = process.extractOne(
            skill, 
            self.skill_index, 
            scorer=fuzz.WRatio,
            score_cutoff=self.threshold
        )
        
        if result:
            match, score, _ = result
            return self._get_canonical(match)
        
        return skill
    
    def normalize_list(self, skills: List[str]) -> List[str]:
        """Normalize a list of skills"""
        if not skills:
            return []

        normalized_skills = set()
        
        # First pass: Extract skills from categorized sections
        for skill in skills:
            if not isinstance(skill, str) or not skill.strip():
                continue
                
            # Clean up the skill
            skill = skill.strip()
            
            # Skip if too short or just punctuation/spaces
            if len(skill) <= 1 or not re.search(r'[a-zA-Z0-9]', skill):
                continue
                
            # Handle category headers with colon
            if ':' in skill:
                _, content = skill.split(':', 1)
                parts = []
                # Split by multiple delimiters
                for delimiter in [',', '&', '|', '/', 'and']:
                    if delimiter in content:
                        parts.extend([p.strip() for p in content.split(delimiter)])
                        break
                if not parts:  # No delimiters found
                    parts = [content.strip()]
            else:
                # Handle non-categorized skills
                parts = [skill]
            
            for part in parts:
                part = part.strip()
                if not part or len(part) <= 1:
                    continue
                    
                # Clean up the part
                part = re.sub(r'^[-•*]\s*', '', part)  # Remove bullet points
                part = re.sub(r'\s+', ' ', part)  # Normalize whitespace
                
                # Handle parenthetical information
                if '(' in part and ')' in part:
                    # Extract main skill and sub-skills
                    main_skill = re.sub(r'\([^)]*\)', '', part).strip()
                    sub_skills = re.findall(r'\((.*?)\)', part)
                    
                    if main_skill:
                        normalized = self.normalize(main_skill)
                        if normalized:
                            normalized_skills.add(normalized)
                    
                    # Add sub-skills if they exist
                    for sub_skill in sub_skills:
                        sub_parts = [s.strip() for s in re.split(r'[,&]', sub_skill)]
                        for sub_part in sub_parts:
                            if sub_part and len(sub_part) > 1:
                                normalized = self.normalize(sub_part)
                                if normalized:
                                    normalized_skills.add(normalized)
                else:
                    # Normalize the skill
                    normalized = self.normalize(part)
                    if normalized:
                        normalized_skills.add(normalized)
        
        # Filter out common words that aren't skills
        stop_words = {'and', 'or', 'with', 'using', 'in', 'on', 'for', 'to', 'of', 'the', 'a', 'an'}
        normalized_skills = {s for s in normalized_skills if s.lower() not in stop_words}
        
        return sorted(list(normalized_skills))
    
    def _get_canonical(self, skill: str) -> str:
        for canonical, variants in self.ontology.items():
            if skill == canonical or skill in variants:
                return canonical
        return skill
    
    def add_custom_mapping(self, variant: str, canonical: str):
        if canonical not in self.ontology:
            self.ontology[canonical] = []
            if canonical not in self.skill_index:
                self.skill_index.append(canonical)
                self.lower_index[canonical.lower()] = canonical
        
        if variant not in self.ontology[canonical]:
            self.ontology[canonical].append(variant)
            if variant not in self.skill_index:
                self.skill_index.append(variant)
                self.lower_index[variant.lower()] = variant