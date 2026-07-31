"""
Unit tests for src/scripts/detect_duplicates.py
"""

import json

import src.scripts.detect_duplicates as detect_duplicates


class TestLoadIcebergRows:
    def test_builds_select_query_with_needed_fields(self, mocker):
        mock_spark = mocker.Mock()
        mock_df = mocker.Mock()
        mock_df.collect.return_value = []
        mock_spark.sql.return_value = mock_df
        mocker.patch(
            "src.scripts.detect_duplicates.get_spark",
            return_value=mock_spark,
        )

        detect_duplicates.load_iceberg_rows()

        expected_columns = ", ".join(detect_duplicates.FIELDS_NEEDED)
        mock_spark.sql.assert_called_once_with(f"SELECT {expected_columns} FROM local.booking.rental_property")

    def test_uses_named_spark_session(self, mocker):
        mock_get_spark = mocker.patch(
            "src.scripts.detect_duplicates.get_spark",
            return_value=mocker.Mock(sql=mocker.Mock(return_value=mocker.Mock(collect=lambda: []))),
        )

        detect_duplicates.load_iceberg_rows()

        mock_get_spark.assert_called_once_with("detect-duplicates")

    def test_converts_rows_to_dicts(self, mocker):
        mock_spark = mocker.Mock()
        mock_row_1 = mocker.Mock()
        mock_row_1.asDict.return_value = {"external_id": "BC-1"}
        mock_row_2 = mocker.Mock()
        mock_row_2.asDict.return_value = {"external_id": "BC-2"}
        mock_df = mocker.Mock()
        mock_df.collect.return_value = [mock_row_1, mock_row_2]
        mock_spark.sql.return_value = mock_df
        mocker.patch(
            "src.scripts.detect_duplicates.get_spark",
            return_value=mock_spark,
        )

        result = detect_duplicates.load_iceberg_rows()

        assert result == [{"external_id": "BC-1"}, {"external_id": "BC-2"}]

    def test_returns_empty_list_when_no_rows(self, mocker):
        mock_spark = mocker.Mock()
        mock_df = mocker.Mock()
        mock_df.collect.return_value = []
        mock_spark.sql.return_value = mock_df
        mocker.patch(
            "src.scripts.detect_duplicates.get_spark",
            return_value=mock_spark,
        )

        result = detect_duplicates.load_iceberg_rows()

        assert result == []


class TestLoadPartnerRows:
    def test_loads_flat_list(self, mocker):
        mock_path_instance = mocker.Mock()
        mock_path_instance.read_text.return_value = json.dumps([{"external_id": "V-1"}, {"external_id": "V-2"}])
        mocker.patch(
            "src.scripts.detect_duplicates.Path",
            return_value=mock_path_instance,
        )

        result = detect_duplicates.load_partner_rows("some/path.json")

        assert result == [{"external_id": "V-1"}, {"external_id": "V-2"}]

    def test_loads_properties_wrapper(self, mocker):
        mock_path_instance = mocker.Mock()
        mock_path_instance.read_text.return_value = json.dumps({"properties": [{"external_id": "V-1"}]})
        mocker.patch(
            "src.scripts.detect_duplicates.Path",
            return_value=mock_path_instance,
        )

        result = detect_duplicates.load_partner_rows("some/path.json")

        assert result == [{"external_id": "V-1"}]

    def test_loads_data_wrapper(self, mocker):
        mock_path_instance = mocker.Mock()
        mock_path_instance.read_text.return_value = json.dumps({"data": [{"external_id": "V-1"}]})
        mocker.patch(
            "src.scripts.detect_duplicates.Path",
            return_value=mock_path_instance,
        )

        result = detect_duplicates.load_partner_rows("some/path.json")

        assert result == [{"external_id": "V-1"}]

    def test_returns_empty_list_when_neither_wrapper_key_present(self, mocker):
        mock_path_instance = mocker.Mock()
        mock_path_instance.read_text.return_value = json.dumps({"other": []})
        mocker.patch(
            "src.scripts.detect_duplicates.Path",
            return_value=mock_path_instance,
        )

        result = detect_duplicates.load_partner_rows("some/path.json")

        assert result == []

    def test_prefers_properties_key_over_data_key(self, mocker):
        mock_path_instance = mocker.Mock()
        mock_path_instance.read_text.return_value = json.dumps({"properties": [{"external_id": "P-1"}], "data": [{"external_id": "D-1"}]})
        mocker.patch(
            "src.scripts.detect_duplicates.Path",
            return_value=mock_path_instance,
        )

        result = detect_duplicates.load_partner_rows("some/path.json")

        assert result == [{"external_id": "P-1"}]

    def test_constructs_path_from_given_string(self, mocker):
        mock_path_instance = mocker.Mock()
        mock_path_instance.read_text.return_value = json.dumps([])
        mock_path_cls = mocker.patch(
            "src.scripts.detect_duplicates.Path",
            return_value=mock_path_instance,
        )

        detect_duplicates.load_partner_rows("custom/path.json")

        mock_path_cls.assert_called_once_with("custom/path.json")


