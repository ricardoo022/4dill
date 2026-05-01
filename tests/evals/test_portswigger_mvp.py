"""
Tests for PortSwigger MVP Dataset (US-045).

Validates dataset structure, integrity, and acceptance criteria:
- Exactly 4 labs in the 'quick' subset
- No duplicate lab_ids
- Summary metadata matches actual counts
- All labs have required fields including expected_backend_type
- All labs map to custom_api backend for MVP stability
"""

import json
from pathlib import Path

import pytest

DATASET_PATH = Path(__file__).parent / "datasets" / "portswigger_mvp.json"


@pytest.fixture
def mvp_dataset():
    """Load the PortSwigger MVP dataset."""
    with open(DATASET_PATH) as f:
        data = json.load(f)
    return data


class TestPortSwiggerMVPFormat:
    """Test basic dataset format and structure."""

    def test_dataset_file_exists(self):
        """Dataset file should exist at expected location."""
        assert DATASET_PATH.exists(), f"Dataset not found at {DATASET_PATH}"

    def test_dataset_json_parses(self):
        """Dataset should be valid JSON."""
        with open(DATASET_PATH) as f:
            data = json.load(f)
        assert data is not None

    def test_dataset_has_required_top_level_fields(self, mvp_dataset):
        """Dataset should have version, created, description, subsets, summary, labs."""
        required_fields = ["version", "created", "description", "subsets", "summary", "labs"]
        for field in required_fields:
            assert field in mvp_dataset, f"Missing required field: {field}"

    def test_dataset_version_is_string(self, mvp_dataset):
        """Version should be a string."""
        assert isinstance(mvp_dataset["version"], str)

    def test_dataset_has_quick_subset(self, mvp_dataset):
        """Dataset should have a 'quick' subset."""
        assert "quick" in mvp_dataset["subsets"], "Missing 'quick' subset"
        quick = mvp_dataset["subsets"]["quick"]
        assert "labs" in quick
        assert "description" in quick


class TestPortSwiggerMVPQuickSubset:
    """Test acceptance criteria for the 'quick' subset."""

    def test_quick_subset_has_exactly_four_labs(self, mvp_dataset):
        """Per US-045: quick subset must have exactly 4 labs."""
        quick_labs = mvp_dataset["subsets"]["quick"]["labs"]
        assert len(quick_labs) == 4, f"Expected 4 labs in quick subset, got {len(quick_labs)}"

    def test_quick_subset_lab_ids_valid(self, mvp_dataset):
        """All lab_ids in quick subset should reference existing labs."""
        quick_lab_ids = mvp_dataset["subsets"]["quick"]["labs"]
        all_lab_ids = [lab["lab_id"] for lab in mvp_dataset["labs"]]

        for lab_id in quick_lab_ids:
            assert lab_id in all_lab_ids, f"Lab {lab_id} in quick subset but not in labs array"

    def test_quick_subset_covers_four_categories(self, mvp_dataset):
        """Quick subset should cover 4 different vulnerability categories."""
        quick_lab_ids = mvp_dataset["subsets"]["quick"]["labs"]
        labs_by_id = {lab["lab_id"]: lab for lab in mvp_dataset["labs"]}

        categories = {labs_by_id[lab_id]["category"] for lab_id in quick_lab_ids}
        assert len(categories) == 4, f"Expected 4 categories, got {len(categories)}: {categories}"


class TestPortSwiggerMVPLabIntegrity:
    """Test lab-level integrity."""

    def test_no_duplicate_lab_ids(self, mvp_dataset):
        """All lab_ids must be unique."""
        lab_ids = [lab["lab_id"] for lab in mvp_dataset["labs"]]
        assert len(lab_ids) == len(set(lab_ids)), "Duplicate lab_ids found"

    def test_all_labs_have_required_fields(self, mvp_dataset):
        """Each lab must have all required fields."""
        required_fields = [
            "lab_id",
            "lab_url",
            "category",
            "fase_phase",
            "expected_vulnerability",
            "difficulty",
            "expected_backend_type",
        ]
        for lab in mvp_dataset["labs"]:
            for field in required_fields:
                assert field in lab, f"Lab {lab.get('lab_id', 'UNKNOWN')} missing field: {field}"

    def test_all_labs_have_custom_api_backend(self, mvp_dataset):
        """Per US-045 MVP: all labs must have expected_backend_type == 'custom_api'."""
        for lab in mvp_dataset["labs"]:
            assert (
                lab["expected_backend_type"] == "custom_api"
            ), f"Lab {lab['lab_id']} has backend_type {lab['expected_backend_type']}, expected 'custom_api'"

    def test_all_lab_urls_are_strings(self, mvp_dataset):
        """All lab_urls should be valid URL strings."""
        for lab in mvp_dataset["labs"]:
            assert isinstance(lab["lab_url"], str), f"Lab {lab['lab_id']} url not a string"
            assert lab["lab_url"].startswith("https://"), f"Lab {lab['lab_id']} url should be HTTPS"

    def test_all_labs_have_valid_difficulty(self, mvp_dataset):
        """All labs should have difficulty in [beginner, intermediate, advanced]."""
        valid_difficulties = ["beginner", "intermediate", "advanced"]
        for lab in mvp_dataset["labs"]:
            assert (
                lab["difficulty"] in valid_difficulties
            ), f"Lab {lab['lab_id']} has invalid difficulty: {lab['difficulty']}"

    def test_all_labs_have_integer_fase_phase(self, mvp_dataset):
        """All labs should have integer fase_phase."""
        for lab in mvp_dataset["labs"]:
            assert isinstance(
                lab["fase_phase"], int
            ), f"Lab {lab['lab_id']} fase_phase should be integer, got {type(lab['fase_phase'])}"
            assert (
                1 <= lab["fase_phase"] <= 21
            ), f"Lab {lab['lab_id']} fase_phase {lab['fase_phase']} out of range [1-21]"


