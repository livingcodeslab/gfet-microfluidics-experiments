"""Interact with the Opentrons OT-2R via the HTTP API"""
from functools import partial
from typing import Any, Protocol, Sequence
from urllib.parse import urljoin

import requests

from gdnasynth.ot2r.types import HTTPRequestMethod
from gdnasynth.ot2r.commands.base_types import NonEmptyString
from gdnasynth.ot2r.commands.types import APIError, OpentronsVersion
from gdnasynth.ot2r.serialization import to_jsonable


_GENERAL_ERROR_CODE = "4000"


class RobotError(Exception):
    """Base class for errors talking to the OT-2R robot."""


class RobotUnreachable(RobotError):
    """The robot could not be reached (powered off, network down, ...)."""


class RobotResponseError(RobotError):
    """The robot returned an error response (HTTP status >= 400)."""

    def __init__(
            self,
            status_code: int,
            body: str,
            api_errors: Sequence[APIError] = ()
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.api_errors = tuple(api_errors)
        super().__init__(
            f"OT-2R robot responded with HTTP {status_code}: "
            f"{body.strip() or '<empty body>'}")


def parse_api_errors(data: Sequence[dict]) -> Sequence[APIError]:
    """Parse the ``errors`` list of a robot-server error envelope."""
    return tuple(
        APIError(
            id=NonEmptyString(item["id"]),
            title=NonEmptyString(item.get("title", item["id"])),
            detail=NonEmptyString(item["detail"]),
            errorCode=NonEmptyString(
                item.get("errorCode", _GENERAL_ERROR_CODE)),
            source=item.get("source"),
            meta=item.get("meta"))
        for item in data)


class RequestSender(Protocol):
    """Send a request to the robot.

    The connection details (robot address and Opentrons version) are
    already bound, so callers supply only the request-specific
    arguments.
    """
    def __call__(
            self,
            endpoint: str,
            method: HTTPRequestMethod,
            data: dict,
            **kwargs: Any
    ) -> requests.Response:
        """Send a request to the given endpoint on the robot."""


def make_request_sender(
        robot_address: str, opentrons_version: OpentronsVersion
) -> RequestSender:
    """Bind connection details into a RequestSender.

    :param robot_address: The URL/IP address of the robot.
    :type robot_address: str
    :param opentrons_version: The Opentrons API version to use.
    :type opentrons_version: gdnasynth.ot2r.commands.types.OpentronsVersion

    :rtype gdnasynth.ot2r.http.RequestSender
    """
    return partial(
        send_request,
        robot_address=robot_address,
        opentrons_version=opentrons_version)


def _response_error(response: requests.Response) -> RobotResponseError:
    """Build a RobotResponseError, parsing an API error envelope if present."""
    api_errors: Sequence[APIError] = ()
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and "errors" in payload:
        api_errors = parse_api_errors(payload["errors"])
    return RobotResponseError(response.status_code, response.text, api_errors)


def send_request(
        robot_address: str,
        endpoint: str,
        method: HTTPRequestMethod,
        opentrons_version: OpentronsVersion,
        data: dict,
        **kwargs
) -> requests.Response:
    """Send a HTTP request to the OT-2R robot.

    :param robot_address: The URL/IP address of the robot.
    :type robot_address: str
    :param endpoint: The endpoint to send request to on the robot's HTTP API
    :type endpoint: str
    :param method: The HTTP method to use
    :type method: gdnasynth.ot2r.types.HTTPRequestMethod
    :param opentrons_version: The Opentrons API version to use.
    :type opentrons_version: gdnasynth.ot2r.commands.types.OpentronsVersion
    :param data: The data to send with the HTTP request.  For a multipart
        upload, this holds the form fields and the files are passed via the
        ``files`` keyword argument.
    :type data: dict

    :rtype requests.Response

    :raises AttributeError: if the method is not supported.
    :raises RobotUnreachable: if the robot cannot be reached.
    :raises RobotResponseError: if the robot responds with HTTP status >= 400.
    """
    try:
        _method = method.lower()
        assert _method in ("get", "post", "put", "delete", "patch")
    except AssertionError as _aerr:
        raise AttributeError(
            "You attempted to send a HTTP request with an unsupported method "
            f"({_method.upper()}) to the OT-2R robot.") from _aerr

    request_method = getattr(requests, _method)
    files = kwargs.pop("files", None)
    headers = {
        **kwargs.pop("headers", {}),
        "Accept": "application/json",
        "opentrons-version": f"{opentrons_version}",
    }
    timeout = kwargs.pop("timeout", (9.13, 20))
    if files is None:
        headers["Content-Type"] = "application/json"
        body = {("params" if _method == "get" else "json"): to_jsonable(data)}
    else:
        body = {"data": data, "files": files}
    try:
        response = request_method(
            url=urljoin(robot_address, endpoint),
            headers=headers, timeout=timeout, **body, **kwargs)
    except requests.exceptions.RequestException as _reqerr:
        raise RobotUnreachable(
            f"Could not reach the OT-2R robot at {robot_address}."
        ) from _reqerr

    if response.status_code >= 400:
        raise _response_error(response)
    return response
