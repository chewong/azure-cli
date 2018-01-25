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
PLACEHOLDER_SPLIT_REGEX = r'\s*{\d+\.split\(((\'.*\')|(".*"))\)\[\d+\]}'
ENV_VAR_REGEX = r'\$[a-zA-Z][a-zA-Z0-9]*'

COLLISION_WARNING = '\'%s\' is currently mapped to \'%s\' in alias configuration.'

logger = get_logger(__name__)


class AliasTransformer:

    def __init__(self, reserved_commands):
        from configparser import ConfigParser, DuplicateSectionError

        self.alias_table = ConfigParser()
        try:
            self.alias_table.read(GLOBAL_ALIAS_PATH)
        except DuplicateSectionError:
            pass

        self.reserved_commands = reserved_commands
        # A regex that detects if we have
        self.collision_regex = r'^'
        # A cache that keeps track of which alias collided with a reserved command
        self.collision_cache = set()

    def transform(self, args):
        """ Transform any aliases in args to their respective commands """
        transformed_commands = []
        args_iter = enumerate(map(str.lower, args), 1)

        def is_collision(alias):
            """ Check if a given alias collides with a reserved command """
            # Collision in this context is defined as an alias containing the exact same characters as a
            # reserved command in the same level. For example:
            # level 0 | level 1 | level 2 | ...
            #    az       vm       create   ...
            # If a user defined an alias [vm]->[account list], and typed 'az vm', there is a collision because 'vm' in
            # 'az vm' is in level 1 and 'vm' itself is a level-1-reserved word. However, if the alias is [vm]->[list],
            # 'az account vm' would translate to 'az account list' because vm is not a level-2-reserved word.
            # However, we do not encourage customers to define alias that contains reserved words

            # self.collision_regex is an regex that we keep building throughout transform(), which checks for
            # collision. Simply append alias to self.collision_regex and check if there are commands in
            # self.reserved_words that prefix with self.collision_regex. If the result set is empty, we can conclude
            # that there is no collision occurred (for now).
            self.collision_regex += r'{}($|\s)'.format(alias)
            collided = self.get_truncated_reserved_commands()

            if collided:
                self.collision_cache.add(alias)
                self.reserved_commands = collided
                return True
            return False

        for i, alias in args_iter:
            # Full alias is an alias plus any placeholder
            full_alias = self.get_full_alias(alias)
            num_pos_args = self.count_positional_args(full_alias)
            cmd_derived_from_alias = self.alias_table[full_alias].get(
                'command', alias) if full_alias in self.alias_table else alias

            # If we have an alias collision, DO NOT transform it and simply append it to transformed_commands
            if alias[0] != '-' and is_collision(alias):
                transformed_commands.append(alias)
                if alias != cmd_derived_from_alias:
                    logger.warning(COLLISION_WARNING, alias, cmd_derived_from_alias)
                continue

            if num_pos_args == 0 and alias != cmd_derived_from_alias:
                # Truncate the list of reserved commands based on newly-dervied command
                self.collision_regex = self.collision_regex.replace(alias, cmd_derived_from_alias)
                self.reserved_commands = self.get_truncated_reserved_commands()
            elif num_pos_args > 0:
                # Take arguments indexed from i to i + num_pos_args and inject
                # them as positional arguments into the command
                for placeholder, pos_arg in self.build_pos_args_map(args[i: i + num_pos_args]):
                    if placeholder not in cmd_derived_from_alias:
                        raise CLIError('Inconsistent placeholder indexing in alias command.')
                    cmd_derived_from_alias = cmd_derived_from_alias.replace(placeholder, pos_arg)
                    # Skip the next arg because it has been already consumed as a positional argument above
                    next(args_iter)

            # Invoke split() because the command that the alias points to might contain spaces
            transformed_commands += cmd_derived_from_alias.split()

        transformed_commands = self.inject_env_vars(transformed_commands)

        if transformed_commands != args:
            self.check_recursive_alias(transformed_commands)
            logger.debug(
                'Alias Transfromer: Command Arguments Transformed From %s to %s', args, transformed_commands)

        return transformed_commands

    def get_full_alias(self, query):
        """ Return the full alias (with the placeholders, if any) given a search query """
        if query in self.alias_table:
            return query
        for section in self.alias_table.sections():
            if section.split()[0] == query:
                return section
        return ''

    def count_positional_args(self, full_alias):  # pylint: disable=no-self-use
        """ Count how many positional arguments there are in an alias. """
        return len(re.findall(PLACEHOLDER_REGEX, full_alias))

    def build_pos_args_map(self, args):  # pylint: disable=no-self-use
        """
        Build and return a tuple of tuples ([0], [1]) where the [0] is the positional argument
        placeholder and [1] is the argument value. e.g. (('{0}', pos_arg_1), ('{1}', pos_arg_2) ... )
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
            if subcommand not in self.collision_cache and self.get_full_alias(subcommand):
                raise CLIError('Potentially recursive alias: \'{}\' is associated by another alias'.format(subcommand))

    def get_truncated_reserved_commands(self):
        """ List all the reserved commands where their prefix is the same as the current collision regex """
        return list(filter(re.compile(self.collision_regex).match, self.reserved_commands))
