"""Mirror a Windows render endpoint to other WASAPI render endpoints."""
from threading import Lock

import pyaudiowpatch as pa


class PlaybackBuffer:
    def __init__(self, frame_bytes, rate):
        self.frame_bytes = frame_bytes
        self.target = (rate * 80 // 1000) * frame_bytes
        self.maximum = self.target * 3
        self.samples = bytearray()
        self.primed = False
        self.lock = Lock()

    def append(self, samples):
        with self.lock:
            self.samples.extend(samples)
            if len(self.samples) > self.maximum:
                del self.samples[:-self.target]

    def read(self, frame_count):
        size = frame_count * self.frame_bytes
        with self.lock:
            if len(self.samples) < size:
                self.primed = False
            if not self.primed:
                if len(self.samples) < max(size, self.target):
                    return bytes(size)
                self.primed = True
            chunk = bytes(self.samples[:size])
            del self.samples[:size]
            return chunk


class WindowsMix:
    def __init__(self):
        self.audio = None
        self.streams = []

    def __enter__(self):
        self.audio = pa.PyAudio()
        return self

    def __exit__(self, *exc):
        try:
            self.stop()
        finally:
            self.audio.terminate()

    def outputs(self):
        return {
            device['index']: device for device in self.audio.get_device_info_generator_by_host_api(
                host_api_type=pa.paWASAPI
            ) if device['maxOutputChannels'] and not device['isLoopbackDevice']
        }

    def default_output(self):
        return self.audio.get_host_api_info_by_type(pa.paWASAPI)['defaultOutputDevice']

    @property
    def running(self):
        return bool(self.streams)

    def check(self):
        if self.running and not all(stream.is_active() for stream in self.streams):
            raise RuntimeError('An audio stream stopped. Check the Windows audio outputs and refresh.')

    def start(self, source, destinations):
        if self.running:
            raise RuntimeError('Stop the current Windows mix first.')
        if not destinations or source in destinations or len(set(destinations)) != len(destinations):
            raise ValueError('Choose a source and at least one different speaker output.')
        devices = self.outputs()
        if source not in devices or not set(destinations) <= devices.keys():
            raise ValueError('An audio output is unavailable. Refresh the list and select it again.')

        # PortAudio matches loopback devices by name. Ambiguity could feed an
        # output back into its own capture, so require a unique source match.
        source_device = devices[source]
        name = source_device['name']
        loopbacks = [
            device for device in self.audio.get_loopback_device_info_generator()
            if device['name'] == name + ' [Loopback]'
        ]
        if sum(device['name'] == name for device in devices.values()) != 1 or len(loopbacks) != 1:
            raise ValueError('The source needs a unique Windows Sound output name. Rename duplicate outputs and refresh.')
        loopback = loopbacks[0]
        channels = min(2, loopback['maxInputChannels'])
        rate = int(loopback['defaultSampleRate'])
        if channels < 1 or rate < 1:
            raise ValueError('Windows did not report a usable format for this source.')
        buffers = []
        options = dict(format=pa.paInt16, channels=channels, rate=rate,
                       frames_per_buffer=max(1, rate // 100), start=False)
        try:
            for index in destinations:
                try:
                    self.audio.is_format_supported(rate, output_device=index, output_channels=channels,
                                                   output_format=pa.paInt16)
                    buffer = PlaybackBuffer(channels * 2, rate)

                    def render(data, frame_count, timing, flags, buffer=buffer):
                        return buffer.read(frame_count), pa.paContinue

                    self.streams.append(self.audio.open(output=True, output_device_index=index,
                                                        stream_callback=render, **options))
                except (ValueError, OSError) as error:
                    raise RuntimeError(f"Could not open {devices[index]['name']} at {rate} Hz: {error}") from error
                buffers.append(buffer)

            def capture(data, frame_count, timing, flags):
                if data:
                    for buffer in buffers:
                        buffer.append(data)
                return None, pa.paContinue

            self.streams.append(self.audio.open(input=True, input_device_index=loopback['index'],
                                                stream_callback=capture, **options))
            for stream in self.streams:
                stream.start_stream()
        except BaseException:
            self.stop()
            raise

    def stop(self):
        streams, self.streams = self.streams, []
        errors = []
        for stream in reversed(streams):
            try:
                stream.close()
            except (OSError, ValueError) as error:
                errors.append(error)
        if errors:
            raise RuntimeError(f'Windows reported an error while closing the mix: {errors[0]}') from errors[0]
