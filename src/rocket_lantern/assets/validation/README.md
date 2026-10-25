# Audio validation fixture

`silence.mp3.b64` contains 100 ms of silence, generated with Qt's MP3
encoder from zero-valued PCM buffers. It contains no third-party recording.

The source and packaged smoke tests decode it alongside a generated WAV
without opening an audio device. It is not part of the user sound library.
