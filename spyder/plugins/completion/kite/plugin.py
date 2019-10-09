# -*- coding: utf-8 -*-

# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""Kite completion HTTP client."""

# Standard library imports
import logging
import functools

# Qt imports
from qtpy.QtCore import Slot

# Local imports
from spyder.config.base import _, running_under_pytest
from spyder.config.manager import CONF
from spyder.utils.programs import run_program
from spyder.api.completion import SpyderCompletionPlugin
from spyder.plugins.completion.kite.client import KiteClient
from spyder.plugins.completion.kite.utils.status import (
    check_if_kite_running, check_if_kite_installed)
from spyder.plugins.completion.kite.utils.install import (
    KiteInstallationThread)
from spyder.plugins.completion.kite.widgets.install import KiteInstallerDialog
from spyder.plugins.completion.kite.widgets.status import KiteStatusWidget


logger = logging.getLogger(__name__)


class KiteCompletionPlugin(SpyderCompletionPlugin):
    CONF_SECTION = 'kite'
    CONF_FILE = False

    COMPLETION_CLIENT_NAME = 'kite'

    def __init__(self, parent):
        SpyderCompletionPlugin.__init__(self, parent)
        self.available_languages = []
        self.client = KiteClient(None)
        self.kite_process = None

        # Installation
        self.kite_installation_thread = KiteInstallationThread(self)
        self.kite_installer = KiteInstallerDialog(
            parent,
            self.kite_installation_thread)

        # Status
        statusbar = parent.statusBar()  # MainWindow status bar
        self.open_file_updated = False
        self.kite_status_widget = KiteStatusWidget(None, statusbar, self)

        # Signals
        self.client.sig_client_started.connect(self.http_client_ready)
        self.client.sig_status_response_ready.connect(
            self.set_kite_status)
        self.client.sig_response_ready.connect(
            functools.partial(self.sig_response_ready.emit,
                              self.COMPLETION_CLIENT_NAME))
        self.kite_installation_thread.sig_installation_status.connect(
            self.set_kite_status)
        self.kite_installer.sig_visibility_changed.connect(
            self.show_status_tooltip)
        self.kite_status_widget.sig_clicked.connect(
            self.show_installation_dialog)
        self.main.sig_setup_finished.connect(self.mainwindow_setup_finished)

        # Config
        self.update_configuration()

    @Slot(list)
    def http_client_ready(self, languages):
        logger.debug('Kite client is available for {0}'.format(languages))
        self.available_languages = languages
        self.sig_plugin_ready.emit(self.COMPLETION_CLIENT_NAME)

    @Slot()
    def mainwindow_setup_finished(self):
        """
        This is called after the main window setup finishes to show Kite's
        installation dialog and onboarding if necessary.
        """
        kite_installation_enabled = self.get_option('show_installation_dialog')
        if kite_installation_enabled:
            self.show_installation_dialog()

    @Slot(str)
    @Slot(dict)
    def set_kite_status(self, status):
        """Show Kite status for the current file."""
        self.kite_status_widget.set_value(status)

    @Slot(bool)
    def show_status_tooltip(self, visible):
        """Show tooltip over the status widget for the installation process."""
        if not visible:
            if self.is_installing():
                text = _("Kite installation will continue in the background."
                         "<br>Click here to show the installation "
                         "dialog again.")
            else:
                text = _("Click here to show the installation dialog again.")
            self.kite_status_widget.show_tooltip(text)

    @Slot()
    def show_installation_dialog(self):
        """Show installation dialog."""
        installed, path = check_if_kite_installed()
        if not installed and not running_under_pytest():
            self.kite_installer.show()

    def send_request(self, language, req_type, req, req_id):
        if self.enabled and language in self.available_languages:
            self.client.sig_perform_request.emit(req_id, req_type, req)
        else:
            self.sig_response_ready.emit(self.COMPLETION_CLIENT_NAME,
                                         req_id, {})

    def send_status_request(self, filename):
        """Request status for the given file."""
        if not self.is_installing():
            self.client.sig_perform_status_request.emit(filename)

    def start_client(self, language):
        return language in self.available_languages

    def start(self):
        # Always start client to support possibly undetected Kite builds
        self.client.start()

        if not self.enabled:
            return
        installed, path = check_if_kite_installed()
        if not installed:
            return
        logger.debug('Kite was found on the system: {0}'.format(path))
        running = check_if_kite_running()
        if running:
            return
        logger.debug('Starting Kite service...')
        self.kite_process = run_program(path)

    def shutdown(self):
        self.client.stop()
        if self.kite_process is not None:
            self.kite_process.kill()

    def update_configuration(self):
        self.client.enable_code_snippets = CONF.get('lsp-server',
                                                    'code_snippets')
        self.enabled = self.get_option('enable')

    def is_installing(self):
        """Check if an installation is taking place."""
        return (self.kite_installation_thread.isRunning()
                and not self.kite_installation_thread.cancelled)

    def installation_cancelled_or_errored(self):
        """Check if an installation was cancelled or failed."""
        return self.kite_installation_thread.cancelled_or_errored()
