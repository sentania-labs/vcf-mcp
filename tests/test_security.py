from __future__ import annotations

import logging
import os
import stat
from pathlib import Path
from unittest import mock

import pytest

from vcf_mcp.security import SecretStoreUnavailable, validate_private_file


def _private_file(path: Path, mode: int) -> None:
    path.write_text("synthetic-private-value")
    path.chmod(mode)


def test_owned_group_writable_file_is_corrected_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "session_secret"
    _private_file(path, 0o660)

    with caplog.at_level(logging.WARNING, logger="vcf_mcp.security"):
        details = validate_private_file(path)

    assert details.st_mode & 0o777 == 0o600
    assert path.stat().st_mode & 0o777 == 0o600
    assert str(path) in caplog.text
    assert "mode 0660" in caplog.text
    assert "corrected to 0600" in caplog.text


def test_group_access_is_accepted_and_logged_when_chmod_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "credential_keyring.json"
    _private_file(path, 0o660)

    with (
        mock.patch(
            "vcf_mcp.security.os.chmod",
            side_effect=PermissionError("read-only mount"),
        ),
        caplog.at_level(logging.WARNING, logger="vcf_mcp.security"),
    ):
        details = validate_private_file(path)

    assert details.st_mode & 0o777 == 0o660
    assert str(path) in caplog.text
    assert "could not be tightened to 0600" in caplog.text
    assert "only service-owner and group access is present" in caplog.text


def test_supplementary_group_access_is_accepted_when_chmod_fails(
    tmp_path: Path,
) -> None:
    path = tmp_path / "credential_keyring.json"
    _private_file(path, 0o660)
    file_gid = path.stat().st_gid

    with (
        mock.patch(
            "vcf_mcp.security.os.chmod",
            side_effect=PermissionError("read-only mount"),
        ),
        mock.patch("vcf_mcp.security.os.getegid", return_value=file_gid + 1),
        mock.patch("vcf_mcp.security.os.getgroups", return_value=[file_gid]),
    ):
        details = validate_private_file(path)

    assert details.st_mode & 0o777 == 0o660


def test_unrelated_group_access_is_refused_when_chmod_fails(
    tmp_path: Path,
) -> None:
    path = tmp_path / "credential_keyring.json"
    _private_file(path, 0o660)
    file_gid = path.stat().st_gid
    service_gids = [file_gid + 1, file_gid + 2]

    with (
        mock.patch(
            "vcf_mcp.security.os.chmod",
            side_effect=PermissionError("read-only mount"),
        ),
        mock.patch("vcf_mcp.security.os.getegid", return_value=service_gids[0]),
        mock.patch(
            "vcf_mcp.security.os.getgroups", return_value=[service_gids[1]]
        ),
        pytest.raises(SecretStoreUnavailable) as failure,
    ):
        validate_private_file(path)

    message = str(failure.value)
    assert str(path) in message
    assert f"gid {file_gid}" in message
    assert str(service_gids) in message
    assert "set the file group to a service group or set mode to 0600" in message


def test_successful_no_op_chmod_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "session_secret"
    _private_file(path, 0o604)

    with (
        mock.patch("vcf_mcp.security.os.chmod"),
        pytest.raises(SecretStoreUnavailable) as failure,
    ):
        validate_private_file(path)

    message = str(failure.value)
    assert str(path) in message
    assert "still has mode 0604" in message
    assert "set mode to 0600" in message


def test_chmod_revalidation_refuses_changed_file_type(tmp_path: Path) -> None:
    path = tmp_path / "session_secret"
    _private_file(path, 0o604)
    initial = path.stat()
    changed = mock.Mock(
        st_mode=stat.S_IFDIR | 0o600,
        st_uid=initial.st_uid,
        st_gid=initial.st_gid,
    )

    with (
        mock.patch.object(Path, "stat", side_effect=[initial, changed]),
        pytest.raises(SecretStoreUnavailable) as failure,
    ):
        validate_private_file(path)

    message = str(failure.value)
    assert str(path) in message
    assert "not a regular file" in message
    assert "mode 0600" in message


def test_chmod_revalidation_refuses_changed_ownership(tmp_path: Path) -> None:
    path = tmp_path / "session_secret"
    _private_file(path, 0o604)
    initial = path.stat()
    changed_uid = initial.st_uid + 1
    changed = mock.Mock(
        st_mode=stat.S_IFREG | 0o600,
        st_uid=changed_uid,
        st_gid=initial.st_gid,
    )

    with (
        mock.patch.object(Path, "stat", side_effect=[initial, changed]),
        pytest.raises(SecretStoreUnavailable) as failure,
    ):
        validate_private_file(path)

    message = str(failure.value)
    assert str(path) in message
    assert f"owned by uid {changed_uid}" in message
    assert f"set ownership to uid {os.geteuid()}" in message
    assert "mode to 0600" in message


def test_other_access_is_refused_when_chmod_fails(tmp_path: Path) -> None:
    path = tmp_path / "audit_digest_key"
    _private_file(path, 0o604)

    with (
        mock.patch(
            "vcf_mcp.security.os.chmod",
            side_effect=PermissionError("read-only mount"),
        ),
        pytest.raises(SecretStoreUnavailable) as failure,
    ):
        validate_private_file(path)

    message = str(failure.value)
    assert str(path) in message
    assert "mode 0604" in message
    assert "outside the service group" in message
    assert "set mode to 0600" in message


def test_file_owned_by_another_user_is_refused_without_chmod(tmp_path: Path) -> None:
    path = tmp_path / "session_secret"
    _private_file(path, 0o660)
    service_uid = os.geteuid() + 1

    with (
        mock.patch("vcf_mcp.security.os.geteuid", return_value=service_uid),
        mock.patch("vcf_mcp.security.os.chmod") as chmod,
        pytest.raises(SecretStoreUnavailable) as failure,
    ):
        validate_private_file(path)

    assert str(path) in str(failure.value)
    assert f"set ownership to uid {service_uid}" in str(failure.value)
    chmod.assert_not_called()
