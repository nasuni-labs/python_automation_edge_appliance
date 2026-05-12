import logging

from playwright.sync_api import Page, sync_playwright
from ea_wizard_crawler import edge_run_wrapper
from key_retriever import KEYS_TO_RETRIEVE, merge_dictionaries
import time
import json
from api_reporting import auth_to_api


def nmc_logon(page: Page, ip: str, username: str, password: str):
        """Logs a playwright page onto the NMC at the given IP
        Args:
            page (p_page): The playwright page to be logged into the NMC
            ip (str): The ip/hostname of the NMC to be logged into
            username (str): username for the nmc
            password (str): password for the nmc

        Returns:
        """
        page.goto(f"https://{ip}/login/?next=/")
        page.get_by_placeholder("Username").fill(username)
        page.get_by_placeholder("Password").fill(password)
        page.get_by_placeholder("Password").press("Enter")
        time.sleep(3)
        if page.get_by_placeholder("Username").is_visible():
            return 1
        else:
            return page


if __name__ == "__main__":
    with open("vars.json", "r") as f:
        raw_string_dict = json.load(f)
        merged_vars = merge_dictionaries(raw_string_dict["Plain_Vars"], raw_string_dict["Key_Vault_Vars"], KEYS_TO_RETRIEVE)
        try:
            token = auth_to_api(merged_vars["nmc_ip"], merged_vars["api_user"], merged_vars["api_pass"], merged_vars["validate_ssl"])["token"]
        except TypeError as e:
            logging.error("Failed to authenticate to the API. Please check your credentials and try again.")
            exit(1)
        merged_vars["api_token"] = token
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=merged_vars['headless_mode'])
            context = browser.new_context(http_credentials={'username': 'doesnotmatter', "password": "purposelyfalse"},
                                    ignore_https_errors=not merged_vars["validate_ssl"])
            page = context.new_page()
            nmc_logon(page, merged_vars["nmc_ip"], merged_vars["nmc_user"], merged_vars["nmc_pass"])
            print(edge_run_wrapper(page, merged_vars["nmc_ip"], merged_vars))

