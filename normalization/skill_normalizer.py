# normalization/skill_normalizer.py
import json
from rapidfuzz import fuzz, process
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class SkillNormalizer:
    def __init__(self, ontology_path: str, threshold: int = 90):
        self.ontology = self._load_ontology(ontology_path)
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
        logger.debug(f"Normalizing skill: {skill}")
        if skill is None:
            return None
        if skill == "":  # Handle empty string
            return ""
            
        # Case-insensitive exact match
        if skill.lower() in self.lower_index:
            original_case = self.lower_index[skill.lower()]
            return self._get_canonical(original_case)
        
        # Fuzzy match
        result = process.extractOne(
            skill, 
            self.skill_index, 
            scorer=fuzz.WRatio,
            score_cutoff=self.threshold
        )
        
        if result:
            match, score, _ = result
            return self._get_canonical(match)
        return skill  # Return original for no match
    
    def normalize_list(self, skills: List[Optional[str]]) -> List[Optional[str]]:
        normalized_skills = set()
        for skill in skills:
            if skill is None:
                normalized_skills.add(None)
            elif isinstance(skill, str):
                normalized_skills.add(self.normalize(skill))
        return list(normalized_skills)
    
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