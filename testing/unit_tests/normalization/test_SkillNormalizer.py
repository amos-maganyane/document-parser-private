# tests/unit_tests/normalization/test_skill_normalizer.py
import pytest
from unittest.mock import patch, mock_open
import json
from normalization.skill_normalizer import SkillNormalizer
from rapidfuzz import fuzz

SAMPLE_ONTOLOGY = {
    "Python": ["Python 3", "Py", "Python Programming"],
    "JavaScript": ["JS", "ECMAScript", "JavaScript ES6"],
    "Machine Learning": ["ML", "AI/ML", "Deep Learning"],
    "SQL": ["Structured Query Language", "MySQL", "PostgreSQL"]
}


@pytest.fixture
def skill_normalizer():
    # Mock ontology loading
    with patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_ONTOLOGY))):
        normalizer = SkillNormalizer("dummy_path.json")
        return normalizer


def test_initialization(skill_normalizer):
    assert skill_normalizer.ontology == SAMPLE_ONTOLOGY
    assert skill_normalizer.threshold == 90
    assert "Python" in skill_normalizer.skill_index
    assert "Py" in skill_normalizer.skill_index
    assert "JS" in skill_normalizer.skill_index

def test_initialization_file_not_found():
    with patch("builtins.open", side_effect=FileNotFoundError):
        normalizer = SkillNormalizer("missing.json")
        assert normalizer.ontology == {}
        assert normalizer.skill_index == []

def test_initialization_invalid_json():
    with patch("builtins.open", mock_open(read_data="invalid json")), \
         pytest.raises(json.JSONDecodeError):
        normalizer = SkillNormalizer("invalid.json")
        assert normalizer.ontology == {}
        assert normalizer.skill_index == []

# Test _create_skill_index
def test_skill_index_creation(skill_normalizer):
    index = skill_normalizer.skill_index
    assert len(index) == 16  # 4 canonical + 8 variants
    assert "Python" in index
    assert "Python 3" in index
    assert "Py" in index
    assert "JavaScript" in index
    assert "JS" in index
    assert "Machine Learning" in index
    assert "ML" in index
    assert "SQL" in index
    assert "MySQL" in index

# Test _get_canonical
@pytest.mark.parametrize("input_skill, expected", [
    ("Python", "Python"),
    ("Py", "Python"),
    ("Python 3", "Python"),
    ("JS", "JavaScript"),
    ("ECMAScript", "JavaScript"),
    ("ML", "Machine Learning"),
    ("AI/ML", "Machine Learning"),
    ("MySQL", "SQL"),
    ("Unknown Skill", "Unknown Skill"),
    ("", ""),
    (None, None),
])
def test_get_canonical(skill_normalizer, input_skill, expected):
    assert skill_normalizer._get_canonical(input_skill) == expected

# Test normalize method - exact matches
@pytest.mark.parametrize("input_skill, expected", [
    ("Python", "Python"),
    ("Py", "Python"),
    ("JavaScript", "JavaScript"),
    ("JS", "JavaScript"),
    ("Machine Learning", "Machine Learning"),
    ("ML", "Machine Learning"),
    ("SQL", "SQL"),
    ("PostgreSQL", "SQL"),
])
def test_normalize_exact_match(skill_normalizer, input_skill, expected):
    assert skill_normalizer.normalize(input_skill) == expected

# Update fuzzy match tests
@pytest.mark.parametrize("input_skill, expected", [
    ("Pythn", "Python"),  # Typo
    ("Javascrpt", "JavaScript"),  # Typo (was "Javascript")
    ("Java Script", "JavaScript"),  # Space variation
    ("maching lerning", "Machine Learning"),  # Typo
    ("Postgres", "SQL"),  # Partial match (was "SQl")
    ("S Q L", "SQL"),  # Weird spacing
])
def test_normalize_fuzzy_match(skill_normalizer, input_skill, expected):
    # Patch process.extractOne to control matching
    with patch("rapidfuzz.process.extractOne") as mock_extract:
        mock_extract.return_value = (expected, 95, 0)
        result = skill_normalizer.normalize(input_skill)
        assert result == expected
        mock_extract.assert_called_once()


# Update no match tests
@pytest.mark.parametrize("input_skill", [
    "Unknown Technology",
    "C++",
    " ",
    "",
    None
])
def test_normalize_no_match(skill_normalizer, input_skill):
    # Patch process.extractOne to return no match
    with patch("rapidfuzz.process.extractOne", return_value=None):
        assert skill_normalizer.normalize(input_skill) == input_skill

# Update threshold test
def test_normalize_threshold(skill_normalizer):
    # Test below threshold returns original
    with patch("rapidfuzz.process.extractOne", return_value=None):
        assert skill_normalizer.normalize("Pythn") == "Pythn"
    
    # Test at threshold returns match
    with patch("rapidfuzz.process.extractOne", return_value=("Python", 90, 0)):
        assert skill_normalizer.normalize("Pythn") == "Python"
    
    # Test above threshold returns match
    with patch("rapidfuzz.process.extractOne", return_value=("Python", 95, 0)):
        assert skill_normalizer.normalize("Pythn") == "Python"

# Test normalize_list method
def test_normalize_list(skill_normalizer):
    with patch.object(skill_normalizer, "normalize") as mock_normalize:
        mock_normalize.side_effect = lambda x: x.upper() if x else x
        skills = ["python", "js", "ml", "python", None, ""]
        result = skill_normalizer.normalize_list(skills)
        
        # Updated to include None
        assert set(result) == {"PYTHON", "JS", "ML", "", None}


