"""例文の音声を Azure 音声合成で作り、音節ごとの時刻と一緒に書き出す。

使い方:
  py tools/gen_audio.py                 # 全文・全声・全速度
  py tools/gen_audio.py --only l1-1,l3-3 --voices f --rates n
  py tools/gen_audio.py --force         # キャッシュを無視して合成し直す
  py tools/gen_audio.py --rebuild       # 合成はせず、キャッシュから時刻だけ計算し直す

キー: 環境変数 AZURE_SPEECH_KEY / AZURE_SPEECH_REGION、
      なければ %USERPROFILE%\\.azure_speech.env（KEY=VALUE の行）
出力: audio/<voice>/<id>-<rate>.mp3 と audio/manifest.json
キャッシュ: tools/.cache/（WAV と合成時のイベント。git には入れない）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / 'index.html'
OUT = ROOT / 'audio'
CACHE = ROOT / 'tools' / '.cache'
OVERRIDES = ROOT / 'tools' / 'audio_overrides.json'

VOICES = [
    {'key': 'f', 'name': 'en-US-AvaNeural', 'label': '女性'},
    {'key': 'm', 'name': 'en-US-AndrewNeural', 'label': '男性'},
]
RATES = [
    {'key': 's', 'ssml': '-20%'},
    {'key': 'n', 'ssml': '+0%'},
    {'key': 'q', 'ssml': '+25%'},
]

# Azure の口の形（viseme）ID のうち母音のもの。6 (j i ɪ) と 7 (w u) は半母音も含むが、母音扱いにする。
VOWEL_VISEMES = set(range(1, 12))
TICKS_PER_MS = 10_000


# ===== 例文の読み込み（index.html の parseSentence と同じ分け方） =====
@dataclass(frozen=True)
class Syll:
    text: str
    stress: bool
    word: int


def parse_sentence(src: str) -> tuple[list[Syll], list[str]]:
    sylls: list[Syll] = []
    words: list[str] = []
    for wi, raw in enumerate(src.strip().split()):
        m = re.match(r'^(.*?)([.,!?;:]*)$', raw)
        body = m.group(1)
        sm = re.match(r'^([^*]*)\*([^*]+)\*(.*)$', body)
        parts = [(sm.group(1), False), (sm.group(2), True), (sm.group(3), False)] if sm else [(body, False)]
        for txt, stress in parts:
            if not txt:
                continue
            for p in ([txt] if stress else [q for q in txt.split('·') if q]):
                sylls.append(Syll(p, stress, wi))
        words.append(re.sub(r'[*·]', '', body))
    if not any(s.stress for s in sylls):
        raise ValueError(f'強い音節がない文です: {src}')
    return sylls, words


def load_items() -> list[tuple[str, str]]:
    html = INDEX.read_text(encoding='utf-8')
    start = html.index('const LEVELS')
    end = html.index('const DEMO_JA', start)
    block = html[start:end]
    pat = re.compile(r"""\{\s*id:\s*'([^']+)',\s*t:\s*(['"])((?:\\.|(?!\2).)*)\2""")
    items = [(m.group(1), re.sub(r'\\(.)', r'\1', m.group(3))) for m in pat.finditer(block)]
    if not items:
        raise RuntimeError('index.html の LEVELS から例文を読めませんでした')
    return items


# ===== Azure =====
def load_credentials() -> tuple[str, str]:
    key = os.environ.get('AZURE_SPEECH_KEY')
    region = os.environ.get('AZURE_SPEECH_REGION')
    env_file = Path.home() / '.azure_speech.env'
    if (not key or not region) and env_file.exists():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            k, _, v = line.partition('=')
            k, v = k.strip(), v.strip().strip('"\'')
            if k == 'AZURE_SPEECH_KEY' and not key:
                key = v
            elif k == 'AZURE_SPEECH_REGION' and not region:
                region = v
    if not key or not region:
        raise RuntimeError(f'Azure のキーが見つかりません。環境変数か {env_file} に AZURE_SPEECH_KEY と AZURE_SPEECH_REGION を書いてください')
    return key, region


