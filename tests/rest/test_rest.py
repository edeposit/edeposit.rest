#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Interpreter version: python 2.7
#
# Imports =====================================================================
import os
import time
import json
import random
import urlparse
import threading
import subprocess

import pytest
import requests
import dhtmlparser
from requests.auth import HTTPBasicAuth
from zeo_connector_defaults import CLIENT_CONF_PATH


# Variables ===================================================================
PORT = random.randint(20000, 60000)
URL = "http://127.0.0.1:%d/api/v1/" % PORT
SERV = None


# Fixtures ====================================================================
@pytest.fixture(scope="module", autouse=True)
def bottle_server(request, zeo):
    # run the bottle REST server
    def run_bottle():
        command_path = os.path.join(
            os.path.dirname(__file__),
            "../../bin/edeposit_rest_webserver.py"
        )

        assert os.path.exists(command_path)

        global SERV
        SERV = subprocess.Popen([
            command_path,
            "--zeo-client-conf-file", CLIENT_CONF_PATH,
            "--port", str(PORT),
            "--host", "127.0.0.1",
            "--server", "paste",
            "--debug",
            "--quiet",
        ])

    serv = threading.Thread(target=run_bottle)
    serv.setDaemon(True)
    serv.start()

    time.sleep(1)  # TODO: replace with circuit breaked http ping

    def shutdown_server():
        SERV.terminate()

    request.addfinalizer(shutdown_server)


# Tests =======================================================================
def check_errors(response):
    try:
        response.raise_for_status()
    except requests.HTTPError:
        dom = dhtmlparser.parseString(response.text.encode("utf-8"))
        pre = dom.find("pre")

        if not pre:
            raise

        error_msg = pre[1].getContent()
        error_msg = error_msg.replace("&#039;", "'")
        error_msg = error_msg.replace("&quote;", '"')
        raise requests.HTTPError(error_msg)

    return response.text


def send_request(data):
    return requests.post(
        urlparse.urljoin(URL, "submit"),
        data={"json_data": json.dumps(data)},
        auth=HTTPBasicAuth('user', 'pass'),
    )


def test_submit_epub_minimal(bottle_server):
    resp = send_request({
        "title": "Název",
        "poradi_vydani": "3",
        "misto_vydani": "Praha",
        "rok_vydani": "1989",
        "zpracovatel_zaznamu": "/me",
    })

    assert check_errors(resp)


def test_submit_epub_minimal_numeric():
    resp = send_request({
        "title": "Název",
        "poradi_vydani": "3",
        "misto_vydani": "Praha",
        "rok_vydani": 1989,  # numeric now!
        "zpracovatel_zaznamu": "/me",
    })

    assert check_errors(resp)


def test_submit_epub_minimal_year_fail():
    resp = send_request({
        "title": "Název",
        "poradi_vydani": "3",
        "misto_vydani": "Praha",
        "rok_vydani": "azgabash",  # ordinary string should fail
        "zpracovatel_zaznamu": "/me",
    })

    with pytest.raises(requests.HTTPError):
        check_errors(resp)
