import pytest  # type: ignore

from level0.import_l0_handler.import_level0 import stw_correction


@pytest.mark.parametrize("filename, correction", [
    ('017f6e6c.ac2', 0 * 2**32),
    ('11f1eafe.fba', 1 * 2**32),
    ('20683ad2.ac2', 2 * 2**32),
    ('30683ad2.ac2', 3 * 2**32),
])
def test_correction(filename: str, correction: int):
    assert stw_correction(filename) == correction