class TestPortSwiggerMVPSummary:
    """Test summary metadata matches reality."""

    def test_summary_total_labs_quick_matches_actual(self, mvp_dataset):
        """Summary.total_labs_quick should match actual quick subset size."""
        expected = len(mvp_dataset["subsets"]["quick"]["labs"])
        actual = mvp_dataset["summary"]["total_labs_quick"]
        assert actual == expected, f"Summary says {actual} labs, actually {expected}"

    def test_summary_categories_covered_matches_actual(self, mvp_dataset):
        """Summary.categories_covered should match actual categories in quick subset."""
        quick_lab_ids = mvp_dataset["subsets"]["quick"]["labs"]
        labs_by_id = {lab["lab_id"]: lab for lab in mvp_dataset["labs"]}

        actual_categories = sorted({labs_by_id[lab_id]["category"] for lab_id in quick_lab_ids})
        expected_categories = sorted(mvp_dataset["summary"]["categories_covered"])

        assert (
            actual_categories == expected_categories
        ), f"Summary categories {expected_categories} don't match actual {actual_categories}"

    def test_summary_total_subsets_matches_actual(self, mvp_dataset):
        """Summary.total_subsets should match actual number of subsets."""
        expected = len(mvp_dataset["subsets"])
        actual = mvp_dataset["summary"]["total_subsets"]
        assert actual == expected, f"Summary says {actual} subsets, actually {expected}"

    def test_summary_backend_type_is_custom_api(self, mvp_dataset):
        """Summary.backend_type should be 'custom_api' for MVP."""
        assert mvp_dataset["summary"]["backend_type"] == "custom_api"


class TestPortSwiggerMVPContent:
    """Test specific lab content."""

    def test_has_sql_injection_lab(self, mvp_dataset):
        """MVP should include a SQL injection lab."""
        categories = [lab["category"] for lab in mvp_dataset["labs"]]
        assert "sql-injection" in categories

    def test_has_xss_lab(self, mvp_dataset):
        """MVP should include an XSS lab."""
        categories = [lab["category"] for lab in mvp_dataset["labs"]]
        assert "xss" in categories

    def test_has_authentication_lab(self, mvp_dataset):
        """MVP should include an authentication lab."""
        categories = [lab["category"] for lab in mvp_dataset["labs"]]
        assert "authentication" in categories

    def test_has_xxe_lab(self, mvp_dataset):
        """MVP should include an XXE lab."""
        categories = [lab["category"] for lab in mvp_dataset["labs"]]
        assert "xxe" in categories

    def test_sqli_lab_has_correct_id(self, mvp_dataset):
        """SQL injection lab should be sqli-login-bypass."""
        sqli_labs = [lab for lab in mvp_dataset["labs"] if lab["category"] == "sql-injection"]
        assert len(sqli_labs) == 1
        assert sqli_labs[0]["lab_id"] == "sqli-login-bypass"

    def test_xss_lab_has_correct_id(self, mvp_dataset):
        """XSS lab should be xss-reflected-html-nothing-encoded."""
        xss_labs = [lab for lab in mvp_dataset["labs"] if lab["category"] == "xss"]
        assert len(xss_labs) == 1
        assert xss_labs[0]["lab_id"] == "xss-reflected-html-nothing-encoded"

    def test_auth_lab_has_correct_id(self, mvp_dataset):
        """Authentication lab should be auth-username-enum-different-responses."""
        auth_labs = [lab for lab in mvp_dataset["labs"] if lab["category"] == "authentication"]
        assert len(auth_labs) == 1
        assert auth_labs[0]["lab_id"] == "auth-username-enum-different-responses"

    def test_xxe_lab_has_correct_id(self, mvp_dataset):
        """XXE lab should be xxe-file-upload."""
        xxe_labs = [lab for lab in mvp_dataset["labs"] if lab["category"] == "xxe"]
        assert len(xxe_labs) == 1
        assert xxe_labs[0]["lab_id"] == "xxe-file-upload"
