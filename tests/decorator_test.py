from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import time
import unittest

import requests

from shared_timeout_requests import shared_timeout


class SleepHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(1)
        try:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(bytes("<html><body><p>Request: %s</p></body></html>" % self.path, "utf-8"))
        except BrokenPipeError:
            pass


class TestDecorator(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.server_address = ('localhost', 29091)
        cls.httpd = HTTPServer(cls.server_address, SleepHandler)
        
        cls.server_thread = Thread(target=cls.httpd.serve_forever)
        cls.server_thread.setDaemon(True)
        cls.server_thread.start()
        
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.server_thread.join()
    
    def test_no_argument(self):
        @shared_timeout(timeout=1)
        def get_by_ftp_url(url: str, loop_count: int = 1, callback = None):
            try:
                status_codes = []
                for i in range(loop_count):
                    print(f"iteration: {i + 1}")
                    response = requests.get(url)
                    status_codes.append(response.status_code)
                return status_codes
            except Exception as e:
                if callback:
                    callback(e)
                else:
                    raise e
                return []
        
        try:
            get_by_ftp_url("http://localhost:29091/", 10)
            exception = None
        except Exception as e:
            exception = e
        
        assert isinstance(exception, requests.Timeout), f"Exception is {exception}"

    def test_argument_with_defaults(self):
        @shared_timeout(timeout=1)
        def get_by_ftp_url(url: str, /, loop_count: int = 1, *, callback = None):
            try:
                status_codes = []
                for i in range(loop_count):
                    print(f"iteration: {i + 1}")
                    response = requests.get(url)
                    status_codes.append(response.status_code)
                return status_codes
            except Exception as e:
                if callback:
                    callback(e)
                else:
                    raise e
                return []
        
        exception = None
        def catch(e):
            nonlocal exception
            exception = e
        get_by_ftp_url("http://localhost:29091/", loop_count=10, callback=catch)
        
        assert isinstance(exception, requests.Timeout), f"Exception is {exception}"


if __name__ == "__main__":
    unittest.main()
