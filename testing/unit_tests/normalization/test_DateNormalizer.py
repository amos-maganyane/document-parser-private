import sys
import os
import pytest
from unittest.mock import patch
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from normalization.date_normalizer import DateNormalizer

@pytest.fixture
def normalizer():
    return DateNormalizer()


def test_empty_input(normalizer):
    assert normalizer.normalize("") is None
    assert normalizer.normalize(None) is None


@pytest.mark.parametrize("input_date, expected", [
    ("2023-12-31", "2023-12-31"),
    ("January 15, 2020", "2020-01-15"),
    ("15-Jan-2023", "2023-01-15"),
    ("02/28/2022", "2022-02-28"),
    ("2024-07-04T12:00:00Z", "2024-07-04"),
    ("next thursday", None),
])
def test_dateparser_success(normalizer, input_date, expected):
    with patch('dateparser.parse') as mock_parse:
        if expected:
            y, m, d = map(int, expected.split('-'))
            mock_date = datetime(y, m, d)
            mock_parse.return_value = mock_date
            assert normalizer.normalize(input_date) == expected
        else:
            mock_parse.return_value = None
            assert normalizer.normalize(input_date) is None


@pytest.mark.parametrize("input_date, expected", [
    ("Sep 2020", "2020-09-01"),
    ("DECEMBER 2025", "2025-12-01"),
    ("September 2023", "2023-09-01"),
    ("9/2021", "2021-09-01"),
    ("05/2022", "2022-05-01"),
    ("5-2022", "2022-05-01"),
    ("2024", "2024-01-01"),
    ("May2023", "2023-05-01"),
    ("In 1999", "1999-01-01"),
    ("Until 2005", "2005-01-01"),
    ("Apr-2025", "2025-04-01"),
])
def test_fallback_patterns(normalizer, input_date, expected):
    with patch('dateparser.parse', return_value=None):
        assert normalizer.normalize(input_date) == expected


@pytest.mark.parametrize("input_date", [
    "Random text",
    "32/13/2020",
    "Feb 30",
    "202",
    "Present",
    "Current",
    "Q1 2023",
    "13/2022",
    "Feb 29 2021",
])
def test_invalid_dates(normalizer, input_date):
    with patch('dateparser.parse', return_value=None):
        assert normalizer.normalize(input_date) is None


@pytest.mark.parametrize("month_input, expected_month", [
    ("jan", "01"), ("JANUARY", "01"), ("Jan", "01"),
    ("feb", "02"), ("Feb", "02"), 
    ("mar", "03"), ("march", "03"),
    ("apr", "04"), ("ApR", "04"),
    ("may", "05"), 
    ("jun", "06"), ("june", "06"),
    ("jul", "07"), ("july", "07"),
    ("aug", "08"), ("august", "08"),
    ("sep", "09"), ("sept", "09"), ("September", "09"),
    ("oct", "10"), ("October", "10"),
    ("nov", "11"), ("November", "11"),
    ("dec", "12"), ("December", "12"),
    ("invalid", "01"),
])
def test_month_mapping(normalizer, month_input, expected_month):
    with patch('dateparser.parse', return_value=None):
        result = normalizer.normalize(f"{month_input} 2023")
        assert result == f"2023-{expected_month}-01"



def test_fallback_priority(normalizer):
    with patch('dateparser.parse', return_value=None):
        assert normalizer.normalize("Oct 2025") == "2025-10-01"
        assert normalizer.normalize("10/2025") == "2025-10-01"
        assert normalizer.normalize("2025") == "2025-01-01"


def test_real_dateparser_integration(normalizer):
    assert normalizer.normalize("2023-12-31") == "2023-12-31"
    assert normalizer.normalize("15 January 2020") == "2020-01-15"
    assert normalizer.normalize("Feb 29 2020") == "2020-02-29"
    assert normalizer.normalize("Feb 29 2021") is None