def synthesize(text: str, voice: str, rate: str, creds: tuple[str, str]) -> tuple[bytes, list[dict], list[dict]]:
    import azure.cognitiveservices.speech as speechsdk

    cfg = speechsdk.SpeechConfig(subscription=creds[0], region=creds[1])
    cfg.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
    synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
    words: list[dict] = []
    visemes: list[dict] = []

    def on_word(evt) -> None:
        if evt.boundary_type == speechsdk.SpeechSynthesisBoundaryType.Word:
            words.append({'text': evt.text, 'ms': evt.audio_offset / TICKS_PER_MS,
                          'dur': evt.duration.total_seconds() * 1000})

    def on_viseme(evt) -> None:
        visemes.append({'id': evt.viseme_id, 'ms': evt.audio_offset / TICKS_PER_MS})

    synth.synthesis_word_boundary.connect(on_word)
    synth.viseme_received.connect(on_viseme)
    ssml = ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
            f'<voice name="{voice}"><prosody rate="{rate}">{escape(text)}</prosody></voice></speak>')
    result = synth.speak_ssml_async(ssml).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        detail = result.cancellation_details
        raise RuntimeError(f'合成に失敗しました（{voice} {rate} "{text}"）: {detail.reason} {detail.error_details}')
    return result.audio_data, words, visemes


# ===== 音節の時刻 =====
def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", '', w.lower().replace('’', "'"))


def split_word(ws: float, we: float, n: int, texts: list[str], visemes: list[dict]) -> tuple[list[float], bool]:
    """1語を n 音節に分ける境目（各音節の始まり）を返す。母音の口の形のまとまりを音節の核とみなす。"""
    if n == 1:
        return [ws], False
    inside = [v for v in visemes if ws <= v['ms'] < we]
    runs: list[list[int]] = []  # 母音の口の形が続くまとまり（inside 内の添字）
    for i, v in enumerate(inside):
        if v['id'] not in VOWEL_VISEMES:
            continue
        if runs and runs[-1][-1] == i - 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    # go-ing のように母音どうしが続く語は、まとまりが足りなくなる。長いまとまりの最後の母音から次の音節とする。
    while len(runs) < n and any(len(r) >= 2 for r in runs):
        k = max(range(len(runs)), key=lambda j: len(runs[j]))
        runs[k:k + 1] = [runs[k][:-1], runs[k][-1:]]
    if len(runs) == n:
        starts = [ws]
        for k in range(1, n):
            cons = list(range(runs[k - 1][-1] + 1, runs[k][0]))
            # 子音が2つ以上あれば最後の1つから次の音節（kn-ow など頭の子音は寄せる）
            cut = cons[-1] if cons else runs[k][0]
            starts.append(inside[cut]['ms'])
        return starts, False
    # 母音のまとまりの数が合わないときは文字数で比例配分（あとで耳で確かめる）
    total = sum(len(t) for t in texts) or n
    starts, acc = [], 0
    for t in texts:
        starts.append(ws + (we - ws) * acc / total)
        acc += len(t)
    return starts, True


def syllable_times(src: str, words_ev: list[dict], visemes: list[dict], dur_ms: float) -> tuple[list[list[float]], list[int]]:
    sylls, words = parse_sentence(src)
    if [norm(w) for w in words] != [norm(w['text']) for w in words_ev]:
        raise RuntimeError(f'単語の区切りが合いません: {words} / {[w["text"] for w in words_ev]}')
    starts: list[float] = []
    approx: list[int] = []
    for wi, ev in enumerate(words_ev):
        idx = [i for i, s in enumerate(sylls) if s.word == wi]
        st, is_approx = split_word(ev['ms'], ev['ms'] + ev['dur'], len(idx), [sylls[i].text for i in idx], visemes)
        starts.extend(st)
        if is_approx:
            approx.append(wi)
    times = []
    for i, s in enumerate(starts):
        wi = sylls[i].word
        word_end = words_ev[wi]['ms'] + words_ev[wi]['dur']
        nxt = starts[i + 1] if i + 1 < len(starts) and sylls[i + 1].word == wi else word_end
        end = min(nxt, dur_ms)
        # 母音の始まり（拍に合わせる目安）。音節の中に母音の口の形がなければ音節の始まり
        vowel = next((v['ms'] for v in visemes if s <= v['ms'] < end and v['id'] in VOWEL_VISEMES), s)
        times.append([round(s, 1), round(end, 1), round(vowel, 1)])
    return times, approx


