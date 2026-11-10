'use strict';
// ---- 有料版（月額480円）：パスキーの会員・Stripe の支払い・声の自動採点 ----
// サーバーは rhythm-billing（このサイトの /api/*）。index.html の本体のあとに読み込み、本体の関数（$・el・Engine など）を使う

// 有料版の案内を出すか。止めるときは false にする
const BILLING_ON = true;
const PRICE_LABEL = '月480円';
const MAX_REC_SECONDS = 15;

let account = { signedIn: false, paid: false, name: '', customer: false, periodEnd: 0, cancelAtEnd: false, usage: null };

const apiPost = async (url, body) => {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
    credentials: 'same-origin',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `エラー（${res.status}）`);
  return data;
};
const apiGet = async (url) => {
  const res = await fetch(url, { credentials: 'same-origin' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `エラー（${res.status}）`);
  return data;
};

// ---- パスキー（読譜トレーナーの billing.js と同じ変換） ----
const toBytes = (s) => {
  const b64 = s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4);
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
};
const toB64url = (buf) => {
  let s = '';
  for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
};
const creationOptions = (o) => ({
  ...o,
  challenge: toBytes(o.challenge),
  user: { ...o.user, id: toBytes(o.user.id) },
  excludeCredentials: (o.excludeCredentials || []).map((c) => ({ ...c, id: toBytes(c.id) })),
});
const requestOptions = (o) => ({
  ...o,
  challenge: toBytes(o.challenge),
  allowCredentials: (o.allowCredentials || []).map((c) => ({ ...c, id: toBytes(c.id) })),
});
const registrationJSON = (cred) => ({
  id: cred.id,
  rawId: toB64url(cred.rawId),
  type: cred.type,
  response: {
    clientDataJSON: toB64url(cred.response.clientDataJSON),
    attestationObject: toB64url(cred.response.attestationObject),
    transports: cred.response.getTransports ? cred.response.getTransports() : [],
  },
  clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
  authenticatorAttachment: cred.authenticatorAttachment || undefined,
});
const authenticationJSON = (cred) => ({
  id: cred.id,
  rawId: toB64url(cred.rawId),
  type: cred.type,
  response: {
    clientDataJSON: toB64url(cred.response.clientDataJSON),
    authenticatorData: toB64url(cred.response.authenticatorData),
    signature: toB64url(cred.response.signature),
    userHandle: cred.response.userHandle ? toB64url(cred.response.userHandle) : undefined,
  },
  clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
  authenticatorAttachment: cred.authenticatorAttachment || undefined,
});
const explainPasskey = (e) =>
  e && e.name === 'NotAllowedError' ? 'パスキーの操作が取り消されたか、時間切れになりました。' :
  e && e.name === 'InvalidStateError' ? 'この端末のパスキーは、もう登録してあります。' :
  (e && e.message) || 'パスキーを使えませんでした。';

// ---- 画面の部品（ダイアログはここで作る） ----
const LEGAL = '<a href="https://habatakijuku.com/legal/terms.html" target="_blank" rel="noopener">利用規約</a>・<a href="https://habatakijuku.com/legal/tokushoho.html" target="_blank" rel="noopener">特定商取引法に基づく表記</a>・<a href="https://habatakijuku.com/legal/privacy.html" target="_blank" rel="noopener">プライバシーポリシー</a>';

