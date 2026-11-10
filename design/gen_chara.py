# 楽器トレーナーのキャラクターを表情・ポーズ別の SVG に書き出す（ドラム・ギター・ベース・ヴォーカル・英語リズム共通）
# 使い方: py design/gen_chara.py  → img/chara/*.svg（置いてあるリポジトリのフォルダ名で楽器を選ぶ）
#         py design/gen_chara.py all <ClaudeCodeフォルダ>  → 4サイトまとめて書き出す
# 読譜トレーナー（sight-reading/design/gen_chara.py）と同じ描き方：
# まるい体に大きく低めの目、短い手足。線は一定の太さ、影はくっきりしたセル塗り1段＋光。
# 体の色はサイトのテーマ色の反対側にして、テーマ色のカードの上でも埋もれないようにする
import sys
from pathlib import Path

KINDS: dict[str, dict[str, str | int]] = {
    # ドラム：スネアドラムの子（テーマ＝朱色 → 体は水色）
    'drum-trainer': dict(kind='drum', ink='#2a1d33', light='#8ae3f7', base='#4cc3e6', shade='#2b9fc8', eye='#2f8fd1', crown_dy=-8),
    # ギター：ピックの子（テーマ＝緑 → 体はコーラル）
    'guitar-trainer': dict(kind='pick', ink='#1c3430', light='#ffb08f', base='#ff8a63', shade='#e5623d', eye='#1fae8c', crown_dy=-16),
    # ベース：エレキベースの子（ボディが体、ネックと4つのペグが頭の上に伸びる。テーマ＝緑 → 体はラベンダー）
    'bass-trainer': dict(kind='bass', ink='#1c3430', light='#d3c4ff', base='#ad92ff', shade='#8b6cec', eye='#1fae8c', crown_dy=-6, vb='10 8 210 212'),
    # ヴォーカル：マイクを持って歌う子（テーマ＝赤紫 → 体はミント、マイクは銀）
    'vocal-trainer': dict(kind='singer', ink='#3a1a2c', light='#9ff3d0', base='#5fdcab', shade='#35b788', eye='#e0569a', crown_dy=-20),
    # 英語リズム：メトロノームの子（台形の体の後ろから振り子が伸びる。テーマ＝藍 → 体はあんず色）
    'rhythm-english': dict(kind='metro', ink='#1b2350', light='#ffd2a8', base='#ffab6b', shade='#ef8442', eye='#2f55d4', crown_dy=-12, vb='10 26 210 194'),
}

FLAT_HEAD = '<ellipse cx="100" cy="154" rx="58" ry="49" transform="rotate(-8 100 154)"'
DRUM = '<path d="M40 116 A60 15 0 0 0 160 116 V188 A60 15 0 0 1 40 188 Z"'
PICK = '<path d="M100 214 C 80 204 44 182 42 140 C 40 106 66 92 100 92 C 134 92 160 106 158 140 C 156 182 120 204 100 214 Z"'
MIC = '<circle cx="100" cy="146" r="56"'
# エレキベースのボディ：左右の角（ホーン）は右を長く、下はまるく
BASS = ('<path d="M100 208 C 56 208 36 186 38 158 C 39 140 46 130 44 118 C 44 110 50 108 56 112 '
        'C 66 118 74 122 88 122 C 104 122 118 108 136 94 C 144 88 152 90 152 98 '
        'C 152 114 160 128 162 152 C 164 186 144 208 100 208 Z"')
METRO = '<path d="M76 92 H124 Q132 92 134 100 L160 196 Q162 204 152 204 H48 Q38 204 40 196 L66 100 Q68 92 76 92 Z"'
BODY_SHAPE = {'metro': METRO, 'drum': DRUM, 'pick': PICK, 'clef': FLAT_HEAD, 'mic': MIC, 'bass': BASS, 'singer': MIC}


