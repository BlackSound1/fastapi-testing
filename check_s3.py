"""
Script to check the AWS S3 connection by uploading and deleting a test object.
Avoids going through the whole application flow.
"""

from io import BytesIO

from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from image_utils import _get_s3_client


def check_s3_connection():
    s3 = _get_s3_client()
    print(f"Bucket: {settings.s3_bucket_name}")
    print(f"Region: {settings.s3_region}\n")

    test_key = "profile_pics/test.txt"

    # Test upload
    try:
        s3.upload_fileobj(
            BytesIO(b"Test"),
            settings.s3_bucket_name,
            test_key,
            ExtraArgs={"ContentType": "text/plain"},
        )
        print("Upload: SUCCESS")
    except (BotoCoreError, ClientError) as e:
        print(f"Upload: FAILED - {e}")
        return

    # Test delete
    try:
        s3.delete_object(Bucket=settings.s3_bucket_name, Key=test_key)
        print("Delete: SUCCESS")
    except (BotoCoreError, ClientError) as e:
        print(f"Delete: FAILED - {e}")
        return


if __name__ == "__main__":
    check_s3_connection()
