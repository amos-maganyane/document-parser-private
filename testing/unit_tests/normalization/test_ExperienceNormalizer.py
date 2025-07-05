# tests/unit_tests/normalization/test_experience_normalizer.py
import pytest
import json
import os
from unittest.mock import patch, mock_open, MagicMock
from datetime import date
from normalization.experience_normalizer import ExperienceNormalizer

# Sample data for mapping files
SAMPLE_COMPANIES = {
    "Google": ["Google LLC", "Google Inc."],
    "Microsoft": ["Microsoft Corp", "MSFT"],
    "Amazon": ["Amazon.com", "Amazon Web Services"]
}

SAMPLE_TITLES = {
    "Software Engineer": ["SW Engineer", "Software Developer"],
    "Product Manager": ["PM", "Product Lead"],
    "Data Scientist": ["ML Engineer", "Data Analyst"]
}

# Fixture for ExperienceNormalizer with mocked dependencies
@pytest.fixture
def exp_normalizer():
    # Mock file loading
    with patch("builtins.open", mock_open()) as mocked_open:
        # Mock different files based on path
        def mocked_json_load(file):
            if "companies.json" in file.name:
                return SAMPLE_COMPANIES
            elif "titles.json" in file.name:
                return SAMPLE_TITLES
            return {}
        
        mocked_open.return_value.__enter__.return_value.read.side_effect = lambda: json.dumps(
            SAMPLE_COMPANIES if "companies.json" in mocked_open.call_args[0][0] else SAMPLE_TITLES
        )
        
        # Mock date normalizer and skill normalizer
        with patch("normalization.experience_normalizer.DateNormalizer") as mock_dn, \
             patch("normalization.experience_normalizer.SkillNormalizer") as mock_sn:
            
            mock_dn_instance = mock_dn.return_value
            mock_dn_instance.normalize.side_effect = lambda x: f"normalized_{x}" if x else None
            
            mock_sn_instance = mock_sn.return_value
            mock_sn_instance.normalize_list.return_value = ["normalized_skill1", "normalized_skill2"]
            
            normalizer = ExperienceNormalizer("data/experience")
            return normalizer

def test_load_mapping_valid_file():
    """Test loading valid mapping files"""
    with patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_COMPANIES))):
        normalizer = ExperienceNormalizer()
        result = normalizer._load_mapping("dummy_path.json")
        assert result == SAMPLE_COMPANIES

def test_load_mapping_invalid_file():
    """Test handling invalid JSON files"""
    with patch("builtins.open", mock_open(read_data="invalid json")), \
         pytest.raises(json.JSONDecodeError):
        normalizer = ExperienceNormalizer()
        normalizer._load_mapping("invalid.json")

def test_load_mapping_missing_file():
    """Test handling missing files"""
    with patch("builtins.open", side_effect=FileNotFoundError):
        normalizer = ExperienceNormalizer()
        result = normalizer._load_mapping("missing.json")
        assert result == {}

def test_create_index():
    normalizer = ExperienceNormalizer()
    index = normalizer._create_index(SAMPLE_COMPANIES)
    assert len(index) == 9  # 3 canonical + 6 variants
    assert "Google" in index
    assert "Google LLC" in index
    assert "MSFT" in index

def test_normalize_company_clean_name(exp_normalizer):
    """Test company name cleaning"""
    result = exp_normalizer.normalize_company("Google Inc. [Special!]")
    assert result == "Google"

def test_normalize_company_exact_match(exp_normalizer):
    """Test exact company match"""
    assert exp_normalizer.normalize_company("Google LLC") == "Google"
    assert exp_normalizer.normalize_company("MSFT") == "Microsoft"

def test_normalize_company_fuzzy_match(exp_normalizer):
    """Test fuzzy company matching"""
    with patch("rapidfuzz.process.extractOne") as mock_extract:
        mock_extract.return_value = ("Amazon.com", 90, 0)
        assert exp_normalizer.normalize_company("Amazn") == "Amazon"
        mock_extract.assert_called_once()

def test_normalize_company_below_threshold(exp_normalizer):
    """Test company matching below threshold"""
    with patch("rapidfuzz.process.extractOne", return_value=(None, 0, None)):
        assert exp_normalizer.normalize_company("Unknown Company") == "Unknown Company"

def test_normalize_company_empty_input(exp_normalizer):
    """Test empty company name handling"""
    assert exp_normalizer.normalize_company("") == ""
    assert exp_normalizer.normalize_company(None) == ""

def test_normalize_title_abbreviation_expansion(exp_normalizer):
    # Add Senior Software Engineer to sample titles
    SAMPLE_TITLES["Senior Software Engineer"] = ["Sr. Software Engineer"]
    exp_normalizer.title_index = exp_normalizer._create_index(SAMPLE_TITLES)
    
    assert exp_normalizer.normalize_title("Sr. SWE") == "Senior Software Engineer"