def make(c: dict[str, str | int]) -> dict[str, str]:
    """1つの楽器ぶんの部品を、その色で組み立てる"""
    ink, base, shade, kind = str(c['ink']), str(c['base']), str(c['shade']), str(c['kind'])
    body = BODY_SHAPE[kind]

    def limb(d: str, end: tuple[float, float], r: float = 8.5, fist: bool = False) -> str:
        x, y = end
        hand = f'<circle cx="{x}" cy="{y}" r="{r}" fill="{base}" stroke="{ink}" stroke-width="3.5"/>'
        if fist:
            hand += f'<path d="M{x - 3.5} {y - 2} q3.5 3 7 0" stroke="{ink}" stroke-width="2" fill="none" stroke-linecap="round"/>'
        return (f'<path d="{d}" stroke="{ink}" stroke-width="14" stroke-linecap="round" fill="none"/>'
                f'<path d="{d}" stroke="{base}" stroke-width="8" stroke-linecap="round" fill="none"/>' + hand)

    l_down = limb('M47 170 q-10 9 -15 22', (31, 194))
    arms = {  # ポーズ名: (左腕, 右腕)
        'down': (l_down, limb('M151 172 q10 9 15 22', (167, 196))),
        'wave': (l_down, limb('M154 162 q12 -6 16 -24', (172, 134))),
        'up': (limb('M48 160 q-12 -8 -12 -26', (36, 130)), limb('M154 160 q14 -8 16 -28', (172, 128))),
        'point': (l_down, limb('M154 166 q10 -2 20 -8', (176, 156))
                  + f'<path d="M182 152 l9 -5" stroke="{ink}" stroke-width="9" stroke-linecap="round"/><path d="M182 152 l9 -5" stroke="{base}" stroke-width="4" stroke-linecap="round"/>'),
        'fists': (limb('M54 174 q-4 10 8 14', (62, 188), fist=True), limb('M146 174 q4 10 -8 14', (138, 188), fist=True)),
    }
    front = ''  # 顔より手前に描くもの（ヴォーカルのマイク）

    def big_eye(x: float, y: float, rx: float = 7, ry: float = 9) -> str:
        return (f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="url(#ge)"/>'
                f'<ellipse cx="{x + 2}" cy="{y - 3.4}" rx="3" ry="3.4" fill="#fff"/><circle cx="{x - 2.4}" cy="{y + 3.6}" r="1.4" fill="#fff" opacity=".9"/>')

    eyes = {
        'dot': big_eye(82, 152) + big_eye(118, 152),
        'happy': ''.join(f'<path d="M{x - 7} 155 q7 -11 14 0" stroke="{ink}" stroke-width="4.5" stroke-linecap="round" fill="none"/>' for x in (82, 118)),
        'worried': big_eye(82, 154, 6.5, 8) + big_eye(118, 154, 6.5, 8)
        + f'<path d="M73 140 l12 -4 M127 140 l-12 -4" stroke="{ink}" stroke-width="3.2" stroke-linecap="round"/>',
    }
    mouth = {
        'open': f'<path d="M94 165 q6 11 12 0 z" fill="#c73a5a" stroke="{ink}" stroke-width="3" stroke-linejoin="round"/><path d="M97 170.5 q3 -2.5 6 0 q-3 2.6 -6 0z" fill="#ff8fa8"/>',
        'smile': f'<path d="M95 166 q5 5 10 0" stroke="{ink}" stroke-width="3.5" stroke-linecap="round" fill="none"/>',
        'wavy': f'<path d="M92 168 q3 -4 6 0 q3 4 6 0 q3 -4 6 0" stroke="{ink}" stroke-width="3" stroke-linecap="round" fill="none"/>',
    }

    def sparkle(x: float, y: float, s: float, color: str = '#ffcf4d') -> str:
        return (f'<path d="M{x} {y - s} Q{x + s * .2} {y - s * .2} {x + s} {y} Q{x + s * .2} {y + s * .2} {x} {y + s} '
                f'Q{x - s * .2} {y + s * .2} {x - s} {y} Q{x - s * .2} {y - s * .2} {x} {y - s}z" fill="{color}" stroke="{ink}" stroke-width="2.5" stroke-linejoin="round"/>')

    def mini_note(x: float, y: float) -> str:
        return (f'<ellipse cx="{x}" cy="{y}" rx="7" ry="5.5" fill="#fff" stroke="{ink}" stroke-width="2.5" transform="rotate(-20 {x} {y})"/>'
                f'<path d="M{x + 6} {y - 2} v-20" stroke="{ink}" stroke-width="2.8" stroke-linecap="round"/>')

    sweat = f'<path d="M38 118 c4 6 7 10 7 13 a7 7 0 0 1 -14 0 c0 -3 3 -7 7 -13z" fill="#9bd7ff" stroke="{ink}" stroke-width="2.5"/>'
    crown = (f'<g transform="translate(0 {c["crown_dy"]}) rotate(-12 84 100)"><path d="M64 112 l4 -20 l9 11 l7 -15 l7 15 l9 -11 l4 20 z" fill="#fff2b3" stroke="{ink}" stroke-width="3.5" stroke-linejoin="round"/>'
             f'<circle cx="84" cy="106" r="3.2" fill="#ff6b8a" stroke="{ink}" stroke-width="2"/></g>')
    pink = '#ff7aa2'
    poses = {
        'hello': ('dot', 'open', 'wave', sparkle(36, 80, 9) + mini_note(204, 178)),
        'happy': ('happy', 'open', 'down', sparkle(36, 90, 10) + sparkle(204, 160, 7, pink)),
        'celebrate': ('happy', 'open', 'up', sparkle(22, 176, 10) + sparkle(206, 182, 9, pink) + sparkle(194, 66, 8) + mini_note(34, 80)),
        'cheer': ('dot', 'smile', 'fists', sparkle(196, 132, 7)),
        'worried': ('worried', 'wavy', 'fists', sweat),
        'guide': ('dot', 'smile', 'point', ''),
        'crown': ('happy', 'smile', 'wave', crown + sparkle(26, 160, 8) + sparkle(206, 100, 7)),
    }

    # 楽器ごとの部品：back＝体の後ろ、detail＝体の上（影と同じく体の形で切り抜く）、over＝輪郭のあと
    back = detail = over = ''
    if kind == 'drum':
        wood, wood_d = '#f6d49a', '#d9a75c'
        for d in ('M58 52 L132 124', 'M142 52 L68 124'):  # 交差したスティック
            back += (f'<path d="{d}" stroke="{ink}" stroke-width="13" stroke-linecap="round"/>'
                     f'<path d="{d}" stroke="{wood}" stroke-width="7" stroke-linecap="round"/>')
        back += ''.join(f'<ellipse cx="{x}" cy="51" rx="7" ry="6" fill="{wood}" stroke="{ink}" stroke-width="3.5"/>' for x in (57, 143))
        detail = (f'<rect x="30" y="176" width="140" height="40" fill="#e9eef7"/>'  # 下のリム（銀）
                  f'<path d="M30 176 H170" stroke="{ink}" stroke-width="3"/>'
                  + ''.join(f'<rect x="{x - 3}" y="128" width="6" height="48" rx="3" fill="#e9eef7" stroke="{ink}" stroke-width="2.5"/>' for x in (52, 148)))
        over = (f'<ellipse cx="100" cy="116" rx="60" ry="15" fill="#fffaf0" stroke="{ink}" stroke-width="5"/>'  # 打面
                f'<path d="M62 118 q38 10 76 0" stroke="#efe2c9" stroke-width="4" stroke-linecap="round" fill="none"/>'
                f'<path d="M72 112 q14 -4 28 -5" stroke="#fff" stroke-width="3" stroke-linecap="round" fill="none"/>')
        hl = '<path d="M56 136 v16" stroke="#fff" stroke-width="5" stroke-linecap="round"/><circle cx="56" cy="162" r="2.6" fill="#fff"/>'
    elif kind == 'pick':
        hl = '<path d="M56 126 q6 -18 26 -24" stroke="#fff" stroke-width="6" stroke-linecap="round" fill="none"/><circle cx="52" cy="141" r="3.2" fill="#fff"/>'
    elif kind == 'bass':
        wood, board, metal = '#f2cf94', '#6b4630', '#e9eef7'
        # ネック（指板・フレット・4本の弦）とヘッド（片側に4つのペグ）。体の後ろから右上へ伸びる
        neck = (f'<rect x="-11" y="-78" width="22" height="80" rx="3" fill="{wood}" stroke="{ink}" stroke-width="3.5"/>'
                f'<rect x="-8" y="-76" width="16" height="78" fill="{board}"/>'
                + ''.join(f'<path d="M-8 {y} h16" stroke="{metal}" stroke-width="1.8"/>' for y in (-14, -28, -40, -51, -61, -70))
                + ''.join(f'<circle cx="0" cy="{y}" r="2.2" fill="#fff"/>' for y in (-21, -45))
                + ''.join(f'<path d="M{x} -76 V2" stroke="#fff" stroke-width="1" opacity=".85"/>' for x in (-5.4, -1.8, 1.8, 5.4))
                + ''.join(f'<path d="M-10 {y} h-7" stroke="{ink}" stroke-width="3"/><circle cx="-19" cy="{y}" r="4.4" fill="{metal}" stroke="{ink}" stroke-width="2.8"/>'
                          for y in (-82, -91, -100, -109))
                + f'<path d="M-10 -74 C -13 -88 -8 -106 3 -116 C 13 -120 18 -112 15 -104 C 12 -94 11 -84 10 -74 Z" fill="{wood}" stroke="{ink}" stroke-width="3.5" stroke-linejoin="round"/>'
                + f'<path d="M-4 -82 C -5 -92 -2 -102 4 -108" stroke="#fff" stroke-width="3" stroke-linecap="round" fill="none" opacity=".8"/>')
        back = f'<g transform="translate(114 122) rotate(18)">{neck}</g>'
        # ピックアップとブリッジ、その間の弦（口の下）
        over = (''.join(f'<path d="M{x} 177 V196" stroke="#fff" stroke-width="1.3" opacity=".9"/>' for x in (89, 96.3, 103.7, 111))
                + f'<rect x="80" y="180" width="40" height="9" rx="4.5" fill="#2b2b33" stroke="{ink}" stroke-width="2.5"/>'
                + ''.join(f'<circle cx="{x}" cy="184.5" r="1.6" fill="{metal}"/>' for x in (89, 96.3, 103.7, 111))
                + f'<rect x="82" y="194" width="36" height="6" rx="2" fill="{metal}" stroke="{ink}" stroke-width="2.5"/>')
        hl = '<path d="M50 142 q1 -16 10 -26" stroke="#fff" stroke-width="5.5" stroke-linecap="round" fill="none"/><circle cx="47" cy="156" r="3" fill="#fff"/>'
    elif kind == 'metro':
        # 振り子（体の後ろから頭の上へ）と、体の下の目盛り
        metal = '#e9eef7'
        back = (f'<g transform="rotate({{TILT}} 100 190)"><path d="M100 190 V44" stroke="{ink}" stroke-width="9" stroke-linecap="round"/>'
                f'<path d="M100 190 V44" stroke="{metal}" stroke-width="4" stroke-linecap="round"/>'
                f'<rect x="88" y="62" width="24" height="16" rx="4" fill="#ffd34d" stroke="{ink}" stroke-width="3.5"/></g>')
        detail = (f'<rect x="20" y="184" width="170" height="40" fill="{c["shade"]}"/>'
                  + ''.join(f'<path d="M{x} 104 h8" stroke="{ink}" stroke-width="2.5" stroke-linecap="round" opacity=".5"/>' for x in (96,)))
        hl = '<path d="M74 108 l-10 40" stroke="#fff" stroke-width="6" stroke-linecap="round"/><circle cx="61" cy="160" r="3.2" fill="#fff"/>'
    else:  # singer：銀のマイクを口の近くに持って歌う
        metal = '#e3e8f1'
        mesh = ''.join(f'<path d="M{x} 164 l32 32 M{x + 32} 164 l-32 32" stroke="{ink}" stroke-width="1.3" opacity=".35"/>' for x in range(50, 110, 7))
        front = (f'<path d="M76 193 L58 217" stroke="{ink}" stroke-width="16" stroke-linecap="round"/>'
                 f'<path d="M76 193 L58 217" stroke="#3a3348" stroke-width="10" stroke-linecap="round"/>'
                 f'<path d="M62 204 l6 4" stroke="#6d6280" stroke-width="2.5" stroke-linecap="round"/>'
                 f'<path d="M70 192 l13 8" stroke="{ink}" stroke-width="8.5" stroke-linecap="round"/><path d="M70 192 l13 8" stroke="{metal}" stroke-width="4" stroke-linecap="round"/>'
                 f'<clipPath id="cm"><circle cx="82" cy="180" r="15.5"/></clipPath>'
                 f'<circle cx="82" cy="180" r="15.5" fill="{metal}"/><g clip-path="url(#cm)">{mesh}<path d="M60 188 Q84 200 100 176 V204 H60Z" fill="#b8c0cf" opacity=".6"/></g>'
                 f'<circle cx="82" cy="180" r="15.5" fill="none" stroke="{ink}" stroke-width="3.5"/><circle cx="76" cy="173" r="3.2" fill="#fff"/>'
                 + limb('M50 176 q2 18 14 30', (64, 207)))
        arms = {k: ('', r) for k, (_, r) in arms.items()}
        hl = '<path d="M60 112 q10 -14 28 -18" stroke="#fff" stroke-width="6" stroke-linecap="round" fill="none"/><circle cx="52" cy="128" r="3.2" fill="#fff"/>'

    defs = (f'<linearGradient id="gb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c["light"]}"/><stop offset="1" stop-color="{base}"/></linearGradient>'
            f'<linearGradient id="ge" x1="0" y1="0" x2="0" y2="1"><stop offset=".35" stop-color="{ink}"/><stop offset="1" stop-color="{c["eye"]}"/></linearGradient>'
            '<radialGradient id="gc"><stop offset="0" stop-color="#ff7a9a" stop-opacity=".85"/><stop offset="1" stop-color="#ff7a9a" stop-opacity="0"/></radialGradient>'
            f'<clipPath id="c">{body}/></clipPath>')
    feet = ''.join(f'<ellipse cx="{x}" cy="202" rx="13" ry="8.5" fill="{base}" stroke="{ink}" stroke-width="3.5"/>'
                   f'<path d="M{x - 7} 206 q7 3 14 0" stroke="{shade}" stroke-width="3" stroke-linecap="round" fill="none"/>' for x in (80, 120))
    torso = (f'{body} fill="url(#gb)"/>'
             f'<g clip-path="url(#c)">{detail}<path d="M168 120 C 160 176 120 200 60 204 L 180 220 Z" fill="{shade}" opacity=".7"/></g>'
             f'{body} fill="none" stroke="{ink}" stroke-width="5" stroke-linejoin="round"/>{over}{hl}')
    cheeks = ''.join(f'<ellipse cx="{x}" cy="166" rx="11" ry="7" fill="url(#gc)"/>' for x in (66, 134))
    out = {}
    for name, (e, m, a, deco) in poses.items():
        out[name] = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{c.get("vb", "10 30 210 190")}">'
                     f'<defs>{defs}</defs><ellipse cx="100" cy="213" rx="38" ry="6" fill="#1e1b3a" opacity=".18"/>'
                     f'{back.replace("{TILT}", str(-16 if name in ("celebrate", "cheer") else 16))}{feet}{arms[a][0]}{arms[a][1]}{torso}{cheeks}{eyes[e]}{mouth[m]}{front}{deco}</svg>')
    return out


def write(repo: Path) -> None:
    out = repo / 'img' / 'chara'
    out.mkdir(parents=True, exist_ok=True)
    files = make(KINDS[repo.name])
    for name, s in files.items():
        (out / f'{name}.svg').write_text(s, encoding='utf-8')
    print(f'{repo.name}: {len(files)} files -> {out}')


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == 'all':
        for name in KINDS:
            write(Path(sys.argv[2]) / name)
        return
    repo = Path(__file__).resolve().parent.parent
    if repo.name not in KINDS:
        raise SystemExit(f'{repo.name} はキャラクターの対象外です（対象: {", ".join(KINDS)}）')
    write(repo)


if __name__ == '__main__':
    main()
