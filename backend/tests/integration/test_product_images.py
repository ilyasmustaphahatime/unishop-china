"""Real MySQL + controlled local objects: media policy, uploads and compensation."""
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import SessionTransaction

from app.api.v1.products.image_dependencies import image_upload_limiter
from app.common.product_image_rules import MAX_MULTIPART_BYTES, MAX_RAW_BYTES, generate_image_ref, generate_storage_key
from app.common.enums import AccountStatus
from app.models import ProductImage, SellerVerification, UserProfile
from app.models.seller_verification import VerificationStatus
from app.repositories.product_image_repository import ProductImageRepository
from app.schemas.product_image import ProductImageOrder
from app.services.product_image_service import ProductImageService
from app.services.product_image_storage import LocalProductImageStorage
from tests.product_image_fixtures import raster
from tests.integration.test_product_listings import (
    world as world, create, action, headers, body, OWN, PUBLIC,
)


@pytest.fixture
def image_world(world, tmp_path):
    image_upload_limiter.clear()
    client, db, owner, other, _ = world
    storage = LocalProductImageStorage(tmp_path / "controlled-media")
    client.app.state.product_image_storage = storage
    slug = create(world)["public_slug"]
    value = SimpleNamespace(client=client,db=db,owner=owner,other=other,slug=slug,storage=storage,world=world,
        own=f"{OWN}/{slug}/images", public=f"{PUBLIC}{slug}/images")
    try:
        yield value
    finally:
        for key in list(storage.keys()):
            storage.delete(key)
        assert list(storage.keys()) == []
        image_upload_limiter.clear()


def upload(w, *, data=None, user=None, name="untrusted.png", type="image/png"):
    return w.client.post(w.own, headers=headers(user or w.owner),
                         files={"file":(name,raster() if data is None else data,type)})


def images(w):
    response = w.client.get(w.own,headers=headers(w.owner))
    assert response.status_code == 200, response.json()
    return response.json()


def count(w):
    return w.db.scalar(select(func.count()).select_from(ProductImage))


@pytest.mark.parametrize("format", ["JPEG","PNG","WEBP"])
def test_upload_metadata_owner_bytes_and_public_headers(image_world,format):
    w = image_world
    result = upload(w,data=raster(format),name="../../PRIVATE ORIGINAL.exe",type="application/octet-stream")
    assert result.status_code == 201, result.json()
    image = result.json()
    assert set(image) == {"ref","position","url","mime_type","width","height","file_size","created_at"}
    assert image["position"] == 0 and image["url"] == w.own + "/" + image["ref"]
    assert image["mime_type"] == {"JPEG":"image/jpeg","PNG":"image/png","WEBP":"image/webp"}[format]
    assert w.owner.id not in result.text and "storage_key" not in result.text and "PRIVATE ORIGINAL" not in result.text
    owner = w.client.get(image["url"],headers=headers(w.owner))
    assert owner.status_code == 200 and owner.headers["content-type"] == image["mime_type"]
    assert owner.headers["cache-control"] == "no-store" and owner.headers["pragma"] == "no-cache"
    assert "content-disposition" not in owner.headers
    assert w.client.get(w.public+"/"+image["ref"]).json() == {"detail":"Image not found."}
    assert action(w.world,w.slug,"publish").status_code == 200
    public = w.client.get(PUBLIC+w.slug).json()
    assert public["images"] == [{"ref":image["ref"],"position":0,"url":w.public+"/"+image["ref"]}]
    media = w.client.get(public["images"][0]["url"])
    assert media.status_code == 200 and media.content == owner.content
    assert media.headers["x-content-type-options"] == "nosniff" and media.headers["cache-control"] == "no-store"
    assert "content-disposition" not in media.headers
    row = w.db.scalar(select(ProductImage))
    assert row.storage_key.startswith("product-media/") and row.storage_key not in result.text
    assert row.file_size == len(media.content)


def test_image_count_cover_reorder_delete_and_new_slot(image_world):
    w = image_world
    assert images(w) == []
    refs = [upload(w).json()["ref"] for _ in range(8)]
    assert len(images(w)) == 8 and count(w) == 8
    assert upload(w).status_code == 409
    reverse = w.client.patch(w.own+"/order",headers=headers(w.owner),json={"images":refs[::-1]})
    assert reverse.status_code == 200
    assert [image["ref"] for image in reverse.json()] == refs[::-1]
    assert [image["position"] for image in reverse.json()] == list(range(8))
    assert w.client.delete(w.own+"/"+refs[-1],headers=headers(w.owner)).status_code == 204
    remaining = images(w)
    assert remaining[0]["ref"] == refs[-2] and remaining[0]["position"] == 0
    assert upload(w).status_code == 201 and len(images(w)) == 8


