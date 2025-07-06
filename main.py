import argparse
import json
import logging
import os
from pathlib import Path
import yaml
from typing import Dict, Any, List, Optional
import sys
import re
import traceback
from datetime import datetime

from parsing_engine.pdf_parser import PDFParser
from normalization.skill_normalizer import SkillNormalizer
from normalization.education_normalizer import EducationNormalizer
from normalization.experience_normalizer import ExperienceNormalizer
from normalization.date_normalizer import DateNormalizer
from schemas.resume_schema import Resume, Education, Experience, Project
from utils.error_handling import ParserError, ConfigError
from utils.file_utils import validate_file_path
from parsing_engine.section_detector import SectionDetector
from models.resume import Resume as ResumeModel, Contact

# Setup logging
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Define base directory and default config
BASE_DIR = Path(__file__).parent.resolve()

DEFAULT_CONFIG = {
    "pdf_parser": {
        "use_ocr": False,
        "layout_analysis": True,
        "section_rules": str(BASE_DIR / "config" / "parsing_rules.yaml"),
        "min_confidence": 0.7
    },
    "normalization": {
        "skill_ontology_path": str(BASE_DIR / "data" / "ontology" / "skills.json"),
        "education_data_dir": str(BASE_DIR / "data" / "education"),
        "experience_data_dir": str(BASE_DIR / "data" / "experience")
    }
}

