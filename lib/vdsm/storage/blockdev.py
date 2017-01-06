#
# Copyright 2017 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

"""
blockdev - data operations on block devices.
"""

from __future__ import absolute_import

import logging

from vdsm import cmdutils
from vdsm import constants
from vdsm import utils
from vdsm.config import config

from vdsm.storage import blkdiscard
from vdsm.storage import fsutils
from vdsm.storage import operation
from vdsm.storage import exception as se

log = logging.getLogger("storage.blockdev")

# Keeping the old value for now.
# TODO: In my tests, 8m gives better performance. Test with different
# storage backends and transport to determine the best value.
OPTIMAL_BLOCK_SIZE = constants.MEGAB


def zero(device_path, size=None, task=None):
    """
    Zero a block device.

    Arguments:
        device_path (str): Path to block device to wipe
        size (int): Number of bytes to write. If not specified, use the device
            size. Size must be aligned to `blockdev.OPTIMAL_BLOCK_SIZE`
        task (`storage.task.Task`): Task running this operation. If specified,
            the zero operation will be aborted if the task is aborted.

    Raises:
        `vdsm.common.exception.ActionStopped` if the wipe was aborted
        `vdsm.storage.exception.VolumesZeroingError` if writing to storage
            failed.
        `vdsm.storage.exception.InvalidParameterException` if size is not
            aligned to `blockdev.OPTIMAL_BLOCK_SIZE`.
    """
    if size is None:
        # Always aligned to LVM extent size (128MiB).
        size = fsutils.size(device_path)
    elif size % OPTIMAL_BLOCK_SIZE:
        raise se.InvalidParameterException("size", size)

    log.info("Zeroing device %s (size=%d)", device_path, size)
    try:
        op = operation.Command([
            constants.EXT_DD,
            "if=/dev/zero",
            "of=%s" % device_path,
            "bs=%d" % OPTIMAL_BLOCK_SIZE,
            "count=%d" % (size // OPTIMAL_BLOCK_SIZE),
            "oflag=direct",
            "conv=notrunc",
        ])
        with utils.stopwatch("Zero device %s" % device_path,
                             level=logging.INFO, log=log):
            if task:
                with task.abort_callback(op.abort):
                    op.run()
            else:
                op.run()
    except se.StorageException as e:
        raise se.VolumesZeroingError("Zeroing device %s failed: %s"
                                     % (device_path, e))


def discard(device_path):
    """
    Discard a block device.

    Discard is best effort; if the operation fails we don't fail the flow
    calling it.

    Arguments:
        device_path (str): Path to block device to discard
    """
    log.info("Discarding device %s", device_path)
    try:
        with utils.stopwatch("Discarded device %s" % device_path,
                             level=logging.INFO, log=log):
            blkdiscard.blkdiscard(device_path)
    except cmdutils.Error as e:
        log.warning("Discarding device %s failed (discard_enable=%s): %s",
                    device_path, discard_enabled(), e)


def discard_enabled():
    """
    Tell if user configured automatic discard of block devices, regardless of
    the devices capabilities.

    Returns:
        bool
    """
    return config.getboolean("irs", "discard_enable")
