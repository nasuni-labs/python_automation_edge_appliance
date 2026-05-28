import time
import logging
import traceback
try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    PlAYWRIGHT_IMP_ERR = traceback.format_exc()
    HAS_PLAYWRIGHT = False

def join_ad_wheel(page: Page, hostname, payload):
    """
    Join an Edge to the Active Directory.

    Args:
        page (page): Page logged into the Edge
        hostname (str): Hostname for the Edge
        payload (dict): A dictionary with the AD information we will use to configure the AD 

    Returns:
        dict: Nasuni Ansible Response
    """
    time.sleep(5)
    domain_omits = payload["omitted_domains"]
    while True:
        # Loading screen
        if page.get_by_role("heading", name="Connecting to Directory Service...", exact=True).is_visible():
            logging.info("%s is configuring. Please wait.", hostname)
            time.sleep(15)

        elif page.get_by_text("Error processing form").first.is_visible():
                logging.info("%s: Script needs a relogin.", hostname)
                time.sleep(3)
                return {
                    "success": False,
                    "retry": "y",
                    "errors": {
                        "loading_page": ["Form Error. We will retry."]
                    }
                }
        # Starting screen
        elif page.get_by_text(
                "Enter the user name and password of a directory user").is_visible():
            logging.warning("%s AD_join_error. Looks like a login or connection error.", hostname)
            return {
                "success": False,
                "errors": {
                    "loading_page": ["Looks like a login or connection error."]
                }
            }
        
        # Filer Domain settings screen.
        elif page.locator("#ds-form-domain-config label").nth(2).is_visible():
            # Gaining domain settings from similar filers
            if payload["local_filer_settings"] is True:
                page.locator("#id_filer").select_option("")
            page.locator("#ds-form-domain-config label").nth(2).click()
            time.sleep(3)
            page.get_by_role("button", name="Continue ").click()
            time.sleep(5)
        
        # Filer Domain Trusts screen
        elif page.get_by_text(
                "Select the domains that will be allowed access from this Filer. Objects in domai").is_visible():
            for i in domain_omits:
                try:
                    page.get_by_role("row", name=f"{i} Trusted").locator("label").set_checked(False,
                                                                                              timeout=5000)
                    logging.info("%s: Removed %s from active domains", hostname, i)
                except PlaywrightTimeout:
                    logging.error("%s: Could not find %s. Skipping", hostname, i)

            logging.info("%s: Joining Adjacent domains", hostname)
            page.get_by_role("button", name="Continue ").click()
            time.sleep(3)

        # Filer Finishing domain Screen
        elif page.get_by_role("button", name=" Finish").is_visible():
            logging.info("%s: Finishing AD join", hostname)
            page.get_by_role("button", name=" Finish").click()
            time.sleep(3)
            
        
        # Domain join successful screen
        elif page.get_by_text("Enabled - Healthy").is_visible():
            return {
                "success": True,
            }
        else:
            time.sleep(3)
            # Ensure we're didn't catch the loading screen right at the wrong time.
            if page.get_by_text("Enabled - Healthy").is_visible():
                return {
                    "success": True,
                }
            logging.error("%s: Unknown page. Please check your appliance", hostname)
            return {
                "success": False,
                "retry": "y",
                "errors": {
                    "loading_page": ["Unknown page. Please check your appliance"]
                }
            }
