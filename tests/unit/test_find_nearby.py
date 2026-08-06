"""
Unit tests for scripts/find_nearby.py
"""

import sys
from unittest.mock import patch

import pytest

from scripts import find_nearby


class TestMain:
    @patch("scripts.find_nearby.get_nearby_properties_for_id")
    def test_no_args_prints_usage_and_exits(self, mock_get_nearby, capsys):
        with patch.object(sys, "argv", ["find_nearby.py"]), pytest.raises(SystemExit) as exc_info:
            find_nearby.main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage: python find_nearby.py" in captured.out
        mock_get_nearby.assert_not_called()

    @patch("scripts.find_nearby.get_nearby_properties_for_id")
    def test_default_radius_and_limit(self, mock_get_nearby, capsys):
        mock_get_nearby.return_value = []

        with patch.object(sys, "argv", ["find_nearby.py", "BC-10178627"]):
            find_nearby.main()

        mock_get_nearby.assert_called_once_with("BC-10178627", radius_km=5, limit=20)

    @patch("scripts.find_nearby.get_nearby_properties_for_id")
    def test_custom_radius(self, mock_get_nearby, capsys):
        mock_get_nearby.return_value = []

        with patch.object(sys, "argv", ["find_nearby.py", "BC-10178627", "10"]):
            find_nearby.main()

        mock_get_nearby.assert_called_once_with("BC-10178627", radius_km=10.0, limit=20)

    @patch("scripts.find_nearby.get_nearby_properties_for_id")
    def test_custom_radius_and_limit(self, mock_get_nearby, capsys):
        mock_get_nearby.return_value = []

        with patch.object(sys, "argv", ["find_nearby.py", "BC-10178627", "10", "15"]):
            find_nearby.main()

        mock_get_nearby.assert_called_once_with("BC-10178627", radius_km=10.0, limit=15)

    @patch("scripts.find_nearby.get_nearby_properties_for_id")
    def test_empty_results_prints_not_found_message(self, mock_get_nearby, capsys):
        mock_get_nearby.return_value = []

        with patch.object(sys, "argv", ["find_nearby.py", "BC-99999999"]):
            find_nearby.main()

        captured = capsys.readouterr()
        assert "No nearby properties found for BC-99999999" in captured.out
        assert "within 5" in captured.out

    @patch("scripts.find_nearby.get_nearby_properties_for_id")
    def test_prints_formatted_results(self, mock_get_nearby, capsys):
        mock_get_nearby.return_value = [
            {
                "id": "p1",
                "property_name": "Sea View Villa",
                "city": "Lisbon",
                "country": "Portugal",
                "usd_price": 200,
                "star_rating": 4.5,
                "distance_km": 1.234,
            },
            {
                "id": "p2",
                "property_name": "City Loft",
                "city": "Porto",
                "country": "Portugal",
                "usd_price": 150,
                "star_rating": 4.0,
                "distance_km": 3.5,
            },
        ]

        with patch.object(sys, "argv", ["find_nearby.py", "BC-10178627"]):
            find_nearby.main()

        captured = capsys.readouterr()
        assert "Properties within 5km of BC-10178627:" in captured.out
        assert "Sea View Villa" in captured.out
        assert "Lisbon, Portugal" in captured.out
        assert "$200" in captured.out
        assert "1.23 km" in captured.out
        assert "City Loft" in captured.out
        assert "3.50 km" in captured.out

    @patch("scripts.find_nearby.get_nearby_properties_for_id")
    def test_radius_and_limit_type_conversion(self, mock_get_nearby, capsys):
        """radius_km must become float, limit must become int."""
        mock_get_nearby.return_value = []

        with patch.object(sys, "argv", ["find_nearby.py", "BC-1", "7.5", "3"]):
            find_nearby.main()

        args, kwargs = mock_get_nearby.call_args
        assert isinstance(kwargs["radius_km"], float)
        assert kwargs["radius_km"] == 7.5
        assert isinstance(kwargs["limit"], int)
        assert kwargs["limit"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