@pytest.mark.parametrize("shape", ["duplicate","missing","extra","foreign","unknown","empty","id","null"])
def test_reorder_requires_exact_unique_owned_set(image_world,shape):
    w = image_world
    refs = [upload(w).json()["ref"] for _ in range(2)]
    foreign_ref = generate_image_ref()
    if shape == "foreign":
        other_slug = w.client.post(OWN, headers=headers(w.other), json=body()).json()["public_slug"]
        foreign_ref = w.client.post(f"{OWN}/{other_slug}/images", headers=headers(w.other),
            files={"file": ("foreign.png", raster(), "image/png")}).json()["ref"]
    submitted = {
        "duplicate":[refs[0],refs[0]],"missing":[refs[0]],"extra":[*refs,generate_image_ref()],
        "foreign":[refs[0],foreign_ref],"unknown":[generate_image_ref(),generate_image_ref()],
        "empty":[],"id":[str(uuid4()),refs[1]],"null":None,
    }[shape]
    response = w.client.patch(w.own+"/order",headers=headers(w.owner),json={"images":submitted})
    assert response.status_code in {409,422}
    assert [image["ref"] for image in images(w)] == refs


def test_zero_single_same_order_and_delete_final_image(image_world):
    w = image_world
    assert w.client.patch(w.own+"/order",headers=headers(w.owner),json={"images":[]}).json() == []
    ref = upload(w).json()["ref"]
    assert w.client.patch(w.own+"/order",headers=headers(w.owner),json={"images":[ref]}).status_code == 200
    assert w.client.delete(w.own+"/"+ref,headers=headers(w.owner)).status_code == 204
    assert images(w) == [] and list(w.storage.keys()) == []
    assert w.client.delete(w.own+"/"+ref,headers=headers(w.owner)).status_code == 404


@pytest.mark.parametrize("operation", ["list","read","upload","reorder","delete"])
def test_cross_seller_all_owner_operations_are_denied(image_world,operation):
    w = image_world
    ref = upload(w).json()["ref"]
    auth = headers(w.other)
    response = (
        w.client.get(w.own,headers=auth) if operation == "list" else
        w.client.get(w.own+"/"+ref,headers=auth) if operation == "read" else
        upload(w,user=w.other) if operation == "upload" else
        w.client.patch(w.own+"/order",headers=auth,json={"images":[ref]}) if operation == "reorder" else
        w.client.delete(w.own+"/"+ref,headers=auth)
    )
    assert response.status_code == 404
    assert len(images(w)) == count(w) == 1


@pytest.mark.parametrize("operation", ["list","read","upload","reorder","delete"])
def test_every_owner_image_operation_requires_bearer(image_world,operation):
    w = image_world
    ref = upload(w).json()["ref"]
    response = (
        w.client.get(w.own) if operation == "list" else w.client.get(w.own+"/"+ref) if operation == "read" else
        w.client.post(w.own,files={"file":("x.png",raster(),"image/png")}) if operation == "upload" else
        w.client.patch(w.own+"/order",json={"images":[ref]}) if operation == "reorder" else
        w.client.delete(w.own+"/"+ref)
    )
    assert response.status_code == 401 and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("policy", ["archived","lost_verification","lost_onboarding"])
def test_cleanup_remains_allowed_when_selling_is_denied(image_world,policy):
    w = image_world
    ref = upload(w).json()["ref"]
    if policy == "archived":
        action(w.world,w.slug,"archive")
    elif policy == "lost_verification":
        row = w.db.scalar(select(SellerVerification).where(SellerVerification.user_id==w.owner.id))
        row.status, row.rejection_reason = VerificationStatus.REJECTED, "Synthetic revocation"
        w.db.commit()
    else:
        w.db.scalar(select(UserProfile).where(UserProfile.user_id==w.owner.id)).onboarding_completed = False
        w.db.commit()
    assert upload(w).status_code == (409 if policy=="archived" else 403)
    assert w.client.patch(w.own+"/order",headers=headers(w.owner),json={"images":[ref]}).status_code == (409 if policy=="archived" else 403)
    assert len(images(w)) == 1
    assert w.client.get(w.own+"/"+ref,headers=headers(w.owner)).status_code == 200
    assert w.client.delete(w.own+"/"+ref,headers=headers(w.owner)).status_code == 204


