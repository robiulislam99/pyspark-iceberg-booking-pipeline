"""
A minimal local stand-in for boto3's S3 client, backed by the filesystem
instead of real S3. Mirrors the boto3 method signatures (put_object,
get_object, list_objects_v2, delete_object) so the calling code reads
the same way it would against real S3 -- swapping this for a real
boto3.client("s3", ...) later requires no logic changes elsewhere,
only construction of a different client instance.
"""
import os
import json
from pathlib import Path

S3_LOCAL_ROOT = os.environ.get("S3_LOCAL_ROOT", "/app/s3_local")


class LocalS3Client:
    def __init__(self, root_dir: str = S3_LOCAL_ROOT):
        self.root_dir = Path(root_dir)

    def _object_path(self, bucket: str, key: str) -> Path:
        return self.root_dir / bucket / key

    def create_bucket(self, Bucket: str):
        (self.root_dir / Bucket).mkdir(parents=True, exist_ok=True)
        return {"Location": f"/{Bucket}"}

    def put_object(self, Bucket: str, Key: str, Body: bytes):
        path = self._object_path(Bucket, Key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Body)
        return {"ETag": f'"{len(Body)}"'}

    def get_object(self, Bucket: str, Key: str):
        path = self._object_path(Bucket, Key)
        if not path.exists():
            raise FileNotFoundError(f"No such key: {Bucket}/{Key}")
        return {"Body": _BytesReader(path.read_bytes())}

    def list_objects_v2(self, Bucket: str, Prefix: str = ""):
        bucket_root = self.root_dir / Bucket
        prefix_path = bucket_root / Prefix
        contents = []
        if prefix_path.exists():
            search_root = prefix_path if prefix_path.is_dir() else prefix_path.parent
            for file_path in search_root.rglob("*.json"):
                key = str(file_path.relative_to(bucket_root))
                if key.startswith(Prefix):
                    contents.append({
                        "Key": key,
                        "Size": file_path.stat().st_size,
                    })
        return {"Contents": contents, "KeyCount": len(contents)}

    def delete_object(self, Bucket: str, Key: str):
        path = self._object_path(Bucket, Key)
        if path.exists():
            path.unlink()
        return {"DeleteMarker": True}


class _BytesReader:
    """Mimics boto3's StreamingBody -- supports .read()."""
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data