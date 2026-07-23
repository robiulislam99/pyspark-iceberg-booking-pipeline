"""
Unit tests for core.image_ranker. Both the HTTP download and the
Hugging Face model calls are mocked -- these tests verify the SORTING
and ERROR-HANDLING logic, not real model accuracy (which can't be
meaningfully unit-tested anyway -- there's no "correct" aesthetic score
to assert against).
"""

from PIL import Image

from core import image_ranker


def _fake_image():
    return Image.new("RGB", (10, 10))


def test_rank_images_orders_best_to_worst(mocker):
    mocker.patch.object(
        image_ranker,
        "_download_image" if hasattr(image_ranker, "_download_image") else "_score_image",
    )
    # _score_image does download + score together; patch it directly with per-url side effects
    mocker.patch.object(
        image_ranker,
        "_score_image",
        side_effect=[0.2, 0.9, 0.5],
    )

    result = image_ranker.rank_images(["url_a", "url_b", "url_c"])

    assert result == ["url_b", "url_c", "url_a"]


def test_rank_images_skips_failed_downloads(mocker, capsys):
    mocker.patch.object(
        image_ranker,
        "_score_image",
        side_effect=[0.8, Exception("404 Client Error"), 0.3],
    )

    result = image_ranker.rank_images(["url_a", "url_b", "url_c"])

    assert result == ["url_a", "url_c"]
    assert "Skipping url_b" in capsys.readouterr().out


def test_rank_images_with_scores_returns_tuples(mocker):
    mocker.patch.object(image_ranker, "_score_image", side_effect=[0.1, 0.7])

    result = image_ranker.rank_images_with_scores(["url_a", "url_b"])

    assert result == [("url_b", 0.7), ("url_a", 0.1)]


def test_analyze_image_rescales_aesthetic_score_to_ten(mocker):
    mocker.patch.object(image_ranker, "_download_image", return_value=_fake_image())
    mocker.patch.object(image_ranker, "_score_aesthetic", return_value=8.5)
    mocker.patch.object(image_ranker, "_classify_room", return_value=("bedroom", 0.77))

    result = image_ranker.analyze_image("some_url")

    assert result == {
        "url": "some_url",
        "aesthetic_score": 8.5,
        "label": "bedroom",
        "label_confidence": 0.77,
    }


def test_analyze_images_sorts_by_aesthetic_score(mocker):
    mocker.patch.object(
        image_ranker,
        "analyze_image",
        side_effect=[
            {"url": "a", "aesthetic_score": 3.0, "label": "house", "label_confidence": 0.5},
            {"url": "b", "aesthetic_score": 9.0, "label": "pool", "label_confidence": 0.9},
        ],
    )

    result = image_ranker.analyze_images(["a", "b"])

    assert [r["url"] for r in result] == ["b", "a"]
