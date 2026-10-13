from datetime import datetime
from pydantic import Field, model_validator

from app.common.product_image_rules import ImageRef, MAX_IMAGES
from app.schemas.catalog import StrictBody


class PublicProductImage(StrictBody):
    ref: ImageRef
    position: int = Field(ge=0, lt=MAX_IMAGES)
    url: str


class OwnProductImage(PublicProductImage):
    mime_type: str
    width: int
    height: int
    file_size: int
    created_at: datetime


class ProductImageOrder(StrictBody):
    images: list[ImageRef] = Field(max_length=MAX_IMAGES)

    @model_validator(mode="after")
    def unique_refs(self):
        if len(set(self.images)) != len(self.images):
            raise ValueError("Image references must be unique.")
        return self