function mountBillingUI() {
  document.body.insertAdjacentHTML('beforeend', `
<dialog id="payDlg">
  <div class="dlg">
    <div class="pay-hero">
      <div class="dlg-head"><img class="chara pay-chara" src="img/chara/crown.svg?v=1" alt="" width="52" height="48"><span style="flex:1"></span><button class="btn icon" data-close aria-label="閉じる">✕</button></div>
      <h2>英語リズム・トレーニング 有料版</h2>
      <p id="payLead">あなたの英語を、耳のいいコーチが毎回採点。</p>
    </div>
    <ul class="benefits">
      <li><span><b>声の自動採点（1日100回）</b><small>手拍子に合わせて1回言うだけで、発音・リズム・抑揚を点数にします。</small></span></li>
      <li><span><b>直すところを日本語で</b><small>「v が b に近く聞こえます」のように、何に聞こえたかと口の動かし方のコツを示します。</small></span></li>
      <li><span><b>リズムの見える化</b><small>強い音と弱い音の長さを図にして、英語らしいリズムに近づいているかがわかります。</small></span></li>
      <li><span><b>採点の記録</b><small>文ごとの最高点と、日ごとの平均点の移り変わりを残します。</small></span></li>
    </ul>
    <div class="price-card"><div><small>月額</small><br><b>480<span>円</span></b></div><div style="text-align:right"><small>いつでも解約できます<br>解約しても、期間の終わりまで使えます</small></div></div>
    <div class="btn-col">
      <button class="btn gold big" id="payBuy">有料版にする</button>
      <button class="btn" id="payTrial" hidden>まず無料で3回ためす</button>
    </div>
    <div class="trust">
      <span>🔒 お支払いは Stripe（世界中で使われている決済サービス）で行います。カード番号はこのサイトに届きません。</span>
      <span>ログインはパスキー（指紋・顔・PIN）。パスワードもメールアドレスも要りません。</span>
      <span>採点のときだけ、録音を Microsoft Azure の音声認識に送ります。録音は保存しません。</span>
      <span>${LEGAL}</span>
    </div>
  </div>
</dialog>
<dialog id="acctDlg">
  <div class="dlg">
    <div class="dlg-head"><h2>アカウント</h2><button class="btn icon" id="acctClose" aria-label="閉じる">✕</button></div>
    <p id="acctMsg" class="note"></p>
    <div data-view="register">
      <p>表示名（ニックネーム）を決めて、この端末にパスキーを作ります。</p>
      <input id="acctName" class="acct-input" maxlength="30" placeholder="ニックネーム" autocomplete="nickname">
      <div class="btn-row"><button class="btn-primary" id="acctRegisterBtn">パスキーを作って続ける</button></div>
      <p class="note">前に作った方は <button class="link" data-goto="login">パスキーでログイン</button></p>
    </div>
    <div data-view="login" hidden>
      <p>この端末（または同じアカウントの端末）に保存したパスキーでログインします。</p>
      <div class="btn-row"><button class="btn-primary" id="acctLoginBtn">パスキーでログイン</button></div>
      <p class="note">パスキーをなくした方は <button class="link" data-goto="recover">復旧コードを使う</button>／初めての方は <button class="link" data-goto="register">パスキーを作る</button></p>
    </div>
    <div data-view="recover" hidden>
      <p>登録したときにメモした復旧コードを入れてください。</p>
      <input id="acctCode" class="acct-input" placeholder="XXXXX-XXXXX-XXXXX-XXXXX" autocomplete="off">
      <div class="btn-row"><button class="btn-primary" id="acctRecoverBtn">復旧コードでログイン</button></div>
    </div>
    <div data-view="recovery" hidden>
      <p>パスキーをなくしたときに使う<strong>復旧コード</strong>です。この画面にしか出ないので、メモして大切に保管してください。</p>
      <p id="acctRecovery" class="acct-code"></p>
      <div class="btn-row"><button class="btn-primary" id="acctRecoveryDone">メモしました</button></div>
    </div>
    <p id="acctError" class="acct-error" hidden></p>
  </div>
</dialog>
<div class="toast" id="toast" hidden></div>`);

  // 設定の中のアカウント欄
  $('settingsDlg').querySelector('.dlg').insertAdjacentHTML('beforeend', `
    <div class="plan-box">
      <h3>アカウント・有料版</h3>
      <p class="note" id="planStatus"></p>
      <div class="btn-row" id="planBtns"></div>
      <p class="note plan-legal">申し込むと利用規約に同意したものとみなします。${LEGAL}</p>
    </div>`);

  // 練習の画面の採点ボタンと結果の置き場所
  $('player').querySelector('.main-btns').insertAdjacentHTML('beforeend', '<button class="btn gold big" id="scoreBtn">🎯 採点</button>');
  $('player').querySelector('.main-btns').insertAdjacentHTML('afterend', '<p class="score-hint" id="scoreHint"></p><div class="score-box" id="scoreBox"></div>');
}

