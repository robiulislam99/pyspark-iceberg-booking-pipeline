"""
Unit tests for src/core/duplicate_detector.py
"""

import pytest
import src.core.duplicate_detector as duplicate_detector


class TestParseLatlon:
    def test_parses_wkt_point_string(self):
        result = duplicate_detector.parse_latlon("SRID=4326;POINT (-97.085391 27.797983)")

        assert result == (27.797983, -97.085391)

    def test_parses_plain_point_string(self):
        result = duplicate_detector.parse_latlon("POINT(-97.085391 27.797983)")

        assert result == (27.797983, -97.085391)

    def test_returns_none_for_unrecognized_string(self):
        result = duplicate_detector.parse_latlon("not a point")

        assert result is None

    def test_parses_lat_lon_dict(self):
        result = duplicate_detector.parse_latlon({"lat": 27.79, "lon": -97.08})

        assert result == (27.79, -97.08)

    def test_parses_latitude_longitude_dict(self):
        result = duplicate_detector.parse_latlon({"latitude": 27.79, "longitude": -97.08})

        assert result == (27.79, -97.08)

    def test_parses_geojson_coordinates_dict(self):
        result = duplicate_detector.parse_latlon({"coordinates": [-97.08, 27.79]})

        assert result == (27.79, -97.08)

    def test_returns_none_for_none_input(self):
        result = duplicate_detector.parse_latlon(None)

        assert result is None

    def test_returns_none_for_unrecognized_dict_shape(self):
        result = duplicate_detector.parse_latlon({"foo": "bar"})

        assert result is None

    def test_returns_none_for_unrecognized_type(self):
        result = duplicate_detector.parse_latlon(12345)

        assert result is None


class TestHaversineDistanceMeters:
    def test_zero_distance_for_identical_points(self):
        result = duplicate_detector.haversine_distance_meters(27.797983, -97.085391, 27.797983, -97.085391)

        assert result == pytest.approx(0.0, abs=1e-6)

    def test_known_distance_between_two_points(self):
        # Roughly 1 degree of latitude apart, ~111km
        result = duplicate_detector.haversine_distance_meters(0.0, 0.0, 1.0, 0.0)

        assert result == pytest.approx(111195, rel=0.01)

    def test_distance_is_symmetric(self):
        d1 = duplicate_detector.haversine_distance_meters(27.79, -97.08, 27.80, -97.09)
        d2 = duplicate_detector.haversine_distance_meters(27.80, -97.09, 27.79, -97.08)

        assert d1 == pytest.approx(d2)


class TestCosineSimilarity:
    def test_identical_vectors_score_one(self):
        result = duplicate_detector._cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])

        assert result == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        result = duplicate_detector._cosine_similarity([1.0, 0.0], [0.0, 1.0])

        assert result == pytest.approx(0.0)

    def test_opposite_vectors_score_negative_one(self):
        result = duplicate_detector._cosine_similarity([1.0, 0.0], [-1.0, 0.0])

        assert result == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        result = duplicate_detector._cosine_similarity([0.0, 0.0], [1.0, 1.0])

        assert result == 0.0


class TestTextSimilarity:
    def test_returns_zero_when_text_a_empty(self, mocker):
        mock_generate = mocker.patch("src.core.duplicate_detector.generate_embedding")

        result = duplicate_detector.text_similarity("", "some text")

        assert result == 0.0
        mock_generate.assert_not_called()

    def test_returns_zero_when_text_b_none(self, mocker):
        mock_generate = mocker.patch("src.core.duplicate_detector.generate_embedding")

        result = duplicate_detector.text_similarity("some text", None)

        assert result == 0.0
        mock_generate.assert_not_called()

    def test_computes_cosine_similarity_of_embeddings(self, mocker):
        mocker.patch(
            "src.core.duplicate_detector.generate_embedding",
            side_effect=[[1.0, 0.0], [1.0, 0.0]],
        )

        result = duplicate_detector.text_similarity("Villa Palmilla", "Villa Palmilla")

        assert result == pytest.approx(1.0)

    def test_calls_generate_embedding_for_each_text(self, mocker):
        mock_generate = mocker.patch(
            "src.core.duplicate_detector.generate_embedding",
            side_effect=[[1.0, 0.0], [0.0, 1.0]],
        )

        duplicate_detector.text_similarity("text a", "text b")

        assert mock_generate.call_args_list[0].args[0] == "text a"
        assert mock_generate.call_args_list[1].args[0] == "text b"


class TestNumericMatch:
    def test_returns_one_when_equal(self):
        assert duplicate_detector._numeric_match(3, 3) == 1.0

    def test_returns_zero_when_different(self):
        assert duplicate_detector._numeric_match(3, 4) == 0.0

    def test_returns_zero_when_a_none(self):
        assert duplicate_detector._numeric_match(None, 3) == 0.0

    def test_returns_zero_when_b_none(self):
        assert duplicate_detector._numeric_match(3, None) == 0.0

    def test_returns_zero_when_both_none(self):
        assert duplicate_detector._numeric_match(None, None) == 0.0


