import pytest
import responses

from sigma_sdlc.client.sigma_client import SigmaAPIError, SigmaClient

BASE_URL = "https://api.example.com"


@pytest.fixture
def client():
    return SigmaClient(BASE_URL, "test-token")


class TestAuthenticate:
    @responses.activate
    def test_successful_auth(self):
        responses.post(
            f"{BASE_URL}/v2/auth/token",
            json={"access_token": "bearer-123"},
            status=200,
        )
        client = SigmaClient.authenticate(BASE_URL, "id", "secret")
        assert client.session.headers["Authorization"] == "Bearer bearer-123"

    @responses.activate
    def test_invalid_credentials(self):
        responses.post(
            f"{BASE_URL}/v2/auth/token",
            json={"error": "unauthorized"},
            status=401,
        )
        with pytest.raises(SigmaAPIError, match="Invalid client credentials"):
            SigmaClient.authenticate(BASE_URL, "bad-id", "bad-secret")


class TestGetWorkspaces:
    @responses.activate
    def test_returns_workspaces(self, client):
        responses.get(
            f"{BASE_URL}/v2/workspaces",
            json={"entries": [{"id": "ws1", "name": "Workspace 1"}]},
        )
        result = client.get_workspaces()
        assert len(result) == 1
        assert result[0]["id"] == "ws1"

    @responses.activate
    def test_pagination(self, client):
        responses.get(
            f"{BASE_URL}/v2/workspaces",
            json={"entries": [{"id": "ws1"}], "nextPage": "page2"},
        )
        responses.get(
            f"{BASE_URL}/v2/workspaces",
            json={"entries": [{"id": "ws2"}]},
        )
        result = client.get_workspaces()
        assert len(result) == 2


class TestGetDataModels:
    @responses.activate
    def test_returns_models(self, client):
        responses.get(
            f"{BASE_URL}/v2/workspaces/ws1/data-models",
            json={"entries": [{"id": "dm1"}]},
        )
        result = client.get_data_models("ws1")
        assert result[0]["id"] == "dm1"


class TestGetDataModel:
    @responses.activate
    def test_returns_model(self, client):
        responses.get(
            f"{BASE_URL}/v2/data-models/dm1",
            json={"id": "dm1", "name": "Test Model"},
        )
        result = client.get_data_model("dm1")
        assert result["name"] == "Test Model"

    @responses.activate
    def test_not_found(self, client):
        responses.get(f"{BASE_URL}/v2/data-models/bad", status=404)
        with pytest.raises(SigmaAPIError, match="not found"):
            client.get_data_model("bad")


class TestCreateDataModel:
    @responses.activate
    def test_creates_model(self, client):
        responses.post(
            f"{BASE_URL}/v2/data-models",
            json={"id": "new1", "name": "New Model"},
            status=201,
        )
        result = client.create_data_model({"name": "New Model"})
        assert result["id"] == "new1"


class TestUpdateDataModel:
    @responses.activate
    def test_updates_model(self, client):
        responses.put(
            f"{BASE_URL}/v2/data-models/dm1",
            json={"id": "dm1", "name": "Updated"},
        )
        result = client.update_data_model("dm1", {"name": "Updated"})
        assert result["name"] == "Updated"


class TestErrorHandling:
    @responses.activate
    def test_401_error(self, client):
        responses.get(f"{BASE_URL}/v2/workspaces", status=401)
        with pytest.raises(SigmaAPIError, match="Authentication failed"):
            client.get_workspaces()

    @responses.activate
    def test_server_error_retries(self, client):
        responses.get(f"{BASE_URL}/v2/data-models/dm1", status=500)
        responses.get(f"{BASE_URL}/v2/data-models/dm1", status=500)
        responses.get(
            f"{BASE_URL}/v2/data-models/dm1",
            json={"id": "dm1"},
        )
        # Patch sleep to avoid waiting
        import unittest.mock
        with unittest.mock.patch("sigma_sdlc.client.sigma_client.time.sleep"):
            result = client.get_data_model("dm1")
        assert result["id"] == "dm1"

    @responses.activate
    def test_server_error_exhausts_retries(self, client):
        for _ in range(3):
            responses.get(f"{BASE_URL}/v2/data-models/dm1", status=500)

        import unittest.mock
        with unittest.mock.patch("sigma_sdlc.client.sigma_client.time.sleep"):
            with pytest.raises(SigmaAPIError, match="Server error"):
                client.get_data_model("dm1")

    @responses.activate
    def test_rate_limit_retries(self, client):
        responses.get(f"{BASE_URL}/v2/data-models/dm1", status=429)
        responses.get(
            f"{BASE_URL}/v2/data-models/dm1",
            json={"id": "dm1"},
        )
        import unittest.mock
        with unittest.mock.patch("sigma_sdlc.client.sigma_client.time.sleep"):
            result = client.get_data_model("dm1")
        assert result["id"] == "dm1"