def test_normalize_title_exact_match(exp_normalizer):
    """Test exact title match"""
    assert exp_normalizer.normalize_title("Software Developer") == "Software Engineer"
    assert exp_normalizer.normalize_title("Product Lead") == "Product Manager"

def test_normalize_title_fuzzy_match(exp_normalizer):
    """Test fuzzy title matching"""
    with patch("rapidfuzz.process.extractOne") as mock_extract:
        mock_extract.return_value = ("ML Engineer", 95, 0)
        assert exp_normalizer.normalize_title("Machine Learning Eng") == "Data Scientist"
        mock_extract.assert_called_once()

def test_normalize_company_below_threshold(exp_normalizer):
    with patch("rapidfuzz.process.extractOne", return_value=None):
        assert exp_normalizer.normalize_company("Unknown Company") == "Unknown Company"

def test_normalize_title_empty_input(exp_normalizer):
    """Test empty title handling"""
    assert exp_normalizer.normalize_title("") == ""
    assert exp_normalizer.normalize_title(None) == ""

def test_normalize_dates(exp_normalizer):
    """Test date normalization"""
    # Mock DateNormalizer
    exp_normalizer.date_normalizer.normalize.side_effect = lambda x: f"normalized_{x}"
    
    start, end = exp_normalizer.normalize_dates("Jan 2020", "Dec 2022")
    assert start == "normalized_Jan 2020"
    assert end == "normalized_Dec 2022"

def test_normalize_dates_invalid_input(exp_normalizer):
    exp_normalizer.date_normalizer.normalize.side_effect = [
        None,  # start_date
        None   # end_date
    ]
    start, end = exp_normalizer.normalize_dates("invalid", "invalid")
    assert start is None
    assert end is None


def test_normalize_technologies(exp_normalizer):
    """Test technology normalization"""
    result = exp_normalizer.normalize_technologies(["python", "aws"])
    assert result == ["normalized_skill1", "normalized_skill2"]

def test_normalize_description_cleaning(exp_normalizer):
    """Test job description cleaning"""
    input_desc = """
    •  Developed new features
       - Optimized performance
    
    Fixed bugs  in production.
    """
    
    expected = "Developed new features Optimized performance Fixed bugs in production."
    result = exp_normalizer.normalize_description(input_desc)
    assert result == expected

def test_normalize_description_capitalization(exp_normalizer):
    """Test description capitalization"""
    assert exp_normalizer.normalize_description("developed features") == "Developed features"
    assert exp_normalizer.normalize_description("") == ""

def test_normalize_description_whitespace(exp_normalizer):
    """Test whitespace normalization"""
    input_desc = "  Developed  features   \n\n  Fixed  bugs  "
    expected = "Developed features Fixed bugs"
    assert exp_normalizer.normalize_description(input_desc) == expected

def test_get_canonical(exp_normalizer):
    """Test canonical name retrieval"""
    assert exp_normalizer._get_canonical("Google LLC", SAMPLE_COMPANIES) == "Google"
    assert exp_normalizer._get_canonical("Unknown", SAMPLE_COMPANIES) == "Unknown"

def test_calculate_duration_valid(exp_normalizer):
    """Test duration calculation with valid dates"""
    # Mock DateNormalizer to return real date objects
    exp_normalizer.date_normalizer.normalize.side_effect = lambda x, **kw: date(2020, 1, 1) if "start" in x else date(2022, 1, 1)
    
    duration = exp_normalizer.calculate_duration("start", "end")
    assert duration == 24  # 2 years * 12 months

# Update the test_calculate_duration_current_position method
# tests/unit_tests/normalization/test_ExperienceNormalizer.py
def test_calculate_duration_current_position(exp_normalizer):
    """Test duration calculation for current position"""
    exp_normalizer.date_normalizer.normalize.side_effect = lambda x, **kw: date(2020, 1, 1) if "start" in x else None
    
    # Patch date.today() directly
    with patch("normalization.experience_normalizer.date_today") as mock_date:
        mock_date.today.return_value = date(2023, 1, 1)
        duration = exp_normalizer.calculate_duration("start", "Present")
        assert duration == 36  # 3 years * 12 months

def test_calculate_duration_invalid_dates(exp_normalizer):
    """Test duration calculation with invalid dates"""
    exp_normalizer.date_normalizer.normalize.return_value = None
    assert exp_normalizer.calculate_duration("invalid", "dates") == 0

def test_calculate_duration_end_before_start(exp_normalizer):
    exp_normalizer.date_normalizer.normalize.side_effect = lambda x, **kw: date(2022, 1, 1) if "start" in x else date(2020, 1, 1)
    assert exp_normalizer.calculate_duration("start", "end") == 0

def test_calculate_duration_partial_months(exp_normalizer):
    exp_normalizer.date_normalizer.normalize.side_effect = lambda x, **kw: date(2022, 1, 15) if "start" in x else date(2022, 3, 10)
    assert exp_normalizer.calculate_duration("start", "end") == 1
