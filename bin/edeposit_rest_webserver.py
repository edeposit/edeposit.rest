#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Interpreter version: python 2.7
#
# Imports =====================================================================
from __future__ import unicode_literals

import sys
import json
import uuid
import os.path
import argparse
from os.path import join
from os.path import dirname

from bottle import run
from bottle import get
from bottle import post
from bottle import route
from bottle import abort
from bottle import request
from bottle import auth_basic
from bottle import SimpleTemplate

from bottle_rest import form_to_params

import dhtmlparser
from docutils.core import publish_parts

from models import SchemaError
from models import EpublicationValidator
from models import czech_to_edeposit_dict
from models.riv import RIV_CATEGORIES
from models.libraries import LIBRARY_MAP
from models.libraries import DEFAULT_LIBRARY

sys.path.insert(0, join(dirname(__file__), "../src/edeposit/amqp"))

try:
    from rest import settings
    from rest.database import UserHandler
    from rest.database import CacheHandler
    from rest.database import StatusHandler
except ImportError:
    from edeposit.amqp.rest import settings
    from edeposit.amqp.rest.database import UserHandler
    from edeposit.amqp.rest.database import CacheHandler
    from edeposit.amqp.rest.database import StatusHandler


# Variables ===================================================================
TEMPLATE_PATH = join(
    dirname(__file__), "../src/edeposit/amqp/rest/html_templates"
)
V1_PATH = "/api/v1/"
USER_DB = None


# Functions & classes =========================================================
def check_auth(username, password):
    request.environ["username"] = username
    request.environ["password"] = password

    return True  # TODO: remove
    return USER_DB.is_valid_user(
        username=username,
        password=password
    )


def process_metadata(json_metadata):
    metadata = json.loads(json_metadata)

    # make sure, that `nazev_souboru` is present in input metadata
    filename = metadata.get("nazev_souboru", None)
    if not filename:
        abort(text="Parametr `nazev_souboru` je povinný!")
    del metadata["nazev_souboru"]

    # validate structure of metadata and map errors to abort() messages
    try:
        metadata = EpublicationValidator.validate(metadata)
    except SchemaError as e:
        msg = e.message.replace("Missing keys:", "Chybějící klíče:")
        abort(text=msg)

    # add DEFAULT_LIBRARY to metadata - it is always present
    libraries = metadata.get("libraries_that_can_access", [])
    libraries.append(DEFAULT_LIBRARY)
    metadata["libraries_that_can_access"] = libraries

    # convert input metadata to data for edeposit
    return czech_to_edeposit_dict(metadata)


# API definition ==============================================================
@route(join(V1_PATH, "track/<uid>"))  # TODO: change from route() to get()
@auth_basic(check_auth)
def track_publication(uid=None):
    if not uid:
        return track_publications()


@route(join(V1_PATH, "track"))  # TODO: change from route() to get()
@auth_basic(check_auth)
def track_publications():
    pass


@get(join(V1_PATH, "submit"))  # TODO: remove
@post(join(V1_PATH, "submit"))
@auth_basic(check_auth)
@form_to_params
def submit_publication(json_metadata):
    username = request.environ["username"]
    metadata = process_metadata(json_metadata)

    # make sure that user is sending the file with the metadata
    if not request.files:
        abort(text="Tělo requestu musí obsahovat ohlašovaný soubor!")

    # get handler to upload object
    file_key = request.files.keys()[0]
    upload_file = request.files[file_key].file

    # generate the ID for the REST request
    rest_id = str(uuid.uuid4())
    metadata["rest_id"] = rest_id

    # put it into the cache database
    cache_db = CacheHandler()
    cache_db.add(
        username=username,
        rest_id=rest_id,
        metadata=metadata,
        file_obj=upload_file,
    )

    # put the tracking request to the StatusHandler
    status_db = StatusHandler()
    status_db.register_status_tracking(
        username=username,
        rest_id=rest_id
    )

    return rest_id


@get(join(V1_PATH, "structures", "riv"))
def riv_structure():
    return dict(RIV_CATEGORIES)


@get(join(V1_PATH, "structures", "library_map"))
def library_structure():
    return LIBRARY_MAP


@route("/")
def description_page():
    with open(join(TEMPLATE_PATH, "index.html")) as f:
        content = f.read()

    dom = dhtmlparser.parseString(content)
    for rst in dom.find("rst"):
        rst_content = publish_parts(rst.getContent(), writer_name='html')
        rst_content = rst_content['html_body'].encode("utf-8")
        rst.replaceWith(dhtmlparser.HTMLElement(rst_content))

    return dom.prettify()


# Main program ================================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server",
        default=settings.WEB_SERVER,
        help="Type of the server used for threading. Default '%s'." % (
            settings.WEB_SERVER
        )
    )
    parser.add_argument(
        "--host",
        default=settings.WEB_ADDR,
        help="Address to which the bottle should listen. Default '%s'." % (
            settings.WEB_ADDR
        )
    )
    parser.add_argument(
        "--port",
        default=settings.WEB_PORT,
        type=int,
        help="Port on which the server should listen. Default %d." % (
            settings.WEB_PORT
        )
    )
    parser.add_argument(
        "--zeo-client-conf-file",
        default=settings.ZEO_CLIENT_CONF_FILE,
        help="Path to the ZEO configuration file. Default %s." % (
            settings.ZEO_CLIENT_CONF_FILE
        )
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Use debug mode. Default False."
    )
    parser.add_argument(
        "--reloader",
        action="store_true",
        help="Use reloader."
    )
    parser.add_argument(
        "--quiet",
        default=False,
        action="store_true",
        help="Be quiet."
    )

    args = parser.parse_args()

    # don't forget to set connection to database
    USER_DB = UserHandler(
        conf_path=args.zeo_client_conf_file,
        project_key=settings.PROJECT_KEY,
    )

    # run the server
    run(
        server=args.server,
        host=args.host,
        port=args.port,
        debug=args.debug or settings.WEB_DEBUG,
        reloader=args.reloader or settings.WEB_RELOADER,
        quiet=args.quiet
    )
else:
    # don't forget to set connection to database
    USER_DB = UserHandler(
        conf_path=settings.ZEO_CLIENT_CONF_FILE,
        project_key=settings.PROJECT_KEY,
    )
