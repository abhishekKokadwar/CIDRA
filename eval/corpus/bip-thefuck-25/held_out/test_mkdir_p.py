"""Held-out tests for bip-thefuck-25 (never shown to the model).

The visible test checks `mkdir` and `hdfs dfs -mkdir` with plain paths. These
check the same rule on another wrapper command, and that the rule still fires
for a path that merely contains "-p", as directory names often do.
"""
from thefuck.rules.mkdir_p import get_new_command, match
from tests.utils import Command


def test_the_rule_fires_for_a_path_containing_dash_p():
    assert match(Command('mkdir my-project/src/app',
                         stderr='mkdir: my-project/src: No such file or directory'), None)


def test_new_command_for_another_mkdir_wrapper():
    assert get_new_command(Command('hadoop fs -mkdir a/b/c'), None) == 'hadoop fs -mkdir -p a/b/c'
