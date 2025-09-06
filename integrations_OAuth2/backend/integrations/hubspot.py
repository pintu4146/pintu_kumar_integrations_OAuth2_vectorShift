# slack.py
import json
import secrets
import asyncio
import base64
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
import time
import httpx
import os

from core.app_logger import get_logger
from integrations.integration_item import IntegrationItem
from redis_client import add_key_value_redis, get_value_redis, delete_key_redis


logger = get_logger(__name__)

CLIENT_ID = os.environ.get('HUBSPOT_CLIENT_ID', '64f2eb48-2bc2-4da3-9353-756774b07a6c')
CLIENT_SECRET = os.environ.get('HUBSPOT_CLIENT_SECRET', 'fb187e7b-f70b-4dd9-a427-a0550f27885d')
REDIRECT_URI = os.environ.get('HUBSPOT_REDIRECT_URI', 'http://localhost:8000/integrations/hubspot/oauth2callback')
SCOPES = os.environ.get('HUBSPOT_SCOPES', 'oauth crm.objects.companies.read')

REDIRECT_URI = 'http://localhost:8000/integrations/hubspot/oauth2callback'

SCOPES = 'oauth crm.objects.companies.read'
 
if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("HUBSPOT_CLIENT_ID and HUBSPOT_CLIENT_SECRET must be set in the environment.")


def get_authorization_url():
    """Constructs the HubSpot authorization URL."""

    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES,
    }
    url = httpx.URL("https://app.hubspot.com/oauth/authorize", params=params)
    return str(url)


async def authorize_hubspot(user_id, org_id):
    """
    Generates the authorization URL and saves the state to Redis.
    """
    state = secrets.token_urlsafe(32)
    # Securely map the state to the user and org IDs
    state_data = json.dumps({'user_id': user_id, 'org_id': org_id})
    await add_key_value_redis(f'hubspot_state:{state}', state_data, expire=600)
    authorization_url = get_authorization_url()
    final_url = f'{authorization_url}&state={state}'
    logger.debug(f"Generated HubSpot authorization URL for user {user_id}")
    return final_url


async def oauth2callback_hubspot(request: Request):
    """
    Handles the OAuth2 callback from HubSpot, exchanges the code for a token.
    """
    if request.query_params.get('error'):
        raise HTTPException(status_code=400, detail=request.query_params.get('error_description', 'Unknown error'))
    code = request.query_params.get('code')
    state = request.query_params.get('state')
    
    state_data_json = await get_value_redis(f'hubspot_state:{state}')
    if not state_data_json:
        raise HTTPException(status_code=400, detail='State does not match or has expired.')

    state_data = json.loads(state_data_json)
    user_id = state_data['user_id']
    org_id = state_data['org_id']

    async with httpx.AsyncClient() as client:
        token_url = 'https://api.hubapi.com/oauth/v1/token'
        payload = {
            'grant_type': 'authorization_code',
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'redirect_uri': REDIRECT_URI,
            'code': code,
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8'}

        response, _ = await asyncio.gather(
            client.post(token_url, data=payload, headers=headers),
            delete_key_redis(f'hubspot_state:{state}')
        )

        response.raise_for_status()

    # Store the timestamp of when the token was created for future refresh logic
    credentials = response.json()
    credentials['created_at'] = int(time.time())

    # Store credentials without a Redis-level expiration. Token lifetime will be managed by the app.
    await add_key_value_redis(f'hubspot_credentials:{org_id}:{user_id}', json.dumps(credentials))

    close_window_script = "<html><script>window.close();</script></html>"
    return HTMLResponse(content=close_window_script)


async def _get_refreshed_token(user_id: str, org_id: str, credentials: dict) -> dict:
    """Refreshes an expired HubSpot access token."""
    logger.info(f"Refreshing HubSpot token for user {user_id}")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'https://api.hubapi.com/oauth/v1/token',
            data={
                'grant_type': 'refresh_token',
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'refresh_token': credentials['refresh_token'],
            }
        )
        response.raise_for_status()
        new_credentials = response.json()
        # Preserve the original refresh token if a new one isn't provided
        new_credentials['refresh_token'] = new_credentials.get('refresh_token', credentials['refresh_token'])
        new_credentials['created_at'] = int(time.time())
        
        # Persist the newly refreshed credentials
        await add_key_value_redis(f'hubspot_credentials:{org_id}:{user_id}', json.dumps(new_credentials))
        return new_credentials


async def get_hubspot_credentials(user_id, org_id):
    """
    Retrieves credentials, refreshing the token if necessary.
    Returns only the access_token for security.
    """
    credentials_json = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}')
    if not credentials_json:
        raise HTTPException(status_code=401, detail='No HubSpot credentials found. Please re-authenticate.')
    
    credentials = json.loads(credentials_json)

    # Refresh the token if it's expired or will expire in the next 5 minutes
    if time.time() > credentials.get('created_at', 0) + credentials.get('expires_in', 0) - 300:
        credentials = await _get_refreshed_token(user_id, org_id, credentials)

    logger.debug(f"Retrieved HubSpot credentials for user {user_id}")
    # Return only the access token to the frontend, not the refresh token or secrets.
    return {"access_token": credentials["access_token"]}

def create_integration_item_metadata_object(item: dict, item_type: str) -> IntegrationItem:
    """Creates a standardized IntegrationItem from a HubSpot API response."""
    properties = item.get('properties', {})
    name = properties.get('company')
    if not name:
        firstname = properties.get('firstname', '')
        lastname = properties.get('lastname', '')
        name = f"{firstname} {lastname}".strip()

    return IntegrationItem(
        id=item.get('id'),
        type=item_type,
        name=name,
        creation_time=item.get('createdAt'),
        last_modified_time=item.get('updatedAt'),
    )


async def get_items_hubspot(credentials):
    """Fetches items (e.g., companies) from HubSpot and converts them to IntegrationItems."""
    # The credentials passed here are now just the access token from the frontend
    credentials = json.loads(credentials) 
    access_token = credentials.get('access_token')
    headers = {'Authorization': f'Bearer {access_token}'}
    list_of_integration_item_metadata = []

    # Example: Fetching companies from HubSpot
    companies_url = 'https://api.hubapi.com/crm/v3/objects/companies'
    async with httpx.AsyncClient() as client:
        response = await client.get(companies_url, headers=headers)
        response.raise_for_status()
        companies = response.json().get('results', [])
        for company in companies:
            list_of_integration_item_metadata.append(
                create_integration_item_metadata_object(company, 'HubSpot Company')
            )

    logger.info(f"Fetched {len(list_of_integration_item_metadata)} companies from HubSpot for user.")
    return list_of_integration_item_metadata