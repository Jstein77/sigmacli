import base64
import logging
import time

import requests

logger = logging.getLogger(__name__)


class SigmaAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Sigma API error ({status_code}): {message}")


class SigmaClient:
    def __init__(self, base_url: str, bearer_token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
            }
        )

    @classmethod
    def authenticate(cls, base_url: str, client_id: str, client_secret: str) -> "SigmaClient":
        """Authenticate using client credentials and return a SigmaClient."""
        base_url = base_url.rstrip("/")
        credentials = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()

        logger.debug("Authenticating with %s", base_url)
        resp = requests.post(
            f"{base_url}/v2/auth/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        )

        if resp.status_code == 401:
            raise SigmaAPIError(401, "Invalid client credentials")
        resp.raise_for_status()

        token = resp.json()["access_token"]
        logger.debug("Authentication successful")
        return cls(base_url, token)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an API request with retry and error handling."""
        url = f"{self.base_url}{path}"
        max_retries = 3

        for attempt in range(max_retries):
            logger.debug("%s %s (attempt %d)", method, url, attempt + 1)
            resp = self.session.request(method, url, **kwargs)

            if resp.status_code == 401:
                raise SigmaAPIError(401, "Authentication failed. Please re-authenticate.")
            if resp.status_code == 404:
                raise SigmaAPIError(404, f"Resource not found: {path}")
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning("Rate limited, waiting %ds", wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning("Server error %d, retrying in %ds", resp.status_code, wait)
                    time.sleep(wait)
                    continue
                raise SigmaAPIError(resp.status_code, f"Server error after {max_retries} retries")

            resp.raise_for_status()
            return resp.json() if resp.content else {}

        raise SigmaAPIError(429, f"Rate limited after {max_retries} retries")

    def _paginate(self, path: str, **kwargs) -> list:
        """Fetch all pages of a paginated endpoint."""
        results = []
        params = kwargs.pop("params", {})

        while True:
            data = self._request("GET", path, params=params, **kwargs)
            entries = data.get("entries", data.get("data", []))
            results.extend(entries)

            next_page = data.get("nextPage")
            if not next_page:
                break
            params["page"] = next_page

        return results

    def get_workspaces(self) -> list:
        return self._paginate("/v2/workspaces")

    def get_data_models(self, workspace_id: str) -> list:
        return self._paginate(f"/v2/workspaces/{workspace_id}/data-models")

    def get_data_model(self, model_id: str) -> dict:
        return self._request("GET", f"/v2/data-models/{model_id}")

    def create_data_model(self, config: dict) -> dict:
        return self._request("POST", "/v2/data-models", json=config)

    def update_data_model(self, model_id: str, config: dict) -> dict:
        return self._request("PUT", f"/v2/data-models/{model_id}", json=config)
