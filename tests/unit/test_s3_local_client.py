"""
Unit tests for src/clients/s3_local_client.py

Run:
    docker compose exec spark pytest tests/unit/test_s3_local_client.py -v
"""

import pytest

from clients.s3_local_client import LocalS3Client


@pytest.fixture
def client(tmp_path):
    return LocalS3Client(root_dir=str(tmp_path))


def test_create_bucket(client, tmp_path):
    response = client.create_bucket(Bucket="my-bucket")

    assert response == {"Location": "/my-bucket"}
    assert (tmp_path / "my-bucket").is_dir()


def test_put_object_and_get_object(client):
    client.create_bucket(Bucket="my-bucket")
    body = b'{"foo": "bar"}'

    put_response = client.put_object(Bucket="my-bucket", Key="data/file.json", Body=body)
    assert put_response == {"ETag": f'"{len(body)}"'}

    get_response = client.get_object(Bucket="my-bucket", Key="data/file.json")
    assert get_response["Body"].read() == body


def test_put_object_creates_parent_dirs_without_explicit_create_bucket(client):
    body = b"hello"
    client.put_object(Bucket="my-bucket", Key="a/b/c/file.txt", Body=body)

    get_response = client.get_object(Bucket="my-bucket", Key="a/b/c/file.txt")
    assert get_response["Body"].read() == body


def test_get_object_missing_raises_file_not_found(client):
    client.create_bucket(Bucket="my-bucket")

    with pytest.raises(FileNotFoundError):
        client.get_object(Bucket="my-bucket", Key="does/not/exist.json")


def test_list_objects_v2_returns_matching_keys(client):
    client.put_object(Bucket="my-bucket", Key="data/a.json", Body=b"{}")
    client.put_object(Bucket="my-bucket", Key="data/b.json", Body=b"{}")
    client.put_object(Bucket="my-bucket", Key="other/c.json", Body=b"{}")

    response = client.list_objects_v2(Bucket="my-bucket", Prefix="data/")

    keys = sorted(item["Key"] for item in response["Contents"])
    assert keys == ["data/a.json", "data/b.json"]
    assert response["KeyCount"] == 2


def test_list_objects_v2_ignores_non_json_files(client, tmp_path):
    client.put_object(Bucket="my-bucket", Key="data/a.json", Body=b"{}")
    (tmp_path / "my-bucket" / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "my-bucket" / "data" / "notes.txt").write_text("not json")

    response = client.list_objects_v2(Bucket="my-bucket", Prefix="data/")

    keys = [item["Key"] for item in response["Contents"]]
    assert keys == ["data/a.json"]


def test_list_objects_v2_no_matches_returns_empty(client):
    client.create_bucket(Bucket="my-bucket")

    response = client.list_objects_v2(Bucket="my-bucket", Prefix="nothing/")

    assert response == {"Contents": [], "KeyCount": 0}


def test_delete_object_removes_file(client):
    client.put_object(Bucket="my-bucket", Key="data/a.json", Body=b"{}")

    response = client.delete_object(Bucket="my-bucket", Key="data/a.json")

    assert response == {"DeleteMarker": True}
    with pytest.raises(FileNotFoundError):
        client.get_object(Bucket="my-bucket", Key="data/a.json")


def test_delete_object_missing_key_does_not_raise(client):
    client.create_bucket(Bucket="my-bucket")

    response = client.delete_object(Bucket="my-bucket", Key="does/not/exist.json")

    assert response == {"DeleteMarker": True}
