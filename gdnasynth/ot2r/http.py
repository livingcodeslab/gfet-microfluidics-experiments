"""Interact with the Opentrons OT-2R via the HTTP API"""
from urllib.parse import urljoin

import requests

from gdnasynth.ot2r.types import HTTPRequestMethod
from gdnasynth.ot2r.commands.types import OpentronsVersion


def send_request(
        robot_address: str,
        endpoint: str,
        method: HTTPRequestMethod,
        opentrons_version: OpentronsVersion,
        data: dict,
        **kwargs
) -> requests.Response:
    """Send a HTTP request to the OT-2R robot.

    :param config: The robot configuration information.
    :type config: gdnasynth.ot2r.types.Configuration
    :param endpoint: The endpoint to send request to on the robot's HTTP API
    :type endpoint: str
    :param method: The HTTP method to use
    :type method: gdnasynth.ot2r.types.HTTPRequestMethod
    :param data: The data to send with the HTTP request
    :type data: dict

    :rtype requests.Response

    :raises AssertionError: If the method is not one of the expected HTTP methods.
    :raises AttributeError:
    """
    try:
        _method = method.lower()
        assert _method in ("get", "post", "put", "delete", "patch")

        request_method = getattr(requests, _method)
        return request_method(
            url=urljoin(robot_address, endpoint),
            **{
                **kwargs,
                ("params" if _method == "get" else "json"): data,
                "timeout": kwargs.get("timeout", (9.13, 20)),
                "headers": {
                    **kwargs.get("headers", {}),
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "opentrons-version": f"{opentrons_version}"
                }
            })
    except AssertionError as _aerr:
        raise AttributeError(
            "You attempted to send a HTTP request with an unsupported method "
            f"({_method.upper()}) to the OT-2R robot.") from _aerr
