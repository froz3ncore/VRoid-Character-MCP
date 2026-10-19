import pytest

from vroid_mcp.runtime import review_folder, validate_capture


@pytest.mark.parametrize('capture_id', ['', 'z' * 32, '../x', 'a/b', r'C:\escape', '0123456789abcdef'])
def test_review_folders_must_be_one_local_capture_id(tmp_path, capture_id):
    with pytest.raises(ValueError):
        review_folder(tmp_path, capture_id)


def test_review_folder_resolves_under_the_lab(tmp_path):
    folder = review_folder(tmp_path, 'a' * 32)
    assert folder == tmp_path / 'reviews' / ('a' * 32)


@pytest.mark.parametrize('views,size', [
    ([], 1024),
    (['front', 'front'], 1024),
    (['../x'], 1024),
    (['front'], 255),
    (['front'], 2049),
    (['front'], 512.5),
])
def test_capture_requests_are_bounded(views, size):
    with pytest.raises(ValueError):
        validate_capture(views, size)


def test_a_normal_capture_request_is_accepted():
    validate_capture(['front', 'full_back'], 1024)
