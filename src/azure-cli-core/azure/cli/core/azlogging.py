# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Logging for Azure CLI

- Loggers: The name of the parent logger is defined in CLI_LOGGER_NAME variable. All the loggers used in the CLI
           must descends from it, otherwise it won't benefit from the logger handlers, filters and level configuration.

- Handlers: There are two default handlers will be added to both CLI parent logger and root logger. One is a colorized
            stream handler for console output and the other is a file logger handler. The file logger can be enabled or
            disabled through 'az configure' command. The logging file locates at path defined in AZ_LOGFILE_DIR.

- Level: Based on the verbosity option given by users, the logging levels for root and CLI parent loggers are:

               CLI Parent                  Root
            Console     File        Console     File
omitted     Warning     Debug       Critical    Debug
--verbose   Info        Debug       Critical    Debug
--debug     Debug       Debug       Debug       Debug

"""

import knack.log
from knack.log import CLILogging, _CustomStreamHandler

CLI_LOGGER_NAME = 'az'


class _NonColorizedCustomStreamHandler(_CustomStreamHandler):

    def _should_enable_color(self):
        return False


class AzCliLogging(CLILogging):

    def _init_console_handlers(self, root_logger, cli_logger, log_level_config):
        if self.cli_ctx.config.getboolean('logging', 'colors', fallback=True):
            stream_handler = _CustomStreamHandler
        else:
            stream_handler = _NonColorizedCustomStreamHandler

        root_logger.addHandler(stream_handler(log_level_config['root'],
                                              self.console_log_format['root']))
        cli_logger.addHandler(stream_handler(log_level_config[knack.log.CLI_LOGGER_NAME],
                                             self.console_log_format[knack.log.CLI_LOGGER_NAME]))
