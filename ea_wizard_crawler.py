import time
import logging
import os
import json

from playwright.sync_api import TimeoutError as PlaywrightTimeout, Error

from ad_management_script import join_ad_wheel
from api_reporting import find_edge_by_params


def grab_machine_status(page, nmc_ip, serial_number, login, password):
    t = 0
    while True:
        if t > 15:
            logging.error("Too many throttles. Skipping fetching NMC status")
            return {
                "error": "Couldn't find Filer page"
            }
        internet_addy = f"https://{nmc_ip}/filers/json/"
        logging.info(internet_addy)
        try:
            page.goto(f"https://{nmc_ip}/filers/refresh/", timeout=90000)
        except TimeoutError:
            logging.info("We timed out. Catching for continuation")
        page.goto(internet_addy)
        time.sleep(5)
        j_string = page.locator("html").text_content()
        try:
            data = json.loads(j_string)
            try:
                filer_info = data[serial_number]
                return filer_info
            except KeyError:
                logging.warning("Serial number Not yet sent to NMC. Waiting 15 Seconds")
                time.sleep(15)
                t = t + 1
                continue

        except ValueError:
            if "login/?next=/" in page.url:
                logging.info("Not logged in. Attempting to log in.")
                page.locator("#id_username").fill(login)
                page.get_by_placeholder("Username").fill(login)
                page.get_by_placeholder("Password").fill(password)
                page.get_by_role("button", name="Log in").click()
                time.sleep(10)
                if not page.locator("#id_username").is_visible():
                    logging.error("Login failed. Check credentials and try again.")
                    return {
                        "error": "Login failed"
                    }
                logging.warning("We had a login error. We have corrected it and are re-logging in.")
            else:
                logging.warning("NMC throttled the request at this endpoint. Waiting 15 seconds.")
            time.sleep(15)
            t = t + 1

