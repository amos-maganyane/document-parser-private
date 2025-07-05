import argparse
import json
import logging
import os
from pathlib import Path
import yaml
from typing import Dict, Any, List
import sys
import re

from parsing_engine.pdf_parser import PDFParser
from normalization.skill_normalizer import SkillNormalizer
from normalization.education_normalizer import EducationNormalizer
from normalization.experience_normalizer import ExperienceNormalizer
from normalization.date_normalizer import DateNormalizer
from schemas.resume_schema import Resume
from utils.error_handling import ParserError, ConfigError
from utils.file_utils import validate_file_path

# Setup logging
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO
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
                norm_config["skill_ontology_path"]
            )
            self.education_normalizer = EducationNormalizer(
                norm_config["education_data_dir"]
            )
            self.experience_normalizer = ExperienceNormalizer(
                norm_config["experience_data_dir"]
            )
            self.date_normalizer = DateNormalizer()

        except Exception as e:
            self.logger.error(f"Failed to initialize components: {str(e)}")
            raise ConfigError(f"Component initialization failed: {str(e)}") from e

    def process_cv(self, file_path: str) -> Resume:
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
            
            return parsed
            
        except Exception as e:
            raise ParserError(f"Failed to parse PDF: {str(e)}") from e

    def normalize_data(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply normalization to parsed data"""
        try:
            normalized = {
                "contact": self._parse_contact(parsed_data.get("contact", "")),  # Add this method
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
        for line in lines:
            line = line.strip()
            # Name (all caps)
            if not contact["name"] and line.isupper() and len(line.split()) >= 2:
                contact["name"] = line
                continue
                
            # Phone
            if not contact["phone"] and re.search(r'\d{3}[-.]?\d{3}[-.]?\d{4}', line):
                contact["phone"] = re.search(r'\d{3}[-.]?\d{3}[-.]?\d{4}', line).group()
                
            # Email
            if not contact["email"] and re.search(r'\b[\w\.-]+@[\w\.-]+\.\w{2,4}\b', line):
                contact["email"] = re.search(r'\b[\w\.-]+@[\w\.-]+\.\w{2,4}\b', line).group()
                
            # LinkedIn
            if not contact["linkedin"] and 'linkedin.com' in line.lower():
                contact["linkedin"] = re.search(r'linkedin\.com/\S+', line).group()
                
            # GitHub
            if not contact["github"] and 'github.com' in line.lower():
                contact["github"] = re.search(r'github\.com/\S+', line).group()
                
        return contact

    def _parse_skills(self, text: str) -> List[str]:
        """Parse skills section into individual skills"""
        if not text:
            return []
        
        skills = []
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Remove category labels
            line = re.sub(r'^.*?:', '', line).strip()
            
            # Split by common separators
            parts = re.split(r'[,•\n|&]|\band\b', line)
            
            # Clean and add individual skills
            for part in parts:
                skill = part.strip()
                if skill and not any(c in skill for c in ':/()'):
                    skills.append(skill)
        
        return list(set(skills))  # Remove duplicates

    def _parse_section_to_entries(self, text: str) -> List[Dict]:
        """Split section text into structured entries"""
        if not text:
            return []
            
        entries = []
        current_entry = {}
        current_lines = []
        
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                if current_lines and current_entry:
                    current_entry["content"] = "\n".join(current_lines)
                    entries.append(current_entry)
                    current_entry = {}
                    current_lines = []
                continue
                
            # Check for new entry indicators
            if any(indicator in line.lower() for indicator in [
                "university", "college", "institute",  # Education
                "developer", "engineer", "manager"     # Experience
            ]):
                if current_lines and current_entry:
                    current_entry["content"] = "\n".join(current_lines)
                    entries.append(current_entry)
                    current_lines = []
                current_entry = {"content": line}
                continue
                
            if current_entry:
                current_lines.append(line)
        
        # Add final entry
        if current_lines and current_entry:
            current_entry["content"] = "\n".join(current_lines)
            entries.append(current_entry)
        
        return entries

    def _parse_projects(self, text: str) -> List[Dict]:
        """Parse projects section into structured entries"""
        projects = []
        current_project = None
        description_lines = []
        
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                if current_project and description_lines:
                    current_project["description"] = "\n".join(description_lines)
                    projects.append(current_project)
                    current_project = None
                    description_lines = []
                continue
                
            # Check for project name indicators
            if not current_project and (line.endswith(':') or line.endswith('-')):
                current_project = {
                    "name": line.rstrip(':-'),
                    "description": "",
                    "technologies": []
                }
            elif current_project:
                description_lines.append(line)
                # Extract technologies from description
                if "technologies used:" in line.lower():
                    tech_text = line.split(":", 1)[1]
                    current_project["technologies"].extend(
                        [t.strip() for t in tech_text.split(",") if t.strip()]
                    )
        
        # Add final project
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

    def build_resume(self, normalized_data: Dict[str, Any]) -> Resume:
        """Create Resume object from normalized data"""
        try:
            resume = Resume(
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

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='CV Parser')
    parser.add_argument('input', help='Input PDF file')
    parser.add_argument('-o', '--output', help='Output JSON file', default='output.json')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('-c', '--config', help='Path to config file')
    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Load configuration
        config = DEFAULT_CONFIG
        if args.config:
            with open(args.config, 'r') as f:
                config.update(yaml.safe_load(f))

        # Initialize and run pipeline
        pipeline = CVPipeline(config)
        resume = pipeline.process_cv(args.input)

        # Save output
        with open(args.output, 'w') as f:
            json.dump(resume.dict(), f, indent=2)
        logger.info(f"Results saved to {args.output}")

    except Exception as e:
        logger.error(f"CV processing failed: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()