import base64
import requests
import yaml


def get_sigma_access_token(env='staging'):
    """
    Get an access token from Sigma Computing API.

    Args:
        env: Environment to use from credentials.yml (default: 'staging')

    Returns:
        dict: Response containing access_token, refresh_token, and expires_in
    """
    # Load credentials from YAML file
    with open('credentials.yml', 'r') as f:
        credentials = yaml.safe_load(f)

    creds = credentials[env]
    base_url = creds['url']
    client_id = creds['client']
    client_secret = creds['secret']

    # Create Basic Auth header by base64 encoding "client_id:client_secret"
    auth_string = f"{client_id}:{client_secret}"
    auth_bytes = auth_string.encode('ascii')
    base64_auth = base64.b64encode(auth_bytes).decode('ascii')

    # Set up headers and request body
    headers = {
        'Authorization': f'Basic {base64_auth}',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }

    data = {
        'grant_type': 'client_credentials'
    }

    # Make POST request to token endpoint
    url = f"{base_url}/v2/auth/token"
    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()

    return response.json()


if __name__ == '__main__':
    # Example usage
    token_response = get_sigma_access_token()
    print(f"Access Token: {token_response['access_token']}")
    print(f"Expires in: {token_response['expires_in']} seconds")
