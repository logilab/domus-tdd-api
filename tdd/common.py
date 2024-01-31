import subprocess
import json

from flask import Response

from tdd.sparql import (
    CONSTRUCT_FROM_GRAPH,
    CLEAR_INSERT_GRAPH,
    GET_NAMED_GRAPHS,
    delete_named_graph,
    query,
)
from tdd.metadata import insert_metadata, delete_metadata
from tdd.errors import IDNotFound
from tdd.config import CONFIG

import re


def get_check_schema_from_url_params(request):
    check_schema_param = request.args.get("check-schema")
    check_schema = CONFIG["CHECK_SCHEMA"]
    if check_schema_param in ["false", "False", "0"]:
        check_schema = False
    return check_schema

def delete_id(uri):
    resp = query(
        GET_NAMED_GRAPHS.format(uri=uri),
    )
    if resp.status_code == 200:
        results = resp.json()["results"]["bindings"]
        for result in results:
            delete_named_graph(result["namedGraph"]["value"])
    delete_metadata(uri)
    return Response(status=204)


def json_ld_to_ntriples(ld_content):
    p = subprocess.Popen(
        ["node", "tdd/lib/transform-to-nt.js", json.dumps(ld_content)],
        stdout=subprocess.PIPE,
    )
    nt_content = p.stdout.read()
    return nt_content.decode("utf-8")


def put_in_sparql(content, uri, context, delete_if_exists, ontology):
    if delete_if_exists:
        delete_id(uri)
    insert_metadata(uri, context, ontology)
    query(
        CLEAR_INSERT_GRAPH.format(
            uri=f'{ontology["prefix"]}:{uri}',
            content=content,
        ),
        request_type="update",
    )


def put_json_in_sparql(
    json_content,
    uri,
    context,
    delete_if_exists,
    ontology,
    forced_type=None,
):
    nt_content = json_ld_to_ntriples(json_content)
    if forced_type:
        nt_content += f"<{uri}> a <{forced_type}>."
    put_in_sparql(nt_content, uri, context, delete_if_exists, ontology)


def put_rdf_in_sparql(g, uri, context, delete_if_exists, ontology, forced_type=None):
    nt_content = g.serialize(format="nt")
    if forced_type:
        nt_content += f"<{uri}> a <{forced_type}>."
    put_in_sparql(nt_content, uri, context, delete_if_exists, ontology)


def frame_nt_content(id, nt_content, frame):
    p = subprocess.Popen(
        ["node", "tdd/lib/frame-jsonld.js", nt_content, json.dumps(frame)],
        stdout=subprocess.PIPE,
    )
    json_ld_compacted = p.stdout.read()
    return json_ld_compacted


def get_id_description(uri, content_type, ontology):
    resp = query(
        CONSTRUCT_FROM_GRAPH.format(named_graph=f'{ontology["prefix"]}:{uri}'),
        headers={"Accept": content_type},
    )
    # if no data, send 404
    if not resp.text.strip() or not (
        re.search(r"^[^\#]", resp.text, re.MULTILINE)
    ):  # because some SPARQL endpoint may send "# Empty file" as response
        raise IDNotFound()
    return resp.text
