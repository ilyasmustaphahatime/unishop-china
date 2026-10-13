"""HTTP-only identity/budgets, strict multipart envelope and safe error mapping."""
from contextlib import contextmanager
import asyncio

from fastapi import Depends, HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect
from starlette.concurrency import run_in_threadpool

from app.api.rate_limits import enforce_authenticated_limit
from app.api.v1.products.dependencies import listing_user, product_peer_limiter, safe_product_operation
from app.common.product_image_rules import CHUNK_BYTES, MAX_RAW_BYTES
from app.common.product_slugs import ProductSlug
from app.core.database import get_db
from app.core.http_input import RequestBodyLimitExceeded
from app.core.product_image_security import ImageIntakeBusy
from app.core.rate_limit import InMemoryRateLimiter
from app.services.product_image_service import ProductImageError, ProductImageService

image_upload_limiter = InMemoryRateLimiter(max_requests=10, window_seconds=600, max_keys=10000)


class CompleteImageMultipartParser(MultiPartParser):
    """Retain framework limits, but require its terminal multipart callback.

    Starlette can return completed parts when EOF arrives in an unfinished next
    part. Its error-file inventory also includes files not yet added to FormData;
    close that owned inventory on rejection/cancellation, not just returned parts.
    This narrow framework seam is covered by parser/closure compatibility tests.
    """
    complete = False

    def on_end(self):
        super().on_end()
        self.complete = True

    async def parse(self):
        try:
            form = await super().parse()
            if not self.complete:
                raise MultiPartException("Incomplete multipart image request.")
            return form
        except BaseException:
            for file in self._files_to_close_on_error:
                file.close()
            raise


def image_upload_user(request: Request, user=Depends(listing_user)):
    def reject(retry_after):
        raise HTTPException(429, "Too many image uploads.", headers={"Retry-After": str(retry_after or 1)})
    enforce_authenticated_limit(request, user.id, ip_limiter=product_peer_limiter,
        user_limiter=image_upload_limiter, namespace="product-image-upload:user", on_rejected=reject)
    return user


async def image_file(request: Request, slug: ProductSlug, user=Depends(image_upload_user), db=Depends(get_db)):
    # Auth/current user budgets and owner/quota checks precede BOTH intake and
    # parsing. No SQL lock is held while awaiting a caller's slow body.
    try:
        service = ProductImageService(request.app.state.product_image_storage,
            api_prefix=request.app.state.settings.api_v1_prefix)
        with safe_image_operation():
            await run_in_threadpool(service.preflight_upload, db, user.id, slug)
        async with request.scope["product_image_intake"](request.receive) as body:
            async def chunks():
                while chunk := await asyncio.to_thread(body.read, CHUNK_BYTES):
                    yield chunk

            form = await CompleteImageMultipartParser(request.headers, chunks(),
                max_files=1, max_fields=0, max_part_size=MAX_RAW_BYTES).parse()
            try:
                items = form.multi_items()
                if len(items) != 1 or items[0][0] != "file" or not isinstance(items[0][1], UploadFile):
                    raise HTTPException(400, "Supply exactly one image file.")
                yield items[0][1].file
            finally:
                await form.close()
    except HTTPException:
        raise
    except ImageIntakeBusy:
        raise HTTPException(429, "Too many image requests.", headers={"Retry-After": "30"}) from None
    except TimeoutError:
        raise HTTPException(408, "Image upload timed out.") from None
    except (ConnectionError, ClientDisconnect):
        raise HTTPException(400, "Image upload interrupted.") from None
    except RequestBodyLimitExceeded:
        raise HTTPException(413, "Image request exceeds input limits.") from None
    except (StarletteHTTPException, MultiPartException, ValueError):
        raise HTTPException(400, "Invalid multipart image request.") from None
    except Exception:
        # Dependency execution precedes the route's safe-operation boundary.
        raise HTTPException(503, "Image upload temporarily unavailable.") from None


def image_service(request: Request):
    return ProductImageService(request.app.state.product_image_storage,
                               api_prefix=request.app.state.settings.api_v1_prefix)


@contextmanager
def safe_image_operation():
    with safe_product_operation():
        try:
            yield
        except ProductImageError as error:
            raise HTTPException(error.status, str(error)) from None
