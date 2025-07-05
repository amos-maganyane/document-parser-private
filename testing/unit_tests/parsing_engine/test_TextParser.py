# testing/unit_tests/parsing_engine/test_text_parser.py

import os
import pytest
import tempfile
import logging
from unittest.mock import patch
from parsing_engine.text_parser import TextParser

# Setup logging for test visibility
logging.basicConfig(level=logging.DEBUG)

class TestTextParser:
    # Test initialization
    def test_init_default_config(self):
        parser = TextParser()
        assert parser.config == {}
        assert parser.section_rules == {}

    def test_init_with_config(self):
        config = {"section_rules": {"patterns": {"contact": ["contact"]}}}
        parser = TextParser(config)
        assert parser.config == config
        assert parser.section_rules == config["section_rules"]

    # Test metadata extraction
    def test_metadata_extraction(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            tmpfile.write(b"Test content")
            tmpfile_path = tmpfile.name

        parser = TextParser()
        metadata = parser._extract_metadata(tmpfile_path)
        assert metadata["format"] == "text"
        assert metadata["file_name"] == os.path.basename(tmpfile_path)
        assert metadata["file_size"] == 12
        os.unlink(tmpfile_path)

    # Test block creation
    def test_create_text_block(self):
        parser = TextParser()
        block = parser._create_text_block("Sample text")
        assert block == {
            "text": "Sample text",
            "type": "text",
            "position": {"x": 0, "y": 0},
            "font": {"size": 11, "name": "Arial"}
        }

    def test_create_heading_block(self):
        parser = TextParser()
        block = parser._create_heading_block("EDUCATION")
        assert block == {
            "text": "EDUCATION",
            "type": "heading",
            "position": {"x": 0, "y": 0},
            "font": {"size": 14, "name": "Arial"}
        }

    # Test content structuring
    # Test content structuring
    @pytest.mark.parametrize("content, expected_blocks", [
        # Single heading with content
        (
            "SUMMARY\nJohn Doe",  # Changed to non-heading content
            [
                {"text": "SUMMARY", "type": "heading", "position": {"x": 0, "y": 0}, "font": {"size": 14, "name": "Arial"}},
                {"text": "John Doe", "type": "text", "position": {"x": 0, "y": 0}, "font": {"size": 11, "name": "Arial"}}
            ]
        ),
        # Multiple sections
        (
            "CONTACT\nJohn Doe\n\nEDUCATION\nUniversity",
            [
                {"text": "CONTACT", "type": "heading", "position": {"x": 0, "y": 0}, "font": {"size": 14, "name": "Arial"}},
                {"text": "John Doe", "type": "text", "position": {"x": 0, "y": 0}, "font": {"size": 11, "name": "Arial"}},
                {"text": "EDUCATION", "type": "heading", "position": {"x": 0, "y": 0}, "font": {"size": 14, "name": "Arial"}},
                {"text": "University", "type": "text", "position": {"x": 0, "y": 0}, "font": {"size": 11, "name": "Arial"}}
            ]
        ),
        # Headings with colons and whitespace
        (
            "SKILLS:\nPython\nEDUCATION: \nComputer Science",
            [
                {"text": "SKILLS:", "type": "heading", "position": {"x": 0, "y": 0}, "font": {"size": 14, "name": "Arial"}},
                {"text": "Python", "type": "text", "position": {"x": 0, "y": 0}, "font": {"size": 11, "name": "Arial"}},
                {"text": "EDUCATION:", "type": "heading", "position": {"x": 0, "y": 0}, "font": {"size": 14, "name": "Arial"}},
                {"text": "Computer Science", "type": "text", "position": {"x": 0, "y": 0}, "font": {"size": 11, "name": "Arial"}}
            ]
        ),
        # Mixed case headings
        (
            "Work Experience\nCompany A\n\nEducation\nSchool B",
            [
                {"text": "Work Experience", "type": "heading", "position": {"x": 0, "y": 0}, "font": {"size": 14, "name": "Arial"}},
                {"text": "Company A", "type": "text", "position": {"x": 0, "y": 0}, "font": {"size": 11, "name": "Arial"}},
                {"text": "Education", "type": "heading", "position": {"x": 0, "y": 0}, "font": {"size": 14, "name": "Arial"}},
                {"text": "School B", "type": "text", "position": {"x": 0, "y": 0}, "font": {"size": 11, "name": "Arial"}}
            ]
        ),
        # Empty lines handling
        (
            "\n\nSUMMARY\n\n\nJohn Doe\n\n\n\n",  # Changed to non-heading content
            [
                {"text": "SUMMARY", "type": "heading", "position": {"x": 0, "y": 0}, "font": {"size": 14, "name": "Arial"}},
                {"text": "John Doe", "type": "text", "position": {"x": 0, "y": 0}, "font": {"size": 11, "name": "Arial"}}
            ]
        ),
        # No headings
        (
            "This is a simple text file\nwith no section headings",
            [
                {"text": "This is a simple text file\nwith no section headings", "type": "text", "position": {"x": 0, "y": 0}, "font": {"size": 11, "name": "Arial"}}
            ]
        ),
        # Heading at end of file
        (
            "John Doe\nSUMMARY",  # Changed to non-heading content
            [
                {"text": "John Doe", "type": "text", "position": {"x": 0, "y": 0}, "font": {"size": 11, "name": "Arial"}},
                {"text": "SUMMARY", "type": "heading", "position": {"x": 0, "y": 0}, "font": {"size": 14, "name": "Arial"}}
            ]
        ),
    ])
    def test_structure_content(self, content, expected_blocks):
        parser = TextParser()
        blocks = parser._structure_content(content)
        assert blocks == expected_blocks

    # Test full parse functionality
    def test_parse_valid_file(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as tmpfile:
            tmpfile.write("CONTACT\nJohn Doe\n\nSKILLS\nPython")
            tmpfile_path = tmpfile.name
        
        parser = TextParser()
        document = parser.parse(tmpfile_path)
        
        assert document["raw_text"] == "CONTACT\nJohn Doe\n\nSKILLS\nPython"
        assert len(document["content"]) == 4
        assert document["tables"] == []
        assert document["images"] == []
        assert document["metadata"]["format"] == "text"
        assert document["metadata"]["file_name"] == os.path.basename(tmpfile_path)
        assert document["metadata"]["file_size"] == len("CONTACT\nJohn Doe\n\nSKILLS\nPython")
        
        os.unlink(tmpfile_path)

    def test_parse_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as tmpfile:
            tmpfile.write("")
            tmpfile_path = tmpfile.name
        
        parser = TextParser()
        document = parser.parse(tmpfile_path)
        
        assert document["raw_text"] == ""
        assert document["content"] == []
        assert document["metadata"]["file_size"] == 0
        
        os.unlink(tmpfile_path)

    # Test error handling
    def test_parse_nonexistent_file(self):
        parser = TextParser()
        document = parser.parse("non_existent_file.txt")
        assert document["raw_text"] == ""
        assert document["content"] == []
        assert document["metadata"] == {
            "format": "text",
            "file_name": "non_existent_file.txt",
            "file_size": 0
        }


    @patch("builtins.open", side_effect=Exception("Test error"))
    def test_parse_file_read_error(self, mock_open):
        parser = TextParser()
        document = parser.parse("any_file.txt")
        
        assert document["raw_text"] == ""
        assert document["content"] == []
        assert document["tables"] == []
        assert document["images"] == []
        assert document["metadata"] == {
            "format": "text",
            "file_name": "any_file.txt",
            "file_size": 0
        }

    # Test heading pattern variations
    # Test heading pattern variations
    @pytest.mark.parametrize("heading, expected_text", [
        ("SUMMARY", "SUMMARY"),
        ("summary", "summary"),
        ("Summary", "Summary"),
        ("SUMMARY:", "SUMMARY:"),
        ("SUMMARY :", "SUMMARY :"),
        ("  SUMMARY  ", "SUMMARY"),
        ("PROFESSIONAL SUMMARY", "PROFESSIONAL SUMMARY"),
        ("WORK EXPERIENCE", "WORK EXPERIENCE"),
        ("SKILLS", "SKILLS"),
        ("EDUCATION", "EDUCATION"),
        ("CONTACT INFO", "CONTACT INFO"),
        ("PERSONAL DETAILS", "PERSONAL DETAILS"),
        ("ABOUT ME", "ABOUT ME"),
        ("ACADEMIC EDUCATION", "ACADEMIC EDUCATION"),
        ("TECHNICAL SKILLS", "TECHNICAL SKILLS")
    ])
    def test_heading_pattern_matching(self, heading, expected_text):
        parser = TextParser()
        blocks = parser._structure_content(f"{heading}\nContent")
        assert len(blocks) == 2
        assert blocks[0]["type"] == "heading"
        assert blocks[0]["text"] == expected_text
        assert blocks[1]["type"] == "text"

    # Test non-heading text
    @pytest.mark.parametrize("non_heading", [
        "Not a heading",
        "Summary of qualifications",
        "Education history",
        "Contact information",
        "SKILLS SECTION",
        "END OF SUMMARY",
        "Details about my education"
    ])
    def test_non_heading_text(self, non_heading):
        parser = TextParser()
        blocks = parser._structure_content(f"{non_heading}\nContent")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        assert non_heading in blocks[0]["text"]
        assert "Content" in blocks[0]["text"]


    # Test multiline content blocks
    def test_multiline_content_block(self):
        content = "SUMMARY\nLine 1\nLine 2\nLine 3"
        parser = TextParser()
        blocks = parser._structure_content(content)
        
        assert len(blocks) == 2
        assert blocks[0]["text"] == "SUMMARY"
        assert blocks[1]["text"] == "Line 1\nLine 2\nLine 3"

    # Test file with only headings
    def test_only_headings_file(self):
        content = "SUMMARY\nCONTACT\nEDUCATION"
        parser = TextParser()
        blocks = parser._structure_content(content)
        
        assert len(blocks) == 3
        for block in blocks:
            assert block["type"] == "heading"

    # Test heading at start and end
    def test_headings_at_boundaries(self):
        content = "SUMMARY\nContent\nEDUCATION"
        parser = TextParser()
        blocks = parser._structure_content(content)
        
        assert len(blocks) == 3
        assert blocks[0]["text"] == "SUMMARY"
        assert blocks[1]["text"] == "Content"
        assert blocks[2]["text"] == "EDUCATION"