let toastTimer = 0;
const toast = (msg) => {
  const t = $('toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 4000);
};

const dateLabel = (secs) => {
  const d = new Date(secs * 1000);
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
};

// ---- 会員の状態 ----
const refreshAccount = async () => {
  account = await apiGet('/api/me');
  renderPlan();
  if (document.body.dataset.view === 'records') renderRecords();
};

const usageText = () => {
  const u = account.usage;
  if (!u) return '';
  return u.kind === 'paid' ? `今日あと ${u.left} 回` : `無料のお試し あと ${u.left} 回`;
};

function renderPlan() {
  if (!BILLING_ON) return;
  const btn = (id, label, cls = 'btn') => `<button class="${cls}" data-plan="${id}">${label}</button>`;
  let status;
  let btns;
  if (account.paid) {
    status = `有料版をお使いです（${account.name}）。${account.cancelAtEnd ? `${dateLabel(account.periodEnd)}で終了します` : `次の更新日は${dateLabel(account.periodEnd)}です`}。採点は${usageText()}。`;
    btns = btn('portal', 'お支払い・解約') + btn('logout', 'ログアウト');
  } else if (account.signedIn) {
    status = `${account.name} でログイン中（${usageText()}）。有料版にすると、声の自動採点を1日100回まで使えます（${PRICE_LABEL}）。`;
    btns = btn('buy', `有料版にする（${PRICE_LABEL}）`, 'btn gold') + (account.customer ? btn('portal', 'お支払いの履歴') : '') + btn('logout', 'ログアウト');
  } else {
    status = `有料版（${PRICE_LABEL}）にすると、声の自動採点（発音・リズム・抑揚）を使えます。無料のアカウントを作ると、3回までためせます。`;
    btns = btn('buy', `有料版にする（${PRICE_LABEL}）`, 'btn gold') + btn('trial', '無料で3回ためす') + btn('login', 'ログイン');
  }
  const banner = $('premiumBanner');
  if (banner) banner.hidden = account.paid;
  $('planStatus').textContent = status;
  $('planBtns').innerHTML = btns;
  renderScoreHint();
}

function renderScoreHint() {
  const hint = $('scoreHint');
  if (!hint) return;
  const base = '🎯 採点：カウントのあと、手拍子に合わせて1回だけ言うと点数が出ます（イヤホン推奨）。';
  hint.textContent = account.signedIn ? `${base}${usageText()}。` : `${base}無料のアカウントで3回ためせます。`;
}

// ---- 有料版の案内・アカウントの画面 ----
const openPaywall = (lead) => {
  $('payLead').textContent = lead || 'あなたの英語を、耳のいいコーチが毎回採点。';
  $('payTrial').hidden = account.signedIn;
  if (!$('payDlg').open) $('payDlg').showModal();
};

const openAcct = (view, message = '') => {
  const dlg = $('acctDlg');
  dlg.querySelectorAll('[data-view]').forEach((e) => { e.hidden = e.dataset.view !== view; });
  $('acctMsg').textContent = message;
  $('acctError').hidden = true;
  if (!dlg.open) dlg.showModal();
};
const acctError = (msg) => {
  $('acctError').textContent = msg;
  $('acctError').hidden = false;
};
const closeAcct = () => { if ($('acctDlg').open) $('acctDlg').close(); };

let afterSignIn = null; // ログインできたら続けてすること（申し込みなど）

const startCheckout = async () => {
  const { url } = await apiPost('/api/checkout');
  location.href = url;
};

const PASSKEY_NOTE = '英語リズム・トレーニング用のパスキー（指紋・顔・PINでログインするしくみ）を作ります。パスワードやメールアドレスは要りません。';

const buyPlan = async () => {
  if ($('payDlg').open) $('payDlg').close();
  if (!account.signedIn) {
    afterSignIn = startCheckout;
    openAcct('register', `有料版の申し込みには、${PASSKEY_NOTE}`);
    return;
  }
  await startCheckout();
};

const startTrial = () => {
  if ($('payDlg').open) $('payDlg').close();
  afterSignIn = async () => toast('アカウントができました。練習の画面の「🎯 採点」で3回ためせます');
  openAcct('register', `無料のアカウントで、採点を3回までためせます。${PASSKEY_NOTE}`);
};

const signedInDone = async (recovery) => {
  await refreshAccount();
  const next = () => {
    closeAcct();
    const fn = afterSignIn;
    afterSignIn = null;
    if (fn) fn().catch((e) => alert(e.message));
  };
  if (!recovery) return next();
  // 復旧コードは1回だけ見せる
  $('acctRecovery').textContent = recovery;
  openAcct('recovery');
  $('acctRecoveryDone').onclick = next;
};

const registerPasskey = async () => {
  if (!window.PublicKeyCredential) return acctError('このブラウザはパスキーに対応していません。新しいブラウザで開いてください。');
  try {
    const opt = await apiPost('/api/register/options', { name: $('acctName').value });
    const cred = await navigator.credentials.create({ publicKey: creationOptions(opt) });
    const done = await apiPost('/api/register/verify', { response: registrationJSON(cred) });
    await signedInDone(done.recovery);
  } catch (e) {
    acctError(explainPasskey(e));
  }
};

const loginPasskey = async () => {
  if (!window.PublicKeyCredential) return acctError('このブラウザはパスキーに対応していません。');
  try {
    const opt = await apiPost('/api/login/options');
    const cred = await navigator.credentials.get({ publicKey: requestOptions(opt) });
    await apiPost('/api/login/verify', { response: authenticationJSON(cred) });
    await signedInDone('');
  } catch (e) {
    acctError(explainPasskey(e));
  }
};

const recoverAccount = async () => {
  try {
    const done = await apiPost('/api/recover', { code: $('acctCode').value });
    // 使った復旧コードは無効になるので新しいコードを見せ、この端末のパスキーを作ってもらう
    afterSignIn = async () => {
      const opt = await apiPost('/api/passkey/options');
      const cred = await navigator.credentials.create({ publicKey: creationOptions(opt) });
      await apiPost('/api/passkey/verify', { response: registrationJSON(cred) });
    };
    await signedInDone(done.recovery);
  } catch (e) {
    acctError(e.message);
  }
};

const onPlanButton = async (what) => {
  try {
    if (what === 'buy') await buyPlan();
    else if (what === 'trial') startTrial();
    else if (what === 'login') { afterSignIn = null; openAcct('login'); }
    else if (what === 'portal') location.href = (await apiPost('/api/portal')).url;
    else if (what === 'logout') {
      await apiPost('/api/logout');
      location.reload();
    }
  } catch (e) {
    alert(e.message);
  }
};

// 支払い画面から戻ってきたとき
const handleCheckoutReturn = async () => {
  const q = new URLSearchParams(location.search);
  const result = q.get('checkout');
  if (!result) return;
  history.replaceState(null, '', location.pathname + location.hash);
  if (result === 'cancel') {
    toast('申し込みは取り消されました');
    return;
  }
  const sessionId = q.get('session_id');
  if (result === 'done' && sessionId) {
    account = await apiPost('/api/checkout/confirm', { sessionId });
    renderPlan();
    toast(account.paid ? 'ありがとうございます。有料版になりました。練習の画面の「🎯 採点」をどうぞ' : 'お支払いの確認に時間がかかっています。少ししてから開き直してください');
  }
};

// ---- 録音 → 16kHz・モノラルの WAV ----
async function recordMic() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('このブラウザは録音に対応していません');
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  const rec = new MediaRecorder(stream);
  const chunks = [];
  rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  const done = new Promise((resolve) => {
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      resolve(new Blob(chunks, { type: rec.mimeType || 'audio/webm' }));
    };
  });
  rec.start();
  return { stop: () => { if (rec.state !== 'inactive') rec.stop(); return done; } };
}

