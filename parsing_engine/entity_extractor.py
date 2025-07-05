from typing import Dict, List, Optional, Tuple
import spacy
from spacy.tokens import Doc, Span

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
# Update the __init__ method in EntityExtractor class
    def __init__(self, config: Dict):
        self.nlp = spacy.load(config.get('base_model', 'en_core_web_lg'))
        self.pii_anonymizer = PIIAnonymizer(config.get('pii_config', {}))
        self.skill_normalizer = SkillNormalizer(config.get('skill_ontology_path'))
        self.date_normalizer = DateNormalizer()
        self.edu_normalizer = EducationNormalizer(config.get('education_data_dir'))
        self.exp_normalizer = ExperienceNormalizer(config.get('experience_data_dir'))
        self.min_confidence = config.get('min_confidence', 0.7)
        
        # Add custom pipeline components - FIXED VERSION
        if 'merge_entities' not in self.nlp.pipe_names:
            self.nlp.add_pipe('merge_entities')
        
        # Configure NLP for resume parsing
        self._configure_nlp()
        
    def _configure_nlp(self):
        # Add patterns for skill detection
        if 'entity_ruler' not in self.nlp.pipe_names:
            ruler = self.nlp.add_pipe("entity_ruler", before="ner")
        else:
            ruler = self.nlp.get_pipe("entity_ruler")
        
        patterns = [
            {"label": "SKILL", "pattern": [{"LOWER": "machine"}, {"LOWER": "learning"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "deep"}, {"LOWER": "learning"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "natural"}, {"LOWER": "language"}, {"LOWER": "processing"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "data"}, {"LOWER": "analysis"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "cloud"}, {"LOWER": "computing"}]},
        ]
        ruler.add_patterns(patterns)
        
    def extract_resume(self, document: Dict) -> Resume:
        try:
            # Extract and anonymize text
            sections = document.get('sections', {})
            raw_text = self._combine_sections(sections)
            anonymized_text, pii_map = self.pii_anonymizer.anonymize(raw_text)
            
            # Process with NLP
            doc = self.nlp(anonymized_text)
            
            # Extract entities
            resume = Resume(
                contact=self._extract_contact(document.get('sections', {}).get('contact', '')),
                summary=self._extract_summary(document.get('sections', {}).get('summary', '')),
                skills=self._extract_skills(doc),
                education=self._extract_education(document.get('sections', {}).get('education', '')),
                experience=self._extract_experience(document.get('sections', {}).get('experience', '')),
                projects=self._extract_projects(document.get('sections', {}).get('projects', '')),
                certifications=self._extract_certifications(document.get('sections', {}).get('education', ''))
            )
            
            return resume
        except Exception as e:
            logging.error(f"Entity extraction failed: {str(e)}")
            # Return partial results if possible
            return Resume()

    def _combine_sections(self, sections: Dict) -> str:
        return "\n\n".join([content['content'] for content in sections.values()])
    
    def _extract_contact(self, contact_text: str) -> Dict:
        """Extracts contact information with advanced pattern matching"""
        contact_info = {}
        
        # Email extraction
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_match = re.search(email_pattern, contact_text)
        if email_match:
            contact_info["email"] = email_match.group(0)
        
        # Phone extraction (international format support)
        # In _extract_contact
        phone_pattern = r'(\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b|\+\d{1,3}[-.\s]?\d{3,}[-.\s]?\d{4,})\b'
        phone_matches = re.findall(phone_pattern, contact_text)
        if phone_matches:
            contact_info["phone"] = phone_matches[0] if isinstance(phone_matches[0], str) else ''.join(phone_matches[0])
        
        # LinkedIn profile extraction
        linkedin_pattern = r'(https?://)?(www\.)?linkedin\.com/(in|pub)/[a-zA-Z0-9-]+'
        linkedin_match = re.search(linkedin_pattern, contact_text)
        if linkedin_match:
            contact_info["linkedin"] = linkedin_match.group(0)
        
        # Location extraction using NLP
        if contact_text.strip():
            doc = self.nlp(contact_text)
            locations = [ent.text for ent in doc.ents if ent.label_ == "GPE"]
            if locations:
                contact_info["location"] = locations[0]
        
        return contact_info
    
    def _extract_summary(self, summary_text: str) -> str:
        """Cleans and extracts the professional summary"""
        # Remove excessive whitespace and line breaks
        cleaned = re.sub(r'\s+', ' ', summary_text).strip()
        # Truncate to 500 characters but preserve sentence boundaries
        if len(cleaned) > 500:
            last_period = cleaned[:500].rfind('.')
            return cleaned[:last_period + 1] if last_period > 0 else cleaned[:497] + '...'
        return cleaned
    
    def _extract_skills(self, doc: Doc) -> List[str]:
        """Extracts skills using multiple techniques"""
        skills = set()
        
        # 1. Extract using NER
        for ent in doc.ents:
            if ent.label_ == "SKILL":
                skills.add(ent.text.strip())
        
        # 2. Extract noun chunks that match skill patterns
        for chunk in doc.noun_chunks:
            if self._is_skill(chunk):
                skills.add(chunk.text.strip())
        
        # 3. Extract from known skill patterns
        for token in doc:
            if token.text.lower() in ['java', 'python', 'c++', 'javascript', 'sql']:
                skills.add(token.text)
        
        # 4. Normalize and deduplicate
        return self.skill_normalizer.normalize_list(list(skills))
    
    def _is_skill(self, chunk: Span) -> bool:
        """Determines if a text span represents a skill"""
        # Heuristic: Skills are typically 1-3 words, not containing stop words
        if len(chunk) > 3 or len(chunk) < 1:
            return False
        if any(token.is_stop for token in chunk):
            return False
        if any(token.is_punct for token in chunk):
            return False
        return True
    
    def _extract_education(self, education_text: str) -> List[Education]:
        """Extracts education information using pattern matching and NLP"""
        if not education_text.strip():
            return []
            
        education_entries = []
        entries = self._split_education_entries(education_text)
        
        for entry in entries:
            if not entry.strip():
                continue
                
            # Extract components using improved parsing
            institution, degree, dates, gpa = self._parse_education_entry(entry)
            field_of_study = self._extract_field_of_study(entry)
            
            # Normalize extracted values
            institution = self.edu_normalizer.normalize_institution(institution) if institution else None
            degree = self.edu_normalizer.normalize_degree(degree) if degree else None
            field_of_study = self.edu_normalizer.normalize_field(field_of_study) if field_of_study else None
            gpa_value = self.edu_normalizer.normalize_gpa(str(gpa)) if gpa is not None else None
            
            # Parse and normalize dates
            start_date, end_date = None, None
            if dates:
                date_parts = re.split(r'\s*[–\-]\s*', dates, 1)
                start_date = self.date_normalizer.normalize(date_parts[0].strip())
                end_date = self.date_normalizer.normalize(date_parts[1].strip()) if len(date_parts) > 1 else None
            
            # Create education object only if we have valid data
            if institution or degree:
                education_entries.append(Education(
                    institution=institution,
                    degree=degree,
                    field_of_study=field_of_study,
                    start_date=start_date,
                    end_date=end_date,
                    gpa=gpa_value
                ))
        
        return education_entries
    
    # In _split_education_entries
    def _split_education_entries(self, text: str) -> List[str]:
        # Group lines by institution
        entries = []
        current_entry = []
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check for new institution pattern
            if re.match(r'^[A-Z][a-zA-Z\s&]+$', line) and current_entry:
                entries.append('\n'.join(current_entry))
                current_entry = [line]
            else:
                current_entry.append(line)
        
        if current_entry:
            entries.append('\n'.join(current_entry))
        
        return entries

    
    def _parse_education_entry(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[float]]:
        """Parses an individual education entry"""
        # Degree pattern: MBA, BSc, Ph.D., etc.
        degree_pattern = r'\b(?:B\.?[A-Z]\.?|M\.?[A-Z]\.?|PhD|Ph\.?D\.?|MBA|MSc|MS|BS|BA)\b'
        
        # Date pattern: 2010-2014, 2015 - 2019, 2020-Present
        date_pattern = r'(\d{4}\s*[–\-]\s*\d{4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{4}\s*[–\-]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{4}|\d{4}\s*[–\-]\s*(?:Present|Current))'
        
        # GPA pattern: GPA: 3.8/4.0, 3.9/4
        gpa_pattern = r'\bGPA\s*[:]?\s*(\d\.\d{1,2})\b'
        
        # Extract components
        degree_match = re.search(degree_pattern, text, re.IGNORECASE)
        date_match = re.search(date_pattern, text)
        gpa_match = re.search(gpa_pattern, text)
        gpa = float(gpa_match.group(1)) if gpa_match else None
        
        # Find institution - typically before degree or dates
        institution_text = text
        if degree_match:
            institution_text = institution_text[:degree_match.start()]
        if date_match:
            institution_text = institution_text[:date_match.start()]
        
        # Clean institution name
        institution = institution_text.strip()
        institution = re.sub(r'[,;]$', '', institution)
        
        return (
            institution if institution else None,
            degree_match.group(0) if degree_match else None,
            date_match.group(0) if date_match else None,
            gpa
        )
    
    def _extract_field_of_study(self, text: str) -> Optional[str]:
        """Extracts field of study from education entry"""
        patterns = [
            r'in\s(.+?)(?:[,;]|$)',
            r'Major\s*[:]?\s*(.+)',
            r'Field\s*[:]?\s*(.+)',
            r'Concentration\s*[:]?\s*(.+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def _extract_experience(self, experience_text: str) -> List[Experience]:
        """Extracts work experience using advanced pattern matching"""
        if not experience_text.strip():
            return []
            
        experiences = []
        entries = self._split_experience_entries(experience_text)
        
        for entry in entries:
            if not entry.strip():
                continue
                
            # Extract components
            company, position, dates, description = self._parse_experience_entry(entry)
            
            # Extract skills from description
            technologies = []
            if description:
                doc = self.nlp(description)
                technologies = [ent.text for ent in doc.ents if ent.label_ == "SKILL"]
            
            # Normalize extracted values
            company = self.exp_normalizer.normalize_company(company) if company else None
            position = self.exp_normalizer.normalize_title(position) if position else None
            technologies = self.exp_normalizer.normalize_technologies(technologies)
            description = self.exp_normalizer.normalize_description(description) if description else None
            
            # Parse and normalize dates
            start_date, end_date = None, None
            if dates:
                date_parts = re.split(r'\s*[–\-]\s*', dates, 1)
                start_date = self.date_normalizer.normalize(date_parts[0].strip())
                end_date = self.date_normalizer.normalize(date_parts[1].strip()) if len(date_parts) > 1 else None
            
            # Create experience object only if we have valid data
            if company or position:
                experiences.append(Experience(
                    company=company,
                    position=position,
                    start_date=start_date,
                    end_date=end_date,
                    description=description,
                    technologies=technologies
                ))
        
            return experiences 
          
    def _split_experience_entries(self, text: str) -> List[str]:
        """Splits experience text into individual entries using blank lines as separators"""
        # Split by blank lines (two or more newlines with optional whitespace)
        entries = re.split(r'\n\s*\n', text.strip())
        return [entry.strip() for entry in entries if entry.strip()]
        
    def _parse_experience_entry(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        date_pattern = (
            r'(\d{4}\s*[–\-]\s*\d{4}|'
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{4}\s*[–\-]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{4}|'
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{4}\s*[–\-]\s*(?:Present|Current)|'
            r'\d{4}\s*[–\-]\s*(?:Present|Current))'
        )
        # Split into header and description
        parts = text.split('\n', 1)
        header = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else None
        
        # Extract dates
        date_match = re.search(date_pattern, text)  # Search entire text
        dates = date_match.group(0) if date_match else None
        
        # Remove dates from header
        header_clean = re.sub(date_pattern, '', header).strip() if date_match else header
        
        # Split company and position
        company, position = None, None
        if ',' in header_clean:
            parts = header_clean.rsplit(',', 1)
            company = parts[0].strip()
            position = parts[1].strip()
        elif ' at ' in header_clean.lower():
            parts = header_clean.lower().split(' at ', 1)
            position = parts[0].strip()
            company = parts[1].strip()
        else:
            # Fallback: first part is company, rest is position
            match = re.match(r'^([\w\s&]+)\s+(.+)$', header_clean)
            if match:
                company = match.group(1).strip()
                position = match.group(2).strip()
            else:
                position = header_clean
        
        return company, position, dates, description
    
    def _extract_projects(self, projects_text: str) -> List[Project]:
        """Extracts projects with names and descriptions"""
        if not projects_text.strip():
            return []
            
        projects = []
        entries = self._split_project_entries(projects_text)
        
        for entry in entries:
            if not entry.strip():
                continue
                
            # Extract project components
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
        # Split by project titles (typically bold or underlined)
        entries = re.split(r'\n(?=\s*[•\-*]?\s*[A-Z][^\n:]+[:\n])', text)
        return [entry.strip() for entry in entries if entry.strip()]
    
    def _parse_project_entry(self, text: str) -> Tuple[Optional[str], Optional[str], List[str]]:
        """Parses an individual project entry"""
        # Split into name and description
        parts = text.split('\n', 1)
        name = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else None
        
        # Clean project name (remove bullets or numbering)
        name = re.sub(r'^[\s•\-*]+', '', name)
        name = re.sub(r':$', '', name)
        
        # Extract technologies from description
        technologies = []
        if description:
            doc = self.nlp(description)
            technologies = [ent.text for ent in doc.ents if ent.label_ == "SKILL"]
        
        return name, description, technologies
    
    def _extract_certifications(self, education_text: str) -> List[str]:
        patterns = [
            r'AWS\s+Certified\s+[^\n,]+',
            r'Google\s+[^\n,]+(?:Certification|Professional)',
            r'Microsoft\s+Certified\s*:\s*[^\n,]+',
            r'Certified\s+[^\n,]+Specialist',
            r'\b(CISSP|PMP|CFA|CPA|CISM|CRISC)\b'
        ]
        
        certifications = []
        for pattern in patterns:
            matches = re.findall(pattern, education_text, re.IGNORECASE)
            certifications.extend(matches)
        
        return list(set(certifications))