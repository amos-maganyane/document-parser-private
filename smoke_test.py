import os
import json
import tempfile
from typing import Dict
import spacy
from schemas.resume_schema import Resume, Education, Experience
from parsing_engine.text_parser import TextParser
from parsing_engine.section_detector import SectionDetector
from parsing_engine.entity_extractor import EntityExtractor
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Mock configuration
CONFIG = {
    'pii_config': {
        'detection_rules': {
            'email': [r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'],
            'phone': [r'(\+\d{1,2}\s?)?(\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}']
        },
        'replacement_strategy': "hash"
    },
    'skill_ontology_path': os.path.join('data', 'ontology', 'skills_ontology.json'),
    'education_data_dir': 'data/education',
    'experience_data_dir': 'data/experience',
    'base_model': 'en_core_web_sm',
    'section_rules': {
        'patterns': {
            'contact': [r'contact', r'details'],
            'summary': [r'summary', r'profile'],
            'experience': [r'experience', r'work\s+history'],
            'education': [r'education', r'qualifications'],
            'skills': [r'skills', r'technologies'],
            'projects': [r'projects', r'portfolio']
        },
        'confidence_threshold': 0.5,  # Lowered threshold
        'min_heading_size': 10  # Lowered font size
    }
}

def create_sample_data_files():
    os.makedirs('data/ontology', exist_ok=True)
    os.makedirs('data/education', exist_ok=True)
    os.makedirs('data/experience', exist_ok=True)
    
    # Skill ontology
    skill_ontology = {
        "Python": ["Py", "Python 3"],
        "Java": ["J2EE", "Java EE"],
        "Docker": ["Docker Engine"],
        "AWS": ["Amazon Web Services"],
        "Flask": ["Flask framework"],
        "Spring Boot": ["SpringBoot"]
    }
    with open(os.path.join('data', 'ontology', 'skills_ontology.json'), 'w') as f:
        json.dump(skill_ontology, f)
    
    # Institution mapping
    institutions = {
        "University of Technology": ["Tech Univ", "Uni of Tech"]
    }
    with open(os.path.join('data', 'education', 'institutions.json'), 'w') as f:
        json.dump(institutions, f)
    
    # Company mapping
    companies = {
        "Tech Innovations Inc": ["Tech Innovations", "Tech Inc"]
    }
    with open(os.path.join('data', 'experience', 'companies.json'), 'w') as f:
        json.dump(companies, f)

SAMPLE_RESUME = """
John Doe
San Francisco, CA | john.doe@email.com | (123) 456-7890

SUMMARY:
Senior software engineer with 5+ years of experience in backend development. 
Skilled in Python, Java, and cloud technologies.

WORK EXPERIENCE:
Senior Software Engineer, Tech Innovations Inc (2019-2023)
- Developed microservices using Python and Spring Boot
- Containerized applications using Docker
- Deployed solutions on AWS

Software Developer, Startup Labs (2017-2019)
- Built REST APIs with Flask
- Optimized SQL queries

EDUCATION:
BSc Computer Science, University of Technology (2015-2019)
GPA: 3.8/4.0

SKILLS:
Python, Java, Docker, AWS, Flask, Spring Boot, SQL

PROJECTS:
Recommendation System - ML project using Python
"""

def debug_print_document(document: Dict, title: str):
    """Print document structure for debugging"""
    print(f"\n=== {title} ===")
    print(f"Raw text length: {len(document.get('raw_text', ''))} characters")
    print(f"Metadata: {json.dumps(document.get('metadata', {}), indent=2)}")
    
    print("\nContent Blocks:")
    for i, block in enumerate(document.get('content', [])[:5]):  # Print first 5 blocks
        print(f"Block {i+1}:")
        print(f"  Type: {block.get('type', 'unknown')}")
        print(f"  Text: {block.get('text', '')[:80]}{'...' if len(block.get('text', '')) > 80 else ''}")
        if 'font' in block:
            print(f"  Font: {block['font'].get('size', '?')}pt {block['font'].get('name', '?')}")

def debug_print_sections(sections: Dict):
    """Print detected sections for debugging"""
    print("\n=== DETECTED SECTIONS ===")
    for section, content in sections.items():
        print(f"\n{section.upper()} SECTION:")
        print(f"Content: {content['content'][:200]}{'...' if len(content['content']) > 200 else ''}")
        print(f"Block count: {len(content['blocks'])}")

def run_smoke_test():
    print("=== STARTING DOCUMENT PARSER DEBUG TEST ===")
    
    # Create sample data files
    create_sample_data_files()
    
    # Create temp resume file
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as f:
        f.write(SAMPLE_RESUME)
        resume_path = f.name
    
    print(f"Created test resume at: {resume_path}")
    
    # Step 1: Parse text
    print("\n[1/3] PARSING TEXT...")
    text_parser = TextParser(config=CONFIG)
    parsed_doc = text_parser.parse(resume_path)
    debug_print_document(parsed_doc, "PARSED DOCUMENT")
    
    # Step 2: Detect sections
    print("\n[2/3] DETECTING SECTIONS...")
    section_detector = SectionDetector(CONFIG.get('section_rules', {}))
    sectioned_doc = section_detector.detect_sections(parsed_doc)
    
    if 'sections' in sectioned_doc:
        debug_print_sections(sectioned_doc['sections'])
    else:
        print("!!! NO SECTIONS DETECTED !!!")
    
    # Step 3: Extract entities
    print("\n[3/3] EXTRACTING ENTITIES...")
    entity_extractor = EntityExtractor(CONFIG)
    
    # Check if sections were detected
    if 'sections' not in sectioned_doc or not sectioned_doc['sections']:
        print("!!! WARNING: No sections detected. Entity extraction may fail !!!")
    
    resume = entity_extractor.extract_resume(sectioned_doc)
    
    # Step 4: Print results
    print("\n=== PARSING RESULTS ===")
    print(f"Contact: {resume.contact}")
    print(f"Summary: {resume.summary[:100]}{'...' if len(resume.summary) > 100 else ''}")
    
    print("\nEducation:")
    for edu in resume.education:
        print(f" - {edu.degree} at {edu.institution} ({edu.start_date} to {edu.end_date})")
    
    print("\nExperience:")
    for exp in resume.experience:
        print(f" - {exp.position} at {exp.company} ({exp.start_date} to {exp.end_date})")
        print(f"   Technologies: {exp.technologies}")
    
    print(f"\nSkills: {resume.skills}")
    
    print("\nProjects:")
    for project in resume.projects:
        print(f" - {project.name}")
    
    # Step 5: Print raw extracted data
    print("\n=== RAW EXTRACTED DATA ===")
    print(json.dumps(resume.dict(), indent=2))
    
    # Clean up
    os.unlink(resume_path)
    print("\nTEST COMPLETED!")

if __name__ == "__main__":
    # Ensure spaCy model is installed
    try:
        nlp = spacy.load(CONFIG['base_model'])
    except OSError:
        print(f"Downloading spaCy model: {CONFIG['base_model']}")
        spacy.cli.download(CONFIG['base_model'])
        nlp = spacy.load(CONFIG['base_model'])
    
    run_smoke_test()