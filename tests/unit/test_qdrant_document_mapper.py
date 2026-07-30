"""
Unit tests for src/mappers/qdrant_document_mapper.py
"""

import uuid

import src.mappers.qdrant_document_mapper as qdrant_document_mapper


class TestExternalIdToPointId:
    def test_returns_valid_uuid_string(self):
        result = qdrant_document_mapper.external_id_to_point_id("BC-12908249")

        assert isinstance(result, str)
        parsed = uuid.UUID(result)
        assert str(parsed) == result

    def test_is_deterministic(self):
        first = qdrant_document_mapper.external_id_to_point_id("BC-12908249")
        second = qdrant_document_mapper.external_id_to_point_id("BC-12908249")

        assert first == second

    def test_different_ids_produce_different_uuids(self):
        first = qdrant_document_mapper.external_id_to_point_id("BC-12908249")
        second = qdrant_document_mapper.external_id_to_point_id("BC-99999999")

        assert first != second

    def test_matches_manual_uuid5_computation(self):
        expected = str(uuid.uuid5(uuid.NAMESPACE_DNS, "BC-12908249"))

        result = qdrant_document_mapper.external_id_to_point_id("BC-12908249")

        assert result == expected


class TestBooleanFlagsAsText:
    def test_returns_empty_list_when_no_flags_set(self):
        result = qdrant_document_mapper._boolean_flags_as_text({})

        assert result == []

    def test_includes_pet_friendly_when_true(self):
        result = qdrant_document_mapper._boolean_flags_as_text({"IsPetFriendly": True})

        assert "pet friendly" in result

    def test_includes_adult_only_when_true(self):
        result = qdrant_document_mapper._boolean_flags_as_text({"AdultOnly": True})

        assert "adults only" in result

    def test_includes_long_stay_friendly_when_true(self):
        result = qdrant_document_mapper._boolean_flags_as_text({"LongStayFriendlyHome": True})

        assert "long stay friendly" in result

    def test_includes_work_friendly_when_true(self):
        result = qdrant_document_mapper._boolean_flags_as_text({"WorkFriendlyHome": True})

        assert "work friendly" in result

    def test_excludes_flags_when_false(self):
        prop = {
            "IsPetFriendly": False,
            "AdultOnly": False,
            "LongStayFriendlyHome": False,
            "WorkFriendlyHome": False,
        }

        result = qdrant_document_mapper._boolean_flags_as_text(prop)

        assert result == []

    def test_includes_all_flags_when_all_true(self):
        prop = {
            "IsPetFriendly": True,
            "AdultOnly": True,
            "LongStayFriendlyHome": True,
            "WorkFriendlyHome": True,
        }

        result = qdrant_document_mapper._boolean_flags_as_text(prop)

        assert result == [
            "pet friendly",
            "adults only",
            "long stay friendly",
            "work friendly",
        ]

    def test_preserves_order(self):
        prop = {
            "WorkFriendlyHome": True,
            "IsPetFriendly": True,
        }

        result = qdrant_document_mapper._boolean_flags_as_text(prop)

        assert result == ["pet friendly", "work friendly"]


class TestBuildEmbeddingText:
    def test_combines_all_available_fields(self):
        document = {
            "City": "Cox's Bazar",
            "Country": "Bangladesh",
            "Property": {
                "PropertyName": "Sea Breeze Villa",
                "PropertyType": "Villa",
                "PropertyTypeCategory": "Luxury",
                "PropertyDescription": "A lovely beachfront villa",
                "Amenities": ["WiFi", "Pool"],
                "IsPetFriendly": True,
            },
            "Partner": {"Amenities": ["24/7 Support"]},
        }

        result = qdrant_document_mapper.build_embedding_text(document)

        assert "Sea Breeze Villa" in result
        assert "Villa" in result
        assert "Luxury" in result
        assert "Cox's Bazar" in result
        assert "Bangladesh" in result
        assert "A lovely beachfront villa" in result
        assert "WiFi, Pool" in result
        assert "24/7 Support" in result
        assert "pet friendly" in result

    def test_uses_pipe_separator(self):
        document = {
            "City": "Dhaka",
            "Country": "Bangladesh",
            "Property": {"PropertyName": "Test Home"},
        }

        result = qdrant_document_mapper.build_embedding_text(document)

        assert " | " in result
        assert result == "Test Home | Dhaka | Bangladesh"

    def test_missing_property_and_partner_keys_default_to_empty_dict(self):
        document = {"City": "Dhaka", "Country": "Bangladesh"}

        result = qdrant_document_mapper.build_embedding_text(document)

        assert result == "Dhaka | Bangladesh"

    def test_none_values_are_excluded(self):
        document = {
            "City": None,
            "Country": "Bangladesh",
            "Property": {
                "PropertyName": None,
                "PropertyType": "Cabin",
            },
        }

        result = qdrant_document_mapper.build_embedding_text(document)

        assert result == "Cabin | Bangladesh"

    def test_empty_document_returns_empty_string(self):
        result = qdrant_document_mapper.build_embedding_text({})

        assert result == ""

    def test_omits_amenities_when_absent(self):
        document = {
            "Property": {"PropertyName": "Simple House"},
        }

        result = qdrant_document_mapper.build_embedding_text(document)

        assert result == "Simple House"

    def test_includes_boolean_flags_at_end(self):
        document = {
            "Property": {
                "PropertyName": "Cabin",
                "IsPetFriendly": True,
                "AdultOnly": True,
            },
        }

        result = qdrant_document_mapper.build_embedding_text(document)

        assert result == "Cabin | pet friendly | adults only"


