"""
Sigma Computing API client for authentication and making API requests.
"""
import requests
import yaml
from setup_sigma_connection import get_sigma_access_token


class SigmaClient:
    """Simple Sigma API client."""

    def __init__(self, env='staging'):
        """Initialize client with access token."""
        token_response = get_sigma_access_token(env)
        self.access_token = token_response['access_token']

        # Load base URL from credentials
        with open('credentials.yml', 'r') as f:
            credentials = yaml.safe_load(f)
        self.base_url = credentials[env]['url']

    def _get_headers(self):
        """Get headers with bearer token."""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json'
        }

    def get(self, endpoint, params=None):
        """Make GET request to Sigma API."""
        url = self.base_url + endpoint
        response = requests.get(url, headers=self._get_headers(), params=params)
        response.raise_for_status()
        return response.json()

    def get_raw(self, endpoint, params=None):
        """Make GET request and return raw response (doesn't raise on error)."""
        url = self.base_url + endpoint
        response = requests.get(url, headers=self._get_headers(), params=params)
        return response

    def post(self, endpoint, json_data=None):
        """Make POST request to Sigma API."""
        url = self.base_url + endpoint
        headers = self._get_headers()
        headers['Content-Type'] = 'application/json'
        response = requests.post(url, headers=headers, json=json_data)
        return response

    def put(self, endpoint, json_data=None):
        """Make PUT request to Sigma API."""
        url = self.base_url + endpoint
        headers = self._get_headers()
        headers['Content-Type'] = 'application/json'
        response = requests.put(url, headers=headers, json=json_data)
        return response

    def get_paginated(self, endpoint, params=None):
        """Get all results from a paginated endpoint using token-based pagination."""
        if params is None:
            params = {}

        all_entries = []
        next_page = None

        while True:
            # Use the nextPage token from previous response
            if next_page:
                params['page'] = next_page
            elif 'page' in params:
                # Remove page param for first request
                del params['page']

            result = self.get(endpoint, params)

            entries = result.get('entries', [])
            if not entries:
                break

            all_entries.extend(entries)

            # Get the nextPage token for the next iteration
            next_page = result.get('nextPage')

            # Check if there are more pages
            if not next_page or not result.get('hasMore', False):
                break

        return all_entries