class TestCategoricalMatch:
    def test_returns_one_for_exact_match(self):
        assert duplicate_detector._categorical_match("Villa", "Villa") == 1.0

    def test_case_insensitive_match(self):
        assert duplicate_detector._categorical_match("Villa", "VILLA") == 1.0

    def test_strips_whitespace(self):
        assert duplicate_detector._categorical_match(" Villa ", "Villa") == 1.0

    def test_returns_zero_for_mismatch(self):
        assert duplicate_detector._categorical_match("Villa", "Cabin") == 0.0

    def test_returns_zero_when_a_empty(self):
        assert duplicate_detector._categorical_match("", "Villa") == 0.0

    def test_returns_zero_when_b_none(self):
        assert duplicate_detector._categorical_match("Villa", None) == 0.0


class TestCompareProperties:
    def test_returns_all_expected_score_keys(self, mocker):
        mocker.patch(
            "src.core.duplicate_detector.generate_embedding",
            return_value=[1.0, 0.0],
        )
        source = {
            "property_name": "Villa Palmilla",
            "location_display": "Port Aransas, TX",
            "property_description": "A lovely villa",
            "other_policy": "No smoking",
            "property_type": "Villa",
            "bedroom_count": 4,
            "bathroom_count": 3,
        }
        candidate = dict(source)

        result = duplicate_detector.compare_properties(source, candidate)

        expected_keys = {
            "property_name",
            "location_display",
            "property_description",
            "other_policy",
            "property_type",
            "bedroom_count",
            "bathroom_count",
            "overall_score",
        }
        assert set(result.keys()) == expected_keys

    def test_identical_properties_score_close_to_one(self, mocker):
        mocker.patch(
            "src.core.duplicate_detector.generate_embedding",
            return_value=[1.0, 0.0],
        )
        source = {
            "property_name": "Villa Palmilla",
            "location_display": "Port Aransas, TX",
            "property_description": "A lovely villa",
            "other_policy": "No smoking",
            "property_type": "Villa",
            "bedroom_count": 4,
            "bathroom_count": 3,
        }
        candidate = dict(source)

        result = duplicate_detector.compare_properties(source, candidate)

        assert result["overall_score"] == pytest.approx(1.0, abs=1e-4)

    def test_completely_different_properties_score_zero(self, mocker):
        mocker.patch(
            "src.core.duplicate_detector.generate_embedding",
            side_effect=lambda text: [1.0, 0.0] if text and "A" in text else [0.0, 1.0],
        )
        source = {
            "property_name": "A Villa",
            "location_display": "A Place",
            "property_description": "A description",
            "other_policy": "A policy",
            "property_type": "A type",
            "bedroom_count": 4,
            "bathroom_count": 3,
        }
        candidate = {
            "property_name": "Z Cabin",
            "location_display": "Z Place",
            "property_description": "Z description",
            "other_policy": "Z policy",
            "property_type": "Z type",
            "bedroom_count": 1,
            "bathroom_count": 1,
        }

        result = duplicate_detector.compare_properties(source, candidate)

        assert result["overall_score"] == pytest.approx(0.0, abs=1e-4)

    def test_overall_score_is_rounded_to_4_decimals(self, mocker):
        mocker.patch(
            "src.core.duplicate_detector.generate_embedding",
            return_value=[1.0, 0.0],
        )
        source = {
            "property_name": "Villa",
            "location_display": "Place",
            "property_description": "Desc",
            "other_policy": "Policy",
            "property_type": "Villa",
            "bedroom_count": 4,
            "bathroom_count": 3,
        }
        candidate = dict(source)

        result = duplicate_detector.compare_properties(source, candidate)

        assert result["overall_score"] == round(result["overall_score"], 4)

    def test_handles_missing_fields_gracefully(self, mocker):
        mocker.patch(
            "src.core.duplicate_detector.generate_embedding",
            return_value=[1.0, 0.0],
        )
        source = {"property_name": "Villa"}
        candidate = {}

        result = duplicate_detector.compare_properties(source, candidate)

        assert result["bedroom_count"] == 0.0
        assert result["bathroom_count"] == 0.0
        assert result["overall_score"] >= 0.0


