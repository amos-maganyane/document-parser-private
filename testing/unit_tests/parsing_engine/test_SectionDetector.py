# testing/unit_tests/parsing_engine/test_section_detector.py

import pytest
from parsing_engine.section_detector import SectionDetector

class TestSectionDetector:
    # Test Initialization
    def test_init_with_empty_rules(self):
        detector = SectionDetector({})
        assert detector.section_rules == {}
        assert detector.confidence_threshold == 0.5
        assert detector.min_heading_size == 10

    def test_init_with_partial_rules(self):
        rules = {"patterns": {"education": ["edu"]}}
        detector = SectionDetector(rules)
        assert detector.section_rules == {"education": ["edu"]}
        assert detector.confidence_threshold == 0.5
        assert detector.min_heading_size == 10

    def test_init_with_full_rules(self):
        rules = {
            "patterns": {"education": ["edu"]},
            "confidence_threshold": 0.7,
            "min_heading_size": 12
        }
        detector = SectionDetector(rules)
        assert detector.section_rules == {"education": ["edu"]}
        assert detector.confidence_threshold == 0.7
        assert detector.min_heading_size == 12

    # Test _get_dominant_font_size
    def test_font_size_heading_type(self):
        block = {"type": "heading", "text": "Education"}
        detector = SectionDetector({})
        assert detector._get_dominant_font_size(block) == 14

    def test_font_size_dict_format(self):
        block = {"font": {"size": 16}, "text": "Content"}
        detector = SectionDetector({})
        assert detector._get_dominant_font_size(block) == 16

    def test_font_size_summary_field(self):
        block = {"font_summary": {"dominant_size": 12}, "text": "Content"}
        detector = SectionDetector({})
        assert detector._get_dominant_font_size(block) == 12

    def test_font_size_fallback_default(self):
        block = {"text": "No font info"}
        detector = SectionDetector({})
        assert detector._get_dominant_font_size(block) == 10

    # Test _match_section_heading
    def test_match_heading_with_font_size_below_threshold(self):
        rules = {"patterns": {"education": [r"education"]}}
        detector = SectionDetector(rules)
        assert detector._match_section_heading("Education", 8) is None

    def test_match_heading_with_colon_bypass(self):
        rules = {"patterns": {"summary": [r"summary"]}}
        detector = SectionDetector(rules)
        assert detector._match_section_heading("Professional Summary:", 8) == "summary"

    def test_match_multiple_patterns(self):
        rules = {
            "patterns": {
                "education": [r"education", r"academic"],
                "experience": [r"experience"]
            }
        }
        detector = SectionDetector(rules)
        # Should match both education patterns
        assert detector._match_section_heading("Academic Background", 12) == "education"

    def test_confidence_threshold(self):
        rules = {
            "patterns": {"skills": [r"skill.*", r"technologies"]},
            "confidence_threshold": 0.7
        }
        detector = SectionDetector(rules)
        # 1/2 patterns = 0.5 confidence < 0.7 threshold
        assert detector._match_section_heading("Skills", 12) is None

    def test_no_match(self):
        rules = {"patterns": {"education": [r"university"]}}
        detector = SectionDetector(rules)
        assert detector._match_section_heading("Work History", 12) is None

    def test_empty_rules(self):
        detector = SectionDetector({})
        assert detector._match_section_heading("Education", 12) is None

    def test_document_processing(self):
        rules = {
            "patterns": {
                "education": [r"education"],
                "experience": [r"experience"]
            }
        }
        detector = SectionDetector(rules)
        
        document = {
            "content": [
                {"text": "John Doe", "position": {"page": 1}, "font": {"size": 20}},
                {"text": "Work Experience", "position": {"page": 1}, "font": {"size": 14}},
                {"text": "Company A", "position": {"page": 1}, "font": {"size": 12}},
                {"text": "Education", "position": {"page": 2}, "font": {"size": 14}},
                {"text": "University B", "position": {"page": 2}, "font": {"size": 11}},
                {"text": "", "position": {"page": 3}},  # Empty block
                {"text": "Certificates", "position": {"page": 3}, "font": {"size": 9}}  # Font too small
            ],
            "raw_text": "Full raw text",
            "metadata": {"source": "test"}
        }
        
        result = detector.detect_sections(document)
        sections = result["sections"]
        
        assert list(sections.keys()) == ["experience", "education"]
        assert sections["experience"]["content"] == "Company A\n"
        assert sections["education"]["content"] == "University B\n"  # Now passes
        
        # Verify block accumulation
        assert len(sections["experience"]["blocks"]) == 1
        assert sections["experience"]["blocks"][0]["text"] == "Company A"
        assert sections["education"]["blocks"][0]["text"] == "University B"
        
        # Verify positions
        assert sections["experience"]["position"] == {"page": 1}
        assert sections["education"]["position"] == {"page": 2}
        
        # Verify metadata preservation
        assert result["raw"] == "Full raw text"
        assert result["metadata"] == {"source": "test"}

    def test_no_sections_detected(self):
        detector = SectionDetector({})
        document = {
            "content": [
                {"text": "No sections here", "font": {"size": 12}}
            ]
        }
        result = detector.detect_sections(document)
        assert result["sections"] == {}

    def test_content_without_headings(self):
        rules = {"patterns": {"summary": [r"summary"]}}
        detector = SectionDetector(rules)
        document = {
            "content": [
                {"text": "Professional experience", "font": {"size": 12}}
            ]
        }
        result = detector.detect_sections(document)
        assert result["sections"] == {}

    def test_multiple_blocks_in_section(self):
        rules = {"patterns": {"experience": [r"experience"]}}
        detector = SectionDetector(rules)
        document = {
            "content": [
                {"text": "Work Experience", "font": {"size": 14}},
                {"text": "Job 1", "font": {"size": 12}},
                {"text": "Job 2", "font": {"size": 12}}
            ]
        }
        result = detector.detect_sections(document)
        section = result["sections"]["experience"]
        assert section["content"] == "Job 1\nJob 2\n"
        assert len(section["blocks"]) == 2

    def test_heading_detection_after_content(self):
        rules = {"patterns": {"skills": [r"skills"]}}
        detector = SectionDetector(rules)
        document = {
            "content": [
                {"text": "Introduction", "font": {"size": 12}},
                {"text": "Skills", "font": {"size": 14}},
                {"text": "Python", "font": {"size": 12}}
            ]
        }
        result = detector.detect_sections(document)
        assert "skills" in result["sections"]
        assert result["sections"]["skills"]["content"] == "Python\n"

    def test_skip_small_content_block(self):
        rules = {"patterns": {"education": [r"education"]}}
        detector = SectionDetector(rules)
        document = {
            "content": [
                {"text": "Education", "font": {"size": 14}},
                {"text": "University", "font": {"size": 12}},
                {"text": "Page 1", "font": {"size": 8}}  # Should be skipped
            ]
        }
        result = detector.detect_sections(document)
        section = result["sections"]["education"]
        assert section["content"] == "University\n"
        assert len(section["blocks"]) == 1

    def test_keep_small_heading_with_colon(self):
        rules = {"patterns": {"skills": [r"skills"]}}
        detector = SectionDetector(rules)
        document = {
            "content": [
                {"text": "Skills:", "font": {"size": 8}},  # Small but ends with colon
                {"text": "Python", "font": {"size": 12}}
            ]
        }
        result = detector.detect_sections(document)
        assert "skills" in result["sections"]
        assert result["sections"]["skills"]["content"] == "Python\n"

    