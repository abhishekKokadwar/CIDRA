"""Held-out tests for bip-thefuck-2 (never shown to the model).

The visible test mocks Path and checks which directories are listed. These use
real directories with real files, on a PATH joined with the platform's
separator, and check the executables found.
"""
import pytest

from thefuck.utils import get_all_executables


@pytest.mark.usefixtures('no_memoize')
@pytest.mark.parametrize('pathsep', [';', ':'])
def test_executables_from_every_path_entry(tmpdir, monkeypatch, pathsep):
    first, second = tmpdir.mkdir('first'), tmpdir.mkdir('second')
    first.join('alpha').write('')
    second.join('beta').write('')
    monkeypatch.setattr('os.pathsep', pathsep)
    monkeypatch.setenv('PATH', pathsep.join([str(first), str(second)]))
    found = get_all_executables()
    assert 'alpha' in found and 'beta' in found
