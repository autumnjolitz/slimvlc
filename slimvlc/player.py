import urllib.parse
import logging
import time
from enum import Enum
from threading import Thread, Lock

from PySide2 import QtCore
from PySide2.QtWidgets import QApplication, QOpenGLWidget
from PySide2.QtGui import QCursor

from vlc import (
    Instance, EventType, VideoMarqueeOption, Position, TrackType,
    Media,
    libvlc_video_get_spu,
    # MediaSlaveType,
)
import ctypes
import vlc
try:
    from vlc import libvlc_errmsg
except ImportError:
    def libvlc_errmsg():
        '''Sets the LibVLC error status and message for the current thread.
        Any previous error is overridden.
        @param fmt: the format string.
        @param ap: the arguments.
        @return: a nul terminated string in any case.
        '''
        f = vlc._Cfunctions.get('libvlc_errmsg', None) or \
            vlc._Cfunction('libvlc_errmsg', (), None, ctypes.c_char_p)
        return f()
    vlc._Globals['libvlc_errmsg'] = libvlc_errmsg
    libvlc_errmsg()

logger = logging.getLogger(__name__)

# EMPTY_SUBTITLE_SRT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'empty.srt')

'''
VLC options:
--codec=x264,ffmpeg          :: this prevents it from using videotoolbox which breaks on olderitems
--verbose=3                  :: verbose
-V macosx                    :: Video output for drawing into a window
--freetype-fontsize 20       :: Does this work?
--sub-source marq{size=20}   :: For the OSD counter marquee
--play-and-exit              :: Die after play/exit
--no-metadata-network-access :: avoid fetching metadata
'''


def humanize_time(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)

    return "%d:%02d:%02d" % (h, m, s)


class Status(Enum):
    REQUIRES_MEDIA = 1
    PARSING = 2
    PARSED = 3


class VLCWindow(QOpenGLWidget):
    def __init__(self, vlc):
        assert isinstance(vlc, VLC)
        self._vlc = vlc

        super(VLCWindow, self).__init__()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent)

        QApplication.setOverrideCursor(QCursor(QtCore.Qt.BlankCursor))

        p = self.palette()
        p.setColor(self.backgroundRole(), QtCore.Qt.gray)
        self.setPalette(p)
        self.showFullScreen()
        self.raise_()

        self._subtitle_index = 0
        self._vlc._player.set_nsobject(self.winId())

        self._vlc.add_event_listener(
            EventType.MediaPlayerEndReached, self.close)
        self._vlc.add_event_listener(EventType.MediaPlayerStopped, self.close)
        self._vlc.add_event_listener(
            EventType.MediaPlayerPositionChanged, self._vlc._on_position_change)
        self._vlc.add_event_listener(EventType.MediaPlayerVout, self._on_play_start)
        self.play()

    def _on_play_start(self):
        self._vlc._subtitle_index = 0
        self._vlc._player.video_set_spu(-1)

    def play(self):
        self._vlc.play()

    def pause(self):
        if self._vlc._player.is_playing():
            QApplication.restoreOverrideCursor()
        else:
            QApplication.setOverrideCursor(QCursor(QtCore.Qt.BlankCursor))
        self._vlc.pause()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (QtCore.Qt.Key_Escape, ord('Q')):
            self.close()
        elif key in (QtCore.Qt.Key_Left, QtCore.Qt.LeftArrow):
            self._vlc.timestamp_ms -= 10 * 1000
        elif key in (QtCore.Qt.Key_Right, QtCore.Qt.RightArrow):
            self._vlc.timestamp_ms += 10 * 1000
        elif key in (QtCore.Qt.Key_Up, QtCore.Qt.UpArrow):
            self._vlc.timestamp_ms += 60 * 1000
        elif key in (QtCore.Qt.Key_Down, QtCore.Qt.DownArrow):
            self._vlc.timestamp_ms -= 60 * 1000
        elif key == QtCore.Qt.Key_Space:
            self.pause()
        elif key == ord('O'):
            self._vlc.osd_visibility = not self._vlc.osd_visibility
        elif key == ord('C'):
            self._vlc.cycle_subtitles()
        elif key == ord('T'):
            self._vlc.take_snapshot()
        else:
            try:
                logger.debug('Unknown key {}, {}'.format(key, chr(key)))
            except UnicodeError:
                logger.debug('Unknown key {} ???'.format(key))


