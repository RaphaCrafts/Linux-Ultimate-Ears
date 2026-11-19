from types import SimpleNamespace
import struct

import pytest

pytest.importorskip('pyaudiowpatch')
from speakerstudio import windows_mix


@pytest.mark.parametrize('mixed_formats', [False, True])
@pytest.mark.parametrize('fail_output', [None, 3])
def test_mix_fans_out_to_each_selected_endpoint_and_releases_streams(monkeypatch, mixed_formats, fail_output):
    def device(index, name, loopback=False):
        return dict(index=index, name=name, maxInputChannels=2 if loopback else 0,
                    maxOutputChannels=0 if loopback else 2, isLoopbackDevice=loopback,
                    defaultSampleRate=48000)

    source = device(1, 'Host')
    outputs = [device(index, f'Speaker {index}') for index in range(2, 6)]
    if mixed_formats:
        outputs[0]['defaultSampleRate'] = 44100
        outputs[1].update(defaultSampleRate=32000, maxOutputChannels=1)
    loopback = device(6, 'Host [Loopback]', loopback=True)
    opened = []

    class Stream:
        active = False
        closed = False

        def start_stream(self):
            self.active = True

        def is_active(self):
            return self.active

        def close(self):
            self.active = False
            self.closed = True

    def open_stream(**options):
        if fail_output is not None and options.get('output_device_index') == fail_output:
            raise OSError('Endpoint unavailable')
        stream = Stream()
        opened.append((stream, options))
        return stream

    def supported(rate, output_device, output_channels, output_format):
        output = next(row for row in outputs if row['index'] == output_device)
        # Reproduce the screenshot: Bluetooth rejects the source's 48 kHz.
        if rate != output['defaultSampleRate']:
            raise ValueError('Invalid sample rate', -9997)
        assert output_channels == output['maxOutputChannels']
        assert output_format == windows_mix.pa.paInt16
        return True

    audio = SimpleNamespace(
        get_device_info_generator_by_host_api=lambda **kwargs: [source, *outputs, loopback],
        get_loopback_device_info_generator=lambda: [loopback],
        is_format_supported=supported,
        open=open_stream,
        terminate=lambda: None,
    )
    monkeypatch.setattr(windows_mix.pa, 'PyAudio', lambda: audio)
    with windows_mix.WindowsMix() as mix:
        with pytest.raises(ValueError, match='different speaker output'):
            mix.start(1, [1, 2])
        assert not opened
        if fail_output is not None:
            with pytest.raises(RuntimeError, match='Speaker 3.*Endpoint unavailable'):
                mix.start(1, [2, 3, 4, 5])
            assert not mix.running and all(stream.closed for stream, _ in opened)
            opened.clear()
            fail_output = None
        mix.start(1, [2, 3, 4, 5])
        assert [options['output_device_index'] for _, options in opened[:-1]] == [2, 3, 4, 5]
        capture = opened[-1][1]['stream_callback']
        frames = struct.pack('<hh', 2000, 6000) * 4800
        capture(frames, 4800, {}, 0)
        for stream, options in opened[:-1]:
            render = options['stream_callback']
            count = options['rate'] // 100
            expected_frame = struct.pack('<h', 4000) if options['channels'] == 1 else frames[:4]
            assert render(None, count, {}, 0)[0] == expected_frame * count
        assert opened[-1][1]['rate'] == 48000
        assert opened[-1][1]['channels'] == 2
        mix.check()
        opened[0][0].active = False
        with pytest.raises(RuntimeError, match='audio stream stopped'):
            mix.check()
    assert not mix.running and all(stream.closed for stream, _ in opened)


@pytest.mark.parametrize('source_rate,rate', [(48000, 44100), (44100, 48000)])
@pytest.mark.parametrize('source_channels,channels', [(2, 2), (2, 1), (1, 2)])
def test_pcm_conversion_preserves_timing_and_callback_continuity(source_rate, rate, source_channels, channels):
    frames = b''.join(struct.pack('<h', i) * source_channels for i in range(4800))
    converter = windows_mix.PcmConverter(source_rate, source_channels, rate, channels)
    step = 97 * source_channels * 2
    chunks = b''.join(converter.convert(frames[i:i + step]) for i in range(0, len(frames), step))
    whole = windows_mix.PcmConverter(source_rate, source_channels, rate, channels).convert(frames)
    assert chunks == whole
    assert abs(len(chunks) // (2 * channels) - 4800 * rate / source_rate) <= 1
    samples = struct.unpack('<' + 'h' * (len(chunks) // 2), chunks)
    for frame in range(0, len(samples) // channels, 113):
        expected = frame * source_rate / rate
        for channel in range(channels):
            assert abs(samples[frame * channels + channel] - expected) <= 1


def test_playback_buffer_caps_backlog_and_reprimes_after_underrun():
    buffer = windows_mix.PlaybackBuffer(4, 1000)
    assert buffer.read(10) == bytes(40)
    buffer.append(bytes(4000) + b'abcd' * 80)
    assert buffer.read(80) == b'abcd' * 80
    assert buffer.read(10) == bytes(40)
    buffer.append(b'efgh' * 20)
    assert buffer.read(10) == bytes(40)