class TestFindDuplicates:
    def test_returns_empty_list_when_no_source_rows(self, mocker):
        result = duplicate_detector.find_duplicates([], [{"latlon": "POINT (-97.08 27.79)"}])

        assert result == []

    def test_returns_empty_list_when_no_candidate_rows(self, mocker):
        result = duplicate_detector.find_duplicates([{"latlon": "POINT (-97.08 27.79)"}], [])

        assert result == []

    def test_skips_source_rows_with_unparseable_latlon(self, mocker):
        mock_compare = mocker.patch("src.core.duplicate_detector.compare_properties")
        source_rows = [{"latlon": None, "external_id": "BC-1"}]
        candidate_rows = [{"latlon": "POINT (-97.08 27.79)", "external_id": "V-1"}]

        result = duplicate_detector.find_duplicates(source_rows, candidate_rows)

        assert result == []
        mock_compare.assert_not_called()

    def test_skips_candidate_rows_with_unparseable_latlon(self, mocker):
        mock_compare = mocker.patch("src.core.duplicate_detector.compare_properties")
        source_rows = [{"latlon": "POINT (-97.08 27.79)", "external_id": "BC-1"}]
        candidate_rows = [{"latlon": None, "external_id": "V-1"}]

        result = duplicate_detector.find_duplicates(source_rows, candidate_rows)

        assert result == []
        mock_compare.assert_not_called()

    def test_skips_pairs_beyond_distance_threshold(self, mocker):
        mock_compare = mocker.patch("src.core.duplicate_detector.compare_properties")
        source_rows = [{"latlon": "POINT (0 0)", "external_id": "BC-1"}]
        candidate_rows = [{"latlon": "POINT (0 1)", "external_id": "V-1"}]  # ~111km away

        result = duplicate_detector.find_duplicates(source_rows, candidate_rows, distance_threshold_m=100)

        assert result == []
        mock_compare.assert_not_called()

    def test_includes_pairs_within_distance_and_above_score_threshold(self, mocker):
        mocker.patch(
            "src.core.duplicate_detector.compare_properties",
            return_value={"overall_score": 0.9},
        )
        source_rows = [{"latlon": "POINT (-97.085391 27.797983)", "external_id": "BC-1"}]
        candidate_rows = [{"latlon": "POINT (-97.085391 27.797983)", "external_id": "V-1"}]

        result = duplicate_detector.find_duplicates(source_rows, candidate_rows, distance_threshold_m=100, score_threshold=0.75)

        assert len(result) == 1
        assert result[0]["source_id"] == "BC-1"
        assert result[0]["candidate_id"] == "V-1"
        assert result[0]["distance_m"] == 0.0
        assert result[0]["scores"] == {"overall_score": 0.9}

    def test_excludes_pairs_below_score_threshold(self, mocker):
        mocker.patch(
            "src.core.duplicate_detector.compare_properties",
            return_value={"overall_score": 0.5},
        )
        source_rows = [{"latlon": "POINT (-97.085391 27.797983)", "external_id": "BC-1"}]
        candidate_rows = [{"latlon": "POINT (-97.085391 27.797983)", "external_id": "V-1"}]

        result = duplicate_detector.find_duplicates(source_rows, candidate_rows, distance_threshold_m=100, score_threshold=0.75)

        assert result == []

    def test_falls_back_to_id_field_when_external_id_missing(self, mocker):
        mocker.patch(
            "src.core.duplicate_detector.compare_properties",
            return_value={"overall_score": 0.9},
        )
        source_rows = [{"latlon": "POINT (-97.085391 27.797983)", "id": "BC-fallback"}]
        candidate_rows = [{"latlon": "POINT (-97.085391 27.797983)", "id": "V-fallback"}]

        result = duplicate_detector.find_duplicates(source_rows, candidate_rows)

        assert result[0]["source_id"] == "BC-fallback"
        assert result[0]["candidate_id"] == "V-fallback"

    def test_results_sorted_best_match_first(self, mocker):
        mocker.patch(
            "src.core.duplicate_detector.compare_properties",
            side_effect=[
                {"overall_score": 0.80},
                {"overall_score": 0.95},
            ],
        )
        source_rows = [{"latlon": "POINT (-97.085391 27.797983)", "external_id": "BC-1"}]
        candidate_rows = [
            {"latlon": "POINT (-97.085391 27.797983)", "external_id": "V-1"},
            {"latlon": "POINT (-97.085391 27.797983)", "external_id": "V-2"},
        ]

        result = duplicate_detector.find_duplicates(source_rows, candidate_rows, score_threshold=0.0)

        assert [m["candidate_id"] for m in result] == ["V-2", "V-1"]

    def test_compares_every_source_against_every_candidate_within_range(self, mocker):
        mock_compare = mocker.patch(
            "src.core.duplicate_detector.compare_properties",
            return_value={"overall_score": 0.9},
        )
        source_rows = [
            {"latlon": "POINT (-97.085391 27.797983)", "external_id": "BC-1"},
            {"latlon": "POINT (-97.085391 27.797983)", "external_id": "BC-2"},
        ]
        candidate_rows = [
            {"latlon": "POINT (-97.085391 27.797983)", "external_id": "V-1"},
        ]

        duplicate_detector.find_duplicates(source_rows, candidate_rows)

        assert mock_compare.call_count == 2

    def test_default_thresholds_are_used_when_not_specified(self, mocker):
        mocker.patch(
            "src.core.duplicate_detector.compare_properties",
            return_value={"overall_score": 0.9},
        )
        source_rows = [{"latlon": "POINT (-97.085391 27.797983)", "external_id": "BC-1"}]
        candidate_rows = [{"latlon": "POINT (-97.085391 27.797983)", "external_id": "V-1"}]

        result = duplicate_detector.find_duplicates(source_rows, candidate_rows)

        assert len(result) == 1