class EdgeAppliance:
    """
     A class used to represent a Nasuni Appliance.

        Attributes:
            appl_type: the type of appliance that this wizard manages. Set to 'edge' for Edge appliance.
            ip: Ip address for the filer
            serial_num: serial number to use for the filer.
            auth_code: an auth code for the serial number.
            mach_name: a name for the filer, used on its networking page and as its filer_name
            vars_dict: a dictionary that the filer receives inputs from.
            output_dict: a dictionary that the filer writes to
            page: contains a page that can be used to navigate around this filer
            networking: a dictionary describing any networking configuration choices that should be made as part of the configuration process
            ad_config: a dictionary describing any active directory configuration choices that should be made as part of the configuration process
            in_dr: helps manage the state of the dr screen, especially when making an update.
            wizard_tasks: a task that the edge appliance wizard has most recently performed. Used to assist in debugging.
            encryption: manages the results for the encryption details that playa can manage.
            functions_list: contains an incomplete list of operation/wizard actions we have performed on this filer. Helps to prevent the script from hanging.
            status: contains a list of settings that the object manages, and displays them.

        Methods:
            boot_up_appliance(self) : Does any number of administrative tasks on the appliance
    """
    def __init__(self, ip: str,
                 filer_serial: str,
                 filer_auth_code: str,
                 mach_name: str,
                 vars_dict: dict,
                 output_dict: dict):
        """
        Args:
            ip (str): ip address for the given filer
            filer_serial (str): The serial to be used for the filer
            filer_auth_code (str): The auth code to be used for the filer
            region : dict
                A region with all the ad information that will be used to configure the filer
            mach_name : str
                A name for the filer, to be used as it's NOC name and as it's hostnmae
            vars_dict : dict
                A dictionary that the filer pulls certain login information from.
            output_dict: dict
                A dictionary that the filer writes it's status to
        """
        self.appl_type = "edge"
        self.ip = ip
        self.serial_num = filer_serial
        self.auth_code = filer_auth_code
        self.mach_name = mach_name
        self.vars_dict = vars_dict
        self.output_dict = output_dict
        self.page = None
        self.networking = {}
        self.ad_config = {}
        self.in_dr = False
        self.porttag = ":8443"
        self.wizard_tasks = "default_task"
        self.encryption = {
            "escrow_passphrase": "unset",
            "encryption_key_list": [],
        }
        self.functions_list = {
            'confirmnew': 0,
            'adjoins': 0,
            'logins': 0,
            'serials': 0,
            'namings': 0,
            'nmcjoin': 0,
            'network': 0,
            'encryption': 0,
            'update_reloads': 0,
            'escrow_tries': 0,
        }
        self.status = {
            "gui_data": {},
            "version": "unknown",
        }

    def check_endpoint(self):
        """A function we use to validate the availability of the filer to the internet before proceeding to the wizard."""
        # New Check Endpoint
        logging.debug("Checking Connectivity.")
        self.page.goto(f"https://{self.ip}{self.porttag}/", timeout=90000)
        return 0

    def get_state_from_nmc(self):
        self.status["gui_data"] = grab_machine_status(self.page, self.vars_dict["nmc_ip"], self.serial_num, self.vars_dict["nmc_user"], self.vars_dict["nmc_pass"])
        self.status["api_data"] = find_edge_by_params(self.vars_dict["nmc_ip"], self.vars_dict["api_token"], self.serial_num, False)
        return 0

    def get_back(self):
        """Clicks the back button on a filer. Occasionally used for managing states"""
        self.page.get_by_role("link", name=" Back").click()
        return 0

    def confirm_dr(self):
        """Handles authenticating with an in-use serial number. For now, just exits by saying we don't support Disaster Recovery."""
        self.wizard_tasks = "perform_dr"
        logging.error("The serial number is already in use, and this script does not support DR. Please check your serial number")
        self.page.goto(f"https://{self.ip}{self.porttag}/wizard/reset/")
        self.get_back()
        return 1

    def get_network(self):
        """Configures the scripts network page
        Proxies and Static network setting are both currently unscripted

        Returns:
            Exit Code:
                1 if we have seen this screen too many times
                0 if all operations were attempted
         """
        self.wizard_tasks = "configure_network"
        hostname = self.mach_name[:15]
        if "diff_hostname" in self.vars_dict.keys():
            hostname = self.vars_dict["diff_hostname"][:15]

        self.functions_list["network"] = self.functions_list["network"] + 1
        if self.functions_list["network"] > 2:
            logging.error("%s: Issue on networking screen. Likely an illegal hostname. Discontinuing Filer setup", self.mach_name)
            return 1

        self.page.goto(f"https://{self.ip}{self.porttag}/wizard/network/", timeout=0)
        time.sleep(5)
        self.page.locator("#id_hostname").fill(hostname)
        # Machine
        try:
            appl_network_setting = self.vars_dict["network_setting"]
        except KeyError:
            logging.warning("%s: Couldn't find a network setting. Changing to 'DHCP'", self.mach_name)
            appl_network_setting = "DCHP"
        if appl_network_setting == "dhcp2":
            self.page.locator("#id_bootproto").select_option("dhcp2")

        if appl_network_setting == "static":
            try:
                gateway = self.vars_dict["default_gateway"]
            except KeyError:
                logging.warning("%s: Couldn't find a gateway. Setting to ''", self.mach_name)
                gateway = ""
            self.page.locator("#id_gateway").fill(gateway)

        if appl_network_setting == "static" or appl_network_setting == "dhcp2":
            try:
                domain = self.vars_dict["search_domain"]
            except KeyError:
                logging.warning("%s: Keeping 'search domain' unset", self.mach_name)
                domain = ""
            self.page.locator("#id_search_domain").fill(domain)
            if "dns_1" in self.vars_dict.keys():
                self.page.locator("#id_primary_dns").fill(self.vars_dict["dns_1"])
            if "dns_2" in self.vars_dict.keys():
                self.page.locator("#id_secondary_dns").fill(self.vars_dict["dns_2"])
        elif self.vars_dict["proxy"] is True:
            self.page.locator(".controls > label").click()
        self.page.get_by_role("button", name="Continue ").click()
        self.wizard_tasks = "Network Connecting"
        time.sleep(30)
        return 0

    def get_proxy(self):
        """Bypasses proxy configuration for filers and the NMC"""
        self.wizard_tasks = "configure_proxy"
        logging.error("%s: Proxy Support Not Available", self.mach_name)
        return 1

    def get_netready(self):
        """Toggles through the netready page.

        Returns
            An exit code (int)
                1 if the networking never came back up after the reboot.
                0 if all operations were attempted
         """
        self.wizard_tasks = "wait_for_proxy"
        #  Ensures we're on the right page.
        self.page.get_by_role("cell", name="Hostname").click()
        self.page.get_by_role("button", name="Continue ").click()
        if self.appl_type == "edge":
            self.page.get_by_role("link", name="here").click(timeout=60000)
        n = 0
        while True:
            try:
                logging.info("%s: reloading page", self.mach_name)
                self.page.reload(timeout=0)
                break

            except Error as e:

                a = self.process_error(self.page, e)
                if a == 1:
                    self.output_dict[self.mach_name] = 1
                    return 1
        self.wizard_tasks = "Networking"
        return 0

    def get_updates(self):
        """Manages the updates page for the filer

        Due to an issue on our end, the update screen tends to bug. We do not update the filer during this wizard build
        This page also occurs if the filer is up-to-date"""

        update = "n"
        logging.debug("%s: Update = %s", self.mach_name, update)
        time.sleep(5)
        if self.page.get_by_text("Uncheck to skip the update.").is_visible():
            logging.info("%s Update Available", self.mach_name)
            box_checked = False
            update_text = "will NOT"
            wait_time = 1
            logging.info("%s: We %s update", self.mach_name, update_text)
            try:
                self.page.locator("label").nth(1).set_checked(box_checked, timeout=5000)
                self.page.get_by_role("button", name="Continue ").click(timeout=10000)
                time.sleep(wait_time)
                self.page.reload(wait_until='networkidle')
            except PlaywrightTimeout:
                logging.warning("%s: update screen is in a weird configuration: Reloading page", self.mach_name)
                self.page.reload()
            except Error as e:
                a = self.process_error(self.page, e)
                if a == 1:
                    self.output_dict[self.mach_name] = 1
                    return 1
                self.page.reload()

        elif self.page.get_by_text("up to date").is_visible():
            logging.info("%s: Filer Up-to-date", self.mach_name)
            self.page.get_by_role("button", name="Continue ").click()
        else:
            logging.warning("%s: Cannot parse update screen. Likely a reload error.", self.mach_name)
        self.wizard_tasks = "updates"
        return 0

    def get_updatenew(self):
        """A clone of the get_update function.

        If you deny the update on one part of the wizard, this page will show up later.
        There is currently no support for actually updating on this page instead of the first. It is listed here
        for comepleteness"""
        a = self.get_updates()
        self.wizard_tasks = "updatenew"
        return a

    def get_serial(self):
        """Writes the filer's given serial number to the Wizard Serials screen.

        Returns:
            1 if we've hit this page too many times
            0 if all operations were attempted
         """
        # If we've hit this page a couple of times, we assume that the serial data is inaccurate
        self.wizard_tasks = "serial"
        serials = self.functions_list["serials"]
        if serials >= 3:
            logging.error(
                "%s Serial collision. Script has retried once or twice. The script will now close", self.mach_name)
            return 1
        try:
            b = self.vars_dict["serial_number"]
            c = self.vars_dict["auth_code"]
        except KeyError:
            logging.error("%s missing serial number information", self.mach_name)
            return 1

        self.functions_list["serials"] = self.functions_list["serials"] + 1
        self.page.locator("#id_serial_number").fill(b)
        self.page.locator("#id_auth_code").fill(c)
        self.serial_num = b
        self.page.get_by_role("button", name="Continue ").click()
        self.wizard_tasks = "serial"
        return 0

    def get_install(self):
        """Auto-executes the install new filer button. Resets the wizard if we have tried more than three times.

        Returns
            0 if all operations were attempted
            1 if we have attempted this screen more than 5 times"""

        self.wizard_tasks = "get_install"
        self.functions_list["confirmnew"] = self.functions_list["confirmnew"] + 1
        logging.debug("%s: running get_install for time number %s", self.mach_name, self.functions_list['confirmnew'])
        self.page.locator("#id_confirm").click()
        if self.functions_list["confirmnew"] >= 3:
            self.page.goto(f"https://{self.ip}{self.porttag}/wizard/reset/")
        elif self.functions_list["confirmnew"] <= 5:
            logging.info("%s: Get install - Executing", self.mach_name)
            self.page.locator("#id_confirm").fill("Install New Filer")
            logging.info("%s: Before Install Continue", self.mach_name)
            self.page.get_by_role("button", name="Continue ").click(timeout=900000)
            logging.info("%s: Get install - Finished pressing install button", self.mach_name)
            self.page.reload(wait_until='networkidle', timeout=900000)
        else:
            logging.error(
                "%s Four repeats of the install filer page. Likely an incorrect serial. Exiting.", self.mach_name)
            return 1

        time.sleep(5)
        logging.info("%s: Reloading after completing get-install", self.mach_name)

        self.page.reload(wait_until="networkidle", timeout=900000)
        logging.warning("%s: Finished get_install reload", self.mach_name)
        self.wizard_tasks = "get_install"
        return 0

    def get_eula(self):
        """Controls the edge_appliance's get_eula screen

        Args

        Returns
            0 when script has EULA has been checked through.
        """
        time.sleep(5)
        try:
            accept_eula = self.vars_dict["accept_eula"]
        except KeyError:
            accept_eula = "n"
        if accept_eula == "y":
            self.page.locator("label").click()
        while True:
            if self.page.locator("label").is_checked():
                break
            else:
                time.sleep(5)
        self.page.get_by_role("button", name="Continue ").click()
        self.wizard_tasks = "eula"
        return 0

    def get_filername(self):
        """Names the filer with the name given by self.mach_name.

        Returns
            Return code
                0 if all operations were attempted.
                1 if the get_filer_name operation has been tried more than 3 times
        """
        self.functions_list["namings"] = self.functions_list["namings"] + 1
        self.page.locator("#id_description").fill(self.vars_dict["description"])
        if self.functions_list["namings"] == 3:
            logging.error("""%s: Filer is retrying name page.
                          Likely name collison. The thread should now exit""", self.mach_name)
            return 1
        self.page.get_by_role("button", name="Continue ").click()
        self.wizard_tasks = "filer_name"
        return 0

    def get_nmcjoin(self):
        """Joins the NMC.

       """
        #  Currently the script does not support skipping this function. However, we do make a note of it
        #  to identify which username/password pair we may need for future authentication of this filer
        self.functions_list["nmcjoin"] = 1
        join_nmc = True
        if 'nmc_join' in self.vars_dict.keys():
            join_nmc = self.vars_dict['nmc_join']
            logging.info("NMC join info: %s", join_nmc)
        self.page.locator("label").nth(1).set_checked(join_nmc)
        self.status["gui_data"]["joined_nmc"] = join_nmc
        self.page.get_by_role("button", name="Continue ").click()
        self.wizard_tasks = "nmc_join"
        return 0

    def get_admin(self):
        """Fills in a username and password at the getadmin page.

        Returns
            0:
        """
        time.sleep(3)
        self.page.reload()

        if self.page.get_by_text("The gateway did not receive a timely response from the upstream server").is_visible():
            logging.info("%s: Gateway Timeout. Reloading...", self.mach_name)
            self.page.reload()
            return 0
        self.page.locator("#id_username").fill(self.vars_dict["edge_user"])
        self.page.locator("#id_pass1").fill(self.vars_dict["edge_pass"])
        self.page.locator("#id_pass2").fill(self.vars_dict["edge_pass"])
        self.page.get_by_role("button", name="Continue ").click()
        logging.error("%s: We recorded a get admin continue input", self.mach_name)
        self.page.goto(f"https://{self.ip}{self.porttag}/")
        self.wizard_tasks = "all"
        return 0

    def make_login_attempt(self, login, password):
        self.page.locator("#id_username").fill(login)
        self.page.get_by_placeholder("Username").fill(login)
        self.page.get_by_placeholder("Password").fill(password)
        self.page.get_by_role("button", name="Log in").click()
        time.sleep(5)
        if not self.page.locator("#id_username").is_visible():
            return True
        else:
            return False
        
    def get_login(self):
        """Logs into the filer.

        Returns
            Return code
                1 if this is the Sixth time we've attempted to login on this filer
                0 otherwise"""
        # Tries both the NMC login and the filer login. The script will only try to RE-login four times
        # ; if we arrive to this page more than four times independently we assume that we have
        # erroneous login data. An extra login might be necessary because the Edge will kick out the current session
        # as a part of joining the NMC at an undetermined time.
        if self.functions_list["logins"] > 4:
            logging.error("%s: Too many login attempts. No further operations will be done on this filer", self.mach_name)
            return 1
        else:
            self.functions_list["logins"] = self.functions_list["logins"] + 1
        login = self.vars_dict["nmc_user"]
        password = self.vars_dict["nmc_pass"]
        if self.make_login_attempt(login, password):
            logging.warning("Logged in under NMC creds")
            return 0
        logging.warning("%s used NMC creds and couldn't login. We will try the Edge credentials", self.mach_name)
        login = self.vars_dict["edge_user"]
        password = self.vars_dict["edge_pass"]
        if self.make_login_attempt(login, password):
            logging.warning("Logged in under Edge creds")
            return 0
        logging.warning("%s: Login shows a failure with both filer-based logons and NMC based logons. We will retry", self.mach_name)
        return 1

    def check_login(self):
        """"A wrapper for the get_login function. Checks the page_url for the login script, and if it exists, runs
        the get_login function using the input data."""
        if "login/?next=/" in self.page.url:
            logging.warning("%s Not logged in: Retrying", self.mach_name)
            return self.get_login()
        return 0
        
    def get_ad_config(self):
        """Joins AD. Uses the username and password for the configuration error.

        Returns
            Exit code
            1 for AD configuration issue"""
        while True:
            if self.page.get_by_text("Enabled - Healthy").is_visible():
                logging.warning("%s: AD Already set", self.mach_name)
                return 0
            self.page.goto(f"https://{self.ip}:8443/directoryservices")
            
            self.page.locator("#id_computerou").fill(self.vars_dict["computer_ou"])
            self.page.locator("#id_domain").fill(self.vars_dict["ad_fdqn"])
            self.page.locator("#id_controllers").fill(self.vars_dict["dns_ad"])
        
            self.page.get_by_role("button", name="Continue ").click()
            self.page.locator("#ads_username").fill(self.vars_dict["ad_username"])
            self.page.locator("#ads_password").fill(self.vars_dict["ad_password"])
            self.page.locator("#ads_password2").fill(self.vars_dict["ad_password"])
            self.page.locator("#ds-auth-confirm").get_by_role("button", name="Submit").click()
            time.sleep(3)
            
            tries = 0
        
            a = join_ad_wheel(self.page, self.ip, self.vars_dict)
            if a['success'] == False:
                if 'retry' in a.keys() and a['retry'] == "y":
                    self.page.reload()
                    logging.error("%s: AD Join Failed. checking login", self.mach_name)
                    a = self.check_login()
                    if a == 0:
                        if tries < 5:
                            logging.error("%s: AD Join Failed. Retrying...", self.mach_name)
                            tries = tries + 1
                            continue
                logging.error("%s: AD Join Failed. Error was %s", self.mach_name, a['errors'])
                return 1
            return 0
       
    def boot_up_appliance(self, page):
        """
        Completes the intialization of a filer depending on volume data

        Returns:
            0 if all operations completed
            1 if there was an issue completing the operation
        """
        # Using a serial number, auth code, a region, a machine name, and some environmental variables,
        # including vars_dict, pings the Edge Appliance's IP address and boots up a new filer using that address.

        # List of the different serial functions that the edge appliance wizard may perform.
        function_wizard = {
            'network': self.get_network,
            'proxy': self.get_proxy,
            'netready': self.get_netready,
            'updates': self.get_updates,
            'serial': self.get_serial,
            'confirmnew': self.get_install,
            'update_new': self.get_updatenew,
            'eula': self.get_eula,
            'description': self.get_filername,
            'checknmc': self.get_nmcjoin,
            'createuser': self.get_admin,
            'confirmrecovery': self.confirm_dr,
        }

        # Setting a default timeout to 15 seconds.
        self.page = page
        self.page.set_default_timeout(15000)

        # Assessing connectivity
        n = 0
        while True:
            try:
                a = self.check_endpoint()
                break
            except Error as e:
                logging.error("processing error on check_endpoint miss")
                a = self.process_error(self.page, e)
                self.wizard_tasks = "Connect to appliance"
                if a == 1:
                    break
                n = n + 1
                logging.warning("Edge is not up. Continuing")
                if n > 6:
                    return 3
        if a != 0:
            logging.error("Could not connect to %s at %s. Skipping this appliance...", self.mach_name, self.ip)
            self.output_dict[self.mach_name] = 1
            return a

        # Running wizard
        self.page.goto(f"https://{self.ip}{self.porttag}/", timeout=90000, wait_until='networkidle')
        time.sleep(3)
        while 'wizard' in self.page.url or 'site_media' in self.page.url:
            function = function_wizard[self.page.url.split('/')[4]]
            try:
                logging.info("%s: %s: Could not complete setup.", self.mach_name, function.__name__)
                info = function()
                if info == 1:
                    self.output_dict[self.mach_name] = 1
                    return
            # If we experience a timeout error, we will reload the page.
            except PlaywrightTimeout:
                logging.info("%s: %s: Timeout Error. We will retry", self.mach_name, function.__name__)
                continue

            # If we error, we want to know whether the Error was a appropriate.
            except Error as e:
                a = self.process_error(page, e)
                if a == 1:
                    return 1
                
        # Post-Wizard functionality
        # First, we build a list of things to do. (Only AD configuration for now)
        jobs = [self.get_ad_config]
        self.wizard_tasks = "ad_config"

        # Makes a list of jobs, then continues through the job list until all jobs are done.
        iterator = 0
        job_length = len(jobs)
        self.output_dict[self.mach_name] = 0
        tries = 0
       
        while iterator < job_length:
            function = jobs[iterator]
            done = True
            if tries >= 5:
                logging.error("%s: %s: Could not complete setup.", self.mach_name, function.__name__)
                self.output_dict[self.mach_name] = 1
                return 1
            try:
                logging.debug("%s: %s:", self.mach_name, function.__name__)
                b = function()
                if b != 0:
                    self.output_dict[self.mach_name] = 1
            except PlaywrightTimeout as e:
                logging.info("%s: %s: Timeout Error. We will retry", self.mach_name, function.__name__)
                done = False
                tries = tries + 1
                a = self.check_login()
                if a == 1:
                    break
                continue
            except Error as e:
                a = self.process_error(page, e)
                done = False
                tries = tries + 1
                if a == 1:
                    self.output_dict[self.mach_name] = 1
                    return 1
            if done:
                tries = 0
                iterator += 1
        # ---------------------
        self.get_state_from_nmc()
        return
    
    def white_list_error(self, e):
        if (
            e.message.find("net::ERR_CONNECTION_REFUSED") > -1 or
            e.message.find("net::ERR_CONNECTION_TIMED_OUT") > -1 or
            e.message.find("net::ERR_ABORTED") > -1 or
            e.message.find("Not attached to an active page") > -1
        ):
            return True
        return False
    
    def process_error(self, page, e):
        """Handles connectivity errors to the Filer. If the Filer is experiencing a connectivity error, will reload the page.
        Waits a total of five minutes, if we have 5 continuous minutes of poor connectivity, we will raise the error.
        Connectivity errors are builtin to allow for network disruption due to reboots, which happen occasionally during the wizard,
        most commonly during network configuration."""
        if self.white_list_error(e):
            t = 0
            while True:
                try:
                    page.reload(timeout=120000)
                    logging.info("%s: Successful reload. We are continuing", self.mach_name)
                    break
                except Error as e:
                    if self.white_list_error(e):
                        logging.warning("%s: Error message %s", self.mach_name, e.message)
                        t = t + 1
                        if t > 3:
                            self.output_dict[self.mach_name] = 1
                            logging.error("Unresolved connectivity error. We have waited five minutes. Please check your network")
                            return 1
                        logging.warning("Continuing")
                        time.sleep(15)
                        continue
                    elif (
                        e.message.find("net::ERR_NETWORK_CHANGED") > -1
                    ):
                        logging.error("Network Changed Unexpectedly. Exiting. Please run script again.")
                        return 1
                    else:
                        logging.error("Unknown_accounted_for playwright error. Raising")
                        logging.warning(e.message)
                        logging.error("Error Message Above")
                        raise e
            return 0
        elif (
            e.message.find("net::ERR_NETWORK_CHANGED") > -1
        ):
            logging.error("Network Changed Unexpectedly. Exiting. Please run script again.")
            return 1
        else:
            logging.error("Unknown playwright error. Raising")
            logging.warning(e.message)
            logging.error("Error Message Above")
            raise e