async function toWav16k(blob) {
  // 16kHz の OfflineAudioContext で読み込むと、その場で 16kHz に変換される
  const ctx = new OfflineAudioContext(1, 1, 16000);
  const buf = await ctx.decodeAudioData(await blob.arrayBuffer());
  const n = Math.min(buf.length, 16000 * MAX_REC_SECONDS);
  const mono = new Float32Array(n);
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const ch = buf.getChannelData(c);
    for (let i = 0; i < n; i++) mono[i] += ch[i] / buf.numberOfChannels;
  }
  const out = new DataView(new ArrayBuffer(44 + n * 2));
  const put = (o, s) => [...s].forEach((ch, i) => out.setUint8(o + i, ch.charCodeAt(0)));
  put(0, 'RIFF');
  out.setUint32(4, 36 + n * 2, true);
  put(8, 'WAVE');
  put(12, 'fmt ');
  out.setUint32(16, 16, true);
  out.setUint16(20, 1, true);
  out.setUint16(22, 1, true);
  out.setUint32(24, 16000, true);
  out.setUint32(28, 32000, true);
  out.setUint16(32, 2, true);
  out.setUint16(34, 16, true);
  put(36, 'data');
  out.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) out.setInt16(44 + i * 2, Math.max(-1, Math.min(1, mono[i])) * 0x7fff, true);
  return out.buffer;
}

