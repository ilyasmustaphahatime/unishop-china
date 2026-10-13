"""Small in-memory synthetic raster fixtures; never real documents/images."""
from io import BytesIO
from PIL import Image


def raster(format="PNG", *, size=(12, 8), alpha=False, exif=None, animated=False):
    mode = "RGBA" if alpha else "RGB"
    with Image.new(mode, size, (30, 80, 120, 90) if alpha else (30, 80, 120)) as image:
        stream = BytesIO()
        options = {"exif": exif} if exif else {}
        if format == "WEBP":
            options["lossless"] = True
        if animated:
            with Image.new(mode, size, (150, 10, 50, 120) if alpha else (150, 10, 50)) as other:
                image.save(stream, format=format, save_all=True, append_images=[other], duration=100, loop=0, **options)
        else:
            image.save(stream, format=format, **options)
        return stream.getvalue()
