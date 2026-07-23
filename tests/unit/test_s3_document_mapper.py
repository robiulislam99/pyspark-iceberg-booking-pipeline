"""
Unit tests for mappers.s3_document_mapper. image_ranker.analyze_images
is mocked -- this test verifies FIELD MAPPING logic only, not the real
model's scoring behavior (that belongs in a separate, explicit test for
core.image_ranker, run rarely/manually since it needs network + model).
"""
from mappers.s3_document_mapper import to_s3_document


def test_maps_identity_and_location_fields(iceberg_row, mocker):
    mocker.patch(
        "mappers.s3_document_mapper.analyze_images",
        return_value=[],
    )
    document = to_s3_document(iceberg_row)

    assert document["ID"] == "BC-12908249"
    assert document["City"] == "Port Aransas"
    assert document["Lat"] == "27.797983"
    assert document["Lng"] == "-97.085391"


def test_maps_property_fields(iceberg_row, mocker):
    mocker.patch("mappers.s3_document_mapper.analyze_images", return_value=[])
    document = to_s3_document(iceberg_row)

    prop = document["Property"]
    assert prop["PropertyName"] == "Villa Palmilla"
    assert prop["Counts"]["Bedroom"] == 4
    assert prop["Price"] == 1301.0


def test_ranked_image_uses_top_analyzed_result(iceberg_row, mocker):
    mocker.patch(
        "mappers.s3_document_mapper.analyze_images",
        return_value=[
            {"url": "https://example.com/best.jpg", "aesthetic_score": 9.1, "label": "bedroom", "label_confidence": 0.9},
            {"url": "https://example.com/worst.jpg", "aesthetic_score": 3.2, "label": "bathroom", "label_confidence": 0.7},
        ],
    )
    document = to_s3_document(iceberg_row)

    assert document["Property"]["RankedImage"] == "https://example.com/best.jpg"
    assert document["Property"]["RankedImages"]["Count"] == 2
    assert document["Property"]["ImageAnalysis"][0]["Label"] == "bedroom"


def test_no_images_leaves_ranked_fields_empty(iceberg_row, mocker):
    analyze_mock = mocker.patch("mappers.s3_document_mapper.analyze_images")
    iceberg_row["images"] = []

    document = to_s3_document(iceberg_row)

    analyze_mock.assert_not_called()
    assert document["Property"]["RankedImage"] is None
    assert document["Property"]["RankedImages"] == {"Count": 0, "Images": []}