@pytest.mark.parametrize("state", ["pause","archive","suspended","banned","deleted","verification","onboarding",
                                  "email","phone","city","category"])
def test_public_media_never_outlives_parent_visibility(image_world,state):
    w = image_world
    ref = upload(w).json()["ref"]
    action(w.world,w.slug,"publish")
    assert w.client.get(w.public+"/"+ref).status_code == 200
    if state in {"pause","archive"}:
        action(w.world,w.slug,state)
    else:
        if state in {"suspended","banned","deleted"}:
            w.owner.account_status = getattr(AccountStatus,state.upper())
        elif state == "verification":
            row = w.db.scalar(select(SellerVerification).where(SellerVerification.user_id==w.owner.id))
            row.status, row.rejection_reason = VerificationStatus.REJECTED,"Synthetic revocation"
        elif state == "onboarding":
            w.db.scalar(select(UserProfile).where(UserProfile.user_id==w.owner.id)).onboarding_completed=False
        elif state in {"email","phone"}:
            setattr(w.owner,state+"_verified",False)
        else:
            from app.models import ProductListing, City, Category
            product = w.db.scalar(select(ProductListing))
            w.db.get(City if state=="city" else Category,product.city_id if state=="city" else product.category_id).is_active=False
        w.db.commit()
    response = w.client.get(w.public+"/"+ref)
    assert response.status_code == 404 and response.json() == {"detail":"Image not found."}
    assert count(w)==1 and len(list(w.storage.keys()))==1


@pytest.mark.parametrize("payload", [b"MZ executable",b"<svg><script>attack</script></svg>",b"<html>attack</html>",
                                    b"%PDF-1.7",b"PK archive",b"random",b"",b"\xff\xd8\xff"])
def test_fake_mime_never_reaches_storage(image_world,payload):
    w = image_world
    response = upload(w,data=payload,name="../../SECRET.jpg",type="image/jpeg")
    assert response.status_code == 422
    assert "SECRET" not in response.text and count(w)==0 and list(w.storage.keys())==[]


@pytest.mark.parametrize("format", ["GIF","WEBP","PNG"])
def test_animated_upload_rejected(image_world,format):
    w = image_world
    assert upload(w,data=raster(format,animated=True)).status_code==422
    assert count(w)==0 and list(w.storage.keys())==[]


@pytest.mark.parametrize("failure", ["save","flush","commit"])
def test_upload_failure_rolls_back_compensates_and_recovers_session(image_world,monkeypatch,failure):
    w = image_world
    with monkeypatch.context() as fault:
        def fail(*args,**kwargs):
            raise RuntimeError("SYNTHETIC SECRET SQL PATH")
        if failure=="save":
            fault.setattr(w.storage,"save",fail)
        elif failure=="commit":
            commit = SessionTransaction.commit
            def failed_metadata_commit(transaction, *args, **kwargs):
                if (transaction.session is w.db and transaction.parent is None
                    and any(isinstance(row, ProductImage) for row in w.db.identity_map.values())):
                    fail()
                return commit(transaction, *args, **kwargs)
            fault.setattr(SessionTransaction,"commit",failed_metadata_commit)
        else:
            original=w.db.flush
            def flush(*args,**kwargs):
                if any(isinstance(row,ProductImage) for row in w.db.new):
                    fail()
                return original(*args,**kwargs)
            fault.setattr(w.db,"flush",flush)
        response=upload(w)
        assert response.status_code==503 and "SYNTHETIC SECRET" not in response.text
    assert count(w)==0 and list(w.storage.keys())==[] and w.db.is_active
    assert upload(w).status_code==201


