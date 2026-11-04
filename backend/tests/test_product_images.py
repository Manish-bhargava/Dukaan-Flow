"""Product details endpoint and admin image upload to Cloudinary (faked at the HTTP layer)."""

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token
from app.models import Product
from app.modules.products import images
from seed.run_seed import seed_id
from tests.conftest import seed_user

BS075 = seed_id("product", "SKU-BS-075")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
SECURE_URL = "https://res.cloudinary.com/demo-cloud/image/upload/v1730700000/dukaanflow/products/sku-bs-075.png"


@pytest.fixture
def as_user(tx_client, tx):
    def call(key, method, url, **kw):
        token, _ = create_access_token(seed_user(tx, key))
        return tx_client.request(method, f"/api/v1{url}", headers={"Authorization": f"Bearer {token}"}, **kw)
    return call


class FakeCloudinary:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": "Invalid Signature"}})
        return httpx.Response(200, json={"secure_url": SECURE_URL, "public_id": "dukaanflow/products/sku-bs-075"})


@pytest.fixture
def cloudinary(monkeypatch):
    fake = FakeCloudinary()
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "demo-cloud")
    monkeypatch.setattr(settings, "CLOUDINARY_API_KEY", "123456")
    monkeypatch.setattr(settings, "CLOUDINARY_API_SECRET", "test-secret")
    monkeypatch.setattr(images, "_http_client", lambda: httpx.Client(transport=httpx.MockTransport(fake.handler)))
    return fake


def upload(as_user, key="admin", content=PNG, content_type="image/png"):
    return as_user(key, "POST", f"/products/{BS075}/image", files={"file": ("pack.png", content, content_type)})


# ---------------------------------------------------------------- delivery URLs


def test_delivery_url_adds_auto_format_quality_and_padding():
    assert images.delivery_url(SECURE_URL, 800) == (
        "https://res.cloudinary.com/demo-cloud/image/upload/f_auto,q_auto,c_pad,b_white,w_800,h_800/"
        "v1730700000/dukaanflow/products/sku-bs-075.png"
    )


@pytest.mark.parametrize("url", [None, "", "https://example.com/biscuit.png", "/local/placeholder.svg"])
def test_non_cloudinary_urls_are_unchanged(url):
    assert images.delivery_url(url, 800) == url


def test_signature_matches_cloudinary_algorithm():
    # Example from Cloudinary's signing docs: sorted params + secret, SHA-1.
    params = {"timestamp": "1315060510", "public_id": "sample_image", "eager": "w_400,h_300,c_pad|w_260,h_200,c_crop"}
    assert images.sign(params, "abcd") == "bfd09f95f331f558cbd1320e67aa8d488770583e"


# ---------------------------------------------------------------- upload


def test_admin_upload_stores_url_and_public_id(as_user, cloudinary, tx):
    response = upload(as_user)
    assert response.status_code == 200, response.json()
    data = response.json()["data"]
    assert data["image_public_id"] == "dukaanflow/products/sku-bs-075"
    assert "/f_auto,q_auto,c_pad,b_white,w_800,h_800/" in data["image_url"]
    assert ",w_400,h_400/" in data["thumbnail_url"]

    product = tx.scalar(select(Product).where(Product.id == BS075))
    assert (product.image_url, product.image_public_id) == (SECURE_URL, "dukaanflow/products/sku-bs-075")

    # A signed request; the secret itself is never sent.
    [request] = cloudinary.requests
    assert str(request.url) == "https://api.cloudinary.com/v1_1/demo-cloud/image/upload"
    body = request.content
    assert b"test-secret" not in body and b'name="signature"' in body and b'name="api_key"' in body
    assert b"dukaanflow/products/sku-bs-075" in body and b'name="overwrite"' in body

    # Retailers now get optimized URLs in the catalogue and product details.
    listed = next(p for p in as_user("retailer_sharma", "GET", "/products", params={"limit": 100}).json()["data"]["items"]
                  if p["sku"] == "SKU-BS-075")
    assert listed["image_url"] == data["image_url"] and listed["thumbnail_url"] == data["thumbnail_url"]
    assert "test-secret" not in str(listed)


