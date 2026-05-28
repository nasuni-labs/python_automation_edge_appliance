from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

def get_keyvault_secret(vault_url: str, secret_name: str) -> str:
    """
    Retrieve a secret value from Azure KeyVault.
    
    Args:
        vault_url: The URL of the KeyVault (e.g., "https://myvault.vault.azure.net/")
        secret_name: The name of the secret to retrieve
    
    Returns:
        The secret value as a string
    
    Raises:
        azure.core.exceptions.ResourceNotFoundError: If the secret doesn't exist
        azure.core.exceptions.ClientAuthenticationError: If authentication fails
    """
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)
    secret = client.get_secret(secret_name)
    return secret.value

KEYS_TO_RETRIEVE = [
    'serial_number',       # Serial number of the Filer
    'auth_code',           # Setting to 'NMC' retrieves the auth code for the above serial automatically.
    'description',         # description of the edge in the NOC and NMC
    'dhcp_hostname',       # description of the edge in the DHCP configuration screen
    'network_setting',     # Set to dhcp or dhcp2. dhcp2 allows customization of DNS, and permits AD join
    'dns_1',               # DNS server number 1
    'dns_2',               # DNS server number 2
    'dns_ad',              # DNS server for the AD screen. Please list this variable, but you may leave it blank or use the same sever as dns_1
    'nmc_join',            # Whether to join the NMC
    'proxy',               # Should be set to 'False'. Proxy support is not currently implemented in the script.
    'accept_eula',         # Should be set to 'y' to accept the EULA. If not accepted, the script will hang unless run in interactive mode.
    'default_gateway',     # Default gateway for the edge. If network_setting is set to dhcp, the default gateway for the cloud provider is used instead
    'search_domain',       # Search domain for the edge. If network_setting is set to dhcp, this variable is not used. Both default gateway and search domain may be set to empty strings.
    'ad_username',         # Username for joining AD
    'ad_password',         # Password for joining AD
    'computer_ou',         # Organizational Unit for the computer account in AD. If blank, the computer account will be created in the default Computers OU.
    'omitted_domains',     # Domains from the trusted forest that you do NOT want Nasuni to trust. Already trusted domains are trusted by default by Nasuni
    'ad_fdqn',             # Fully qualified domain name for the AD domain
    'edge_user',           # Username for the edge appliance. Will be usurped by the NMC if nmc_join is set to true.
    'edge_pass',           # Password for the edge appliance
    'nmc_user',            # Username for the NMC, 
    'nmc_pass',            # Password for the NMC
    'nmc_ip',              # Hostname for the NMC.
    'api_user',            # Exports other information from the API. May be the same as nmc_user
    'api_pass',            # Password for the API user. May be the same as nmc_pass
    'edge_ip',             # IP address for the edge Appliance
    'headless_mode',       # if false, runs the playwright script in a browser window so you can follow the configuaration. Leave true for pipeline builds or builds as a function.
    'validate_ssl',        # if true, validates ssl during API calls and wizard connections
    'local_filer_settings' # Whether to pull filer settings from a similar filer in the environment. If true, the script will likely ignore domain_omits
]

def merge_dictionaries(dict1: dict, dict2: dict, keys: list) -> dict:
    """
    Takes a list of keys expected to be in either of two dictionaries. Returns an error if it's in neither dictionary. If it's in the first dictionary, returns the value from the first dictionary. If it's from the second dictionary,
    uses the value as a Key with the key_vault_uri listed in the first dictionary to complete the dictionary. Returns the completed dictionary."""
    output_dict = {}
    raw_string_dict_keys = dict1.keys()
    key_vault_dict_keys = dict2.keys()
    if "key_vault_uri" not in raw_string_dict_keys:
        raise KeyError("key_vault_uri is not in the first dictionary. This is required to retrieve secrets from the key vault.")
    key_vault_uri = dict1["key_vault_uri"]
    for i in KEYS_TO_RETRIEVE:
        if i in raw_string_dict_keys:
            output_dict[i] = dict1[i]
        elif i in key_vault_dict_keys:
            output_dict[i] = get_keyvault_secret(key_vault_uri, dict2[i])
        else:
            raise KeyError(f"{i} is not in either dictionary. Please check the input dictionaries.")
    return output_dict