def test_compensation_failure_is_detectable_and_never_exposed(image_world,monkeypatch,caplog):
    w=image_world
    with monkeypatch.context() as fault:
        def fail(*args,**kwargs):
            raise RuntimeError("SYNTHETIC CLEANUP FAILURE")
        commit = SessionTransaction.commit
        def failed_post_storage_commit(transaction, *args, **kwargs):
            if transaction.session is w.db and transaction.parent is None and list(w.storage.keys()):
                fail()
            return commit(transaction, *args, **kwargs)
        fault.setattr(SessionTransaction,"commit",failed_post_storage_commit)
        fault.setattr(w.storage,"delete",fail)
        assert upload(w).status_code==503
    key=next(iter(w.storage.keys()))
    assert count(w)==0 and "COMPENSATION_FAILED" in caplog.text and key not in caplog.text
    audit=ProductImageService(w.storage).audit(w.db)
    assert audit["report_only"] and len(audit["issues"])==1 and audit["issues"][0]["problem"]=="orphan_object"
    assert key not in str(audit) and str(w.storage.root) not in str(audit)
    w.storage.delete(key)


def test_physical_delete_failure_commits_revocation_and_reports_orphan(image_world,monkeypatch,caplog):
    w=image_world
    ref=upload(w).json()["ref"]
    action(w.world,w.slug,"publish")
    key=next(iter(w.storage.keys()))
    with monkeypatch.context() as fault:
        def fail(*args,**kwargs):
            raise OSError("SYNTHETIC PRIVATE STORAGE PATH")
        fault.setattr(w.storage,"delete",fail)
        assert w.client.delete(w.own+"/"+ref,headers=headers(w.owner)).status_code==204
    assert count(w)==0 and "DELETE_CLEANUP_FAILED" in caplog.text and key not in caplog.text
    assert w.client.get(w.public+"/"+ref).status_code==404
    assert ProductImageService(w.storage).audit(w.db)["issues"][0]["problem"]=="orphan_object"
    w.storage.delete(key)


def test_missing_object_is_reported_without_deleting_metadata(image_world):
    w=image_world
    ref=upload(w).json()["ref"]
    action(w.world,w.slug,"publish")
    w.storage.delete(next(iter(w.storage.keys())))
    for path,auth in ((w.own+"/"+ref,headers(w.owner)),(w.public+"/"+ref,{})):
        response=w.client.get(path,headers=auth)
        assert response.status_code==404 and str(w.storage.root) not in response.text
    assert count(w)==1 and ProductImageService(w.storage).audit(w.db)["issues"]==[{"ref":ref,"problem":"missing_object"}]


def test_random_storage_key_collision_never_deletes_existing_bytes(image_world,monkeypatch):
    w=image_world
    ref=upload(w).json()["ref"]
    key=next(iter(w.storage.keys()))
    original=w.storage.read(key)
    monkeypatch.setattr("app.services.product_image_service.generate_storage_key",lambda:key)
    assert upload(w).status_code==503
    assert w.storage.read(key)==original and count(w)==1
    assert images(w)[0]["ref"]==ref


def test_ref_collision_retries_only_named_constraint_and_exhaustion_compensates(image_world,monkeypatch):
    w=image_world
    ref=upload(w).json()["ref"]
    generated=generate_image_ref()
    choices=iter([ref,generated])
    with monkeypatch.context() as fault:
        fault.setattr("app.repositories.product_image_repository.generate_image_ref",lambda:next(choices))
        assert upload(w).json()["ref"]==generated
    with monkeypatch.context() as fault:
        fault.setattr("app.repositories.product_image_repository.generate_image_ref",lambda:ref)
        assert upload(w).status_code==503
    assert count(w)==2 and len(list(w.storage.keys()))==2


def test_unrelated_integrity_error_is_not_retried(image_world,monkeypatch):
    w=image_world
    calls=[]
    def ref():
        calls.append(generate_image_ref())
        return calls[-1]
    monkeypatch.setattr("app.repositories.product_image_repository.generate_image_ref",ref)
    with pytest.raises(IntegrityError) as error:
        ProductImageRepository().create(w.db,product_listing_id=str(uuid4()),storage_key=generate_storage_key(),
            mime_type="image/png",width=1,height=1,file_size=10,position=0)
    assert error.value.orig.args[0]==1452 and len(calls)==1 and w.db.is_active
    assert upload(w).status_code==201


