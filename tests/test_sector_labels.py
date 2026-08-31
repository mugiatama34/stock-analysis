import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_analysis import sector_labels


def test_known_sector_translated():
    assert sector_labels.translate_sector("Technology") == "Teknoloji"


def test_unknown_sector_returns_original_english():
    assert sector_labels.translate_sector("Something Unmapped") == "Something Unmapped"


def test_none_sector_stays_none():
    assert sector_labels.translate_sector(None) is None


def test_known_industry_translated():
    assert sector_labels.translate_industry("Semiconductors") == "Yarı İletkenler"


def test_unknown_industry_returns_original_english():
    assert sector_labels.translate_industry("Something Unmapped") == "Something Unmapped"