# Using a playwright page logged into the NMC, and the IP address/hostname of the NMC itself, grabs the serial numbers from the NMC
def grab_nmc_serials(page, ip_addy) -> dict:
    while True:
        internet_addy = f"https://{ip_addy}//account/serial_numbers/json/"
        page.goto(internet_addy)
        time.sleep(5)
        j_string = page.locator("html").text_content()
        try:
            data = json.loads(j_string)
            break
        except ValueError:
            logging.warning("NMC throttled the request at this endpoint. Waiting 15 seconds.")
            time.sleep(15)

    a = {}
    for key in data:
        value = data[key]
        a[value["serial_number"]] = value["auth_code"]
        # Currently configured to grab the entire list
    return a


def edge_run_wrapper(page, ip_addy, data_block):
    """Using the NMC, transforms the data dictionary from the top of this file into working Nasuni filer"""
    new_block = data_block
    new_block['filer_waits'] = 20
    if data_block["auth_code"] == "NMC":
        try:
            data_block["auth_code"] = grab_nmc_serials(page, ip_addy)[data_block["serial_number"]]
        except KeyError:
            return {
                "status": "error",
                "job": "filer create",
                "error": "No Serial Error",
                "messages": "The NMC Serial list for the resource does not have the assigned serial number; neither active nor inactive"
            }
    output_dict = {}
    edge = EdgeAppliance(data_block['edge_ip'], data_block['serial_number'], data_block['auth_code'], data_block['dhcp_hostname'], data_block, output_dict)
    logging.info(data_block.keys())
    edge.boot_up_appliance(page)
    if output_dict[data_block['dhcp_hostname']] == 1:
        return {
            "status": "error",
            "job": "filer create",
            "error": "wizard/networking error",
            "messages": f"Edge failed during: {edge.wizard_tasks}"
        }
    logging.debug("Serial Number: %s", edge.serial_num)
    return {
        "status": "success",
        "job": "filer create",
        "error": "none",
        "messages": edge.status
    }
