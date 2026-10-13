"""Report-only product-media consistency check; never delete rows or objects."""
from pathlib import Path
import argparse
import json
import sys

BACKEND=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()  # No destructive mode or operator-supplied keys/paths.
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.core.database import engine
    from app.services.product_image_service import ProductImageService
    from app.services.product_image_storage import product_image_storage
    try:
        with Session(engine) as db:
            result=ProductImageService(product_image_storage(settings)).audit(db)
        print(json.dumps(result))
        return 1 if result["issues"] else 0
    except Exception:
        print(json.dumps({"report_only":True,"status":"unavailable","detail":"Media audit unavailable."}))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
