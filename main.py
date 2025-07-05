# main.py
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any
import yaml

from pydantic import ValidationError
from schemas.resume_schema import Resume, Education, Experience, Project

# Import pipeline components
from parsing_engine.pdf_parser import PDFParser
from normalization.skill_normalizer import SkillNormalizer
from normalization.experience_normalizer import ExperienceNormalizer
from normalization.education_normalizer import EducationNormalizer
from normalization.date_normalizer import DateNormalizer
from utils.error_handling import ConfigError, ParserError
from utils.file_utils import validate_file_path
from utils.logging import setup_logging

# ----------------------------------------
# Configuration
# ----------------------------------------
DEFAULT_CONFIG = {
    "pdf_parser": {
        "use_ocr": False,
        "layout_analysis": True,
        "section_rules": "config/parsing_rules.yaml",
        "min_confidence": 0.7
    },
    "normalization": {
        "skill_ontology_path": "data/ontology/skills.json",
        "education_data_dir": "data/education",
        "experience_data_dir": "data/experience"
    }
}

# ----------------------------------------
# CV Processing Pipeline
# ----------------------------------------
class CVPipeline:
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or DEFAULT_CONFIG
        self.logger = logging.getLogger(__name__)
        self._initialize_components()
        
    def _initialize_components(self):
        """Initialize all pipeline components with configuration"""
        try:
            # Load section rules if it's a file path
            section_rules = self.config.get("section_rules", {})
            if isinstance(section_rules, str):
                try:
                    with open(section_rules, 'r') as f:
                        section_rules = yaml.safe_load(f)
                except Exception as e:
                    raise ConfigError(f"Failed to load section rules: {str(e)}") from e

            if not isinstance(section_rules, dict):
                raise ConfigError("section_rules must be a dictionary")

            # Initialize PDF parser
            self.pdf_parser = PDFParser({**self.config["pdf_parser"], "section_rules": section_rules})

            # Initialize normalizers
            norm_config = self.config["normalization"]
            self.skill_normalizer = SkillNormalizer(norm_config["skill_ontology_path"])
            self.education_normalizer = EducationNormalizer(norm_config["education_data_dir"])
            self.experience_normalizer = ExperienceNormalizer(norm_config["experience_data_dir"])
            self.date_normalizer = DateNormalizer()

        except KeyError as e:
            raise ConfigError(f"Missing configuration key: {e}") from e
        except Exception as e:
            raise ConfigError(f"Component initialization failed: {str(e)}") from e

    def parse_cv(self, file_path: str) -> Dict[str, Any]:
        """Parse PDF CV file"""
        self.logger.info(f"Parsing PDF: {file_path}")

        try:
            return self.pdf_parser.parse(file_path)
        except Exception as e:
            raise ParserError(f"Failed to parse PDF: {str(e)}") from e

    def normalize_data(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply normalization to parsed data"""
        try:
            skills = parsed_data.get("skills", [])
            if not isinstance(skills, list):
                raise ParserError("Skills data must be a list")
            
            return {
                "contact": parsed_data.get("contact", {}),
                "summary": parsed_data.get("summary", ""),
                # Change normalize to normalize_list for handling lists of skills
                "skills": self.skill_normalizer.normalize_list(skills),
                "education": self.education_normalizer.normalize(parsed_data.get("education", [])),
                "experience": self.experience_normalizer.normalize(parsed_data.get("experience", [])),
                "projects": parsed_data.get("projects", []),
                "certifications": parsed_data.get("certifications", []),
                "dates": self.date_normalizer.normalize(parsed_data.get("dates", [])),
            }
        except Exception as e:
            raise ParserError(f"Normalization failed: {str(e)}") from e

    def build_resume(self, normalized_data: Dict[str, Any]) -> Resume:
        """Create validated resume model from normalized data"""
        try:
            # Map normalized data to Resume model
            return Resume(
                contact=normalized_data.get("contact", {}),
                summary=normalized_data.get("summary", ""),
                skills=normalized_data.get("skills", []),
                education=[
                    Education(**edu) for edu in normalized_data.get("education", [])
                ],
                experience=[
                    Experience(**exp) for exp in normalized_data.get("experience", [])
                ],
                projects=[
                    Project(**proj) for proj in normalized_data.get("projects", [])
                ],
                certifications=normalized_data.get("certifications", []),
            )
        except ValidationError as e:
            self.logger.error("Resume validation failed:")
            self.logger.error(json.dumps(e.errors(), indent=2))
            raise

    def process_cv(self, file_path: str) -> Resume:
        """Full CV processing pipeline"""
        self.logger.info(f"Processing CV: {file_path}")
        
        # Validate input file
        validate_file_path(file_path)
        
        # Execute pipeline
        parsed_data = self.parse_cv(file_path)
        normalized_data = self.normalize_data(parsed_data)
        resume = self.build_resume(normalized_data)
        
        return resume

# ----------------------------------------
# Main CLI handler
# ----------------------------------------
def main():
    # Setup argument parser
    parser = argparse.ArgumentParser(description="PDF CV Parser")
    parser.add_argument("file", type=str, help="Path to PDF CV file")
    parser.add_argument("-o", "--output", type=str, help="Save output to JSON file")
    parser.add_argument("-c", "--config", type=str, help="Path to custom config file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    # Configure logging
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    try:
        # Load custom config if provided
        config = DEFAULT_CONFIG
        if args.config:
            try:
                with open(args.config, "r") as f:
                    config = json.load(f)
                logger.info(f"Loaded custom config from {args.config}")
            except Exception as e:
                logger.warning(f"Failed to load custom config: {str(e)}. Using defaults.")

        # Process CV
        pipeline = CVPipeline(config)
        resume = pipeline.process_cv(args.file)

        # Convert to JSON-serializable dict
        output = resume.dict()

        # Output results
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            logger.info(f"Result written to {args.output}")
        else:
            print(json.dumps(output, indent=2))
            
        sys.exit(0)
        
    except Exception as e:
        logger.exception("CV processing failed")
        sys.exit(1)

if __name__ == "__main__":
    main()