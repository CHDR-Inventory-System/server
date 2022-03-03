from flask import current_app
from PIL import Image, ImageOps
import os.path


def compress_image(image_path: str):
    """
    Takes a path to an image, resizes and compresses it, then saves it
    to the same location. Note that this will replace the original image.
    """
    try:
        # Don't optimize the image if it's already smaller than 500 KB
        if os.path.getsize(image_path) <= 500_000:
            return

        image = Image.open(image_path)
        width, height = image.size
        scale_factor = 0.70
        width = int(width * scale_factor)
        height = int(height * scale_factor)

        image = image.resize((width, height), Image.LANCZOS)

        # Sometimes resizing the image causes its rotation to change
        # so we need to make sure the original orientation is kept
        image = ImageOps.exif_transpose(image)

        image.save(
            image_path,
            quality=35,
            optimize=True,
        )

        image.close()
    except Exception as err:
        current_app.logger.exception(str(err))
