from typing import Dict, List, Optional, Tuple
from transformers import pipeline

from normalization.experience_normalizer import ExperienceNormalizer
from .pii_handler import PIIAnonymizer
from normalization.skill_normalizer import SkillNormalizer
from normalization.date_normalizer import DateNormalizer
from normalization.education_normalizer import EducationNormalizer
from schemas.resume_schema import Resume, Education, Experience, Project
import dateparser
import re
import logging
from datetime import date

class EntityExtractor:
    def __init__(self, config: Dict):
        self.ner_pipeline = pipeline("ner", model="dslim/bert-base-NER", aggregation_strategy="simple")
        self.pii_anonymizer = PIIAnonymizer(config.get('pii_config', {}))
        self.skill_normalizer = SkillNormalizer(config.get('skill_ontology_path', 'data/ontology/skills_ontology.json'))
        self.date_normalizer = DateNormalizer()
        self.edu_normalizer = EducationNormalizer(config.get('education_data_dir', 'data/education'))
        self.exp_normalizer = ExperienceNormalizer(config.get('experience_data_dir', 'data/experience'))
        self.min_confidence = config.get('min_confidence', 0.7)

    def extract_resume(self, document: Dict) -> Resume:
        try:
            sections = document.get('sections', {})
            raw_text = self._combine_sections(sections)
            anonymized_text, pii_map = self.pii_anonymizer.anonymize(raw_text)

            resume = Resume(
                contact=self._extract_contact(sections.get('contact', '')),
                summary=self._extract_summary(sections.get('summary', '')),
                skills=self._extract_skills(sections.get('skills', '')),
                education=self._extract_education(sections.get('education', '')),
                experience=self._extract_experience(sections.get('experience', '')),
                projects=self._extract_projects(sections.get('projects', '')),
                certifications=self._extract_certifications(sections.get('education', ''))
            )

            return resume
        except Exception as e:
            logging.error(f"Entity extraction failed: {str(e)}")
            return Resume()

    def _combine_sections(self, sections: Dict) -> str:
        return "\n\n".join([content['content'] for content in sections.values()])

    def _extract_contact(self, contact_text: str) -> Dict:
        contact_info = {}
        
        # Extract name (assuming it's the first line before any common contact patterns)
        name_match = re.match(r'^([A-Z][a-zA-Z\s]+)\n', contact_text)
        if name_match:
            contact_info["name"] = name_match.group(1).strip()
            contact_text = contact_text[name_match.end():].strip() # Remove name from text

        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_match = re.search(email_pattern, contact_text)
        if email_match:
            contact_info["email"] = email_match.group(0)

        phone_pattern = r'(\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b|\+\d{1,3}[-.\s]?\d{3,}[-.\s]?\d{4,})\b'
        phone_matches = re.findall(phone_pattern, contact_text)
        if phone_matches:
            contact_info["phone"] = phone_matches[0] if isinstance(phone_matches[0], str) else ''.join(phone_matches[0])

        linkedin_pattern = r'(https?://)?(www\.)?linkedin\.com/(in|pub)/[a-zA-Z0-9-]+\b'
        linkedin_match = re.search(linkedin_pattern, contact_text)
        if linkedin_match:
            contact_info["linkedin"] = linkedin_match.group(0)

        github_pattern = r'(https?://)?(www\.)?github\.com/[a-zA-Z0-9-]+/?\b'
        github_match = re.search(github_pattern, contact_text)
        if github_match:
            contact_info["github"] = github_match.group(0)

        if contact_text.strip():
            entities = self.ner_pipeline(contact_text)
            locations = [entity['word'] for entity in entities if entity['entity_group'] == 'LOC']
            if locations:
                contact_info["location"] = locations[0]

        return contact_info

    def _extract_summary(self, summary_text: str) -> str:
        cleaned = re.sub(r'\s+', ' ', summary_text).strip()
        if len(cleaned) > 500:
            last_period = cleaned[:500].rfind('.')
            return cleaned[:last_period + 1] if last_period > 0 else cleaned[:497] + '...'
        return cleaned

    def _extract_skills(self, skills_text: str) -> List[str]:
        if not skills_text.strip():
            return []

        skills = set()
        # Split by common delimiters and clean up
        potential_skills = re.split(r'[\n,;•/]+', skills_text)
        for skill_phrase in potential_skills:
            skill_phrase = skill_phrase.strip()
            if not skill_phrase:
                continue
            
            # Use NER for broader entity recognition, but also consider direct matches
            entities = self.ner_pipeline(skill_phrase)
            found_ner_skill = False
            for entity in entities:
                # Common NER tags for skills might be MISC, ORG, or even others depending on model training
                if entity['entity_group'] in ['MISC', 'ORG', 'LOC', 'PROD'] or "skill" in entity['word'].lower():
                    skills.add(entity['word'])
                    found_ner_skill = True
            
            # If NER didn't find anything, consider the whole phrase as a potential skill
            if not found_ner_skill:
                skills.add(skill_phrase)

        normalized_skills = []
        for skill in skills:
            if len(skill) <= 1 or skill.isdigit():
                continue
            norm_skill = self.skill_normalizer.normalize(skill)
            if norm_skill:
                normalized_skills.append(norm_skill)

        return sorted(list(set(normalized_skills)))

    def _extract_education(self, education_text: str) -> List[Education]:
        if not education_text.strip():
            return []

        entries = []
        # Split education entries by common patterns like newlines followed by a capital letter
        # or specific keywords indicating a new entry.
        education_entries = re.split(r'\n(?=[A-Z][^a-z])', education_text)

        for entry_text in education_entries:
            entry_text = entry_text.strip()
            if not entry_text:
                continue
            
            # Attempt to extract institution, degree, and field of study
            institution = self._extract_institution(entry_text)
            degree = self._extract_degree(entry_text)
            field_of_study = self._extract_field_of_study(entry_text)
            
            start_date, end_date = self.date_normalizer.extract_period(entry_text)

            entries.append(Education(
                institution=self.edu_normalizer.normalize_institution(institution or ''),
                degree=self.edu_normalizer.normalize_degree(degree or ''),
                field_of_study=field_of_study,
                start_date=start_date,
                end_date=end_date,
                description=entry_text
            ))
        return entries

    def _extract_experience(self, experience_text: str) -> List[Experience]:
        if not experience_text.strip():
            return []

        entries = []
        # Split experience entries by common patterns like newlines followed by a capital letter
        # or specific keywords indicating a new entry, often combined with date patterns.
        experience_entries = re.split(r'\n(?=[A-Z][^a-z])', experience_text)

        for entry_text in experience_entries:
            entry_text = entry_text.strip()
            if not entry_text:
                continue

            # Attempt to extract company and position
            company = self._extract_company(entry_text)
            position = self._extract_position(entry_text)

            start_date, end_date = self.date_normalizer.extract_period(entry_text)

            technologies = self._extract_skills(entry_text)

            entries.append(Experience(
                company=self.exp_normalizer.normalize_company(company or ''),
                position=self.exp_normalizer.normalize_title(position or ''),
                start_date=str(start_date) if start_date else None,
                end_date=str(end_date) if end_date else None,
                description=entry_text,
                technologies=technologies
            ))
        return entries

    def _extract_company(self, text: str) -> Optional[str]:
        entities = self.ner_pipeline(text)
        for entity in entities:
            if entity['entity_group'] == 'ORG':
                return entity['word']
        # Fallback to regex if NER doesn't find an organization
        # Look for common company indicators (e.g., Inc, LLC, Co, Group)
        match = re.search(r'\b([A-Z][a-zA-Z0-9\s,.-]+(?:Inc|LLC|Co|Company|Group|Corp|Corporation|Ltd|Limited))\b', text)
        if match:
            return match.group(1)
        return None

    def _extract_position(self, text: str) -> Optional[str]:
        entities = self.ner_pipeline(text)
        for entity in entities:
            if entity['entity_group'] == 'JOB_TITLE': # Assuming JOB_TITLE is a possible NER tag
                return entity['word']
            # Often positions are tagged as MISC or other general entities
            if entity['entity_group'] == 'MISC' and ("developer" in entity['word'].lower() or "engineer" in entity['word'].lower()):
                return entity['word']
        # Fallback to regex for common job titles
        match = re.search(r'\b(software engineer|developer|data scientist|project manager|analyst|consultant)\b', text, re.IGNORECASE)
        if match:
            return match.group(0)
        return None

    def _extract_projects(self, projects_text: str) -> List[Project]:
        if not projects_text.strip():
            return []

        projects = []
        entries = self._split_project_entries(projects_text)

        for entry in entries:
            if not entry.strip():
                continue

            name, description, technologies = self._parse_project_entry(entry)

            if name:
                projects.append(Project(
                    name=name,
                    description=description,
                    technologies=technologies
                ))
        return projects

    def _split_project_entries(self, text: str) -> List[str]:
        """Splits projects section into individual entries"""
        # Enhanced project boundary detection
        boundaries = [
            r"\n(?=[A-Z][\w\s-]+ - [\w\s]+(?:app|system|platform|game))",  # Project Name - Description
            r"\n(?=\d+\.\s+[A-Z][\w\s-]+)",  # Numbered list
            r"\n(?=Project \d+:)",  # "Project X:"
            r"\n(?=\s*[•\-*]?\s*[A-Z][^\n:]+[:\n])", # Bullet points or titles
            r"\n\n(?=[A-Z])" # Split by double newline if the next line starts with a capital letter
        ]
        
        # Create a combined regex for splitting
        pattern = "|".join(boundaries)
        entries = re.split(pattern, text)
        
        return [entry.strip() for entry in entries if entry.strip()]

    def _parse_project_entry(self, text: str) -> Tuple[Optional[str], Optional[str], List[str]]:
        """Parses an individual project entry"""
        # Split into name and description
        parts = text.split('\n', 1)
        name = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else None
        
        # Clean project name (remove bullets or numbering)
        name = re.sub(r'^[\s•\-*]+\s*', '', name)
        name = re.sub(r':\s*', '', name)  # Remove trailing colon if it's a heading
        
        # Extract technologies from description
        technologies = []
        if description:
            technologies = self._extract_skills(description)
        
        return name, description, technologies

    def _extract_certifications(self, certifications_text: str) -> List[str]:
        if not certifications_text.strip():
            return []

        certifications = []
        # Split certifications by common patterns like newlines followed by a capital letter
        # or specific keywords indicating a new entry.
        certification_entries = re.split(r'\n(?=[A-Z][^a-z])', certifications_text)

        for entry_text in certification_entries:
            if not entry_text.strip():
                continue
            certifications.append(entry_text.strip())
        return certifications

    def _extract_institution(self, text: str) -> Optional[str]:
        entities = self.ner_pipeline(text)
        for entity in entities:
            if entity['entity_group'] == 'ORG':
                return entity['word']
        # Fallback to regex if NER doesn't find an organization
        match = re.search(r'(university|college|institute|school|academy)\b', text, re.IGNORECASE)
        if match:
            return match.group(0)
        return None

    def _extract_degree(self, text: str) -> Optional[str]:
    # Attempt to extract degree using NER
        entities = self.ner_pipeline(text)
        for entity in entities:
            if "degree" in entity['word'].lower() or "certificate" in entity['word'].lower():
                return entity['word']

        # Fallback to regex if NER fails
        match = re.search(r'\b(bachelor|master|phd|bsc|msc|mba|ba|bs|ms|ma)\b\.?', text, re.IGNORECASE)
        if match:
            return match.group(0)

        # Return None if no degree found
        return None
    
    def _extract_field_of_study(self, text: str) -> Optional[str]:
        # Look for common field of study keywords
        fields = [
            "computer science", "software engineering", "electrical engineering",
            "mechanical engineering", "civil engineering", "data science",
            "artificial intelligence", "machine learning", "information technology",
            "business administration", "finance", "marketing", "physics",
            "mathematics", "chemistry", "biology", "psychology", "history",
            "literature", "arts", "design"
        ]
        for field in fields:
            if re.search(r'\b' + re.escape(field) + r'\b', text, re.IGNORECASE):
                return field
        return None
        
        # Extract technologies from description
        technologies = []
        if description:
            technologies = self._extract_skills(description)
        
        return name, description, technologies