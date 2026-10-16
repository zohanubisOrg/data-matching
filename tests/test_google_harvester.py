import io
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from product_mapper.harvest.google_images_harvester import GoogleImagesHarvester
from product_mapper.harvest.image_downloader import ImageDownloaderAndFilter


def test_google_images_parse_html():
    harvester = GoogleImagesHarvester()
    sample_html = '''
    <html>
        <script>
            var data = [["https://example.com/packshot.jpg", 1200, 1200], ["https://gstatic.com/thumb.jpg", 100, 100]];
        </script>
        <img src="https://supplier.eu/products/noodles.png" />
    </html>
    '''
    candidates = harvester.parse_image_urls_from_html(sample_html)
    assert len(candidates) >= 1
    assert any("packshot.jpg" in c.url for c in candidates)
    assert not any("gstatic.com" in c.url for c in candidates)


def test_image_downloader_and_filter_valid():
    downloader = ImageDownloaderAndFilter(min_dim=100)
    # Create sample image
    test_img = Image.new("RGB", (200, 200), color="white")
    buf = io.BytesIO()
    test_img.save(buf, format="JPEG")
    raw = buf.getvalue()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "image/jpeg"}
    mock_resp.content = raw

    with patch.object(downloader.session, "get", return_value=mock_resp):
        img, data, reason = downloader.download_and_validate("https://valid.com/item.jpg")
        assert img is not None
        assert data is not None
        assert reason == "OK"


def test_image_downloader_and_filter_resolution_low():
    downloader = ImageDownloaderAndFilter(min_dim=600)
    test_img = Image.new("RGB", (200, 200), color="white")
    buf = io.BytesIO()
    test_img.save(buf, format="JPEG")
    raw = buf.getvalue()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "image/jpeg"}
    mock_resp.content = raw

    with patch.object(downloader.session, "get", return_value=mock_resp):
        img, data, reason = downloader.download_and_validate("https://lowres.com/item.jpg")
        assert img is None
        assert "Resolution too low" in reason
