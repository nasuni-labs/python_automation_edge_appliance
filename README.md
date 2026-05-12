### Nasuni Wizard Deployment

This script is tested on Python 3.13.3 with a 10.2.1 Edge.

A list of python packages that are required and the versions they were tested on is in requirements.txt.

In addition to installing the packages, 'playwright install' must be run to install the playwright browsers.

A list of required variables can be found in vars_example.json. 

Any variables in vars_example.json that one wants pulled from a secret should be placed in the Key Vault Vars subdictionary.

Anything that you want listed as plaintext can be placed in the Plain_Vars.

Explanations for the listed variables can be found in key_retriever.py

Run 'python3 entrypoint.py' to run the script. The script expects vars.json to be a reachable file; it uses that for variables