class TestMain:
    def test_uses_default_path_when_no_arg_given(self, mocker, capsys):
        mocker.patch("sys.argv", ["detect_duplicates.py"])
        mocker.patch(
            "src.scripts.detect_duplicates.load_iceberg_rows",
            return_value=[],
        )
        mock_load_partner_rows = mocker.patch(
            "src.scripts.detect_duplicates.load_partner_rows",
            return_value=[],
        )
        mocker.patch(
            "src.scripts.detect_duplicates.find_duplicates",
            return_value=[],
        )

        detect_duplicates.main()

        mock_load_partner_rows.assert_called_once_with(detect_duplicates.DEFAULT_MOCK_PATH)

    def test_uses_given_path_arg(self, mocker):
        mocker.patch("sys.argv", ["detect_duplicates.py", "custom/mock.json"])
        mocker.patch(
            "src.scripts.detect_duplicates.load_iceberg_rows",
            return_value=[],
        )
        mock_load_partner_rows = mocker.patch(
            "src.scripts.detect_duplicates.load_partner_rows",
            return_value=[],
        )
        mocker.patch(
            "src.scripts.detect_duplicates.find_duplicates",
            return_value=[],
        )

        detect_duplicates.main()

        mock_load_partner_rows.assert_called_once_with("custom/mock.json")

    def test_calls_find_duplicates_with_loaded_rows(self, mocker):
        mocker.patch("sys.argv", ["detect_duplicates.py"])
        source_rows = [{"external_id": "BC-1"}]
        candidate_rows = [{"external_id": "V-1"}]
        mocker.patch(
            "src.scripts.detect_duplicates.load_iceberg_rows",
            return_value=source_rows,
        )
        mocker.patch(
            "src.scripts.detect_duplicates.load_partner_rows",
            return_value=candidate_rows,
        )
        mock_find_duplicates = mocker.patch(
            "src.scripts.detect_duplicates.find_duplicates",
            return_value=[],
        )

        detect_duplicates.main()

        mock_find_duplicates.assert_called_once_with(source_rows, candidate_rows)

    def test_prints_match_count_and_details(self, mocker, capsys):
        mocker.patch("sys.argv", ["detect_duplicates.py"])
        mocker.patch(
            "src.scripts.detect_duplicates.load_iceberg_rows",
            return_value=[{"external_id": "BC-1"}],
        )
        mocker.patch(
            "src.scripts.detect_duplicates.load_partner_rows",
            return_value=[{"external_id": "V-1"}],
        )
        mocker.patch(
            "src.scripts.detect_duplicates.find_duplicates",
            return_value=[
                {
                    "source_id": "BC-1",
                    "candidate_id": "V-1",
                    "distance_m": 12.5,
                    "scores": {"overall_score": 0.91},
                }
            ],
        )

        detect_duplicates.main()

        captured = capsys.readouterr()
        assert "Found 1 likely duplicate(s)" in captured.out
        assert "BC-1" in captured.out
        assert "V-1" in captured.out
        assert "0.91" in captured.out
        assert "12.5" in captured.out

    def test_prints_zero_duplicates_when_no_matches(self, mocker, capsys):
        mocker.patch("sys.argv", ["detect_duplicates.py"])
        mocker.patch(
            "src.scripts.detect_duplicates.load_iceberg_rows",
            return_value=[],
        )
        mocker.patch(
            "src.scripts.detect_duplicates.load_partner_rows",
            return_value=[],
        )
        mocker.patch(
            "src.scripts.detect_duplicates.find_duplicates",
            return_value=[],
        )

        detect_duplicates.main()

        captured = capsys.readouterr()
        assert "Found 0 likely duplicate(s)" in captured.out

    def test_prints_progress_messages_with_counts(self, mocker, capsys):
        mocker.patch("sys.argv", ["detect_duplicates.py"])
        mocker.patch(
            "src.scripts.detect_duplicates.load_iceberg_rows",
            return_value=[{"external_id": "BC-1"}, {"external_id": "BC-2"}],
        )
        mocker.patch(
            "src.scripts.detect_duplicates.load_partner_rows",
            return_value=[{"external_id": "V-1"}],
        )
        mocker.patch(
            "src.scripts.detect_duplicates.find_duplicates",
            return_value=[],
        )

        detect_duplicates.main()

        captured = capsys.readouterr()
        assert "2 properties loaded" in captured.out
        assert "1 properties loaded" in captured.out