def test_mutable_fields_and_foreign_product_refs_are_rejected(image_world):
    w=image_world
    ref=upload(w).json()["ref"]
    row=w.db.scalar(select(ProductImage))
    for field,value in (("public_ref",generate_image_ref()),("storage_key",generate_storage_key()),
                        ("product_listing_id",str(uuid4())),("width",999)):
        with pytest.raises(ValueError):
            setattr(row,field,value)
    with pytest.raises(ValueError):
        ProductImageOrder(images=[ref,ref])
    forged=w.client.patch(w.own+"/order",headers=headers(w.owner),
                         json={"images":[ref],"storage_key":"PRIVATE FIELD","product_id":str(uuid4())})
    assert forged.status_code==422 and "PRIVATE FIELD" not in forged.text


def test_multipart_rejects_fields_multiple_files_and_wrong_part_name(image_world):
    w=image_world
    for options in (
        {"files":{"other":("x.png",raster(),"image/png")}},
        {"files":[("file",("x.png",raster(),"image/png")),("file",("y.png",raster(),"image/png"))]},
        {"files":{"file":("x.png",raster(),"image/png")},"data":{"owner_id":"PRIVATE VALUE"}},
    ):
        response=w.client.post(w.own,headers=headers(w.owner),**options)
        assert response.status_code==400 and "PRIVATE VALUE" not in response.text
    assert count(w)==0 and list(w.storage.keys())==[]


def test_actual_raw_and_multipart_bounds_ignore_forged_length(image_world):
    w=image_world
    assert upload(w,data=b"x"*(MAX_RAW_BYTES+1)).status_code==422
    response=w.client.post(w.own,headers={**headers(w.owner),"Content-Type":"multipart/form-data; boundary=x",
        "Content-Length":"1"},content=b"x"*(MAX_MULTIPART_BYTES+1))
    assert response.status_code==413 and count(w)==0 and list(w.storage.keys())==[]


def test_malformed_uploads_charge_peer_limit_before_auth_parse_or_decode(image_world,monkeypatch):
    w=image_world
    def forbid(*args,**kwargs):
        pytest.fail("malformed multipart reached raster decoding")
    monkeypatch.setattr("app.services.product_image_service.sanitize_product_image",forbid)
    for attempt in range(37):
        response=w.client.post(w.own,content=b"malformed",headers={"Authorization":"Bearer invalid",
            "Content-Type":"multipart/form-data; boundary=absent","X-Forwarded-For":f"198.51.100.{attempt}"})
        assert response.status_code==(401 if attempt<36 else 429)
    assert count(w)==0


def test_authenticated_upload_limit_precedes_decoder(image_world,monkeypatch):
    w=image_world
    calls=[]
    def reject(data):
        from app.services.product_image_sanitizer import UnsafeProductImage
        calls.append(data)
        raise UnsafeProductImage("synthetic")
    monkeypatch.setattr("app.services.product_image_service.sanitize_product_image",reject)
    for attempt in range(11):
        assert upload(w).status_code==(422 if attempt<10 else 429)
    assert len(calls)==10 and count(w)==0

@pytest.mark.parametrize("field,value", [
    ("width",0),("height",6001),("width",-1),("file_size",0),("file_size",MAX_RAW_BYTES+1),
    ("position",-1),("position",16),("mime_type","image/svg+xml"),("storage_key","../../private"),
    ("public_ref","img-"+"A"*32),
])
def test_mysql_image_checks_are_authoritative(image_world,field,value):
    w=image_world
    upload(w)
    row=w.db.scalar(select(ProductImage))
    with pytest.raises(OperationalError) as error:
        with w.db.begin_nested():
            w.db.execute(update(ProductImage).where(ProductImage.id==row.id).values(**{field:value}))
    assert error.value.orig.args[0]==3819 and w.db.is_active
    assert count(w)==1


@pytest.mark.parametrize("operation", ["delete","reorder"])
def test_metadata_commit_failure_never_deletes_bytes_or_changes_order(image_world,monkeypatch,operation):
    w=image_world
    refs=[upload(w).json()["ref"] for _ in range(2)]
    before=images(w)
    keys=set(w.storage.keys())
    with monkeypatch.context() as fault:
        def fail():
            raise RuntimeError("SYNTHETIC COMMIT FAILURE")
        fault.setattr(w.db,"commit",fail)
        response=(w.client.delete(w.own+"/"+refs[0],headers=headers(w.owner)) if operation=="delete" else
            w.client.patch(w.own+"/order",headers=headers(w.owner),json={"images":refs[::-1]}))
        assert response.status_code==503
    assert images(w)==before and set(w.storage.keys())==keys and w.db.is_active