class CVPipeline:
    """Main pipeline for CV parsing and processing"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._initialize_components()

    def _initialize_components(self):
        """Initialize all pipeline components"""
        try:
            # Load section rules
            pdf_config = self.config["pdf_parser"]
            rules_path = Path(pdf_config["section_rules"])
            if not rules_path.is_absolute():
                rules_path = BASE_DIR / rules_path
            
            with open(rules_path, 'r') as f:
                section_rules = yaml.safe_load(f)
                self.logger.debug(f"Loaded section rules from {rules_path}")

            # Initialize parsers and normalizers
            self.pdf_parser = PDFParser({
                **pdf_config,
                "section_rules": section_rules
            })
            
            norm_config = self.config["normalization"]
            self.skill_normalizer = SkillNormalizer(
                ontology_path=str(BASE_DIR / "data" / "ontology" / "skills_ontology.json"),
                patterns_path=str(BASE_DIR / "config" / "patterns.yaml")
            )
            self.education_normalizer = EducationNormalizer(
                norm_config["education_data_dir"]
            )
            self.experience_normalizer = ExperienceNormalizer(
                norm_config["experience_data_dir"]
            )
            self.date_normalizer = DateNormalizer()
            self.section_detector = SectionDetector(rules=section_rules)

        except Exception as e:
            self.logger.error(f"Failed to initialize components: {str(e)}")
            raise ConfigError(f"Component initialization failed: {str(e)}") from e

    def process_cv(self, file_path: str) -> ResumeModel:
        """Process a CV file through the pipeline"""
        self.logger.info(f"Processing CV: {file_path}")
        validate_file_path(file_path)
        
        try:
            # Execute pipeline
            parsed_data = self.parse_cv(file_path)
            self.logger.debug(f"Parsed data: {json.dumps(parsed_data, indent=2)}")
            
            normalized_data = self.normalize_data(parsed_data)
            self.logger.debug(f"Normalized data: {json.dumps(normalized_data, indent=2)}")
            
            resume = self.build_resume(normalized_data)
            self.logger.debug(f"Built resume object: {json.dumps(resume.dict(), indent=2)}")
            
            return resume
            
        except Exception as e:
            self.logger.error(f"CV processing failed: {str(e)}")
            raise

    def parse_cv(self, file_path: str) -> Dict[str, Any]:
        """Parse PDF CV file"""
        try:
            result = self.pdf_parser.parse(file_path)
            self.logger.debug(f"Raw text from PDF:\n{result.get('raw_text', '')}")
            sections = result.get('sections', {})
            
            # Extract raw sections
            parsed = {
                "contact": sections.get('contact', {}).get('content', ''),
                "summary": sections.get('summary', {}).get('content', ''),
                "skills": sections.get('skills', {}).get('content', ''),
                "education": sections.get('education', {}).get('content', ''),
                "experience": sections.get('experience', {}).get('content', ''),
                "projects": sections.get('projects', {}).get('content', ''),
                "certifications": sections.get('certifications', {}).get('content', '')
            }
            
            # Debug log each section with clear separators
            self.logger.info("\n\n=== PARSED SECTIONS START ===")
            for section, content in parsed.items():
                self.logger.info(f"\n=== {section.upper()} SECTION ===\n{content}\n{'='*50}")
            self.logger.info("=== PARSED SECTIONS END ===\n\n")
            
            return parsed
            
        except Exception as e:
            raise ParserError(f"Failed to parse PDF: {str(e)}") from e

    def normalize_data(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply normalization to parsed data"""
        try:
            normalized = {
                "contact": self._parse_contact(parsed_data.get("contact", "")),
                "summary": parsed_data.get("summary", ""),
                "skills": self.skill_normalizer.normalize_list(
                    self._parse_skills(parsed_data.get("skills", ""))
                ),
                "education": self.education_normalizer.normalize(
                    self._parse_section_to_entries(parsed_data.get("education", ""))
                ),
                "experience": self.experience_normalizer.normalize(
                    self._parse_section_to_entries(parsed_data.get("experience", ""))
                ),
                "projects": self._parse_projects(parsed_data.get("projects", "")),
                "certifications": self._parse_certifications(
                    parsed_data.get("certifications", "")
                )
            }
            return normalized
        except Exception as e:
            raise ParserError(f"Normalization failed: {str(e)}") from e

    def _parse_contact(self, text: str) -> Dict[str, str]:
        """Parse contact section"""
        contact = {
            "name": "",
            "phone": "",
            "email": "",
            "linkedin": "",
            "github": ""
        }
        
        if not text:
            return contact
            
        lines = text.split('\n')
        name_found = False
        
        # First pass: Look for name in first few lines
        for i, line in enumerate(lines[:3]):  # Only check first 3 lines for name
            line = line.strip()
            if not line:
                continue
            
            # Name detection with multiple patterns
            if not name_found:
                # All caps name at start of resume
                if i == 0 and line.isupper() and len(line.split()) >= 2:
                    contact["name"] = line.title()  # Convert to title case
                    name_found = True
                    continue
                    
                # Title case name
                elif all(word[0].isupper() for word in line.split() if word) and len(line.split()) >= 2:
                    # Avoid mistaking section headers for names
                    if not any(header in line.lower() for header in [
                        "summary", "experience", "education", "skills", 
                        "projects", "certifications", "achievements"
                    ]):
                        contact["name"] = line
                        name_found = True
                        continue
                        
                # Name with professional title
                elif ":" in line and len(line.split(":")[0].split()) >= 2:
                    potential_name = line.split(":")[0].strip()
                    if all(word[0].isupper() for word in potential_name.split()):
                        contact["name"] = potential_name
                        name_found = True
                        continue
        
        # Second pass: Look for contact details
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Phone patterns
            phone_patterns = [
                r'\+?\d{1,3}[-.]?\d{3}[-.]?\d{3}[-.]?\d{4}',  # International
                r'\d{3}[-.]?\d{3}[-.]?\d{4}',                 # Standard US
                r'\(\d{3}\)\s*\d{3}[-.]?\d{4}'                # (123) 456-7890
            ]
            
            for pattern in phone_patterns:
                if not contact["phone"]:  # Only match first phone number
                    if match := re.search(pattern, line):
                        # Standardize phone format
                        phone = match.group()
                        # Remove all non-digit characters except leading +
                        cleaned = '+' + ''.join(c for c in phone[1:] if c.isdigit()) if phone.startswith('+') else ''.join(c for c in phone if c.isdigit())
                        # Format as XXX-XXX-XXXX for 10-digit numbers
                        if len(cleaned) == 10:
                            contact["phone"] = f"{cleaned[:3]}-{cleaned[3:6]}-{cleaned[6:]}"
                        else:
                            contact["phone"] = cleaned
                        break
            
            # Email pattern
            if not contact["email"]:
                email_match = re.search(r'\b[\w\.-]+@[\w\.-]+\.\w{2,}\b', line)
                if email_match:
                    contact["email"] = email_match.group().lower()  # Normalize to lowercase
            
            # LinkedIn pattern with variations
            if not contact["linkedin"]:
                linkedin_patterns = [
                    r'linkedin\.com/in/[\w-]+/?',
                    r'linked\.in/[\w-]+/?',
                    r'linkedin\.com/[\w/-]+/?'
                ]
                for pattern in linkedin_patterns:
                    if match := re.search(pattern, line.lower()):
                        # Clean and standardize LinkedIn URL
                        linkedin = match.group().rstrip('/')
                        if not linkedin.startswith('http'):
                            linkedin = f"linkedin.com/in/{linkedin.split('/')[-1]}"
                        contact["linkedin"] = linkedin
                        break
            
            # GitHub pattern with variations
            if not contact["github"]:
                github_patterns = [
                    r'github\.com/[\w-]+/?',
                    r'github\.com/[\w-]+/[\w-]+/?'
                ]
                for pattern in github_patterns:
                    if match := re.search(pattern, line.lower()):
                        # Clean and standardize GitHub URL
                        github = match.group().rstrip('/')
                        if not github.startswith('http'):
                            github = f"github.com/{github.split('/')[-1]}"
                        contact["github"] = github
                        break
        
        return contact

    def _parse_skills(self, text: str) -> List[str]:
        """Parse skills section into list of skills"""
        if not text:
            return []
            
        skills = []
        
        # Split into lines and process each line
        lines = text.split('\n')
        current_category = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Skip the "Technical Skills" header
            if line.lower() == "technical skills":
                continue
                
            # Add the line as is - let the normalizer handle the parsing
            skills.append(line)
        
        return skills

    def _parse_section_to_entries(self, text: str) -> List[Dict[str, Any]]:
        """Parse section into structured entries"""
        entries = []
        current_entry = None
        current_lines = []
        
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
                
            # Check for date patterns
            date_pattern = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s*[-–]\s*(?:Present|January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}|(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s*[-–]\s*Present'
            
            # Check for new entry by looking for degree patterns
            if any(pattern in line for pattern in [
                "Bachelor of", "Master of", "National Certificate", "Senior Certificate"
            ]):
                # Save previous entry if exists
                if current_entry and current_lines:
                    current_entry["description"] = "\n".join(current_lines)
                    entries.append(current_entry)
                
                # Start new entry
                current_entry = {
                    "institution": "",
                    "degree": line,
                    "field_of_study": "",
                    "start_date": "",
                    "end_date": "",
                    "description": "",
                    "achievements": []
                }
                current_lines = []
                
                # Look ahead for institution and dates
                next_idx = i + 1
                while next_idx < len(lines) and next_idx <= i + 3:  # Look at next 3 lines max
                    next_line = lines[next_idx].strip()
                    if not next_line:
                        next_idx += 1
                        continue
                        
                    # Check if line is a date
                    date_match = re.search(date_pattern, next_line)
                    if date_match:
                        dates = date_match.group()
                        if "–" in dates or "-" in dates:
                            start, end = re.split(r'[-–]', dates)
                            current_entry["start_date"] = start.strip()
                            current_entry["end_date"] = end.strip()
                        else:
                            current_entry["start_date"] = dates.strip()
                        next_idx += 1
                        continue
                        
                    # If not date, must be institution
                    if not current_entry["institution"]:
                        current_entry["institution"] = next_line
                    
                    next_idx += 1
                
                i = next_idx - 1  # Resume from last processed line
                
            elif current_entry:
                # Process bullet points for achievements
                if line.startswith('•') or line.startswith('-'):
                    line = line.lstrip('•- ').strip()
                    current_entry["achievements"].append(line)
                else:
                    # Non-bullet point line in description
                    current_lines.append(line)
            
            i += 1
        
        # Add final entry
        if current_entry and current_lines:
            current_entry["description"] = "\n".join(current_lines)
            entries.append(current_entry)
        
        return entries

    def _parse_projects(self, text: str) -> List[Dict[str, Any]]:
        """Parse projects section with proper field extraction"""
        if not text:
            return []
            
        projects = []
        current_project = None
        description_lines = []
        
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Project title patterns
            project_patterns = [
                r'^([\w\s-]+)\s+-\s+([\w\s]+)\s+(?:app|game|system|platform)$',  # "ProjectName - A running fitness App"
                r'^project\s+\d+:\s*(.*)',  # "Project 1: Name"
                r'^\d+\.\s*([\w\s-]+)',  # "1. Project Name"
                r'^([\w\s-]+)\s*\((\d{4})\)'  # "Project Name (2023)"
            ]
            
            is_new_project = False
            project_title = None
            project_date = None
            
            for pattern in project_patterns:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    is_new_project = True
                    if len(match.groups()) == 2 and 'app' in line.lower() or 'game' in line.lower():
                        project_title = match.group(1)
                        # Extract date from line or use default
                        date_match = re.search(r'\d{4}', line)
                        project_date = date_match.group() if date_match else "Present"
                    elif len(match.groups()) == 2 and re.match(r'\d{4}', match.group(2)):
                        project_title = match.group(1)
                        project_date = match.group(2)
                    else:
                        project_title = match.group(1)
                        # Extract date from line or use default
                        date_match = re.search(r'\d{4}', line)
                        project_date = date_match.group() if date_match else "Present"
                    break
            
            if is_new_project:
                # Save previous project if exists
                if current_project and description_lines:
                    current_project["description"] = "\n".join(description_lines)
                    projects.append(current_project)
                
                # Initialize new project with required fields
                current_project = {
                    "position": "Project Lead",  # Default role for personal projects
                    "company": "Personal Project",  # Default for personal projects
                    "location": "Remote",  # Default location
                    "start_date": project_date or "Present",
                    "end_date": "Present",
                    "description": "",
                    "technologies": []
                }
                description_lines = []
                
                # Look for technologies in the project title
                tech_matches = re.findall(r'using\s+([\w\s,]+)', line, re.IGNORECASE)
                if tech_matches:
                    current_project["technologies"].extend(
                        [t.strip() for t in tech_matches[0].split(',')]
                    )
                
            elif current_project:
                # Check for technology stack
                if any(tech_indicator in line.lower() for tech_indicator in [
                    "technologies:", "tech stack:", "built with:", "using:", "tools:"
                ]):
                    techs = re.split(r'[,|]', line.split(':', 1)[1])
                    current_project["technologies"].extend(
                        [t.strip() for t in techs if t.strip()]
                    )
                else:
                    description_lines.append(line)
                    
                    # Extract any technologies mentioned in description
                    tech_matches = re.findall(r'using\s+([\w\s,]+)', line, re.IGNORECASE)
                    if tech_matches:
                        current_project["technologies"].extend(
                            [t.strip() for t in tech_matches[0].split(',')]
                        )
        
        # Add last project
        if current_project and description_lines:
            current_project["description"] = "\n".join(description_lines)
            projects.append(current_project)
        
        return projects

    def _parse_certifications(self, text: str) -> List[str]:
        """Parse certifications section into list of certifications"""
        if not text:
            return []
            
        certifications = []
        current_cert = []
        
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                if current_cert:
                    certifications.append(" ".join(current_cert))
                    current_cert = []
                continue
                
            if any(keyword in line.lower() for keyword in [
                "certification", "certificate", "certified", 
                "license", "credential"
            ]):
                if current_cert:
                    certifications.append(" ".join(current_cert))
                current_cert = [line]
            elif current_cert:
                current_cert.append(line)
        
        # Add final certification
        if current_cert:
            certifications.append(" ".join(current_cert))
        
        return certifications

    def build_resume(self, normalized_data: Dict[str, Any]) -> ResumeModel:
        """Create Resume object from normalized data"""
        try:
            resume = ResumeModel(
                contact=normalized_data.get("contact", {}),
                summary=normalized_data.get("summary", ""),
                skills=normalized_data.get("skills", []),
                education=normalized_data.get("education", []),
                experience=normalized_data.get("experience", []),
                projects=normalized_data.get("projects", []),
                certifications=normalized_data.get("certifications", [])
            )
            return resume
            
        except Exception as e:
            raise ParserError(f"Resume building failed: {str(e)}") from e

    def _parse_experience(self, text: str) -> List[Dict[str, Any]]:
        """Parse experience section into structured entries"""
        entries = []
        current_entry = None
        current_lines = []
        
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
                
            # Check for date patterns
            date_pattern = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s*[-–]\s*(?:Present|January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}|(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s*[-–]\s*Present'
            
            # Check for new entry by looking for job titles
            if any(pattern in line for pattern in [
                "Developer", "Engineer", "Mentor", "Consultant", "Analyst", "Manager", "Architect", "Lead"
            ]):
                # Save previous entry if exists
                if current_entry and current_lines:
                    current_entry["description"] = "\n".join(current_lines)
                    entries.append(current_entry)
                
                # Start new entry
                current_entry = {
                    "position": line,
                    "company": "",
                    "location": "",
                    "start_date": "",
                    "end_date": "",
                    "description": "",
                    "technologies": []
                }
                current_lines = []
                
                # Look ahead for company, location, and dates
                next_idx = i + 1
                while next_idx < len(lines) and next_idx <= i + 3:  # Look at next 3 lines max
                    next_line = lines[next_idx].strip()
                    if not next_line:
                        next_idx += 1
                        continue
                        
                    # Check if line is a date
                    date_match = re.search(date_pattern, next_line)
                    if date_match:
                        dates = date_match.group()
                        if "–" in dates or "-" in dates:
                            start, end = re.split(r'[-–]', dates)
                            current_entry["start_date"] = start.strip()
                            current_entry["end_date"] = end.strip()
                        else:
                            current_entry["start_date"] = dates.strip()
                        next_idx += 1
                        continue
                        
                    # Check if line is a location
                    if any(state in next_line for state in ["Gauteng", "Western Cape", "Remote"]):
                        current_entry["location"] = next_line
                        next_idx += 1
                        continue
                        
                    # If not date or location, must be company
                    if not current_entry["company"] and not any(pattern in next_line for pattern in [
                        "Developer", "Engineer", "Mentor", "Consultant", "Analyst", "Manager", "Architect", "Lead"
                    ]):
                        current_entry["company"] = next_line
                    
                    next_idx += 1
                
                i = next_idx - 1  # Resume from last processed line
                
            elif current_entry:
                # Process bullet points for description
                if line.startswith('•') or line.startswith('-'):
                    line = line.lstrip('•- ').strip()
                    # Extract technologies
                    tech_keywords = ["using", "with", "in", "through"]
                    for keyword in tech_keywords:
                        if f" {keyword} " in line:
                            tech_part = line.split(f" {keyword} ")[1].split(".")[0]
                            techs = [t.strip() for t in re.split(r'[,&]', tech_part)]
                            current_entry["technologies"].extend(techs)
                    
                    # Add to description lines
                    current_lines.append(line)
                else:
                    # Non-bullet point line in description
                    current_lines.append(line)
            
            i += 1
        
        # Add final entry
        if current_entry and current_lines:
            current_entry["description"] = "\n".join(current_lines)
            entries.append(current_entry)
        
        return entries

    def parse(self, pdf_path: str) -> Resume:
        """Parse PDF resume into structured data"""
        # Extract text and metadata from PDF
        document = self.pdf_parser.parse(pdf_path)
        
        # Detect sections in the document
        sections = self.section_detector.detect_sections(document)
        
        # Parse each section
        contact_info = Contact(**self._parse_contact(sections.get("contact", {}).get("content", "")))
        summary = sections.get("summary", {}).get("content", "")
        skills = self._parse_skills(sections.get("skills", {}).get("content", ""))
        education = [Education(**entry) for entry in self._parse_section_to_entries(sections.get("education", {}).get("content", ""))]
        
        # Parse experience section using detected section
        experience = [Experience(**entry) for entry in self._parse_experience(sections.get("experience", {}).get("content", ""))]
        
        # Parse projects section
        projects = [Project(**entry) for entry in self._parse_projects(sections.get("projects", {}).get("content", ""))]
        certifications = [str(entry["description"]) for entry in self._parse_section_to_entries(sections.get("certifications", {}).get("content", ""))]
        
        # Normalize skills
        normalized_skills = self.skill_normalizer.normalize_list(skills)
        
        # Build resume object
        resume = Resume(
            contact=contact_info.dict(),
            summary=summary,
            skills=normalized_skills,
            education=education,
            experience=experience,
            projects=projects,
            certifications=certifications
        )
        
        self.logger.debug(f"Built resume object: {json.dumps(resume.dict(), indent=2)}")
        
        return resume

def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Parse a resume PDF into structured JSON')
    parser.add_argument('input', help='Input PDF file')
    parser.add_argument('-o', '--output', default='output.json', help='Output JSON file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-c', '--config', default='config', help='Config directory')
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,  # Always use DEBUG level
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    try:
        # Load configuration
        config = DEFAULT_CONFIG.copy()
        config_dir = Path(args.config)
        if not config_dir.is_absolute():
            config_dir = BASE_DIR / config_dir
            
        # Load and merge config files
        for config_file in config_dir.glob("*.yaml"):
            logging.debug(f"Loading config from {config_file}")
            with open(config_file, 'r') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    if config_file.name == "parsing_rules.yaml":
                        # Store the path to the rules file instead of the rules themselves
                        config["pdf_parser"]["section_rules"] = str(config_file)
                    else:
                        config.update(file_config)
        
        # Initialize pipeline
        pipeline = CVPipeline(config)
        
        # Process the CV
        logging.info(f"Processing CV: {args.input}")
        resume = pipeline.process_cv(args.input)
        
        # Save results
        with open(args.output, 'w') as f:
            json.dump(resume.dict(), f, indent=2)
        logging.info(f"Results saved to {args.output}")
        
    except Exception as e:
        logging.error(f"Processing failed: {str(e)}")
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()