"""⑥ 聞き分けクイズの単語の音声を Azure 音声合成で作る。

使い方:
  py tools/gen_words.py            # まだない音声だけ作る
  py tools/gen_words.py --force    # 全部作り直す

単語は index.html の MINIMAL（const MINIMAL から const MINIMAL_VOICES の間）から読む。
声は index.html の MINIMAL_VOICES と同じものを VOICES に並べる。
キーは gen_audio.py と同じ（環境変数か %USERPROFILE%\\.azure_speech.env）。
出力: audio/words/<声>/<単語>.mp3
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from gen_audio import INDEX, OUT, load_credentials, to_mp3

VOICES = {
    'us1': 'en-US-AvaNeural',
    'us2': 'en-US-AndrewNeural',
    'us3': 'en-US-EmmaNeural',
    'us4': 'en-US-BrianNeural',
    'uk1': 'en-GB-SoniaNeural',
    'uk2': 'en-GB-RyanNeural',
}


def load_words() -> list[str]:
    html = INDEX.read_text(encoding='utf-8')
    start = html.index('const MINIMAL ')
    end = html.index('const MINIMAL_VOICES', start)
    block = html[start:end]
    sets = re.findall(r"\[\s*('[a-z]+'(?:\s*,\s*'[a-z]+')+)\s*\]", block)
    words = sorted({w for s in sets for w in re.findall(r"'([a-z]+)'", s)})
    if not words:
        raise RuntimeError('index.html の MINIMAL から単語を読めませんでした')
    return words


def synthesize_word(word: str, voice: str, creds: tuple[str, str]) -> bytes:
    import azure.cognitiveservices.speech as speechsdk

    cfg = speechsdk.SpeechConfig(subscription=creds[0], region=creds[1])
    cfg.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
    synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
    lang = voice[:5]
    ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang}">'
            f'<voice name="{voice}">{escape(word)}</voice></speak>')
    result = synth.speak_ssml_async(ssml).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        detail = result.cancellation_details
        raise RuntimeError(f'合成に失敗しました（{voice} "{word}"）: {detail.reason} {detail.error_details}')
    return result.audio_data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    words = load_words()
    creds = load_credentials()
    made = 0
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / 'w.wav'
        for key, voice in VOICES.items():
            for word in words:
                mp3 = OUT / 'words' / key / f'{word}.mp3'
                if mp3.exists() and not args.force:
                    continue
                print(f'合成: {key} {word}')
                wav.write_bytes(synthesize_word(word, voice, creds))
                to_mp3(wav, mp3)
                made += 1
    print(f'{len(words)} 語 × {len(VOICES)} 声、新しく作ったもの {made}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
