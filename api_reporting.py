import logging
import requests

HEADERS = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

def auth_to_api(hostname, username, password, validate_ssl=True):
    return_json = {
        "success": False,
        "errors": []
    }
    url = f"https://{hostname}/api/v1/auth/login/"

    headers = HEADERS
    payload = {
        'username': username,
        'password': password
    }
    try:
        response = requests.post(url,
                                 headers=headers,
                                 json=payload,
                                 verify=validate_ssl,
                                    )
        response.raise_for_status()
        result = response.json()
        token = result.get('token')

        if not token:
            return_json["errors"].append("Authentication successful but no token was returned")

        return_json["success"] = True
        return_json["token"] = token
        return return_json

    except requests.exceptions.HTTPError as e:
        logging.warning("raising HTTP error")
        error_msg = str(e)
        try:
            error_data = e.response.json()
            if 'detail' in error_data:
                error_msg = error_data['detail']
            elif 'message' in error_data:
                error_msg = error_data['message']
        except (ValueError, AttributeError):
            pass
         
        return_json["errors"].append(f"Authentication failed: {error_msg}")
        return return_json

    except requests.exceptions.RequestException as e:
        logging.warning("raising exception error")
        return_json["errors"].append(f"Request Error: {str(e)}")
        return return_json

def find_edge_by_params(hostname, token, serial, validate_ssl=True,):
    api_base = f"https://{hostname}/api/v1.2/filers/"
    share = None
    headers = HEADERS
    headers['Authorization'] = f"Token {token}"
    next_query = api_base
    while True:
        if share is not None:
            break
        shares = requests.get(next_query, headers=headers, verify=validate_ssl).json()
        for s in shares['items']:
            if s['serial_number'] == serial:
                share = s
                break
        if shares['next'] is None:
            break
        next_query = shares['next']
        # Turning the 'page' in case we need to search the search query beyond the original 50 edges.
    return share