def test_foreign_image_ref_cannot_be_rebound_or_read_under_another_product(image_world):
    w=image_world
    first=upload(w).json()["ref"]
    second_slug=w.client.post(OWN,headers=headers(w.other),json=body()).json()["public_slug"]
    second_path=f"{OWN}/{second_slug}/images"
    second=w.client.post(second_path,headers=headers(w.other),
        files={"file":("second.png",raster(),"image/png")}).json()["ref"]
    action(w.world,w.slug,"publish")
    assert w.client.get(w.public+"/"+second).json()=={"detail":"Image not found."}
    assert w.client.get(w.own+"/"+second,headers=headers(w.owner)).status_code==404
    assert w.client.delete(w.own+"/"+second,headers=headers(w.owner)).status_code==404
    assert images(w)[0]["ref"]==first
    assert w.client.get(second_path,headers=headers(w.other)).json()[0]["ref"]==second


def test_listing_delete_is_restricted_and_safe_metadata_queries_are_bounded(image_world):
    from app.models import ProductListing
    from sqlalchemy import event
    w=image_world
    upload(w)
    product=w.db.scalar(select(ProductListing))
    with pytest.raises(IntegrityError) as error:
        with w.db.begin_nested():
            w.db.delete(product)
            w.db.flush()
    assert error.value.orig.args[0]==1451 and count(w)==1
    action(w.world,w.slug,"publish")
    statements=[]
    def observe(connection,cursor,statement,parameters,context,many):
        if statement.lstrip().upper().startswith("SELECT") and "product_images" in statement:
            statements.append(statement)
    event.listen(w.db.bind,"before_cursor_execute",observe)
    try:
        assert w.client.get(PUBLIC+w.slug).status_code==200
        assert len(statements)==1
    finally:
        event.remove(w.db.bind,"before_cursor_execute",observe)

def test_deadlock_retry_never_repeats_storage_or_decoder(image_world,monkeypatch):
    from pymysql.err import OperationalError as DriverError
    w=image_world
    calls={"metadata":0,"storage":0,"decode":0}
    original=ProductImageRepository.create
    save=w.storage.save
    from app.services.product_image_sanitizer import sanitize_product_image
    def metadata(self,db,**values):
        calls["metadata"]+=1
        if calls["metadata"]==1:
            raise OperationalError("synthetic",None,DriverError(1213,"Synthetic deadlock"))
        return original(self,db,**values)
    def store(key,data):
        calls["storage"]+=1
        return save(key,data)
    def decode(data):
        calls["decode"]+=1
        return sanitize_product_image(data)
    monkeypatch.setattr(ProductImageRepository,"create",metadata)
    monkeypatch.setattr(w.storage,"save",store)
    monkeypatch.setattr("app.services.product_image_service.sanitize_product_image",decode)
    assert upload(w).status_code==201
    assert calls=={"metadata":2,"storage":1,"decode":1} and count(w)==1


@pytest.mark.parametrize("change", ["archive","approval","quota"])
def test_final_metadata_commit_rechecks_authority_and_quota(image_world,monkeypatch,change):
    from app.services.product_service import ProductService
    from app.services.product_image_service import ProductImageError
    from app.core.authorization import AuthorizationError
    w=image_world
    if change=="quota":
        for _ in range(7):
            upload(w)
    service=ProductImageService(w.storage)
    insert=service._insert_metadata
    def changed(db,user_id,slug,key,clean):
        if change=="archive":
            ProductService().transition(db,user_id,slug,"archive")
        elif change=="approval":
            row=db.scalar(select(SellerVerification).where(SellerVerification.user_id==user_id))
            row.status,row.rejection_reason=VerificationStatus.REJECTED,"Synthetic approval change"
            db.commit()
        else:
            ProductImageService(w.storage).upload(db,user_id,slug,BytesIO(raster()))
        return insert(db,user_id,slug,key,clean)
    monkeypatch.setattr(service,"_insert_metadata",changed)
    with pytest.raises((ProductImageError,AuthorizationError)) as error:
        service.upload(w.db,w.owner.id,w.slug,BytesIO(raster()))
    assert error.value.status==(403 if change=="approval" else 409)
    assert count(w)==(8 if change=="quota" else 0)
    assert len(list(w.storage.keys()))==count(w)