@pytest.mark.parametrize("key", ["order_desk", "retailer_sharma", "salesman_sunil"])
def test_only_admin_can_upload(as_user, cloudinary, key):
    response = upload(as_user, key)
    assert (response.status_code, response.json()["error_code"]) == (403, "FORBIDDEN")
    assert cloudinary.requests == []


@pytest.mark.parametrize("content, content_type", [
    (b"GIF89a" + b"\x00" * 10, "image/gif"),
    (b"not really a png", "image/png"),  # content does not match the declared type
    (b"%PDF-1.7", "application/pdf"),
])
def test_only_real_jpeg_png_webp_are_accepted(as_user, cloudinary, content, content_type):
    response = upload(as_user, content=content, content_type=content_type)
    assert (response.status_code, response.json()["error_code"]) == (422, "VALIDATION_ERROR")
    assert cloudinary.requests == []


def test_jpeg_is_accepted(as_user, cloudinary):
    assert upload(as_user, content=JPEG, content_type="image/jpeg").status_code == 200


def test_images_over_5_mb_are_refused(as_user, cloudinary):
    big = PNG + b"\x00" * images.MAX_BYTES
    response = upload(as_user, content=big)
    assert response.status_code == 422 and "5 MB" in response.json()["message"]
    assert cloudinary.requests == []


def test_not_configured_returns_503_and_keeps_placeholder(as_user, tx):
    response = upload(as_user)
    assert (response.status_code, response.json()["error_code"]) == (503, "IMAGE_STORAGE_NOT_CONFIGURED")
    assert tx.scalar(select(Product.image_url).where(Product.id == BS075)) is None


def test_cloudinary_error_is_reported_without_saving(as_user, cloudinary, tx):
    cloudinary.status = 401
    response = upload(as_user)
    assert (response.status_code, response.json()["error_code"]) == (502, "IMAGE_UPLOAD_FAILED")
    assert tx.scalar(select(Product.image_url).where(Product.id == BS075)) is None


def test_unknown_product_upload_is_404(as_user, cloudinary):
    response = as_user("admin", "POST", f"/products/{seed_id('product', 'nope')}/image",
                       files={"file": ("x.png", PNG, "image/png")})
    assert response.status_code == 404


# ---------------------------------------------------------------- product details


def test_product_details_with_own_price_stock_and_scheme(as_user):
    response = as_user("retailer_sharma", "GET", f"/products/{BS075}")
    assert response.status_code == 200
    p = response.json()["data"]
    assert (p["sku"], p["price"]["case_price"], p["in_stock"]) == ("SKU-BS-075", "777.60", True)
    assert p["schemes"][0]["description"] == "Buy 10 get 1 free"
    assert p["image_url"] is None and p["thumbnail_url"] is None  # placeholder shown by the frontend


def test_product_details_uses_each_retailers_own_price(as_user):
    sharma = as_user("retailer_sharma", "GET", f"/products/{BS075}").json()["data"]["price"]
    gupta = as_user("retailer_gupta", "GET", f"/products/{BS075}").json()["data"]["price"]
    assert sharma != gupta


def test_product_details_access_rules(as_user):
    gupta = str(seed_id("retailer", "gupta"))
    assert as_user("retailer_sharma", "GET", f"/products/{BS075}", params={"retailer_id": gupta}).status_code == 403
    assert as_user("order_desk", "GET", f"/products/{BS075}").status_code == 422  # staff must name a retailer
    assert as_user("order_desk", "GET", f"/products/{BS075}", params={"retailer_id": gupta}).status_code == 200
    assert as_user("retailer_sharma", "GET", f"/products/{seed_id('product', 'nope')}").status_code == 404