class TestToQdrantPoint:
    def test_returns_none_when_no_id(self):
        document = {
            "Property": {"PropertyName": "Test Home", "PropertyDescription": "desc"},
        }

        result = qdrant_document_mapper.to_qdrant_point(document)

        assert result is None

    def test_returns_none_when_no_embeddable_text(self, mocker):
        document = {"ID": "BC-12908249", "Property": {}}

        result = qdrant_document_mapper.to_qdrant_point(document)

        assert result is None

    def test_returns_point_struct_with_correct_id(self, mocker):
        mocker.patch(
            "src.mappers.qdrant_document_mapper.generate_embedding",
            return_value=[0.1, 0.2, 0.3],
        )
        document = {
            "ID": "BC-12908249",
            "City": "Dhaka",
            "Property": {"PropertyName": "Test Home"},
        }

        result = qdrant_document_mapper.to_qdrant_point(document)

        expected_id = qdrant_document_mapper.external_id_to_point_id("BC-12908249")
        assert result.id == expected_id

    def test_returns_point_struct_with_generated_vector(self, mocker):
        mocker.patch(
            "src.mappers.qdrant_document_mapper.generate_embedding",
            return_value=[0.5, 0.6, 0.7],
        )
        document = {
            "ID": "BC-12908249",
            "Property": {"PropertyName": "Test Home"},
        }

        result = qdrant_document_mapper.to_qdrant_point(document)

        assert result.vector == [0.5, 0.6, 0.7]

    def test_calls_generate_embedding_with_built_text(self, mocker):
        mock_generate_embedding = mocker.patch(
            "src.mappers.qdrant_document_mapper.generate_embedding",
            return_value=[0.1, 0.2, 0.3],
        )
        document = {
            "ID": "BC-12908249",
            "City": "Dhaka",
            "Property": {"PropertyName": "Test Home"},
        }

        qdrant_document_mapper.to_qdrant_point(document)

        expected_text = qdrant_document_mapper.build_embedding_text(document)
        mock_generate_embedding.assert_called_once_with(expected_text)

    def test_payload_contains_expected_fields(self, mocker):
        mocker.patch(
            "src.mappers.qdrant_document_mapper.generate_embedding",
            return_value=[0.1, 0.2, 0.3],
        )
        document = {
            "ID": "BC-12908249",
            "City": "Dhaka",
            "Country": "Bangladesh",
            "Published": True,
            "Property": {
                "PropertyName": "Test Home",
                "PropertyType": "Villa",
                "Price": 150,
                "FeatureImage": "image.jpg",
                "StarRating": 4.5,
                "ReviewScore": 9.2,
                "Counts": {"Bedroom": 3, "Bathroom": 2, "Occupancy": 6},
                "MinStay": 2,
                "IsPetFriendly": True,
                "AdultOnly": False,
                "LongStayFriendlyHome": True,
                "WorkFriendlyHome": False,
            },
        }

        result = qdrant_document_mapper.to_qdrant_point(document)

        assert result.payload == {
            "external_id": "BC-12908249",
            "property_name": "Test Home",
            "property_type": "Villa",
            "city": "Dhaka",
            "country": "Bangladesh",
            "usd_price": 150,
            "published": True,
            "feature_image": "image.jpg",
            "star_rating": 4.5,
            "review_score": 9.2,
            "bedroom_count": 3,
            "bathroom_count": 2,
            "occupancy": 6,
            "min_stay": 2,
            "is_pet_friendly": True,
            "adult_only": False,
            "long_stay_friendly_home": True,
            "work_friendly_home": False,
        }

    def test_payload_defaults_boolean_flags_to_false_when_missing(self, mocker):
        mocker.patch(
            "src.mappers.qdrant_document_mapper.generate_embedding",
            return_value=[0.1, 0.2, 0.3],
        )
        document = {
            "ID": "BC-12908249",
            "Property": {"PropertyName": "Test Home"},
        }

        result = qdrant_document_mapper.to_qdrant_point(document)

        assert result.payload["is_pet_friendly"] is False
        assert result.payload["adult_only"] is False
        assert result.payload["long_stay_friendly_home"] is False
        assert result.payload["work_friendly_home"] is False

    def test_payload_handles_missing_counts(self, mocker):
        mocker.patch(
            "src.mappers.qdrant_document_mapper.generate_embedding",
            return_value=[0.1, 0.2, 0.3],
        )
        document = {
            "ID": "BC-12908249",
            "Property": {"PropertyName": "Test Home"},
        }

        result = qdrant_document_mapper.to_qdrant_point(document)

        assert result.payload["bedroom_count"] is None
        assert result.payload["bathroom_count"] is None
        assert result.payload["occupancy"] is None

    def test_payload_handles_missing_property_key(self, mocker):
        mocker.patch(
            "src.mappers.qdrant_document_mapper.generate_embedding",
            return_value=[0.1, 0.2, 0.3],
        )
        document = {"ID": "BC-12908249", "City": "Dhaka"}

        result = qdrant_document_mapper.to_qdrant_point(document)

        assert result.payload["property_name"] is None
        assert result.payload["city"] == "Dhaka"
