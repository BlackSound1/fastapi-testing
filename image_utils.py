import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

PROFILE_PICS_DIR = Path("media/profile_pics")


def process_profile_image(content: bytes) -> str:
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
        filepath = PROFILE_PICS_DIR / filename

        PROFILE_PICS_DIR.mkdir(parents=True, exist_ok=True)

        img.save(filepath, "JPEG", quality=85, optimize=True)

    return filename


def delete_profile_image(filename: str | None) -> None:
    """
    Delete a profile picture.

    :param filename: The filename to delete.
    """
    if filename is None:
        return
    filepath = PROFILE_PICS_DIR / filename
    if filepath.exists():
        filepath.unlink()
