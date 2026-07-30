"""
Unit tests for src/scripts/export_to_qdrant.py
"""

import json

import pytest
import src.scripts.export_to_qdrant as export_to_qdrant


class FakeFile:
    """Minimal stand-in for a pathlib.Path file, sortable by name so it
    works with the module's sorted(files) call."""

    def __init__(self, name: str, content: str):
        self.name = name
        self._content = content

    def read_text(self):
        return self._content

    def __lt__(self, other):
        return self.name < other.name

    def __repr__(self):
        return f"FakeFile({self.name!r})"


class TestExportDate:
    def test_prints_message_when_export_dir_missing(self, mocker, capsys):
        mock_path_instance = mocker.MagicMock()
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = False
        mocker.patch(
            "src.scripts.export_to_qdrant.Path",
            return_value=mock_path_instance,
        )

        export_to_qdrant.export_date("20260714")

        captured = capsys.readouterr()
        assert "No S3 export found for date=20260714" in captured.out

    def test_prints_message_when_no_json_files_found(self, mocker, capsys):
        mock_path_instance = mocker.MagicMock()
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = True
        mock_path_instance.glob.return_value = []
        mocker.patch(
            "src.scripts.export_to_qdrant.Path",
            return_value=mock_path_instance,
        )

        export_to_qdrant.export_date("20260714")

        captured = capsys.readouterr()
        assert "No documents found" in captured.out

    def test_prints_message_when_no_embeddable_documents(self, mocker, capsys):
        mock_path_instance = mocker.MagicMock()
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = True

        fake_file = FakeFile("prop1.json", json.dumps({"ID": "BC-1", "Property": {}}))
        mock_path_instance.glob.return_value = [fake_file]

        mocker.patch(
            "src.scripts.export_to_qdrant.Path",
            return_value=mock_path_instance,
        )
        mocker.patch(
            "src.scripts.export_to_qdrant.to_qdrant_point",
            return_value=None,
        )
        mock_bulk_upsert = mocker.patch("src.scripts.export_to_qdrant.bulk_upsert")

        export_to_qdrant.export_date("20260714")

        captured = capsys.readouterr()
        assert "No embeddable documents found for date=20260714" in captured.out
        mock_bulk_upsert.assert_not_called()

    def test_upserts_all_valid_points_in_single_batch(self, mocker, capsys):
        mock_path_instance = mocker.MagicMock()
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = True

        fake_file_1 = FakeFile("prop1.json", json.dumps({"ID": "BC-1"}))
        fake_file_2 = FakeFile("prop2.json", json.dumps({"ID": "BC-2"}))
        mock_path_instance.glob.return_value = [fake_file_1, fake_file_2]

        mocker.patch(
            "src.scripts.export_to_qdrant.Path",
            return_value=mock_path_instance,
        )

        fake_point_1 = mocker.Mock()
        fake_point_2 = mocker.Mock()
        mocker.patch(
            "src.scripts.export_to_qdrant.to_qdrant_point",
            side_effect=[fake_point_1, fake_point_2],
        )
        mock_bulk_upsert = mocker.patch("src.scripts.export_to_qdrant.bulk_upsert")

        export_to_qdrant.export_date("20260714")

        mock_bulk_upsert.assert_called_once_with([fake_point_1, fake_point_2])
        captured = capsys.readouterr()
        assert "Upserted 2 point(s) into Qdrant (skipped 0) for date=20260714" in captured.out

    def test_skips_documents_that_map_to_none(self, mocker, capsys):
        mock_path_instance = mocker.MagicMock()
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = True

        fake_file_1 = FakeFile("prop1.json", json.dumps({"ID": "BC-1"}))
        fake_file_2 = FakeFile("prop2.json", json.dumps({"ID": None}))
        mock_path_instance.glob.return_value = [fake_file_1, fake_file_2]

        mocker.patch(
            "src.scripts.export_to_qdrant.Path",
            return_value=mock_path_instance,
        )

        fake_point = mocker.Mock()
        mocker.patch(
            "src.scripts.export_to_qdrant.to_qdrant_point",
            side_effect=[fake_point, None],
        )
        mock_bulk_upsert = mocker.patch("src.scripts.export_to_qdrant.bulk_upsert")

        export_to_qdrant.export_date("20260714")

        mock_bulk_upsert.assert_called_once_with([fake_point])
        captured = capsys.readouterr()
        assert "Upserted 1 point(s) into Qdrant (skipped 1) for date=20260714" in captured.out

    def test_batches_points_according_to_batch_size(self, mocker):
        mock_path_instance = mocker.MagicMock()
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = True

        num_files = export_to_qdrant.BATCH_SIZE + 10
        fake_files = [FakeFile(f"prop{i:05d}.json", json.dumps({"ID": f"BC-{i}"})) for i in range(num_files)]
        mock_path_instance.glob.return_value = fake_files

        mocker.patch(
            "src.scripts.export_to_qdrant.Path",
            return_value=mock_path_instance,
        )

        fake_points = [mocker.Mock() for _ in range(num_files)]
        mocker.patch(
            "src.scripts.export_to_qdrant.to_qdrant_point",
            side_effect=fake_points,
        )
        mock_bulk_upsert = mocker.patch("src.scripts.export_to_qdrant.bulk_upsert")

        export_to_qdrant.export_date("20260714")

        assert mock_bulk_upsert.call_count == 2
        first_batch = mock_bulk_upsert.call_args_list[0].args[0]
        second_batch = mock_bulk_upsert.call_args_list[1].args[0]
        assert len(first_batch) == export_to_qdrant.BATCH_SIZE
        assert len(second_batch) == 10

    def test_reads_files_from_correct_directory(self, mocker):
        mock_path_instance = mocker.MagicMock()
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = False
        mock_path_cls = mocker.patch(
            "src.scripts.export_to_qdrant.Path",
            return_value=mock_path_instance,
        )

        export_to_qdrant.export_date("20260714")

        mock_path_cls.assert_called_once_with(export_to_qdrant.S3_LOCAL_ROOT)

    def test_glob_pattern_targets_json_files(self, mocker):
        mock_path_instance = mocker.MagicMock()
        mock_path_instance.__truediv__.return_value = mock_path_instance
        mock_path_instance.exists.return_value = True
        mock_path_instance.glob.return_value = []
        mocker.patch(
            "src.scripts.export_to_qdrant.Path",
            return_value=mock_path_instance,
        )

        export_to_qdrant.export_date("20260714")

        mock_path_instance.glob.assert_called_once_with("*.json")


class TestMainEntrypoint:
    def test_exits_with_usage_message_when_no_date_arg(self, mocker, capsys):
        mocker.patch("sys.argv", ["export_to_qdrant.py"])
        mock_export_date = mocker.patch("src.scripts.export_to_qdrant.export_date")

        with pytest.raises(SystemExit) as exc_info:
            if len(["export_to_qdrant.py"]) != 2:
                print("Usage: python export_to_qdrant.py <YYYYMMDD>")
                raise SystemExit(1)

        assert exc_info.value.code == 1
        mock_export_date.assert_not_called()

    def test_exits_with_usage_message_when_too_many_args(self, mocker, capsys):
        mocker.patch("sys.argv", ["export_to_qdrant.py", "20260714", "extra"])
        mock_export_date = mocker.patch("src.scripts.export_to_qdrant.export_date")

        with pytest.raises(SystemExit) as exc_info:
            if len(["export_to_qdrant.py", "20260714", "extra"]) != 2:
                print("Usage: python export_to_qdrant.py <YYYYMMDD>")
                raise SystemExit(1)

        assert exc_info.value.code == 1
        mock_export_date.assert_not_called()
