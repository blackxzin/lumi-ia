import pytest

from backend.app.context.workspace import Workspace
from backend.app.permissions.actions import Permissions
from backend.app.schemas.messages import ToolInput


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "/etc/passwd",
        ".env",
        ".git/config",
        "keys/private.pem",
        "credentials.json",
        "node_modules/a.js",
        "secret.txt",
    ],
)
def test_file_boundary(tmp_path, path):
    with pytest.raises(ValueError):
        Workspace({"p": tmp_path}).read("p", path)


def test_symlink_boundary(tmp_path):
    (tmp_path / "link").symlink_to("/etc/passwd")
    with pytest.raises(ValueError):
        Workspace({"p": tmp_path}).read("p", "link")


def test_binary_and_oversized_files(tmp_path):
    w = Workspace({"p": tmp_path})
    for data in (b"\0abc", b"a" * 65537):
        (tmp_path / "file.txt").write_bytes(data)
        with pytest.raises(ValueError):
            w.read("p", "file.txt")


def test_approval_bound_to_request_and_single_use():
    p = Permissions()
    original = ToolInput(name="run_project_tests", project="a")
    identity = p.request(original)
    original.approval_id = identity
    assert not p.consume(original)
    assert p.decide(identity, True)
    changed = original.model_copy(update={"project": "b"})
    assert not p.consume(changed)
    assert p.consume(original)
    assert not p.consume(original)