def apply_overrides(times: list[list[float]], ov: dict[str, float]) -> None:
    """{"音節番号": 始まりのms} で境目を手で直す。前の音節の終わりも同じ位置にそろえる。"""
    for k, ms in ov.items():
        i = int(k)
        if not 0 <= i < len(times):
            raise ValueError(f'補正の音節番号 {i} が範囲外です')
        times[i][0] = ms
        times[i][2] = max(times[i][2], ms)
        if i > 0 and times[i - 1][1] > ms:
            times[i - 1][1] = ms


# ===== 書き出し =====
def wav_duration_ms(wav: bytes) -> float:
    # RIFF 24kHz 16bit mono。data チャンクの大きさから長さを出す。
    pos = wav.index(b'data') + 4
    size = int.from_bytes(wav[pos:pos + 4], 'little')
    return size / (24_000 * 2) * 1000


def to_mp3(wav_path: Path, mp3_path: Path) -> None:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(wav_path),
                        '-codec:a', 'libmp3lame', '-b:a', '48k', str(mp3_path)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f'mp3 への変換に失敗しました: {r.stderr.strip()}')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--voices', default=','.join(v['key'] for v in VOICES))
    ap.add_argument('--rates', default=','.join(r['key'] for r in RATES))
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--rebuild', action='store_true')
    args = ap.parse_args()

    items = load_items()
    only = {s for s in args.only.split(',') if s}
    voices = [v for v in VOICES if v['key'] in args.voices.split(',')]
    rates = [r for r in RATES if r['key'] in args.rates.split(',')]
    overrides = json.loads(OVERRIDES.read_text(encoding='utf-8')) if OVERRIDES.exists() else {}
    manifest_path = OUT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    manifest['voices'] = [{'key': v['key'], 'label': v['label']} for v in VOICES]
    manifest['rates'] = [r['key'] for r in RATES]
    entries = manifest.setdefault('items', {})
    creds = None if args.rebuild else load_credentials()
    CACHE.mkdir(parents=True, exist_ok=True)

    warnings = []
    for item_id, src in items:
        if only and item_id not in only:
            continue
        text = re.sub(r'\s+', ' ', ' '.join(w for w in re.sub(r'[*·]', '', src).split()))
        entry = entries.setdefault(item_id, {})
        entry['src'] = src
        for v in voices:
            for r in rates:
                tag = f"{v['key']}-{item_id}-{r['key']}"
                wav_path, ev_path = CACHE / f'{tag}.wav', CACHE / f'{tag}.json'
                h = hashlib.sha1(f"{v['name']}|{r['ssml']}|{text}".encode()).hexdigest()
                n_words = len(parse_sentence(src)[1])
                cached = False
                if ev_path.exists() and wav_path.exists():
                    prev = json.loads(ev_path.read_text(encoding='utf-8'))
                    cached = prev.get('hash') == h and len(prev['words']) == n_words and bool(prev['visemes'])
                if args.force or not cached:
                    if args.rebuild:
                        warnings.append(f'{tag}: キャッシュがないので飛ばしました')
                        continue
                    for attempt in range(3):
                        wav, w_ev, v_ev = synthesize(text, v['name'], r['ssml'], creds)
                        # 単語や口の形のイベントがときどき届かないので、そろうまで合成し直す
                        if len(w_ev) == n_words and v_ev:
                            break
                        print(f'{tag}: イベントが足りないので再合成します（{len(w_ev)}/{n_words} 語）')
                    else:
                        raise RuntimeError(f'{tag}: 3回合成しても単語の時刻がそろいませんでした')
                    wav_path.write_bytes(wav)
                    ev_path.write_text(json.dumps({'hash': h, 'words': w_ev, 'visemes': v_ev}, ensure_ascii=False), encoding='utf-8')
                    print(f'合成: {tag}')
                ev = json.loads(ev_path.read_text(encoding='utf-8'))
                dur = wav_duration_ms(wav_path.read_bytes())
                times, approx = syllable_times(src, ev['words'], ev['visemes'], dur)
                apply_overrides(times, overrides.get(f"{item_id}/{v['key']}/{r['key']}", {}))
                if approx:
                    warnings.append(f'{tag}: 語 {approx} の音節の境目は推定です')
                mp3 = OUT / v['key'] / f"{item_id}-{r['key']}.mp3"
                if args.force or not cached or not mp3.exists():
                    to_mp3(wav_path, mp3)
                entry.setdefault(v['key'], {})[r['key']] = {'dur': round(dur, 1), 'sylls': times}

    OUT.mkdir(exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    for w in warnings:
        print('注意:', w)
    print(f'manifest: {manifest_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
