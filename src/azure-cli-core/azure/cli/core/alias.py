# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os
import re

from knack.log import get_logger
from knack.util import CLIError

from azure.cli.core._environment import get_config_dir

GLOBAL_CONFIG_DIR = get_config_dir()
ALIAS_FILE_NAME = 'alias'
GLOBAL_ALIAS_PATH = os.path.join(GLOBAL_CONFIG_DIR, ALIAS_FILE_NAME)

PLACEHOLDER_REGEX = r'\s*{\d+}'
ENV_VAR_REGEX = r'\$[a-zA-Z][a-zA-Z0-9]*'

logger = get_logger(__name__)


class AliasTransformer:

    def __init__(self):
        from configparser import ConfigParser

        self.alias_map = ConfigParser()
        self.alias_map.read(GLOBAL_ALIAS_PATH)

    def transform(self, args):
        """ Transform any aliases in args to their respective commands """
        transformed = []
        args_iter = enumerate(map(str.lower, args), 1)

        for i, arg in args_iter:
            num_positional_args = self.count_positional_args(arg)

            if num_positional_args == 0:
                # Call split() because the command that the alias points to might contain spaces
                transformed += self.alias_map[arg]['command'].split() if arg in self.alias_map else [arg]
            else:
                command = self.alias_map[self.get_full_alias(arg)]['command']
                for placeholder, replacement in self.build_pos_args_map(args[i: i + num_positional_args]):
                    command = command.replace(placeholder, replacement)
                    # Skip the next iteration because it is already consumed as a positional argument above
                    next(args_iter)

                transformed += command.split()

        transformed = self.inject_env_vars(transformed)

        if transformed != args:
            self.check_recursive_alias(transformed)
            logger.debug(
                'Alias Transfromer: Command Arguments Transformed From %s to %s', args, transformed)

        return transformed

    def count_positional_args(self, alias):
        """ Count how many positional arguments there are in an alias. """
        return len(re.findall(PLACEHOLDER_REGEX, self.get_full_alias(alias)))

    def get_full_alias(self, query):
        """ Return the full alias (with the placeholders, if any) given a query """
        if query in self.alias_map:
            return query
        for section in self.alias_map.sections():
            if section.split()[0] == query:
                return section
        return ''

    def build_pos_args_map(self, args):  # pylint: disable=no-self-use
        """
        Build and return a tuple of tuples ([0], [1]) where the [0] is the positional argument
        placeholder and [1] is the argument value. e.g. ('{0}', pos_arg_1), ('{1}', pos_arg_2) ... )
        """
        return tuple(('{{{}}}'.format(i), arg) for i, arg in enumerate(args))

    def inject_env_vars(self, args):  # pylint: disable=no-self-use
        """ Inject environment variables into the commands """
        command = ' '.join(args)
        env_vars = re.findall(ENV_VAR_REGEX, command)
        for env_var in env_vars:
            command = command.replace(env_var, os.path.expandvars(env_var))
        return command.split()

    def check_recursive_alias(self, commands):
        """ Check for any recursive alias """
        for subcommand in commands:
            if self.get_full_alias(subcommand):
                raise CLIError('Potentially recursive alias: \'{}\' is referred by another alias'.format(subcommand))
