import webrtcvad
import collections
from pathlib import Path
import subprocess
import os
import argparse

def detect_voice_activity_chunks(vad, audio, sample_rate, frame_duration):
    """
    Returns: 
        A generator that yields voiced pcm audio data.

    Arguments:
        vad - An instance of webrtcvad.Vad.
        audio - input PCM audio data
        sample_rate - The audio sample rate, in Hz.
        frame_duration - The frame duration in milliseconds.
    """

    # Number of bytes in each frame
    no_of_bytes_each_frame = int(2 * sample_rate * (frame_duration / 1000.0))

    # The amount to pad the window, in milliseconds.
    padding_duration_ms = frame_duration * 10

    # Number of padding frames
    no_of_padding_frames = int(padding_duration_ms / frame_duration)

    # We use a deque for our sliding window/ring buffer.
    ring_buffer = collections.deque(maxlen=no_of_padding_frames)

    # We have two states: TRIGGERED and NOTTRIGGERED. We start in the
    # NOTTRIGGERED state.
    triggered = False

    # If we're NOTTRIGGERED and more than 90% of the frames in
    # the ring buffer are voiced frames, then enter the
    # TRIGGERED state.
    triggered_sliding_window_threshold = 0.9

    # Create a voice chunk from frames
    make_chunk = lambda voiced_frames: b''.join(voiced_frames)

    # Initialize voice frames
    voiced_frames = []
    for frame in (audio[offset:offset + no_of_bytes_each_frame] for offset in range(0, len(audio), no_of_bytes_each_frame) if offset + no_of_bytes_each_frame < len(audio)):
        is_speech = vad.is_speech(frame, sample_rate)

        # If we're NOTTRIGGERED and more than 90% of the frames in
        # the ring buffer are voiced frames, then enter the
        # TRIGGERED state.
        if not triggered:
            ring_buffer.append((frame, is_speech))
            num_voiced = len([f for f, speech in ring_buffer if speech])
            if num_voiced > triggered_sliding_window_threshold * ring_buffer.maxlen:
                triggered = True

                # We want to yield all the audio we see from now until
                # we are NOTTRIGGERED, but we have to start with the
                # audio that's already in the ring buffer.
                for f, _ in ring_buffer:
                    voiced_frames.append(f)
                ring_buffer.clear()
        else:
            # We're in the TRIGGERED state, so collect the audio data
            # and add it to the ring buffer.
            voiced_frames.append(frame)
            ring_buffer.append((frame, is_speech))
            num_unvoiced = len([f for f, speech in ring_buffer if not speech])

            # If more than 90% of the frames in the ring buffer are
            # unvoiced, then enter NOTTRIGGERED and yield whatever
            # audio we've collected.
            if num_unvoiced > triggered_sliding_window_threshold * ring_buffer.maxlen:
                triggered = False
                yield make_chunk(voiced_frames)
                ring_buffer.clear()
                voiced_frames = []
    if triggered:
        pass
    
    # If we have any leftover voiced audio when we run out of input,
    # yield it.
    if voiced_frames:
        yield make_chunk(voiced_frames)

def split_audio_into_chunks(input_path, output_path, aggressive_level, frame_duration, min_voice_duration):
    """
    This is a function that split audio into voice chunks, each chunks have custom minimum duration.

    Arguments:
        input_path - Input audio file path.
        output_path - Output path to save splitted voice chunks.
        aggressive_level - The webrtcvad's aggressive level.
        frame_duration - Duration of each frame in milliseconds.
        min_voice_duration - Minimum duration of each chunk.
    """
    # Check if input file existed
    if not Path(input_path).is_file(): 
        print("Input file not exist!")
        return

    # Create output folder if not existed
    if os.path.exists(output_path):
        print("Output directory is already existed. Skipping create output folder!")
    else:
        os.makedirs(output_path, exist_ok = True)
        print("Created output folder.")

    # Format audio into 1 channel, 16000 Hz sample rate, 16 bits per sample
    print("Formating audio...")
    sample_rate = 16000
    no_of_channels = 1
    audio = subprocess.check_output([
        'ffmpeg', '-hide_banner', '-nostats', '-nostdin', 
        '-i', input_path, 
        '-ar', str(sample_rate), 
        '-ac', str(no_of_channels), 
        '-f', 's16le', 
        '-acodec', 'pcm_s16le', 
        '-loglevel', 'fatal', 
        '-vn', '-'
    ], stderr = subprocess.DEVNULL)
    print("Done!")

    # Detect voice chunks in input audio
    print("Detecting voice activity...")
    chunks = detect_voice_activity_chunks(webrtcvad.Vad(aggressive_level), audio, sample_rate, frame_duration)
    print("Done!")

    # Save voice chunks to output directory
    print("Saving output voice chunks...")
    for i, chunk in enumerate(chunks):
        if len(chunk) / (2 * sample_rate) > min_voice_duration:
            subprocess.Popen([
                'ffmpeg', '-loglevel', 'fatal', '-hide_banner', '-nostats', '-nostdin', '-y', '-f', 's16le', '-ar', '16000', '-ac', '1', '-i', '-', '-acodec', 'mp3', '-vn',
                os.path.join(output_path, f'{os.path.basename(input_path).split(".")[0]}.{i:04d}.mp3')
            ], stdin = subprocess.PIPE, stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL).communicate(chunk)
            print('Saved {0} chunks!'.format(i))
    print("Done!")

if __name__ == '__main__':

    # Create CLI application
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-path', required=True)
    parser.add_argument('-o', '--output-path', default='voice_chunks')
    parser.add_argument('--aggressive-level', default=1, type=int,choices=[0, 1, 2, 3])
    parser.add_argument('--frame-duration', default=30, type=int, choices=[10, 20, 30])
    parser.add_argument('--min-voice-duration', type=int, default=2)
    args = parser.parse_args()

    split_audio_into_chunks(args.input_path, args.output_path, args.aggressive_level, args.frame_duration, args.min_voice_duration)