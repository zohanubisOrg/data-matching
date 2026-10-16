import pytest
from unittest.mock import MagicMock, patch
from product_mapper.harvest.openfoodfacts_client import OpenFoodFactsClient


def test_openfoodfacts_client_fetch_success():
    client = OpenFoodFactsClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": 1,
        "product": {
            "product_name": "Test Soy Sauce",
            "image_front_url": "https://images.openfoodfacts.org/images/products/123/front_en.jpg",
        },
    }

    with patch.object(client.session, "get", return_value=mock_resp):
        url = client.get_front_packshot_url("1234567890123")
        assert url == "https://images.openfoodfacts.org/images/products/123/front_en.jpg"


def test_openfoodfacts_client_not_found():
    client = OpenFoodFactsClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch.object(client.session, "get", return_value=mock_resp):
        url = client.get_front_packshot_url("0000000000000")
        assert url is None


def test_openfoodfacts_client_selected_images_fallback():
    client = OpenFoodFactsClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": 1,
        "product": {
            "selected_images": {
                "front": {
                    "display": {
                        "fr": "https://images.openfoodfacts.org/display_fr.jpg"
                    }
                }
            }
        },
    }

    with patch.object(client.session, "get", return_value=mock_resp):
        url = client.get_front_packshot_url("9999999999999")
        assert url == "https://images.openfoodfacts.org/display_fr.jpg"