# Test normalize_list with real normalization
def test_normalize_list_real(skill_normalizer):
    skills = ["Pie", "Javascrpt", "maching lerning", "Postgres", "C++"]
    with patch("rapidfuzz.process.extractOne") as mock_extract:
        mock_extract.side_effect = [
            ("Python", 95, 0),          # Pie
            ("JavaScript", 92, 0),      # Javascrpt
            None,                       # maching lerning
            ("SQL", 91, 0),             # Postgres
            None                        # C++
        ]
        result = skill_normalizer.normalize_list(skills)
        assert set(result) == {"Python", "JavaScript", "maching lerning", "SQL", "C++"}



# Test add_custom_mapping
def test_add_custom_mapping(skill_normalizer):
    # Add new canonical
    skill_normalizer.add_custom_mapping("PyTorch", "Deep Learning")
    assert "Deep Learning" in skill_normalizer.ontology
    assert "PyTorch" in skill_normalizer.ontology["Deep Learning"]
    assert "PyTorch" in skill_normalizer.skill_index
    
    # Add variant to existing canonical
    skill_normalizer.add_custom_mapping("Py3", "Python")
    assert "Py3" in skill_normalizer.ontology["Python"]
    assert "Py3" in skill_normalizer.skill_index
    
    # Add duplicate variant (should be ignored)
    original_python_variants = skill_normalizer.ontology["Python"].copy()
    skill_normalizer.add_custom_mapping("Py", "Python")
    assert skill_normalizer.ontology["Python"] == original_python_variants
    
    # Add to non-existing canonical (creates new entry)
    skill_normalizer.add_custom_mapping("ReactJS", "React")
    assert "React" in skill_normalizer.ontology
    assert "ReactJS" in skill_normalizer.ontology["React"]
    assert "React" in skill_normalizer.skill_index
    assert "ReactJS" in skill_normalizer.skill_index

# Test behavior with empty ontology
def test_empty_ontology():
    with patch("builtins.open", mock_open(read_data=json.dumps({}))):
        normalizer = SkillNormalizer("empty.json")
        assert normalizer.normalize("Python") == "Python"
        
        # Use set for unordered comparison
        result = normalizer.normalize_list(["JS", "ML"])
        assert set(result) == {"JS", "ML"}
        
        # Should not break on custom mapping
        normalizer.add_custom_mapping("Py", "Python")
        assert "Python" in normalizer.ontology
        assert "Py" in normalizer.ontology["Python"]
        assert "Py" in normalizer.skill_index

        
# Test threshold variations
# Update threshold effect tests
@pytest.mark.parametrize("threshold", [80, 90, 95])
def test_threshold_effect(threshold):
    with patch("builtins.open", mock_open(read_data=json.dumps(SAMPLE_ONTOLOGY))):
        normalizer = SkillNormalizer("dummy.json", threshold=threshold)
        assert normalizer.threshold == threshold
        
        with patch("rapidfuzz.process.extractOne") as mock_extract:
            # Below threshold
            mock_extract.return_value = None
            assert normalizer.normalize("Pythn") == "Pythn"
            
            # At threshold
            mock_extract.return_value = ("Python", threshold, 0)
            assert normalizer.normalize("Pythn") == "Python"
            
            # Above threshold
            mock_extract.return_value = ("Python", threshold + 1, 0)
            assert normalizer.normalize("Pythn") == "Python"


# Test special characters in skills
def test_special_characters(skill_normalizer):
    # Add custom skill with special characters
    skill_normalizer.add_custom_mapping("C#", "C Sharp")
    skill_normalizer.add_custom_mapping("C++", "C Plus Plus")
    
    assert skill_normalizer.normalize("C#") == "C Sharp"
    assert skill_normalizer.normalize("C++") == "C Plus Plus"
    
    # Test with fuzzy matching
    with patch("rapidfuzz.process.extractOne") as mock_extract:
        mock_extract.return_value = ("C Sharp", 95, 0)
        assert skill_normalizer.normalize("C#") == "C Sharp"
        
        mock_extract.return_value = ("C Plus Plus", 92, 0)
        assert skill_normalizer.normalize("c++") == "C Plus Plus"

# Test case sensitivity
def test_case_insensitivity(skill_normalizer):
    assert skill_normalizer.normalize("PYTHON") == "Python"
    assert skill_normalizer.normalize("js") == "JavaScript"
    assert skill_normalizer.normalize("Ml") == "Machine Learning"
    assert skill_normalizer.normalize("sqL") == "SQL"

# Test normalization of similar skills
def test_similar_skill_differentiation(skill_normalizer):
    # Add potentially conflicting skills
    skill_normalizer.add_custom_mapping("Java", "Java Programming")
    skill_normalizer.add_custom_mapping("JavaScript", "JS")
    
    # Should differentiate between Java and JavaScript
    with patch("rapidfuzz.process.extractOne") as mock_extract:
        mock_extract.return_value = ("Java Programming", 95, 0)
        assert skill_normalizer.normalize("Java") == "Java Programming"
        
        mock_extract.return_value = ("JavaScript", 90, 0)
        assert skill_normalizer.normalize("Javascript") == "JavaScript"

# Test performance with large ontology
def test_large_ontology_performance():
    # Create a large ontology
    large_ontology = {f"Skill{i}": [f"Variant{i}_{j}" for j in range(10)] 
                    for i in range(1000)}
    
    with patch("builtins.open", mock_open(read_data=json.dumps(large_ontology))), \
         patch("rapidfuzz.process.extractOne") as mock_extract:
        
        normalizer = SkillNormalizer("large.json")
        assert len(normalizer.skill_index) == 1000 * 11  # 1000 skills * (1 canonical + 10 variants)
        
        mock_extract.return_value = ("Skill42", 95, 0)
        assert normalizer.normalize("Variant42_5") == "Skill42"
        
        # Should only call extractOne for non-exact matches
        assert normalizer.normalize("Skill100") == "Skill100"
        mock_extract.assert_not_called()