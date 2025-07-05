import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from normalization.education_normalizer import EducationNormalizer

@pytest.fixture
def normalizer(tmp_path):
    institutions = {
        "Massachusetts Institute of Technology": ["MIT", "MIT University"],
        "Stanford University": ["Stanford"],
        "University of California, Berkeley": ["UC Berkeley", "Cal"]
    }
    
    degrees = {
        "Bachelor of Science": ["BS", "BSc"],
        "Master of Business Administration": ["MBA"],
        "Doctor of Philosophy": ["PhD"]
    }
    
    fields = {
        "Computer Science": ["CS", "Comp Sci"],
        "Electrical Engineering": ["EE"],
        "Business Administration": ["Business Admin"]
    }

    (tmp_path / "institutions.json").write_text(json.dumps(institutions))
    (tmp_path / "degrees.json").write_text(json.dumps(degrees))
    (tmp_path / "fields.json").write_text(json.dumps(fields))
    
    return EducationNormalizer(data_dir=str(tmp_path))


def test_init(normalizer, tmp_path):
    assert "Massachusetts Institute of Technology" in normalizer.institution_mapping
    assert "Bachelor of Science" in normalizer.degree_mapping
    assert "Computer Science" in normalizer.field_mapping
    
    assert "MIT" in normalizer.institution_index
    assert "BSc" in normalizer.degree_index


def test_normalize_institution(normalizer):
    assert normalizer.normalize_institution("MIT") == "Massachusetts Institute of Technology"
    assert normalizer.normalize_institution("Stanford") == "Stanford University"
    
    assert normalizer.normalize_institution("MIT Uni") == "Massachusetts Institute of Technology"
    assert normalizer.normalize_institution("Stanford Uni") == "Stanford University"
    assert normalizer.normalize_institution("Cal") == "University of California, Berkeley"
    
    assert normalizer.normalize_institution("M.I.T. University") == "Massachusetts Institute of Technology"
    assert normalizer.normalize_institution("UC Berkeley (Engineering)") == "University of California, Berkeley"
    
    assert normalizer.normalize_institution("Unknown College") == "Unknown"
    assert normalizer.normalize_institution("") == ""
    
    assert normalizer.normalize_institution("M.I.T. & Associates") == "Massachusetts Institute of Technology"


def test_normalize_degree(normalizer):
    assert normalizer.normalize_degree("BS") == "Bachelor of Science"
    assert normalizer.normalize_degree("MBA") == "Master of Business Administration"
    
    assert normalizer.normalize_degree("B.S.") == "Bachelor of Science"
    assert normalizer.normalize_degree("BSc") == "Bachelor of Science"
    assert normalizer.normalize_degree("M.B.A.") == "Master of Business Administration"
    assert normalizer.normalize_degree("PhD") == "Doctor of Philosophy"
    
    assert normalizer.normalize_degree("Bachelor in Science") == "Bachelor of Science"
    assert normalizer.normalize_degree("Masters of Business Admin") == "Master of Business Administration"

    assert normalizer.normalize_degree("B.S. in Engineering") == "Bachelor of Science"
    assert normalizer.normalize_degree("MBA (Finance)") == "Master of Business Administration"
    
    assert normalizer.normalize_degree("Associate Degree") == "Associate"
    assert normalizer.normalize_degree("") == ""


def test_normalize_field(normalizer):
    assert normalizer.normalize_field("CS") == "Computer Science"
    assert normalizer.normalize_field("EE") == "Electrical Engineering"

    assert normalizer.normalize_field("Computer Science") == "Computer Science"
    assert normalizer.normalize_field("Comp Sci") == "Computer Science"
    
    assert normalizer.normalize_field("ComputerScience") == "Computer Science"
    assert normalizer.normalize_field("electrical engineering") == "Electrical Engineering"
    
    assert normalizer.normalize_field("Mechanical Engineering") == "Mechanical Engineering"
    assert normalizer.normalize_field("") == ""
    
    assert normalizer.normalize_field("Business Admin") == "Business Administration"


def test_normalize_dates(normalizer):
    normalizer.date_normalizer = MagicMock()
    normalizer.date_normalizer.normalize.side_effect = lambda x: {
        "Jan 2020": "2020-01-01",
        "2022-05-15": "2022-05-15",
        "invalid": None
    }.get(x)
    
    assert normalizer.normalize_dates("Jan 2020", "2022-05-15") == ("2020-01-01", "2022-05-15")
    
    assert normalizer.normalize_dates("invalid", "invalid") == (None, None)
    
    assert normalizer.normalize_dates("Jan 2020", "invalid") == ("2020-01-01", None)


def test_normalize_gpa(normalizer):
    assert normalizer.normalize_gpa("3.8") == 3.8
    assert normalizer.normalize_gpa("GPA: 3.5/4.0") == 3.5
    assert normalizer.normalize_gpa("3.92") == 3.92
    assert normalizer.normalize_gpa("Overall GPA 3.75") == 3.75
    
    assert normalizer.normalize_gpa("3.2/4.0, Major GPA 3.8") == 3.2
    
    assert normalizer.normalize_gpa("Excellent") is None
    assert normalizer.normalize_gpa("A+") is None
    assert normalizer.normalize_gpa("") is None
    assert normalizer.normalize_gpa("3.8 out of 4") is None


def test_edge_cases(normalizer):
    assert normalizer.normalize_institution(None) == ""
    assert normalizer.normalize_degree("") == ""
    assert normalizer.normalize_field(None) == ""
    assert normalizer.normalize_dates("", "") == (None, None)
    assert normalizer.normalize_gpa(None) is None
    
    assert normalizer.normalize_institution(123) == ""
    assert normalizer.normalize_degree(True) == ""


def test_missing_files(caplog, tmp_path):
    normalizer = EducationNormalizer(data_dir=str(tmp_path / "nonexistent"))
    assert normalizer.institution_mapping == {}
    assert normalizer.degree_mapping == {}
    assert normalizer.field_mapping == {}
    assert normalizer.normalize_institution("MIT") == "MIT"
    assert normalizer.normalize_degree("BS") == "Bachelor of Science"
    assert normalizer.normalize_field("CS") == "Computer Science" 
    assert "not found" in caplog.text


def test_corrupted_files(caplog, tmp_path):
    (tmp_path / "institutions.json").write_text("{invalid}")
    
    normalizer = EducationNormalizer(data_dir=str(tmp_path))
    assert normalizer.institution_mapping == {}
    assert "Error loading" in caplog.text


def test_normalize_education_list(normalizer):
    education_entries = [
        {
            "institution": "MIT",
            "degree": "BS",
            "field_of_study": "CS",
            "start_date": "2018",
            "end_date": "2022",
            "gpa": "3.8"
        },
        {
            "institution": "Stanford",
            "degree": "MBA",
            "start_date": "2022",
            "end_date": "2024"
        }
    ]
    
    normalized = normalizer.normalize(education_entries)
    
    assert len(normalized) == 2
    assert normalized[0]["institution"] == "Massachusetts Institute of Technology"
    assert normalized[0]["degree"] == "Bachelor of Science"
    assert normalized[0]["field_of_study"] == "Computer Science"
    assert normalized[0]["gpa"] == 3.8
    
    assert normalized[1]["institution"] == "Stanford University"
    assert normalized[1]["degree"] == "Master of Business Administration"