// ---- 採点 ----
let scoring = false;

async function runScore() {
  if (scoring) return;
  if (!account.signedIn) {
    openPaywall('まずは無料で3回ためせます。手拍子に合わせて1回言うだけで、発音・リズム・抑揚を採点します。');
    return;
  }
  if (account.usage && account.usage.left <= 0) {
    if (account.paid) toast('今日の採点は100回までです。また明日どうぞ');
    else openPaywall('お試しの3回を使い切りました。続けて採点するには有料版をどうぞ。');
    return;
  }
  stopAll();
  const status = $('workStatus');
  const box = $('scoreBox');
  try { Engine.ensure(); } catch (e) { status.textContent = e.message; return; }
  const it = work.item;
  const parsed = work.lane.parsed;
  const bpm = +$('bpm').value;
  $('recBox').replaceChildren();
  box.replaceChildren();
  let rec;
  try {
    rec = await recordMic();
  } catch (e) {
    status.textContent = `マイクが使えませんでした（${e.message}）。`;
    return;
  }
  scoring = true;
  const btn = $('scoreBtn');
  btn.disabled = true;
  const token = playToken;
  const anim = laneAnimator([work.lane], status, {
    count: (e) => ['いち', 'に', 'さん'][e.n - 1] || String(e.n),
    cycle: () => '🎙 1回だけ言ってください',
  });
  const finish = () => { scoring = false; btn.disabled = false; };
  Engine.play(buildTimeline([parsed], { bpm, cycles: 1, voices: [], clap: true }), {
    onEvent: anim.onEvent,
    onFrame: anim.onFrame,
    onStop: async (completed) => {
      anim.reset();
      if (!completed || token !== playToken) {
        await rec.stop();
        status.textContent = '';
        finish();
        return;
      }
      status.textContent = '採点しています…';
      // 最後の語を言い終わるまで少し待ってから止める
      await new Promise((r) => setTimeout(r, 500));
      const blob = await rec.stop();
      try {
        const wav = await toWav16k(blob);
        const res = await fetch(`/api/score?id=${encodeURIComponent(it.id)}`, { method: 'POST', headers: { 'Content-Type': 'audio/wav' }, body: wav, credentials: 'same-origin' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || `エラー（${res.status}）`);
        if (it !== work.item) return; // 採点中に別の文へ移った
        account.usage = data.usage;
        renderPlan();
        status.textContent = '';
        box.replaceChildren(scoreCard(data, blob));
        box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        logAct('score');
      } catch (e) {
        status.textContent = '';
        box.replaceChildren(el('div', { className: 'sc-err' }, charaImg('worried'), el('span', { textContent: e.message })));
        if (/お試し/.test(e.message)) openPaywall('お試しの3回を使い切りました。続けて採点するには有料版をどうぞ。');
      } finally {
        finish();
      }
    },
  });
}

const grade = (v) => (v >= 80 ? 'good' : v >= 60 ? 'mid' : 'bad');

function meter(label, v, sub = '') {
  return el('div', { className: 'sc-meter' },
    el('span', { className: 'nm', textContent: label }),
    el('span', { className: 'bar' }, el('i', { className: v == null ? '' : grade(v), style: `width:${v ?? 0}%` })),
    el('span', { className: 'v', textContent: v == null ? '—' : String(v) }),
    ...(sub ? [el('small', { className: 'sub', textContent: sub })] : []));
}

// 強い音・弱い音の長さと位置の図
function timeChart(sylls) {
  const timed = sylls.filter((s) => s.start != null);
  if (!timed.length) return el('div');
  const t0 = Math.min(...timed.map((s) => s.start));
  const t1 = Math.max(...timed.map((s) => s.start + s.dur));
  const span = Math.max(1, t1 - t0);
  const track = el('div', { className: 'sc-track' });
  timed.forEach((s) => {
    track.append(el('span', {
      className: 'blk' + (s.stress ? ' st' : ''),
      title: `${s.text}：${s.dur}ミリ秒`,
      style: `left:${(100 * (s.start - t0)) / span}%;width:${Math.max(0.6, (100 * s.dur) / span)}%`,
      textContent: s.text,
    }));
  });
  return track;
}

function scoreCard(r, blob) {
  const words = el('p', { className: 'sc-words' }, ...r.words.flatMap((w, i) => [
    el('span', {
      className: 'w ' + (w.error === 'Omission' ? 'miss' : grade(w.accuracy)) + (w.stress ? ' st' : ''),
      title: w.error === 'Omission' ? '聞き取れませんでした' : `${w.accuracy}点`,
      textContent: w.text + w.punct,
    }),
    ...(i < r.words.length - 1 ? [' '] : []),
  ]));
  const rh = r.rhythm;
  const rhythmSub = [
    rh.evenness != null ? `強い音の間隔のそろい方 ${rh.evenness}点` : '',
    rh.ratio != null ? `弱い音の長さは強い音の約${Math.round(rh.ratio * 10)}割` : '',
  ].filter(Boolean).join('　');
  const audio = el('audio', { controls: true, src: URL.createObjectURL(blob) });
  return el('div', { className: 'sc-card' },
    el('div', { className: 'sc-top' },
      charaImg(r.total >= 85 ? 'celebrate' : r.total >= 60 ? 'happy' : 'cheer', 'sc-chara'),
      el('div', { className: 'sc-total ' + grade(r.total) }, el('b', { textContent: String(r.total) }), el('small', { textContent: '点' })),
      el('div', { className: 'sc-sub' },
        el('div', { textContent: r.total >= r.best && r.best > 0 ? '🏆 この文の自己ベスト！' : `この文の最高 ${r.best}点` }),
        el('div', { textContent: usageText() }))),
    el('div', { className: 'sc-meters' },
      meter('発音', r.pron, `正確さ ${r.accuracy}　流ちょうさ ${r.fluency}　言えた割合 ${r.completeness}`),
      meter('リズム', rh.score, rhythmSub || '強い音が少ない文なので、リズムは測りません'),
      meter('抑揚', r.prosody)),
    words,
    el('div', { className: 'sc-chart' },
      el('div', { className: 'sc-label', textContent: '声の長さの図（赤＝強い音、灰色＝弱い音）' }),
      timeChart(r.sylls),
      el('p', { className: 'sc-note', textContent: '赤のブロックの間隔がそろい、灰色のブロックが短いほど英語らしいリズムです。' })),
    ...(r.tips.length ? [el('ul', { className: 'sc-tips' }, ...r.tips.map((t) => el('li', {}, ...(t.word ? [el('b', { textContent: t.word })] : []), el('span', { textContent: t.text }))))] : []),
    el('div', { className: 'sc-rec' }, el('span', { className: 'note', textContent: '🎙 採点した声' }), audio));
}

// ---- 記録の画面の「声の採点」 ----
function scoreRecordCard() {
  const card = el('div', { className: 'card score-rec' }, el('h3', { textContent: '🎯 声の採点' }));
  if (!BILLING_ON) return card;
  if (!account.signedIn) {
    card.append(el('p', { className: 'note', textContent: '練習の画面の「🎯 採点」で、発音・リズム・抑揚を点数にできます。無料のアカウントで3回ためせます。採点の記録はアカウントに残ります。' }),
      el('div', { className: 'btn-row' }, el('button', { className: 'btn gold', textContent: '有料版について', onclick: () => openPaywall() })));
    return card;
  }
  card.append(el('p', { className: 'note', textContent: '読み込んでいます…' }));
  apiGet('/api/scores').then((h) => {
    const kids = [el('h3', { textContent: '🎯 声の採点' })];
    if (!h.recent.length) {
      kids.push(el('p', { className: 'note', textContent: 'まだ採点の記録がありません。練習の画面の「🎯 採点」をどうぞ。' }));
    } else {
      const all = [...LEVELS.flatMap((l) => l.items), ...DRILLS.flatMap((m) => m.items)];
      const nameOf = (id) => {
        const it = all.find((x) => x.id === id);
        return it ? it.t.replace(/[*·]/g, '') : id;
      };
      const days = h.daily.slice(-14);
      kids.push(el('p', { className: 'note', textContent: `採点した回数 ${h.daily.reduce((a, d) => a + d.n, 0)}回。日ごとの平均点（最近の14日）：` }),
        el('div', { className: 'sc-days' }, ...days.map((d) => el('div', { className: 'd', title: `${d.day}：平均${d.total}点（${d.n}回）` },
          el('i', { className: grade(d.total), style: `height:${Math.max(4, d.total)}%` }), el('span', { textContent: String(+d.day.slice(8)) })))),
        el('div', { className: 'section-title' }, el('h2', { textContent: '最近の採点' })),
        ...h.recent.slice(0, 10).map((s) => el('div', { className: 'sc-row' },
          el('span', { className: 'en', textContent: nameOf(s.sentence) }),
          el('b', { className: grade(s.total), textContent: `${s.total}点` }),
          el('small', { textContent: `最高 ${h.best[s.sentence]}` }))));
    }
    card.replaceChildren(...kids);
  }).catch((e) => card.replaceChildren(el('h3', { textContent: '🎯 声の採点' }), el('p', { className: 'note', textContent: e.message })));
  return card;
}

function initBilling() {
  if (!BILLING_ON) return;
  mountBillingUI();
  $('scoreBtn').addEventListener('click', runScore);
  document.addEventListener('click', (e) => { if (e.target.closest('[data-premium]')) openPaywall(); });
  $('planBtns').addEventListener('click', (e) => {
    const b = e.target instanceof Element ? e.target.closest('button[data-plan]') : null;
    if (b) onPlanButton(b.dataset.plan);
  });
  $('payBuy').addEventListener('click', () => buyPlan().catch((e) => alert(e.message)));
  $('payTrial').addEventListener('click', startTrial);
  $('payDlg').addEventListener('click', (e) => {
    if (e.target === $('payDlg') || (e.target instanceof Element && e.target.closest('[data-close]'))) $('payDlg').close();
  });
  $('acctRegisterBtn').addEventListener('click', registerPasskey);
  $('acctLoginBtn').addEventListener('click', loginPasskey);
  $('acctRecoverBtn').addEventListener('click', recoverAccount);
  $('acctDlg').addEventListener('click', (e) => {
    const b = e.target instanceof Element ? e.target.closest('[data-goto]') : null;
    if (b) openAcct(b.dataset.goto);
  });
  $('acctClose').addEventListener('click', () => { afterSignIn = null; closeAcct(); });
  // 文を移ったら、前の文の採点結果は消す
  const clearScore = () => { $('scoreBox').replaceChildren(); };
  ['focusPrev', 'focusNext', 'focusClose'].forEach((id) => $(id).addEventListener('click', clearScore));
  renderScoreHint();
  refreshAccount()
    .then(handleCheckoutReturn)
    .catch((e) => console.warn('有料版の状態を確かめられませんでした', e));
}

initBilling();
