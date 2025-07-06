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
        self.skill_normalizer = SkillNormalizer(config.get('skill_ontology_path', 'data/ontology/skills_ontology.json'))
        self.date_normalizer = DateNormalizer()
        self.edu_normalizer = EducationNormalizer(config.get('education_data_dir', 'data/education'))
        self.exp_normalizer = ExperienceNormalizer(config.get('experience_data_dir', 'data/experience'))
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
            # Programming Languages
            {"label": "SKILL", "pattern": [{"LOWER": "java"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "python"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "javascript"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "typescript"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "dart"}]},
            
            # Frameworks & Libraries
            {"label": "SKILL", "pattern": [{"LOWER": "spring"}, {"LOWER": "boot"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "angular"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "flutter"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "apache"}, {"LOWER": "kafka"}]},
            
            # Tools & CI/CD
            {"label": "SKILL", "pattern": [{"LOWER": "git"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "linux"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "docker"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "maven"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "gitlab"}, {"LOWER": "ci"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "github"}, {"LOWER": "actions"}]},
            
            # Testing
            {"label": "SKILL", "pattern": [{"LOWER": "junit"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "unittest"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "test"}, {"LOWER": "driven"}, {"LOWER": "development"}]},
            
            # Architecture & Design
            {"label": "SKILL", "pattern": [{"LOWER": "mvc"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "concurrent"}, {"LOWER": "systems"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "microservices"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "api"}, {"LOWER": "development"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "mobile"}, {"LOWER": "development"}]},
            
            # Agile & Process
            {"label": "SKILL", "pattern": [{"LOWER": "scrum"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "kanban"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "sprint"}, {"LOWER": "planning"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "retrospectives"}]},
            
            # Java-specific
            {"label": "SKILL", "pattern": [{"LOWER": "multithreading"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "concurrency"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "stream"}, {"LOWER": "api"}]},
            
            # Databases
            {"label": "SKILL", "pattern": [{"LOWER": "sql"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "sqlite"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "postgresql"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "firebase"}]},
            
            # Cloud & Infrastructure
            {"label": "SKILL", "pattern": [{"LOWER": "ci"}, {"LOWER": "cd"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "rest"}, {"LOWER": "api"}]},
            {"label": "SKILL", "pattern": [{"LOWER": "jwt"}]},
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
    
    def _extract_skills(self, text_or_doc) -> List[str]:
        """Extracts skills from text using pattern matching and NLP"""
        # Convert input to text if it's a Doc
        if isinstance(text_or_doc, Doc):
            text = text_or_doc.text
        else:
            text = str(text_or_doc)

        if not text.strip():
            return []
            
        skills = set()  # Use set to avoid duplicates
        lines = text.split('\n')
        current_category = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check if line is a category header
            if line.endswith(':'):
                current_category = line.rstrip(':')
                continue
                
            # Split line by common delimiters and clean up
            items = [item.strip() for item in re.split(r'[,&/|]', line)]
            for item in items:
                # Skip if too short or just punctuation/spaces
                if not item or len(item) <= 1 or not re.search(r'[a-zA-Z0-9]', item):
                    continue
                
                # Clean up the skill
                skill = re.sub(r'\s+', ' ', item).strip()
                # Remove common prefixes/suffixes
                skill = re.sub(r'^[-•*]\s*', '', skill)
                skill = re.sub(r'\s*[-•*]$', '', skill)
                
                if current_category:
                    skill = f"{current_category}: {skill}"
                skills.add(skill)
        
        # Also extract skills using NLP patterns
        if isinstance(text_or_doc, Doc):
            doc = text_or_doc
        else:
            doc = self.nlp(text)
        
        for ent in doc.ents:
            if ent.label_ == "SKILL" and len(ent.text) > 1:
                skills.add(ent.text)
            
        # Normalize and filter skills
        normalized_skills = []
        for skill in skills:
            # Skip if too short or just numbers
            if len(skill) <= 1 or skill.isdigit():
                continue
            # Normalize through skill normalizer
            norm_skill = self.skill_normalizer.normalize(skill)
            if norm_skill:
                normalized_skills.append(norm_skill)
            
        return sorted(list(set(normalized_skills)))
    
    def _is_skill(self, chunk: Span) -> bool:
        """Determines if a text span represents a skill"""
        # Skip very short or very long chunks
        if len(chunk.text) < 2 or len(chunk.text) > 30:
            return False
            
        # Skip if contains unwanted characters
        if re.search(r'[^\w\s\-/+#]', chunk.text):
            return False
            
        # Skip common non-skill phrases
        non_skills = {'year', 'month', 'day', 'present', 'current', 'company', 'team', 'project'}
        if chunk.text.lower() in non_skills:
            return False
            
        # Must contain at least one word character
        if not re.search(r'\w', chunk.text):
            return False
            
        return True
    
    def _extract_education(self, education_text: str) -> List[Education]:
        """Extracts education information from text"""
        if not education_text.strip():
            return []
            
        entries = []
        current_entry = {}
        lines = education_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_entry:
                    # Try to create Education object
                    try:
                        entries.append(Education(
                            institution=self.edu_normalizer.normalize_institution(current_entry.get('institution', '')),
                            degree=self.edu_normalizer.normalize_degree(current_entry.get('degree', '')),
                            field_of_study=self.edu_normalizer.normalize_field(current_entry.get('field', '')),
                            start_date=self.date_normalizer.normalize(current_entry.get('start_date', '')),
                            end_date=self.date_normalizer.normalize(current_entry.get('end_date', '')),
                            description=current_entry.get('description', ''),
                            achievements=current_entry.get('achievements', [])
                        ))
                    except Exception as e:
                        logging.error(f"Failed to create Education entry: {e}")
                current_entry = {}
                continue
            
            # Extract dates
            date_match = re.search(r'(\w+\s+\d{4})\s*-\s*(\w+\s+\d{4}|\bpresent\b)', line, re.IGNORECASE)
            if date_match:
                current_entry['start_date'] = date_match.group(1)
                current_entry['end_date'] = date_match.group(2)
                continue
            
            # Extract degree and field
            degree_match = re.search(r'(Bachelor|Master|PhD|B\.?S\.?|M\.?S\.?|M\.?B\.?A\.?|Ph\.?D\.?)[^\n]*', line, re.IGNORECASE)
            if degree_match:
                degree_text = degree_match.group(0)
                current_entry['degree'] = degree_text
                # Try to extract field of study
                field_match = re.search(r'(?:in|of)\s+([^,\n]+)', degree_text, re.IGNORECASE)
                if field_match:
                    current_entry['field'] = field_match.group(1)
                continue
            
            # Extract institution
            if not current_entry.get('institution'):
                current_entry['institution'] = line
            else:
                # Append to description or achievements
                if line.startswith(('-', '•')):
                    if 'achievements' not in current_entry:
                        current_entry['achievements'] = []
                    current_entry['achievements'].append(line.lstrip('- •'))
                else:
                    if 'description' not in current_entry:
                        current_entry['description'] = line
                    else:
                        current_entry['description'] += ' ' + line
        
        # Handle last entry
        if current_entry:
            try:
                entries.append(Education(
                    institution=self.edu_normalizer.normalize_institution(current_entry.get('institution', '')),
                    degree=self.edu_normalizer.normalize_degree(current_entry.get('degree', '')),
                    field_of_study=self.edu_normalizer.normalize_field(current_entry.get('field', '')),
                    start_date=self.date_normalizer.normalize(current_entry.get('start_date', '')),
                    end_date=self.date_normalizer.normalize(current_entry.get('end_date', '')),
                    description=current_entry.get('description', ''),
                    achievements=current_entry.get('achievements', [])
                ))
            except Exception as e:
                logging.error(f"Failed to create last Education entry: {e}")
        
        return entries
    
    def _extract_experience(self, experience_text: str) -> List[Experience]:
        """Extracts work experience information from text"""
        if not experience_text.strip():
            return []
            
        entries = []
        current_entry = {}
        lines = experience_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_entry:
                    # Try to create Experience object
                    try:
                        entries.append(Experience(
                            company=current_entry.get('company', 'Unknown'),
                            position=current_entry.get('position', 'Unknown'),
                            start_date=self.date_normalizer.normalize(current_entry.get('start_date', '')),
                            end_date=self.date_normalizer.normalize(current_entry.get('end_date', '')),
                            description=current_entry.get('description', ''),
                            technologies=current_entry.get('technologies', [])
                        ))
                    except Exception as e:
                        logging.error(f"Failed to create Experience entry: {e}")
                current_entry = {}
                continue
            
            # Extract dates
            date_match = re.search(r'(\w+\s+\d{4})\s*-\s*(\w+\s+\d{4}|\bpresent\b)', line, re.IGNORECASE)
            if date_match:
                current_entry['start_date'] = date_match.group(1)
                current_entry['end_date'] = date_match.group(2)
                continue
            
            # Extract position and company
            if not current_entry.get('position'):
                # First non-empty line is usually the position
                current_entry['position'] = line
            elif not current_entry.get('company'):
                # Second non-empty line is usually the company
                current_entry['company'] = line
            else:
                # Extract technologies from description
                tech_matches = re.findall(r'\b[A-Z][A-Za-z0-9.#+]+(?:\s+[A-Z][A-Za-z0-9.#+]+)*\b', line)
                if tech_matches:
                    if 'technologies' not in current_entry:
                        current_entry['technologies'] = []
                    current_entry['technologies'].extend(tech_matches)
                
                # Add to description
                if 'description' not in current_entry:
                    current_entry['description'] = line
                else:
                    current_entry['description'] += ' ' + line
        
        # Handle last entry
        if current_entry:
            try:
                entries.append(Experience(
                    company=current_entry.get('company', 'Unknown'),
                    position=current_entry.get('position', 'Unknown'),
                    start_date=self.date_normalizer.normalize(current_entry.get('start_date', '')),
                    end_date=self.date_normalizer.normalize(current_entry.get('end_date', '')),
                    description=current_entry.get('description', ''),
                    technologies=current_entry.get('technologies', [])
                ))
            except Exception as e:
                logging.error(f"Failed to create last Experience entry: {e}")
        
        return entries
    
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