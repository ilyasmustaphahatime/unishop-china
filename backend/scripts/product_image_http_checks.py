"""Synthetic-only live Phase 10 extension. Canonical bytes stay in temporary storage."""
from io import BytesIO

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SellerVerification, User
from app.models.seller_verification import VerificationStatus

from scripts.product_http_checks import product_category


def raster(format):
    with Image.new("RGBA" if format != "JPEG" else "RGB", (12,8), (20,80,120,100) if format != "JPEG" else (20,80,120)) as image:
        output=BytesIO()
        image.save(output,format=format,**({"lossless":True} if format=="WEBP" else {}))
        return output.getvalue()


def run_product_image_checks(owner,other,check,marker,engine,owner_email):
    assert owner_email == f"pre7-http-{marker}-0@example.com"  # Exact script-owned identity only.
    response=owner.post("/api/v1/seller/products",json={"title":"Synthetic image listing",
        "description":"Temporary product-media lifecycle audit.","price":"19.99","condition":"good",
        "city_slug":"qingdao","category_slug":product_category(marker)})
    check(response.status_code==201,"image-parent-draft")
    slug=response.json()["public_slug"]
    parent="/api/v1/seller/products/"+slug
    private=parent+"/images"
    public="/api/v1/products/"+slug
    refs=[]
    canonical={}
    for format in ("JPEG","PNG","WEBP"):
        response=owner.post(private,files={"file":("../../untrusted.bin",raster(format),"application/octet-stream")})
        check(response.status_code==201,"image-upload-"+format)
        image=response.json()
        refs.append(image["ref"])
        check(set(image)=={"ref","position","url","mime_type","width","height","file_size","created_at"},"image-owner-metadata-"+format)
        media=owner.get(private+"/"+image["ref"])
        check(media.status_code==200 and media.headers.get("x-content-type-options")=="nosniff","image-owner-bytes-"+format)
        check(media.headers.get("cache-control")=="no-store" and "content-disposition" not in media.headers,"image-byte-privacy-"+format)
        canonical[image["ref"]]=media.content
        check(other.get(public+"/images/"+image["ref"]).status_code==404,"image-draft-hidden-"+format)
    # Real HTTP/1.1 chunked transfer: no declared length, bounded aggregate intake.
    boundary = b"unishop-synthetic-wire"
    head = b"--" + boundary + b'\r\nContent-Disposition: form-data; name="file"; filename="synthetic.png"\r\nContent-Type: image/png\r\n\r\n'
    response = owner.post(private, content=iter((head, raster("PNG"), b"\r\n--" + boundary + b"--\r\n")),
                          headers={"Content-Type": "multipart/form-data; boundary=" + boundary.decode()})
    check(response.status_code==201 and response.request.headers.get("transfer-encoding")=="chunked",
          "image-chunked-intake-without-content-length")
    image = response.json()
    refs.append(image["ref"])
    media = owner.get(image["url"])
    check(media.status_code==200 and media.headers.get("content-type")=="image/png","image-chunked-owner-bytes")
    canonical[image["ref"]] = media.content
    check(len(owner.get(private).json())==4,"image-owner-list")
    check(other.get(private).status_code==404,"image-cross-user-list")
    check(other.get(private+"/"+refs[0]).status_code==404,"image-cross-user-bytes")
    check(other.delete(private+"/"+refs[0]).status_code==404,"image-cross-user-delete")
    check(other.post(private,files={"file":("fake.png",raster("PNG"),"image/png")}).status_code in {403,404},"image-cross-user-upload")
    check(other.patch(private+"/order",json={"images":refs}).status_code in {403,404},"image-cross-user-reorder")
    check(owner.post(private,files={"file":("fake.jpg",b"<svg><script>attack</script></svg>","image/jpeg")}).status_code==422,"image-fake-mime-rejected")
    ordered=owner.patch(private+"/order",json={"images":refs[::-1]})
    check(ordered.status_code==200 and [image["ref"] for image in ordered.json()]==refs[::-1],"image-reorder")
    check([image["position"] for image in ordered.json()]==[0,1,2,3],"image-contiguous-cover")
    check(owner.post(parent+"/publish",json={}).status_code==200,"image-parent-publish")
    metadata=other.get(public).json()["images"]
    check([image["ref"] for image in metadata]==refs[::-1],"image-public-ordered-metadata")
    for image in metadata:
        media=other.get(image["url"])
        check(media.status_code==200 and media.content==canonical[image["ref"]],"image-public-canonical-bytes")
        check(media.headers.get("cache-control")=="no-store" and media.headers.get("x-content-type-options")=="nosniff","image-public-safe-headers")
    with Session(engine) as db, db.begin():
        user = db.scalar(select(User).where(User.email == owner_email))
        assert user is not None
        attempt = db.scalar(select(SellerVerification).where(SellerVerification.user_id == user.id))
        assert attempt is not None and attempt.status == VerificationStatus.VERIFIED
        attempt_id, prior_status, prior_reason = attempt.id, attempt.status, attempt.rejection_reason
        attempt.status, attempt.rejection_reason = VerificationStatus.REJECTED, "Synthetic HTTP audit revocation"
    try:
        check(other.get(public).status_code==404,"image-revoked-seller-parent-hidden")
        check(other.get(public+"/images/"+refs[0]).status_code==404,"image-revoked-seller-bytes-hidden")
        check(owner.get(private).status_code==200,"image-revoked-owner-private-read-retained")
        check(owner.post(private,files={"file":("synthetic.png",raster("PNG"),"image/png")}).status_code==403,
              "image-revoked-seller-upload-denied")
    finally:
        with Session(engine) as db, db.begin():
            attempt = db.get(SellerVerification, attempt_id)
            assert attempt is not None
            attempt.status, attempt.rejection_reason = prior_status, prior_reason
    check(other.get(public+"/images/"+refs[0]).status_code==200,"image-restored-seller-visible")
    check(owner.post(parent+"/pause",json={}).status_code==200,"image-parent-pause")
    check(other.get(public+"/images/"+refs[0]).status_code==404,"image-paused-hidden")
    check(owner.post(parent+"/publish",json={}).status_code==200,"image-parent-republish")
    check(other.get(public+"/images/"+refs[0]).status_code==200,"image-republish-visible")
    check(owner.delete(private+"/"+refs[-1]).status_code==204,"image-delete-cover")
    check(owner.get(private).json()[0]["position"]==0 and owner.get(private).json()[0]["ref"]==refs[-2],"image-next-cover")
    check(other.get(public+"/images/"+refs[-1]).status_code==404,"image-deleted-ref-hidden")
    check(owner.post(parent+"/archive",json={}).status_code==200,"image-parent-archive")
    check(other.get(public+"/images/"+refs[0]).status_code==404,"image-archived-hidden")
    check(owner.post(private,files={"file":("x.png",raster("PNG"),"image/png")}).status_code==409,"image-archived-upload-denied")
    check(owner.patch(private+"/order",json={"images":refs[:-1][::-1]}).status_code==409,"image-archived-reorder-denied")
    for ref in refs[:-1]:
        check(owner.delete(private+"/"+ref).status_code==204,"image-archived-owner-cleanup")
    check(owner.get(private).json()==[],"image-final-metadata-empty")
