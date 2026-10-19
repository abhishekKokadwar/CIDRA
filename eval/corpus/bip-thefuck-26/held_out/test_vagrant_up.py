"""Held-out tests for bip-thefuck-26 (never shown to the model).

The visible test checks `vagrant ssh` and `vagrant rdp`. These check the same
rule on other vagrant commands: with a machine name, start that machine or all
of them; without one, start all, with no stray double space.
"""
from thefuck.rules.vagrant_up import get_new_command
from tests.utils import Command

STDERR = 'VM must be running to open SSH connection. Run `vagrant up`\nto start the virtual machine.'


def test_a_named_machine_offers_that_machine_then_all():
    assert get_new_command(Command('vagrant resume web', stderr=STDERR), None) == \
        ['vagrant up web && vagrant resume web', 'vagrant up && vagrant resume web']


def test_no_machine_starts_all():
    assert get_new_command(Command('vagrant provision', stderr=STDERR), None) == 'vagrant up && vagrant provision'
