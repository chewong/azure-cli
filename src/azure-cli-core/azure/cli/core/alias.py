# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os
import re

from knack.log import get_logger

from azure.cli.core._environment import get_config_dir

GLOBAL_CONFIG_DIR = get_config_dir()
ALIAS_FILE_NAME = 'alias'
GLOBAL_ALIAS_PATH = os.path.join(GLOBAL_CONFIG_DIR, ALIAS_FILE_NAME)
PLACEHOLDER_REGEX = r'\s*{\d+}'

logger = get_logger(__name__)

class AliasTransformer:

    def __init__(self):
        from configparser import ConfigParser

        self.alias_map = ConfigParser()
        self.alias_map.read(GLOBAL_ALIAS_PATH)

    def transform(self, args):
        """ Transform aliases to their respective commands """
        transformed = []
        enum_iter = enumerate(args, 1)

        for i, arg in enum_iter:
            num_positional_args = self.count_positional_args(arg)

            if num_positional_args == 0:
                transformed += self.alias_map[arg]['command'].split() if arg in self.alias_map else [arg]
            else:
                command = self.alias_map[self.get_full_alias(arg)]['command']
                for placeholder, replacement in self.build_pos_args_map(args[i:i+num_positional_args]):
                    command = command.replace(placeholder, replacement)
                    # Skip the next iteration because it is consumed as a positional argument
                    next(enum_iter)

                transformed += command.split()

        logger.debug(
            'Alias Transfromer: Command Arguments Transformed From %s to %s', args, transformed)

        return transformed

    def count_positional_args(self, alias):
        """ Count how many positional arguments there are in an alias.
        Can be replaced by defining a new field in ini file """
        return len(re.findall(r'{\d+}', self.get_full_alias(alias)))

    def get_full_alias(self, query):
        """ Return the full alias (with placeholder, if any) given a query """
        if query in self.alias_map:
            return query
        for section in self.alias_map.sections():
            if section.split()[0] == query:
                return section
        return ''

    def build_pos_args_map(self, args):
        """
        Build and return a dictionary where the key is the positional argument placeholder and the value is
        the argument value
        """
        return {'{{{}}}'.format(i) : arg for i, arg in enumerate(args)}.items()
