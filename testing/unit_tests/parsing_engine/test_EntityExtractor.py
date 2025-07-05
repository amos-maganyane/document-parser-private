import pytest
from unittest.mock import MagicMock, patch, create_autospec
from parsing_engine.entity_extractor import EntityExtractor
from schemas.resume_schema import Resume, Education, Experience, Project
from spacy.tokens import Doc, Span, Token
import spacy
import re

# Fixtures --------------------------------------------------------------------

@pytest.fixture
def mock_config():
    return {
        'base_model': 'en_core_web_sm',
        'skill_ontology_path': 'fake/path',
        'education_data_dir': 'fake/edu_dir',
        'experience_data_dir': 'fake/exp_dir',
        'min_confidence': 0.7
    }

@pytest.fixture
def extractor(mock_config):
    with patch('spacy.load'), \
         patch('parsing_engine.entity_extractor.PIIAnonymizer'), \
         patch('parsing_engine.entity_extractor.SkillNormalizer'), \
         patch('parsing_engine.entity_extractor.DateNormalizer'), \
         patch('parsing_engine.entity_extractor.EducationNormalizer'), \
         patch('parsing_engine.entity_extractor.ExperienceNormalizer'):
        
        ex = EntityExtractor(mock_config)
        ex.nlp = MagicMock()
        ex.pii_anonymizer.anonymize.return_value = ("anonymized", {})
        return ex

@pytest.fixture
def mock_doc():
    doc = MagicMock(spec=Doc)
    doc.ents = []
    doc.noun_chunks = []
    return doc

# Tests -----------------------------------------------------------------------

def test_combine_sections(extractor):
    sections = {
        'contact': {'content': 'email@test.com'},
        'summary': {'content': 'Professional summary'}
    }
    result = extractor._combine_sections(sections)
    assert result == "email@test.com\n\nProfessional summary"

def test_extract_contact_email(extractor):
    contact_text = "Contact: email@test.com"
    result = extractor._extract_contact(contact_text)
    assert result["email"] == "email@test.com"

def test_extract_contact_phone(extractor):
    contact_text = "Phone: 123-456-7890"
    result = extractor._extract_contact(contact_text)
    assert result["phone"] == "123-456-7890"

def test_extract_summary_trimming(extractor):
    long_text = "A. " * 200  # ~500+ characters
    result = extractor._extract_summary(long_text)
    assert len(result) <= 500
    assert result.endswith('...') or '.' in result

@patch.object(EntityExtractor, '_is_skill')
def test_extract_skills(mock_is_skill, extractor, mock_doc):
    # Mock entities
    skill_ent = MagicMock(spec=Span)
    skill_ent.label_ = "SKILL"
    skill_ent.text = "Python"
    mock_doc.ents = [skill_ent]
    
    # Mock noun chunks
    chunk = MagicMock(spec=Span)
    chunk.text = "machine learning"
    mock_doc.noun_chunks = [chunk]
    mock_is_skill.return_value = True
    
    # Mock normalizer
    extractor.skill_normalizer.normalize_list.return_value = ["python", "machine learning"]
    
    skills = extractor._extract_skills(mock_doc)
    assert skills == ["python", "machine learning"]
    extractor.skill_normalizer.normalize_list.assert_called_once()

def test_is_skill_heuristics(extractor, mock_doc):
    # Valid skill
    valid_chunk = MagicMock(spec=Span)
    valid_chunk.__len__.return_value = 2
    valid_tokens = [MagicMock(is_stop=False, is_punct=False) for _ in range(2)]
    valid_chunk.__iter__.return_value = valid_tokens
    
    # Invalid (stop word)
    invalid_chunk = MagicMock(spec=Span)
    invalid_tokens = [MagicMock(is_stop=True), MagicMock(is_stop=False)]
    invalid_chunk.__iter__.return_value = invalid_tokens
    
    assert extractor._is_skill(valid_chunk) is True
    assert extractor._is_skill(invalid_chunk) is False

def test_split_education_entries(extractor):
    text = "University A\n2020-2024\nUniversity B\n2018-2020"
    entries = extractor._split_education_entries(text)
    assert entries == ["University A\n2020-2024", "University B\n2018-2020"]

def test_parse_education_entry(extractor):
    text = "MIT, BS Computer Science\n2018-2022 GPA: 3.8"
    institution, degree, dates, gpa = extractor._parse_education_entry(text)
    assert institution == "MIT"
    assert degree == "BS"
    assert dates == "2018-2022"
    assert gpa == 3.8

def test_extract_field_of_study(extractor):
    text = "BS in Computer Science"
    field = extractor._extract_field_of_study(text)
    assert field == "Computer Science"

def test_split_experience_entries(extractor):
    text = "Company A\nSenior Dev\n2020-2023\nDetails\n\nCompany B"
    entries = extractor._split_experience_entries(text)
    assert entries == ["Company A\nSenior Dev\n2020-2023\nDetails", "Company B"]

def test_parse_experience_entry(extractor):
    text = "Google, Senior Engineer\nJan 2020 - Present\nBuilt systems"
    company, position, dates, desc = extractor._parse_experience_entry(text)
    assert company == "Google"
    assert position == "Senior Engineer"
    assert dates == "Jan 2020 - Present"
    assert "Built systems" in desc

def test_extract_certifications(extractor):
    text = "AWS Certified Developer\nGoogle Cloud Professional"
    certs = extractor._extract_certifications(text)
    assert "AWS Certified Developer" in certs
    assert "Google Cloud Professional" in certs

@patch.object(EntityExtractor, '_extract_certifications')
@patch.object(EntityExtractor, '_extract_projects')
@patch.object(EntityExtractor, '_extract_experience')
@patch.object(EntityExtractor, '_extract_education')
@patch.object(EntityExtractor, '_extract_skills')
@patch.object(EntityExtractor, '_extract_summary')
@patch.object(EntityExtractor, '_extract_contact')
def test_extract_resume(mock_contact, mock_summary, mock_skills, mock_education, 
                       mock_experience, mock_projects, mock_certifications, extractor):
    # Mock all dependencies
    mock_contact.return_value = {"email": "test@example.com"}
    mock_summary.return_value = "Summary"
    mock_skills.return_value = ["Python"]
    mock_education.return_value = []
    mock_experience.return_value = []
    mock_projects.return_value = []
    mock_certifications.return_value = []
    
    # Test input with correct structure
    doc = {
        'sections': {
            'contact': {'content': '...'},
            'summary': {'content': '...'},
            'education': {'content': '...'},
            'experience': {'content': '...'},
            'projects': {'content': '...'}
        }
    }
    
    resume = extractor.extract_resume(doc)
    
    assert isinstance(resume, Resume)
    assert resume.contact["email"] == "test@example.com"
    assert "Python" in resume.skills

def test_parse_project_entry(extractor):
    # Mock spaCy output using the existing nlp mock in extractor
    mock_doc = MagicMock()
    mock_ent = MagicMock()
    mock_ent.label_ = "SKILL"
    mock_ent.text = "Python"
    mock_doc.ents = [mock_ent]
    extractor.nlp.return_value = mock_doc

    text = "Project X\nBuilt with Python and Django"
    name, desc, tech = extractor._parse_project_entry(text)
    assert name == "Project X"
    assert "Built with" in desc
    assert "Python" in tech