class VLC(object):
    INSTANCE = None

    def __init__(self, media_path, snapshot_directory=None):
        self._lock = Lock()
        self._subtitles = ()
        self._subtitle_index = None
        self._listeners = {}
        self.snapshot_directory = snapshot_directory

        if self.INSTANCE is None:
            self.INSTANCE = self.__class__.set_instance(
                self.__class__.make_instance())
        self._player = self.INSTANCE.media_player_new()
        self.event_manager = self._player.event_manager()
        self.status = Status.REQUIRES_MEDIA
        self.setup_osd()

        self.media_info(media_path)

    def cycle_subtitles(self):
        assert self.status == Status.PARSED, 'You can\'t cycle subs for this status!'
        logger.debug(f'SPUs offered: {self._player.video_get_spu_description()}')
        logger.debug(f'Tracks {self._subtitles}')

        if len(self._subtitles) < 2:
            logger.debug('No subtitles to cycle with!')
            return

        current_subtitle_track = libvlc_video_get_spu(self._player)
        logger.debug(f'Current subtitle id before set: {current_subtitle_track}')
        self._subtitle_index = (self._subtitle_index + 1) % len(self._subtitles)

        track = self._subtitles[self._subtitle_index]
        track_id = track['id']
        if track_id > -1:
            # VLC subtitles appear to be:
            #   -1 disable
            #   track_id + 1
            track_id += 1
        result = self._player.video_set_spu(track_id)

        logger.info('Setting subtitle track to {} ({}) -> {} -> {}'.format(
            track['name'], track_id, track, result))

        if result == -1:
            logger.error('Unable to set the subtitle track: {}'.format(libvlc_errmsg()))

        current_subtitle_track = libvlc_video_get_spu(self._player)
        logger.debug(f'Current subtitle id after set: {current_subtitle_track}')

    def _handle_mplayer_command(self, command):
        command = urllib.parse.unquote(command)
        if command.startswith('seek '):
            logger.debug('Seek ? {}'.format(command))
            seconds = int(command.split(' ', 2)[1], 10)
            self.timestamp_ms += (seconds * 1000)
        elif command.startswith('screenshot'):
            logger.debug('Screenshot ? {}'.format(command))
            self.take_snapshot()
        elif command.startswith('pause'):
            self.pause()
        elif command.startswith('quit'):
            self._player.stop()
        elif command.startswith('mute'):
            self._player.audio_toggle_mute()

    def enslave(self, path):
        logger.debug(f'Enslaving {path}')
        while True:
            try:
                with open(path, 'rb') as fh:
                    queue = []
                    for char in iter(lambda: fh.read(1), b''):
                        logger.debug('Char! {}'.format(char))
                        if char == b'\n':
                            command = b''.join(queue).decode('utf8')
                            self._handle_mplayer_command(command)
                            queue[:] = []
                            continue
                        queue.append(char)
                    logger.debug('Drained fifo.')
                time.sleep(0.2)
            except Exception:
                logger.exception('wtf')

    def play(self, pause_immediatly=False):
        logger.info('Playing {}'.format(self._media_info.get_mrl()))
        self._player.play()
        if pause_immediatly:
            self._player.pause()

    def take_snapshot(self):
        assert self.status == Status.PARSED and self._player.is_playing()
        if self.snapshot_directory is None:
            return
        self._player.video_take_snapshot(0, self.snapshot_directory, 0, 0)

    def pause(self):
        self._player.pause()

    def setup_osd(self):
        self._player.video_set_marquee_int(VideoMarqueeOption.Enable, True)
        self._player.video_set_marquee_int(VideoMarqueeOption.Size, 24)  # pixels
        self._player.video_set_marquee_int(VideoMarqueeOption.Position, Position.TopRight)

        self._player.video_set_marquee_int(VideoMarqueeOption.Timeout, 1010)  # millisec, 0=forever
        self._player.video_set_marquee_int(VideoMarqueeOption.Refresh, 100)  # millisec (or sec?)
        self.osd_visibility = False  # default disabled.

    @property
    def duration_ms(self):
        media = self._player.get_media()
        if not media:
            return 0
        return media.get_duration()

    @property
    def timestamp_ms(self):
        return self._player.get_time()

    @timestamp_ms.setter
    def timestamp_ms(self, val):
        result = float(val) / self.duration_ms
        logger.debug('Seek -> {} -> {} -> set_position({})'.format(val, self.duration_ms, result))
        self._player.set_position(result)

    def _on_position_change(self):
        seconds = humanize_time(self.timestamp_ms / 1000.)
        duration = humanize_time(self.duration_ms / 1000.)
        if self.osd_visibility:
            self._player.video_set_marquee_string(
                VideoMarqueeOption.Text, '{} / {}'.format(seconds, duration))

    @property
    def osd_visibility(self):
        return self._player.video_get_marquee_int(VideoMarqueeOption.Opacity)

    @osd_visibility.setter
    def osd_visibility(self, val):
        if isinstance(val, bool):
            if val:
                val = 255
            else:
                val = 0

        assert isinstance(val, int) and val >= 0, 'OSD visibility must be a >=0 integer'
        logger.debug('Set the osd visibility to {}'.format(val))
        self._player.video_set_marquee_int(VideoMarqueeOption.Opacity, val)

    def add_event_listener(self, event_type, func):
        assert callable(func)
        try:
            self._listeners[event_type].append(func)
        except KeyError:
            self._listeners[event_type] = [func]
        self.event_manager.event_attach(event_type, self._handle_event)

    def _handle_event(self, event):
        try:
            funcs = self._listeners[event.type]
        except KeyError:
            logger.exception('{} is not registered'.format(event.type))
        else:
            for func in funcs[:]:
                try:
                    func()
                except Exception:
                    logger.exception('Unable to execute! Removing!')
                    funcs.remove(func)

    def remove_event_listener(self, event_type, func):
        try:
            self._listeners[event_type].remove(func)
        except KeyError:
            logger.warning('{} is not registered!'.format(event_type))
        except IndexError:
            logger.warning(
                'Unable to remove {} -> {} as it never existed!'.format(event_type, func))
        else:
            if not self._listeners[event_type]:
                del self._listeners[event_type]

    def _timeout_thread(self, media, timeout):
        time.sleep(timeout)
        self._media_parsed(media, True)

    def media_info(self, path):
        self._subtitles = [{
            'id': -1,
            'name': 'nolang',
            'track': None,
        }]
        self.status = Status.PARSING
        media = Media(path)
        self._media_info = media
        media.event_manager().event_attach(
            EventType.MediaParsedChanged,
            lambda _: self._media_parsed(media))
        # media.slaves_add(MediaSlaveType.subtitle, 1, 'file://' + EMPTY_SUBTITLE_SRT)
        media.parse_with_options(0x0 | 0x1, 10 * 1000)

        t = Thread(target=self._timeout_thread, args=(media, 11))
        t.daemon = True
        t.start()

    def _media_parsed(self, media, timeout=False):
        with self._lock:
            tracks = media.tracks_get()
            if not media or tracks is None:
                logger.warning('No media detected!')
                self.status = Status.REQUIRES_MEDIA
                self._media_info = None
                return

            media.event_manager().event_detach(EventType.MediaParsedChanged)

            if media is self._media_info and timeout:
                logger.debug('Media registered, timeout ignored')
                return

            if media is not self._media_info:
                logger.warning('{} is not the same ({} != {}).'.format(
                    media.get_mrl(),
                    id(media),
                    id(self._media_info)))
                media.release()
                del media
                return

            logger.info('Setting VLC MRL to {}'.format(media.get_mrl()))
            self._player.set_media(self._media_info)
            self.status = Status.PARSED

            for track in tracks:
                logger.debug(f'Track -> {track}')
                if track.type == TrackType.text:
                    self._subtitles.append({
                        'track': track,
                        'id': track.id,
                        'name': track.language
                    })

    @classmethod
    def make_instance(cls, verbose=False):
        assert isinstance(verbose, (int, bool))
        args = [
            '--sub-source=marq',
            '-V', 'caopengllayer',
            '--freetype-fontsize',
            '30',
            '--no-metadata-network-access',
            '--codec=x264,ffmpeg,videotoolbox',
            '--disable-screensaver',
            '--no-snapshot-preview',  # Don't show a snapshot preview after taking it
        ]
        if verbose:
            args.append('--verbose={}'.format(int(verbose)))
        return Instance(args)

    @classmethod
    def set_instance(cls, instance):
        assert isinstance(instance, Instance)
        cls.INSTANCE = instance
        return instance
