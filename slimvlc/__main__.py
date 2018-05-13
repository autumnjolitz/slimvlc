import sys
import os
import logging
import stat
import time
from threading import Thread

from PySide2.QtWidgets import QApplication
from vlc import EventType

from .player import VLC, VLCWindow, Status

logger = logging.getLogger('slimvlc')

DEFAULT_SNAPS_LOCATION = os.path.abspath(os.getcwd())
DEFAULT_FORMATTER = \
    logging.Formatter('[%(asctime)s] [PID %(process)d] [Thread %(thread)d] '
                      '[%(name)s] [%(levelname)s] %(message)s')


def setup_logging():
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(DEFAULT_FORMATTER)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


if __name__ == '__main__':
    import argparse

    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', default=False, action='store_true')
    parser.add_argument(
        '-ss', '--start-position', default=0, type=str,
        help='Start Playback from this point')
    parser.add_argument(
        '-endpos', '--end-position', default=0, type=int,
        help='End playback at this point. If an untyped number is passed, assume seconds. '
        'If a start position is specified and the end position is in seconds, assume an offset.')
    parser.add_argument('filepath', metavar='FILE', help='File to play')
    parser.add_argument(
        '--snaps-dir', help='Directory where snapshots go (defaults to {})'.format(
            DEFAULT_SNAPS_LOCATION), default=DEFAULT_SNAPS_LOCATION)
    parser.add_argument(
        '--slave', help='MPlayer Slave mode emulation - set to a FIFO', default=None)

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        VLC.set_instance(VLC.make_instance(verbose=3))

    vlc = VLC(args.filepath, args.snaps_dir)
    while vlc.status == Status.PARSING:
        time.sleep(0.5)
    if vlc.status != Status.PARSED:
        raise SystemExit('{} did not parse to anything meaningful'.format(args.filepath))

    if args.slave:
        if not os.path.exists(args.slave):
            os.mkfifo(args.slave)
        if not stat.S_ISFIFO(os.stat(args.slave).st_mode):
            raise SystemExit('{} isn\'t a fifo!'.format(args.slave))

        t = Thread(target=vlc.enslave, args=(args.slave,))
        t.daemon = True
        t.start()

    app = QApplication(sys.argv)
    vlc_window = VLCWindow(vlc)

    if args.start_position:
        if args.start_position.isdigit():
            args.start_position = int(args.start_position, '10')
        else:
            hours, minutes, seconds = 0, 0, 0
            if args.start_position.count(':') == 2:
                hours, minutes, seconds = args.start_position.split(':')
            elif args.start_position.count(':') == 1:
                minutes, seconds = args.start_position.split(':')
            else:
                raise SystemExit('Unrecognized start time {}'.format(args.start_position))
            seconds = (float(hours) * 3600) + (float(minutes) * 60) + float(seconds)
            args.start_position = seconds

        # Let the first frame be the trigger to seek (VLC will)
        def seek():
            logger.debug('Seek to {}'.format(args.start_position))
            vlc.timestamp_ms = args.start_position * 1000
            vlc.remove_event_listener(EventType.MediaPlayerPositionChanged, seek)
        vlc.add_event_listener(EventType.MediaPlayerPositionChanged, seek)

    if args.end_position:
        end_position_ms = (args.start_position + args.end_position) * 1000

        def terminate():
            if vlc.timestamp_ms > end_position_ms:
                vlc.pause()
                vlc_window.close()
        vlc.add_event_listener(EventType.MediaPlayerPositionChanged, terminate)
    sys.exit(app.exec_())
