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
from schemas.resume_schema import Resume, Education, Experience, Project
from parsing_engine.entity_extractor import EntityExtractor
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
        "use_marker": False,
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
            self.entity_extractor = EntityExtractor(config={
                "pii_config": self.config.get("pii_config", {}),
                "skill_ontology_path": str(BASE_DIR / "data" / "ontology" / "skills_ontology.json"),
                "education_data_dir": norm_config["education_data_dir"],
                "experience_data_dir": norm_config["experience_data_dir"]
            })
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
            resume = self.parse(file_path)
            resume_dict = resume.model_dump()
            self.logger.debug(f"Built resume object: {json.dumps(resume_dict, indent=2, default=str)}")
            
            return resume
            
        except Exception as e:
            self.logger.error(f"CV processing failed: {str(e)}")
            raise

    def parse(self, pdf_path: str) -> Resume:
        """Parse PDF resume into structured data"""
        # Extract text and metadata from PDF
        document = self.pdf_parser.parse(pdf_path)
        
        # Detect sections in the document
        detected_sections = self.section_detector.detect_sections(document)
        sections = detected_sections.get("sections", {})
        
        # Use EntityExtractor for all structured data extraction
        # The EntityExtractor is initialized with the NER pipeline and normalizers
        # so it can directly process the raw section text.
        contact_info = self.entity_extractor._extract_contact(sections.get("contact", {}).get("content", ""))
        summary = self.entity_extractor._extract_summary(sections.get("summary", {}).get("content", ""))
        skills = self.entity_extractor._extract_skills(sections.get("skills", {}).get("content", ""))
        education = self.entity_extractor._extract_education(sections.get("education", {}).get("content", ""))
        experience = self.entity_extractor._extract_experience(sections.get("experience", {}).get("content", ""))
        projects = self.entity_extractor._extract_projects(sections.get("projects", {}).get("content", ""))
        certifications = self.entity_extractor._extract_certifications(sections.get("certifications", {}).get("content", ""))
        
        # Build resume object
        resume = Resume(
            contact=contact_info,
            summary=summary,
            skills=skills,
            education=education,
            experience=experience,
            projects=projects,
            certifications=certifications
        )
        
        self.logger.debug(f"Built resume object: {json.dumps(resume.model_dump(), indent=2, default=str)}")
        
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
                    elif config_file.name == "pii_config.yaml":
                        config["pii_config"] = file_config
                    else:
                        config.update(file_config)
        
        # Initialize pipeline
        pipeline = CVPipeline(config)
        
        # Process the CV
        logging.info(f"Processing CV: {args.input}")
        resume = pipeline.process_cv(args.input)
        
        # Save results
        with open(args.output, 'w') as f:
            json.dump(resume.model_dump(), f, indent=2, default=str)
        logging.info(f"Results saved to {args.output}")
        
    except Exception as e:
        logging.error(f"Processing failed: {str(e)}")
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()