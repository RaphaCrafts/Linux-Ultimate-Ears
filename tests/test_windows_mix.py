from types import SimpleNamespace

import pytest

pytest.importorskip('pyaudiowpatch')
from speakerstudio import windows_mix


def test_mix_fans_out_to_each_selected_endpoint_and_releases_streams(monkeypatch):
    def device(index, name, loopback=False):
        return dict(index=index, name=name, maxInputChannels=2 if loopback else 0,
                    maxOutputChannels=0 if loopback else 2, isLoopbackDevice=loopback,
                    defaultSampleRate=48000)

    source = device(1, 'Host')
    outputs = [device(index, f'Speaker {index}') for index in range(2, 6)]
    loopback = device(6, 'Host [Loopback]', loopback=True)
    opened = []

    class Stream:
        active = False

        def start_stream(self):
            self.active = True

        def is_active(self):
            return self.active

        def close(self):
            self.active = False

    def open_stream(**options):
        stream = Stream()
        opened.append((stream, options))
        return stream

    audio = SimpleNamespace(
        get_device_info_generator_by_host_api=lambda **kwargs: [source, *outputs, loopback],
        get_loopback_device_info_generator=lambda: [loopback],
        is_format_supported=lambda *args, **kwargs: True,
        open=open_stream,
        terminate=lambda: None,
    )
    monkeypatch.setattr(windows_mix.pa, 'PyAudio', lambda: audio)
    with windows_mix.WindowsMix() as mix:
        with pytest.raises(ValueError, match='different speaker output'):
            mix.start(1, [1, 2])
        assert not opened
        mix.start(1, [2, 3, 4, 5])
        assert [options['output_device_index'] for _, options in opened[:-1]] == [2, 3, 4, 5]
        capture = opened[-1][1]['stream_callback']
        frames = b'\x11\x22\x33\x44' * 3840
        capture(frames, 3840, {}, 0)
        for stream, options in opened[:-1]:
            render = options['stream_callback']
            assert render(None, 480, {}, 0)[0] == frames[:1920]
        mix.check()
        opened[0][0].active = False
        with pytest.raises(RuntimeError, match='audio stream stopped'):
            mix.check()
    assert not mix.running and all(not stream.active for stream, _ in opened)


def test_playback_buffer_caps_backlog_and_reprimes_after_underrun():
    buffer = windows_mix.PlaybackBuffer(4, 1000)
    assert buffer.read(10) == bytes(40)
    buffer.append(bytes(4000) + b'abcd' * 80)
    assert buffer.read(80) == b'abcd' * 80
    assert buffer.read(10) == bytes(40)
    buffer.append(b'efgh' * 20)
    assert buffer.read(10) == bytes(40)
