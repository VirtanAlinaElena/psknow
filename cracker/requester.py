import requests
import traceback

from config import Configuration
from comunicator import Comunicator


class Requester:
    DownMessage = "Server is down. Check connection/config file. Retrying in 10 seconds.."

    class ServerDown(Exception):
        pass

    @staticmethod
    def _decode_json(response):
        try:
            data = response.json()
        except Exception as e:
            return None, "%s\n%s" % (e, traceback.format_exc())

        if data["success"] is False:
            return None, data["reason"]

        return data.get("data"), ""

    def __init__(self, apikey, err_printer):
        self.apikey = apikey
        self.err_printer = err_printer

    def getwork(self):
        """
            Send a request for work to the server
            :return:
                None - Nothing can be down with capabilities
                False - A sha1 has does not match, capabilities need updating
                True - An error occurred
                {data} - Work data requested
            :raises Requester.ServerDown: The server could not be reached
        """
        url = Configuration.remote_server + "getwork"
        Comunicator.info_logger("Requesting work from '%s'" % url)

        response = None
        try:
            response = requests.post(url, json={"apikey": self.apikey, "capabilities": Configuration.capabilities},
                                     timeout=10)
        except requests.exceptions.ConnectionError:
            raise Requester.ServerDown
        except requests.exceptions.Timeout:
            Comunicator.fatal_regular_message("Backend is unresponsive")
        if response.status_code == 502:
            raise Requester.ServerDown

        data, err = Requester._decode_json(response)
        if err != "":
            if err == Configuration.cap_updated:
                return False

            if err == Configuration.no_work_message:
                return None

            self.err_printer("Error retrieving data from server '%s'" % err)
            return True

        return data

    def stopwork(self, suppress_stdout=False):
        """
            Stop current job
            :return:
                True - An error occurred
                None - Current job stopped
            :raises Requester.ServerDown: The server could not be reached
        """
        url = Configuration.remote_server + "stopwork"
        Comunicator.info_logger("Stopping work from '%s'" % url)

        response = None
        try:
            response = requests.post(url, data={"apikey": self.apikey}, timeout=10)
        except requests.exceptions.ConnectionError:
            raise Requester.ServerDown
        except requests.exceptions.Timeout:
            Comunicator.fatal_regular_message("Backend is unresponsive")
        if response.status_code == 502:
            raise Requester.ServerDown

        _, err = Requester._decode_json(response)
        if err != "":
            msg = "Error stopping work '%s'" % err
            if suppress_stdout:
                Comunicator.error_logger(msg)
            else:
                self.err_printer(msg)
            return True

        return None

    def pausework(self):
        """
             Pause current job
             :return:
                True - An error occurred
                None - Current job paused
             :raises Requester.ServerDown: The server could not be reached
         """
        url = Configuration.remote_server + "pausework"
        Comunicator.info_logger("Pausing work from '%s'" % url)
        try:
            response = requests.post(url, data={"apikey": self.apikey})
        except requests.exceptions.ConnectionError:
            raise Requester.ServerDown
        if response.status_code == 502:
            raise Requester.ServerDown

        _, err = Requester._decode_json(response)
        if err != "":
            self.err_printer("Error pausing work '%s'" % err)
            return True

        return None

    def sendeta(self, eta):
        """
            Send eta for current
            :return:
                True - An error occurred
                None - Eta successfully sent
            :raises Requester.ServerDown: The server could not be reached
         """
        url = Configuration.remote_server + "sendeta"
        Comunicator.info_logger("Sending eta to '%s': '%s'" % (url, eta))

        response = None
        try:
            response = requests.post(url, data={"apikey": self.apikey, "eta": eta}, timeout=10)
        except requests.exceptions.ConnectionError:
            raise Requester.ServerDown
        except requests.exceptions.Timeout:
            Comunicator.fatal_regular_message("Backend is unresponsive")
        if response.status_code == 502:
            raise Requester.ServerDown

        _, err = Requester._decode_json(response)
        if err != "":
            self.err_printer("Error sending eta '%s'" % err)
            return True

        return None

    def checkfile(self, filename):
        """
            Check if a capability can be downloaded
            :return:
                True - An error occurred
                None - The file can be downloaded
            :raises Requester.ServerDown: The server could not be reached
         """
        url = Configuration.remote_server + "checkfile"
        Comunicator.info_logger("Checking if file '%s' exists at '%s'" % (filename, url))

        response = None
        try:
            response = requests.post(url, data={"apikey": self.apikey, "file": filename}, timeout=10)
        except requests.exceptions.ConnectionError:
            raise Requester.ServerDown
        except requests.exceptions.Timeout:
            Comunicator.fatal_regular_message("Backend is unresponsive")
        if response.status_code == 502:
            raise Requester.ServerDown

        _, err = Requester._decode_json(response)
        if err != "":
            self.err_printer("Error downloading '%s': '%s'" % (filename, err))
            return True

        return None

    def getfile(self, filename, path):
        """
            Download capability file
            :param filename: Filename of the capability to download
            :param path: Local relative path where to save the downloaded file
            :return:
                None - File downloaded
            :raises Requester.ServerDown: The server could not be reached
        """

        url = Configuration.remote_server + "getfile"
        Comunicator.info_logger("Getting file '%s' from '%s'" % (filename, url))

        try:
            with requests.post(url, data={"apikey": self.apikey, "file": filename}, stream=True, timeout=10) as req:
                req.raise_for_status()
                with open(path, "wb+") as fd:
                    for chunk in req.iter_content(chunk_size=8192):
                        if chunk:
                            fd.write(chunk)
        except requests.exceptions.ConnectionError:
            raise Requester.ServerDown
        except requests.exceptions.Timeout:
            Comunicator.fatal_regular_message("Backend is unresponsive")

        return None

    def getmissing(self):
        """
            Get missing capabilities
            :return:
                True - An error occurred
                [{capability}] - List of capabilities
            :raises Requester.ServerDown: The server could not be reached
        """
        url = Configuration.remote_server + "getmissing"
        Comunicator.info_logger("Getting missing capabilites at '%s'" % url)

        response = None
        try:
            response = requests.post(url, json={"apikey": self.apikey, "capabilities": Configuration.capabilities},
                                     timeout=10)
        except requests.exceptions.ConnectionError:
            raise Requester.ServerDown
        except requests.exceptions.Timeout:
            Comunicator.fatal_regular_message("Backend is unresponsive")
        if response.status_code == 502:
            raise Requester.ServerDown

        data, err = Requester._decode_json(response)
        if err != "":
            self.err_printer("Error while retrieving missing capabilites '%s'" % err)
            return True

        return data

    def sendresult(self, password):
        """
            Send results for current job
            :param password: password for the current job, can be ""
            :return:
                False - The job expired
                True - An error occurred
                None - Current job stopped
            :raises Requester.ServerDown: The server could not be reached
        """
        url = Configuration.remote_server + "sendresult"
        Comunicator.info_logger("Sending result at '%s'" % url)

        response = None
        try:
            response = requests.post(url, data={"apikey": self.apikey, "password": password}, timeout=10)
        except requests.exceptions.ConnectionError:
            raise Requester.ServerDown
        except requests.exceptions.Timeout:
            Comunicator.fatal_regular_message("Backend is unresponsive")
        if response.status_code == 502:
            raise Requester.ServerDown

        _, err = Requester._decode_json(response)
        if err != "":
            if err == Configuration.no_job_message:
                return False
            self.err_printer("Error while sending result '%s'" % err)
            return True

        return None
