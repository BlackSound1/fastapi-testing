import uuid
from io import BytesIO

import boto3
from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool

from config import settings


def _get_s3_client():
    return boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=(
            settings.s3_access_key_id.get_secret_value()
            if settings.s3_access_key_id
            else None
        ),
        aws_secret_access_key=(
            settings.s3_secret_access_key.get_secret_value()
            if settings.s3_secret_access_key
            else None
        ),
        endpoint_url=settings.s3_endpoint_url,
    )


def process_profile_image(content: bytes) -> tuple[bytes, str]:
    """
    Save a given string of bytes into a valid JPEG image.

    :param content: The image bytes.
    :return: The randomly-generated filename of the new image.
    """
    with Image.open(BytesIO(content)) as original:
        # Fix orientation
        img = ImageOps.exif_transpose(original)

        # Resizes/ crops
        img = ImageOps.fit(image=img, size=(300, 300), method=Image.Resampling.LANCZOS)

        # Since we want this to be a JPEG, force RGB colour
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        filename = f"{uuid.uuid4().hex}.jpg"

        # Save the raw bytes to an object
        output = BytesIO()
        img.save(output, "JPEG", quality=85, optimize=True)
        output.seek(0)

    return output.read(), filename


def _upload_to_s3(file_bytes: bytes, key: str) -> None:
    """
    Upload an image (in terms of bytes) to S3.

    :param file_bytes: The file bytes to upload.
    :param key: The name to upload with.
    """
    s3 = _get_s3_client()
    s3.upload_fileobj(
        BytesIO(file_bytes),
        settings.s3_bucket_name,
        key,
        ExtraArgs={"ContentType": "image/jpeg"},
    )


def _delete_from_s3(key: str) -> None:
    """
    Delete an image from S3.

    :param key: The name to delete.
    """
    s3 = _get_s3_client()
    s3.delete_object(Bucket=settings.s3_bucket_name, Key=key)


async def upload_profile_image(file_bytes: bytes, filename: str) -> None:
    """
    Wrapper for a blocking AWS S3 call. Run `_upload_to_s3` in a tread pool.

    :param file_bytes: The file bytes to upload.
    :param filename: The name to upload with.
    """
    key = f"profile_pics/{filename}"
    await run_in_threadpool(_upload_to_s3, file_bytes, key)


async def delete_profile_image(filename: str | None) -> None:
    """
    Wrapper for a blocking AWS S3 call. Run `_delete_from_s3` in a thread pool.

    :param filename: The name to delete.
    """
    if filename is None:
        return
    key = f"profile_pics/{filename}"
    await run_in_threadpool(_delete_from_s3, key)
