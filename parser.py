import json
import re

import xml.etree.ElementTree as ET

namespaces = {
    "poets": "https://poets-project.org/schemas/virtual-graph-schema-v2"
}


def load_xml(file):
    """Parse xml file."""
    try:
        return ET.parse(file).getroot()
    except IOError:
        raise Exception("File not found: %s" % file)


def get_children(parent, child_name):
    """Return children of 'parent' with name 'child_name'."""
    return parent.findall("poets:%s" % child_name, namespaces)


def get_child(parent, child_name):
    """Return child of 'parent' with name 'child_name'."""
    return parent.find("poets:%s" % child_name, namespaces)


def get_text(element):
    """Return inner text of an XML element."""
    return element.text.strip() if element is not None else None


def read_poets_xml(file):
    """Parse POETS xml file."""

    root = load_xml(file)
    graph_type = get_child(root, "GraphType")
    graph_inst = get_child(root, "GraphInstance")
    shared_code = get_child(graph_type, "SharedCode")
    device_types = get_child(graph_type, "DeviceTypes")
    message_types = get_child(graph_type, "MessageTypes")
    graph_type_doc = get_child(graph_type, "Documentation")

    return {
        "graph_type": {
            "id": graph_type.attrib['id'],
            "doc": get_text(graph_type_doc),
            "shared_code": get_text(shared_code),
            "device_types": map(parse_device_type, device_types),
            "message_types": map(parse_message_type, message_types)
        },
        "graph_instance": parse_graph_instance(graph_inst)
    }

    return graph_type


def parse_graph_instance(root):

    devices = [
        {
            "id": device.attrib["id"],
            "type": device.attrib["type"],
            "properties": parse_property_str(get_text(get_child(device, "P")))
        }
        for device in get_child(root, "DeviceInstances")
    ]

    # print get_child(root, "EdgeInstances")

    edges = [
        parse_edge_str(edge.attrib["path"])
        for edge in get_child(root, "EdgeInstances")
    ]

    return {"devices": devices, "edges": edges}


def parse_edge_str(edge_str):
    reg1 = r"(\w+)\:(\w+)\-(\w+)\:(\w+)"
    pat1 = re.compile(reg1, flags=re.MULTILINE)

    for item in pat1.findall(edge_str):
        return {
            "src": item[:2],
            "dst": item[2:]
        }


def parse_property_str(prop_str):
    """Parse a POETS property string.

    Property strings (in POETS) are string representations of JSON
    dictionaries, without the leading and trailing brackets.
    """
    return json.loads("{%s}" % prop_str) if prop_str else {}


def parse_message_type(root):
    """Parse <MessageType> POETS xml element."""

    doc = get_child(root, "Documentation")
    msg = get_child(root, "Message")

    return {
        "id": root.attrib["id"],
        "doc": get_text(doc),
        "fields": parse_state(msg)
    }


def parse_device_type(root):
    """Parse <DeviceType> POETS xml element."""

    msg = get_child(root, "Message")
    state = get_child(root, "State")

    input_pins = [
        {
            "name": pin.attrib["name"],
            "message_type": pin.attrib["messageTypeId"],
            "on_receive": get_child(pin, "OnReceive").text.strip()
        }
        for pin in get_children(root, "InputPin")
    ]

    output_pins = [
        {
            "name": pin.attrib["name"],
            "message_type": pin.attrib["messageTypeId"],
            "on_send": get_child(pin, "OnSend").text.strip()
        }
        for pin in get_children(root, "OutputPin")
    ]

    return {
        "id": root.attrib["id"],
        "state": parse_state(state),
        "ready_to_send": get_child(root, "ReadyToSend").text.strip(),
        "input_pins": input_pins,
        "output_pins": output_pins
    }


def parse_state(root):
    """Parse a POETS xml element with state fields.

    State fields are <Scalar> or <Array> elements.

    """

    if root is None:
        return []

    scalars = [{
        "name": scalar.attrib['name'],
        "type": scalar.attrib['type'],
        "doc": get_text(get_child(scalar, "Documentation")),
    } for scalar in get_children(root, "Scalar")]

    arrays = [{
        "name": array.attrib['name'],
        "type": array.attrib['type'],
        "doc": get_text(get_child(scalar, "Documentation")),
        "length": int(array.attrib['length'])
    } for array in get_children(root, "Array")]

    return {"scalars": scalars, "arrays": arrays}
