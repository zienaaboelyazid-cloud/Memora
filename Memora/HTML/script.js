/* =====================================================================
   MEMORA — real front-end for the Python project
   This talks over HTTP to api_server.py (Flask), which wraps the SAME
   database, face-recognition (InsightFace) and AI-assistant (Ollama)
   code used by main.py. Start api_server.py first, then open this page
   (via VS Code's Live Server, not as a bare file:// page, since
   browsers block camera access on file:// pages).
   ===================================================================== */

const API_BASE = window.MEMORA_API_BASE || 'http://127.0.0.1:5000/api';

async function apiFetch(path, options) {
  let res;
  try {
    res = await fetch(API_BASE + path, Object.assign(
      { headers: { 'Content-Type': 'application/json' } },
      options || {}
    ));
  } catch (networkErr) {
    setServerBanner(true);
    throw new Error("Can't reach the MEMORA server. Is api_server.py running?");
  }
  setServerBanner(false);

  let body = null;
  try { body = await res.json(); } catch (e) { /* empty body is fine */ }

  if (!res.ok) {
    throw new Error((body && body.error) || ('Request failed (' + res.status + ')'));
  }
  return body;
}

const Api = {
  signup: (payload) => apiFetch('/signup', { method: 'POST', body: JSON.stringify(payload) }),
  login: (nationalId) => apiFetch('/login', { method: 'POST', body: JSON.stringify({ nationalId }) }),
  listPatients: () => apiFetch('/patients'),
  getPatient: (id) => apiFetch('/patients/' + id),
  deletePatient: (id) => apiFetch('/patients/' + id, { method: 'DELETE' }),
  setPhoto: (id, image) => apiFetch('/patients/' + id + '/photo', { method: 'POST', body: JSON.stringify({ image }) }),
  listFamily: (id) => apiFetch('/patients/' + id + '/family'),
  addFamily: (id, payload) => apiFetch('/patients/' + id + '/family', { method: 'POST', body: JSON.stringify(payload) }),
  recognize: (id, image) => apiFetch('/patients/' + id + '/recognize', { method: 'POST', body: JSON.stringify({ image }) }),
  getSchedule: (id) => apiFetch('/patients/' + id + '/schedule'),
  setSchedule: (id, schedule) => apiFetch('/patients/' + id + '/schedule', { method: 'POST', body: JSON.stringify({ schedule }) }),
  getSafeZone: (id) => apiFetch('/patients/' + id + '/safezone'),
  setSafeZone: (id, zone) => apiFetch('/patients/' + id + '/safezone', { method: 'POST', body: JSON.stringify(zone) }),
  checkSafeZone: (id, coords) => apiFetch('/patients/' + id + '/safezone/check', { method: 'POST', body: JSON.stringify(coords || {}) }),
  askAssistant: (id, message) => apiFetch('/patients/' + id + '/assistant', { method: 'POST', body: JSON.stringify({ message }) }),
  caregiverLogin: (username, password) => apiFetch('/caregiver/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
};

function setServerBanner(show) {
  const banner = document.getElementById('server-banner');
  if (!banner) return;
  document.getElementById('server-banner-url').textContent = API_BASE;
  banner.style.display = show ? 'block' : 'none';
}

/* ---------------- app state ---------------- */
const state = {
  currentPatientId: null,
  currentSetupPatientId: null,
  dashTab: 'camera',
  camStream: null,
  famCamStream: null,
  photoStream: null,
  pendingPhoto: null,        // dataUrl of the patient's own photo waiting to be saved
  photoPatientId: null,
  photoNext: null,           // what to do once the photo is saved
  scheduleMode: 'ask',       // 'ask' = daily question, 'edit' = patient chose to change it
  currentFirstName: '',
  pendingCapture: null,      // dataUrl waiting to be sent with the family form
  familyModalPatientId: null,
  chatHistory: [],
  scheduleEntries: [],
  leafletMap: null,
  homeMarker: null,
  youMarker: null,
  zoneCircle: null,
  currentZoneRadius: 150,
  homeSet: false,
};
var currentSetupPatientId = null; // referenced from inline HTML

const DEFAULT_LAT = 30.0444;  // Cairo — only used before any home is set
const DEFAULT_LON = 31.2357;

/* ---------------- small helpers ---------------- */
function $(id) { return document.getElementById(id); }
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  $(id).classList.add('active');
  document.body.classList.toggle('on-landing', id === 'screen-role'); // background image is stronger on the first screen only
  window.scrollTo(0, 0);
}
function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toast._h);
  toast._h = setTimeout(() => t.classList.remove('show'), 2800);
}
function isArabicText(s) { return /[\u0600-\u06FF]/.test(s || ''); }
function speak(text, arabicHint) {
  try {
    if (!('speechSynthesis' in window)) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = (arabicHint === undefined ? isArabicText(text) : arabicHint) ? 'ar-EG' : 'en-US';
    u.rate = 1;
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  } catch (e) { /* speech not available */ }
}
function calcAge(dobStr) {
  const dob = new Date(dobStr);
  const today = new Date();
  let age = today.getFullYear() - dob.getFullYear();
  const m = today.getMonth() - dob.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) age--;
  return age;
}
function haversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
function closeModal(id) { $(id).classList.remove('active'); }
function openModalEl(id) { $(id).classList.add('active'); }
function escapeHtml(str) {
  return (str || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* ---------------- navigation ---------------- */
function goRole() { stopAllCameras(); showScreen('screen-role'); }
function goPatientAuth() {
  showScreen('screen-patient-auth');
  switchAuthTab('signup');
  $('signup-error').textContent = '';
  $('login-error').textContent = '';
}
function goCaregiverAuth() {
  showScreen('screen-caregiver-auth');
  $('cg-username').value = '';
  $('cg-password').value = '';
  $('cg-login-error').textContent = '';
}
function switchAuthTab(which) {
  $('tab-btn-signup').classList.toggle('active', which === 'signup');
  $('tab-btn-login').classList.toggle('active', which === 'login');
  $('form-signup').style.display = which === 'signup' ? 'block' : 'none';
  $('form-login').style.display = which === 'login' ? 'block' : 'none';
}
function logout() {
  stopAllCameras();
  clearInterval(state._zoneTimer);
  clearInterval(state._scheduleTimer);
  setDashAvatar(null);
  state.currentPatientId = null;
  showScreen('screen-role');
}

/* ---------------- sign up / login ---------------- */
function updateAgePreview() {
  const dob = $('su-dob').value;
  $('age-preview').textContent = dob ? ('Age: ' + calcAge(dob)) : '';
}

async function handleSignup(ev) {
  ev.preventDefault();
  const firstName = $('su-first').value.trim();
  const lastName = $('su-last').value.trim();
  const dob = $('su-dob').value;
  const nationalId = $('su-nid').value.trim();
  $('signup-error').textContent = '';

  if (!firstName || !lastName || !dob || !nationalId) {
    $('signup-error').textContent = 'Please fill in every field.';
    return false;
  }

  try {
    const patient = await Api.signup({ firstName, lastName, dob, nationalId });
    toast('Account created for ' + firstName);
    speak('Account created. Welcome, ' + firstName + '.', false);
    startPhotoStep(patient, () => startFamilySetup(patient.id));
  } catch (e) {
    $('signup-error').textContent = e.message;
  }
  return false;
}

async function handleLogin(ev) {
  ev.preventDefault();
  const nid = $('li-nid').value.trim();
  try {
    const patient = await Api.login(nid);
    $('login-error').textContent = '';
    toast('Welcome back, ' + patient.firstName + '!');
    if (patient.hasPhoto) afterLogin(patient);
    else startPhotoStep(patient, () => afterLogin(patient));
  } catch (e) {
    $('login-error').textContent = e.message;
  }
  return false;
}

/* ---------------- patient's own photo (sign-up, or first login if none on file) ---------------- */
function photoUrl(patientId) {
  return API_BASE + '/patients/' + patientId + '/photo?t=' + Date.now();
}
function familyPhotoUrl(patientId, personId) {
  return API_BASE + '/patients/' + patientId + '/family/' + personId + '/photo?t=' + Date.now();
}
/* Shared markup for one family-list row: real photo when we have one saved
   for that person, otherwise the same blank circle as before. */
function familyAvatarHtml(patientId, member) {
  if (member.hasPhoto && member.id) {
    return '<img src="' + familyPhotoUrl(patientId, member.id) + '" alt="' + escapeHtml(member.name) +
      '" style="width:44px;height:44px;border-radius:50%;object-fit:cover;">';
  }
  return '<div style="width:44px;height:44px;border-radius:50%;background:var(--surface-alt);"></div>';
}
function startPhotoStep(patient, next) {
  state.photoPatientId = patient.id;
  state.photoNext = next;
  state.pendingPhoto = null;
  $('photo-preview').innerHTML = '';
  $('photo-error').textContent = '';
  $('photo-heading').textContent = 'Add your photo, ' + patient.firstName;
  showScreen('screen-patient-photo');
  speak('Please add a photo of your face.', false);
  startPhotoCamera();
}
function startPhotoCamera() {
  const video = $('photo-video');
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    video.style.display = 'none';
    $('photo-status').textContent = 'Camera not available in this browser — use "Upload instead".';
    return;
  }
  $('photo-status').textContent = 'Starting camera…';
  video.style.display = 'block';
  navigator.mediaDevices.getUserMedia({ video: true }).then(stream => {
    state.photoStream = stream;
    video.srcObject = stream;
    $('photo-status').textContent = 'Look at the camera, then press "Take photo".';
  }).catch(() => {
    video.style.display = 'none';
    $('photo-status').textContent = 'Camera not available in this browser — use "Upload instead".';
  });
}
function setPendingPhoto(dataUrl) {
  state.pendingPhoto = dataUrl;
  $('photo-error').textContent = '';
  $('photo-preview').innerHTML = '<img src="' + dataUrl + '" style="width:96px;height:96px;border-radius:50%;object-fit:cover;">';
}
function photoCapture() {
  const video = $('photo-video');
  if (!video.srcObject) { toast('Camera not available — try uploading a photo.'); return; }
  const canvas = $('photo-canvas');
  canvas.width = video.videoWidth || 320; canvas.height = video.videoHeight || 240;
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  setPendingPhoto(canvas.toDataURL('image/jpeg', 0.9));
}
function photoHandleUpload(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => setPendingPhoto(e.target.result);
  reader.readAsDataURL(file);
}
async function savePatientPhoto() {
  if (!state.pendingPhoto) { $('photo-error').textContent = 'Please take or upload a photo first.'; return; }
  $('photo-error').textContent = 'Checking your photo…';
  try {
    await Api.setPhoto(state.photoPatientId, state.pendingPhoto);
  } catch (e) {
    $('photo-error').textContent = e.message; // e.g. "No face was detected in that photo."
    return;
  }
  stopAllCameras();
  toast('Photo saved.');
  const next = state.photoNext;
  state.photoNext = null;
  if (next) next();
}

/* after a successful login: only ask "what's your schedule today?" when it's due (missing or older than 24h) */
async function afterLogin(patient) {
  state.currentPatientId = patient.id;
  let due = true;
  try { due = (await Api.getSchedule(patient.id)).needsUpdate; } catch (e) { /* can't tell - ask */ }
  if (due) enterSchedule(patient.id, patient.firstName);
  else enterDashboard();
}

/* while the app stays open, ask again once the schedule is 24h old */
async function checkScheduleDue() {
  if (!state.currentPatientId || !$('screen-dashboard').classList.contains('active')) return;
  try {
    const s = await Api.getSchedule(state.currentPatientId);
    if (s.needsUpdate) {
      stopAllCameras();
      enterSchedule(state.currentPatientId, state.currentFirstName);
    }
  } catch (e) { /* server unreachable - try again next time */ }
}
function editScheduleNow() {
  stopAllCameras();
  enterSchedule(state.currentPatientId, state.currentFirstName, 'edit');
}

/* ---------------- family setup (post sign-up) ---------------- */
function startFamilySetup(patientId) {
  state.currentSetupPatientId = patientId;
  currentSetupPatientId = patientId;
  renderSetupFamilyList();
  showScreen('screen-family-setup');
}
async function renderSetupFamilyList() {
  let list = [];
  try { list = await Api.listFamily(state.currentSetupPatientId); } catch (e) { toast(e.message); }
  const ul = $('setup-family-list');
  ul.innerHTML = '';
  list.forEach(m => {
    const li = document.createElement('li');
    li.className = 'family-item';
    li.innerHTML = familyAvatarHtml(state.currentSetupPatientId, m) +
      '<div><div class="fi-name">' + escapeHtml(m.name) + '</div><div class="fi-rel">' + escapeHtml(m.relationship) +
      (m.age != null ? ' · ' + escapeHtml(String(m.age)) : '') + '</div></div>';
    ul.appendChild(li);
  });
  $('setup-family-empty').style.display = list.length ? 'none' : 'block';
}
function finishFamilySetup() {
  const patientId = state.currentSetupPatientId;
  Api.getPatient(patientId).then(data => {
    enterSchedule(patientId, data.profile.firstName);
  }).catch(() => enterSchedule(patientId, ''));
}

/* ---------------- daily schedule ---------------- */
function enterSchedule(patientId, firstName, mode) {
  state.currentPatientId = patientId;
  state.currentFirstName = firstName || '';
  state.scheduleMode = mode || 'ask';
  state.scheduleEntries = [];
  $('schedule-greeting').textContent = 'Hi, ' + firstName + '!';
  speak('Hi, ' + firstName + '! What is your schedule for today?', false);
  renderScheduleEntries();
  showScreen('screen-schedule');
}
function renderScheduleEntries() {
  const ul = $('schedule-entries-list');
  ul.innerHTML = '';
  state.scheduleEntries.forEach(e => {
    const li = document.createElement('li');
    li.innerHTML = '<span class="time">' + escapeHtml(e.time || '—') + '</span><span>' + escapeHtml(e.activity) + '</span>';
    ul.appendChild(li);
  });
}
function addScheduleEntry() {
  const time = $('sched-time').value;
  const activity = $('sched-activity').value.trim();
  if (!activity) { toast('Type or say what happens at that time.'); return; }
  state.scheduleEntries.push({ time, activity });
  $('sched-time').value = '';
  $('sched-activity').value = '';
  renderScheduleEntries();
}
function voiceFillActivity() {
  startSpeechRecognition(text => { $('sched-activity').value = text; });
}
async function finishSchedule() {
  if ($('sched-activity').value.trim()) addScheduleEntry(); // don't lose an item typed but not added yet
  const hasItems = state.scheduleEntries.length > 0;
  // In the daily question an empty answer is saved too ("nothing today"), so we don't ask again until tomorrow.
  if (hasItems || state.scheduleMode !== 'edit') {
    const text = state.scheduleEntries.map(e => (e.time ? e.time + ' - ' : '') + e.activity).join('; ');
    try {
      await Api.setSchedule(state.currentPatientId, text);
      if (hasItems) speak("Got it, I've saved your schedule for today.", false);
    } catch (e) { toast(e.message); }
  }
  enterDashboard();
}

/* ---------------- patient dashboard ---------------- */
function setDashAvatar(patientId) {
  const av = $('dash-avatar');
  if (patientId) av.innerHTML = '<img src="' + photoUrl(patientId) + '" alt="">';
  else av.innerHTML = '<span style="font-size:1rem;">M</span>';
}
async function enterDashboard() {
  try {
    const data = await Api.getPatient(state.currentPatientId);
    $('dash-name').textContent = data.profile.firstName + ' ' + data.profile.lastName;
    state.currentFirstName = data.profile.firstName;
    setDashAvatar(data.profile.hasPhoto ? state.currentPatientId : null);
  } catch (e) { toast(e.message); }

  showScreen('screen-dashboard');
  switchDashTab('camera');
  refreshZonePill();
  clearInterval(state._zoneTimer);
  state._zoneTimer = setInterval(refreshZonePill, 8000);
  clearInterval(state._scheduleTimer);
  state._scheduleTimer = setInterval(checkScheduleDue, 5 * 60 * 1000); // is the schedule 24h old yet?
}
function switchDashTab(tab) {
  state.dashTab = tab;
  document.querySelectorAll('.dash-tab').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.tile').forEach(el => el.classList.toggle('active', el.dataset.tab === tab));
  $('tab-' + tab).style.display = 'block';
  stopAllCameras();
  if (tab === 'camera') { renderDashFamilyList(); startMainCamera(); }
  if (tab === 'map') { initOrRefreshMap(); }
  if (tab === 'assistant') { renderChatIfEmpty(); }
  if (tab === 'mydata') { renderMyData(); }
}

/* ---- camera tab (real webcam + real InsightFace recognition on the server) ---- */
function startMainCamera() {
  const video = $('cam-video');
  $('cam-status').textContent = 'Starting camera…';
  navigator.mediaDevices?.getUserMedia({ video: true })
    .then(stream => {
      state.camStream = stream;
      video.srcObject = stream;
      $('cam-status').textContent = 'Camera ready.';
    })
    .catch(() => {
      $('cam-status').textContent = 'Camera not available in this browser — use "Upload a photo instead".';
    });
}
function stopAllCameras() {
  [state.camStream, state.famCamStream, state.photoStream].forEach(s => { if (s) s.getTracks().forEach(t => t.stop()); });
  state.camStream = null; state.famCamStream = null; state.photoStream = null;
}
function captureFor(mode) {
  const video = $('cam-video');
  if (!video.srcObject) { toast('Camera not available — try uploading a photo.'); return; }
  const canvas = $('cam-canvas');
  canvas.width = video.videoWidth || 320; canvas.height = video.videoHeight || 240;
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
  handleCapturedPhoto(mode, dataUrl);
}
function handleUpload(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => handleCapturedPhoto('recognize', e.target.result);
  reader.readAsDataURL(file);
}
function handleCapturedPhoto(mode, dataUrl) {
  if (mode === 'register') {
    openFamilyModal(state.currentPatientId, dataUrl);
  } else {
    recognizeAgainstFamily(dataUrl);
  }
}
async function recognizeAgainstFamily(dataUrl) {
  const box = $('cam-result');
  box.style.display = 'block';
  box.className = 'result-box';
  box.innerHTML = 'Asking the server to compare this against known faces…';

  try {
    const result = await Api.recognize(state.currentPatientId, dataUrl);

    if (result.message) {
      box.className = 'result-box nomatch';
      box.innerHTML = '<strong>' + escapeHtml(result.message) + '</strong>';
      speak(result.message, false);
      return;
    }

    if (result.found) {
      const pct = Math.round(result.score * 100);
      box.className = 'result-box match';
      box.innerHTML = '<strong>' + escapeHtml(result.name) + '</strong> (' + escapeHtml(result.relationship) + ') — score ' + pct + '%';
      if ((result.relationship || '').toLowerCase().startsWith('patient (self)')) speak('This is you, ' + result.name, false);
      else speak('This is ' + result.name + ', your ' + result.relationship, false);
    } else {
      const pct = Math.round((result.score || 0) * 100);
      box.className = 'result-box nomatch';
      box.innerHTML = '<strong>Unknown</strong> (closest match only ' + pct + '%). Use "Register this face" to add them.' +
        '<div style="margin-top:10px;"><button class="btn btn-primary btn-sm" id="cam-add-unknown">Add them now (name + relationship)</button></div>';
      $('cam-add-unknown').onclick = () => openFamilyModal(state.currentPatientId, dataUrl);
      speak("I don't recognize this person yet.", false);
    }
  } catch (e) {
    box.className = 'result-box nomatch';
    box.innerHTML = escapeHtml(e.message);
  }
}
async function renderDashFamilyList() {
  let list = [];
  try { list = await Api.listFamily(state.currentPatientId); } catch (e) { toast(e.message); }
  const ul = $('dash-family-list');
  ul.innerHTML = '';
  list.forEach(m => {
    const li = document.createElement('li');
    li.className = 'family-item';
    li.innerHTML = familyAvatarHtml(state.currentPatientId, m) +
      '<div><div class="fi-name">' + escapeHtml(m.name) + '</div><div class="fi-rel">' + escapeHtml(m.relationship) +
      (m.age != null ? ' · ' + escapeHtml(String(m.age)) : '') + '</div></div>';
    ul.appendChild(li);
  });
  $('dash-family-empty').style.display = list.length ? 'none' : 'block';
}

/* ---- family modal (shared by setup screen, dashboard, admin panel) ---- */
function openFamilyModal(patientId, precapturedDataUrl) {
  state.familyModalPatientId = patientId;
  $('fam-name').value = ''; $('fam-rel').value = ''; $('fam-age').value = ''; $('fam-notes').value = ''; $('fam-error').textContent = '';
  $('fam-photo-preview').innerHTML = '';
  state.pendingCapture = null;
  if (precapturedDataUrl) {
    state.pendingCapture = precapturedDataUrl;
    $('fam-photo-preview').innerHTML = '<img src="' + precapturedDataUrl + '" style="width:70px;height:70px;border-radius:50%;object-fit:cover;">';
  }
  openModalEl('modal-family');
}
function closeFamilyModal() {
  if (state.famCamStream) { state.famCamStream.getTracks().forEach(t => t.stop()); state.famCamStream = null; }
  $('fam-video').style.display = 'none';
  $('fam-cam-capture').style.display = 'none';
  closeModal('modal-family');
}
function famCamOpen() {
  const video = $('fam-video');
  video.style.display = 'block';
  navigator.mediaDevices?.getUserMedia({ video: true }).then(stream => {
    state.famCamStream = stream;
    video.srcObject = stream;
    $('fam-cam-capture').style.display = 'inline-flex';
  }).catch(() => { toast('Camera not available — try uploading instead.'); video.style.display = 'none'; });
}
function famCamCapture() {
  const video = $('fam-video');
  const canvas = $('fam-canvas');
  canvas.width = video.videoWidth || 320; canvas.height = video.videoHeight || 240;
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
  state.pendingCapture = dataUrl;
  $('fam-photo-preview').innerHTML = '<img src="' + dataUrl + '" style="width:70px;height:70px;border-radius:50%;object-fit:cover;">';
  if (state.famCamStream) { state.famCamStream.getTracks().forEach(t => t.stop()); state.famCamStream = null; }
  video.style.display = 'none'; $('fam-cam-capture').style.display = 'none';
}
function famHandleUpload(ev) {
  const file = ev.target.files[0]; if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    state.pendingCapture = e.target.result;
    $('fam-photo-preview').innerHTML = '<img src="' + e.target.result + '" style="width:70px;height:70px;border-radius:50%;object-fit:cover;">';
  };
  reader.readAsDataURL(file);
}
async function saveFamilyMember() {
  const name = $('fam-name').value.trim();
  const relationship = $('fam-rel').value.trim();
  const ageStr = $('fam-age').value.trim();
  const notes = $('fam-notes').value.trim();
  if (!name || !relationship || !ageStr) { $('fam-error').textContent = 'Please fill in the name, relationship and age.'; return; }
  const age = parseInt(ageStr, 10);
  if (isNaN(age) || age < 0 || age > 130) { $('fam-error').textContent = 'Please enter a valid age.'; return; }
  if (!state.pendingCapture) { $('fam-error').textContent = 'Please take or upload a photo.'; return; }

  try {
    await Api.addFamily(state.familyModalPatientId, { name, relationship, age, notes, image: state.pendingCapture });
  } catch (e) {
    $('fam-error').textContent = e.message; // e.g. "No face was detected in that photo."
    return;
  }

  closeFamilyModal();
  toast(name + ' added.');
  if ($('screen-family-setup').classList.contains('active')) renderSetupFamilyList();
  if ($('screen-dashboard').classList.contains('active')) renderDashFamilyList();
  if ($('screen-caregiver-dashboard').classList.contains('active')) renderCaregiverTable();
}

/* ---- map / safe zone tab (real Leaflet map, real lat/lng, real backend) ---- */
function initOrRefreshMap() {
  if (!state.leafletMap) {
    state.leafletMap = L.map('leaflet-map').setView([DEFAULT_LAT, DEFAULT_LON], 14);
    /* CARTO's free dark_all tiles now need an API key (they show an "API KEY REQUIRED"
       watermark). Esri's dark-gray canvas is free, needs no key, and looks the same.
       Base = the map, Reference = street/place labels on top. Native tiles stop at
       zoom 16; Leaflet just scales them up beyond that. */
    const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/';
    L.tileLayer(ESRI + 'World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19, maxNativeZoom: 16,
      attribution: 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors'
    }).addTo(state.leafletMap);
    L.tileLayer(ESRI + 'World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19, maxNativeZoom: 16
    }).addTo(state.leafletMap);
    state.leafletMap.on('click', onMapClick);
  } else {
    setTimeout(() => state.leafletMap.invalidateSize(), 50);
  }
  loadSafeZoneIntoMap();
}
async function loadSafeZoneIntoMap() {
  let zone = null;
  try { zone = await Api.getSafeZone(state.currentPatientId); } catch (e) { toast(e.message); }

  if (zone) {
    state.homeSet = true;
    state.currentZoneRadius = zone.radius_meters;
    placeHomeMarker(zone.center_lat, zone.center_lon, zone.radius_meters);
    placeYouMarker(zone.center_lat, zone.center_lon);
    state.leafletMap.setView([zone.center_lat, zone.center_lon], 15);
  } else {
    state.homeSet = false;
    placeYouMarker(DEFAULT_LAT, DEFAULT_LON);
  }
  $('radius-slider').value = state.currentZoneRadius;
  $('radius-label').textContent = state.currentZoneRadius;
  updateLiveStatus();
}
/* look-only marker icons (glowing, on-theme) — no effect on the logic */
const HOME_ICON = L.divIcon({
  className: 'mk-wrap',
  html: '<span class="mk mk-home"><i class="mk-pulse"></i>' +
        '<svg viewBox="0 0 24 30" aria-hidden="true"><path d="M12 29C12 29 2 18.5 2 11a10 10 0 0 1 20 0c0 7.5-10 18-10 18z"/><circle cx="12" cy="11" r="3.6"/></svg></span>',
  iconSize: [36, 44], iconAnchor: [18, 42], tooltipAnchor: [0, -40]
});
const YOU_ICON = L.divIcon({
  className: 'mk-wrap',
  html: '<span class="mk mk-you"><i class="mk-pulse"></i><i class="mk-dot"></i></span>',
  iconSize: [34, 34], iconAnchor: [17, 17], tooltipAnchor: [0, -18]
});

function placeHomeMarker(lat, lon, radius) {
  if (state.homeMarker) state.leafletMap.removeLayer(state.homeMarker);
  if (state.zoneCircle) state.leafletMap.removeLayer(state.zoneCircle);
  state.homeMarker = L.marker([lat, lon], { icon: HOME_ICON }).addTo(state.leafletMap)
    .bindTooltip('Home', { direction: 'top', className: 'memora-tip' });
  state.zoneCircle = L.circle([lat, lon], {
    radius: radius, color: '#4FD6FF', weight: 2, dashArray: '7 9',
    fillColor: '#4FD6FF', fillOpacity: 0.12, className: 'zone-circle'
  }).addTo(state.leafletMap);
}
function placeYouMarker(lat, lon) {
  if (state.youMarker) { state.youMarker.setLatLng([lat, lon]); return; }
  state.youMarker = L.marker([lat, lon], { draggable: true, icon: YOU_ICON })
    .addTo(state.leafletMap).bindTooltip('You', { direction: 'top', className: 'memora-tip' });
  state.youMarker.on('drag', updateLiveStatus);
  state.youMarker.on('dragend', updateLiveStatus);
}
async function onMapClick(ev) {
  const { lat, lng } = ev.latlng;
  state.homeSet = true;
  placeHomeMarker(lat, lng, state.currentZoneRadius);
  updateLiveStatus();
  try {
    await Api.setSafeZone(state.currentPatientId, { centerLat: lat, centerLon: lng, radiusMeters: state.currentZoneRadius });
    toast('Home location saved.');
  } catch (e) { toast(e.message); }
}
function updateRadiusPreview(val) {
  state.currentZoneRadius = parseInt(val, 10);
  $('radius-label').textContent = val;
  if (state.zoneCircle) state.zoneCircle.setRadius(state.currentZoneRadius);
  updateLiveStatus();
}
async function commitRadius(val) {
  if (!state.homeSet || !state.homeMarker) return;
  const { lat, lng } = state.homeMarker.getLatLng();
  try {
    await Api.setSafeZone(state.currentPatientId, { centerLat: lat, centerLon: lng, radiusMeters: parseInt(val, 10) });
  } catch (e) { toast(e.message); }
}
function updateLiveStatus() {
  if (!state.homeSet || !state.homeMarker || !state.youMarker) {
    $('map-status-banner').style.display = 'none';
    return;
  }
  const home = state.homeMarker.getLatLng();
  const you = state.youMarker.getLatLng();
  const dist = Math.round(haversineMeters(home.lat, home.lng, you.lat, you.lng));
  const inside = dist <= state.currentZoneRadius;
  const banner = $('map-status-banner');
  banner.style.display = 'block';
  banner.className = 'status-banner ' + (inside ? 'inside' : 'outside');
  banner.textContent = (inside ? 'Inside the safe zone' : 'Outside the safe zone') + ' — ' + dist + ' m from home (live estimate).';
}
function useMyRealGpsAsYou() {
  const info = $('geo-info');
  if (!navigator.geolocation) { info.textContent = 'Geolocation is not available in this browser.'; return; }
  info.textContent = 'Requesting your real location…';
  navigator.geolocation.getCurrentPosition(
    pos => {
      placeYouMarker(pos.coords.latitude, pos.coords.longitude);
      state.leafletMap.panTo([pos.coords.latitude, pos.coords.longitude]);
      info.textContent = 'Moved "You" to your real GPS location.';
      updateLiveStatus();
    },
    () => { info.textContent = 'Location permission was denied or unavailable here.'; }
  );
}
async function checkSafeZoneNow() {
  if (!state.homeSet) { toast('Set a home location on the map first.'); return; }
  const you = state.youMarker.getLatLng();
  try {
    const status = await apiSafeCheck({ lat: you.lat, lon: you.lng });
    showServerZoneResult(status);
  } catch (e) { toast(e.message); }
}
async function checkServerOwnGps() {
  if (!state.homeSet) { toast('Set a home location on the map first.'); return; }
  try {
    const status = await apiSafeCheck({});
    showServerZoneResult(status, true);
  } catch (e) { toast(e.message); }
}
function apiSafeCheck(coords) { return Api.checkSafeZone(state.currentPatientId, coords); }
function showServerZoneResult(status, fromServerGps) {
  const banner = $('map-status-banner');
  banner.style.display = 'block';
  banner.className = 'status-banner ' + (status.inside_safe_zone ? 'inside' : 'outside');
  const sourceNote = fromServerGps ? " (server's own GPS)" : ' (server-verified)';
  banner.textContent = (status.inside_safe_zone ? 'Inside the safe zone' : 'Outside the safe zone') +
    sourceNote + ' — ' + status.distance_meters + ' m from home.';
  speak(status.inside_safe_zone ? 'You are inside the safe zone.' : 'Warning. You are outside the safe zone.', false);
}

/* ---- background safe-zone monitor (top-bar pill) ---- */
let lastZoneInside = null;
async function refreshZonePill() {
  const pill = $('zone-pill'), text = $('zone-pill-text');
  if (!state.currentPatientId) return;

  let zone = null;
  try { zone = await Api.getSafeZone(state.currentPatientId); } catch (e) { return; }

  if (!zone) { pill.className = 'zone-pill'; text.textContent = 'No safe zone yet'; return; }

  if (state.dashTab === 'map' && state.youMarker) {
    const you = state.youMarker.getLatLng();
    const dist = Math.round(haversineMeters(zone.center_lat, zone.center_lon, you.lat, you.lng));
    const inside = dist <= zone.radius_meters;
    pill.className = 'zone-pill ' + (inside ? 'inside' : 'outside');
    text.textContent = (inside ? 'In safe zone' : 'Outside safe zone') + ' · ' + dist + 'm';
    if (lastZoneInside !== null && lastZoneInside !== inside) {
      speak(inside ? 'You are back inside the safe zone.' : 'Warning. You have left the safe zone.', false);
    }
    lastZoneInside = inside;
  } else {
    pill.className = 'zone-pill';
    text.textContent = 'Safe zone set — open Map tab to monitor live';
  }
}

/* ---- AI assistant tab (REAL local Ollama model via the Flask backend) ---- */
function renderChatIfEmpty() {
  if (state.chatHistory.length) return;
  addChatMsg('bot', "I'm ready — ask me about today's schedule, your family, or your safe zone.");
}
function addChatMsg(who, text) {
  state.chatHistory.push({ who, text });
  const log = $('chat-log');
  const div = document.createElement('div');
  div.className = 'msg ' + who;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}
async function sendChat() {
  const input = $('chat-input');
  const text = input.value.trim();
  if (!text) return;
  addChatMsg('user', text);
  input.value = '';

  addChatMsg('bot', '…');
  const placeholder = $('chat-log').lastElementChild;

  try {
    const result = await Api.askAssistant(state.currentPatientId, text);
    placeholder.textContent = result.reply;
    state.chatHistory[state.chatHistory.length - 1].text = result.reply;
    speak(result.reply);
  } catch (e) {
    placeholder.textContent = e.message;
  }
}
function voiceChat() {
  const btn = $('chat-mic');
  btn.classList.add('listening');
  startSpeechRecognition(text => {
    btn.classList.remove('listening');
    $('chat-input').value = text;
    sendChat();
  }, () => btn.classList.remove('listening'));
}
function startSpeechRecognition(onResult, onFail) {
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Rec) { toast('Voice input is not available in this browser — please type instead.'); if (onFail) onFail(); return; }
  try {
    const rec = new Rec();
    rec.lang = 'en-US';
    rec.onresult = e => onResult(e.results[0][0].transcript);
    rec.onerror = () => { toast('Could not hear that — please type instead.'); if (onFail) onFail(); };
    rec.onend = () => { if (onFail) onFail(); };
    rec.start();
  } catch (e) { toast('Voice input is not available here — please type instead.'); if (onFail) onFail(); }
}

/* ---- my data tab ---- */
async function renderMyData() {
  let data;
  try { data = await Api.getPatient(state.currentPatientId); } catch (e) { toast(e.message); return; }
  const p = data.profile;

  $('mydata-profile').innerHTML =
    '<dt>Name</dt><dd>' + escapeHtml(p.firstName + ' ' + p.lastName) + '</dd>' +
    '<dt>Date of birth</dt><dd>' + escapeHtml(p.dob) + ' (age ' + p.age + ')</dd>' +
    '<dt>National ID</dt><dd>' + escapeHtml(p.nationalId) + '</dd>';

  const ul = $('mydata-family'); ul.innerHTML = '';
  data.family.forEach(m => {
    const li = document.createElement('li');
    li.className = 'family-item';
    li.innerHTML = familyAvatarHtml(state.currentPatientId, m) +
      '<div><div class="fi-name">' + escapeHtml(m.name) + '</div><div class="fi-rel">' + escapeHtml(m.relationship) +
      (m.age != null ? ' · ' + escapeHtml(String(m.age)) : '') + '</div>' +
      (m.notes ? '<div class="fi-rel" style="opacity:.75;">' + escapeHtml(m.notes) + '</div>' : '') + '</div>';
    ul.appendChild(li);
  });
  $('mydata-family-empty').style.display = data.family.length ? 'none' : 'block';

  $('mydata-facts').innerHTML = Object.keys(data.facts).length
    ? Object.entries(data.facts).map(([k, v]) => '<p><strong>' + escapeHtml(k) + ':</strong> ' + escapeHtml(v) + '</p>').join('')
    : '<p class="empty-note">No facts/schedule stored yet.</p>';
  $('mydata-facts').innerHTML += '<button class="btn btn-ghost btn-sm" style="margin-top:8px;" onclick="editScheduleNow()">Update today\'s schedule</button>';

  $('mydata-zone').innerHTML = data.safeZone
    ? ('<p>Center: (' + data.safeZone.center_lat.toFixed(5) + ', ' + data.safeZone.center_lon.toFixed(5) + ') — radius ' + data.safeZone.radius_meters + ' m.</p>')
    : '<p class="empty-note">Not set up yet.</p>';
}

/* ---------------- caregiver / admin (static account, checked by the server) ---------------- */
async function handleCaregiverLogin() {
  const username = $('cg-username').value.trim();
  const password = $('cg-password').value;
  try {
    await Api.caregiverLogin(username, password);
    $('cg-login-error').textContent = '';
    enterCaregiverDashboard();
  } catch (e) {
    $('cg-login-error').textContent = e.message;
  }
}
function enterCaregiverDashboard() {
  showScreen('screen-caregiver-dashboard');
  renderCaregiverTable();
}
async function renderCaregiverTable() {
  let patients = [];
  try { patients = await Api.listPatients(); } catch (e) { toast(e.message); }

  $('cg-total-line').textContent = patients.length + ' patient(s) on this device';
  const tbody = $('cg-patient-table');
  tbody.innerHTML = '';

  patients.forEach(p => {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>' + escapeHtml(p.firstName + ' ' + p.lastName) + '</td>' +
      '<td>' + escapeHtml(p.nationalId) + '</td>' +
      '<td>' + p.familyCount + '</td>' +
      '<td></td>';
    const actionsTd = tr.lastElementChild;

    const viewBtn = document.createElement('button');
    viewBtn.className = 'btn btn-ghost btn-sm'; viewBtn.textContent = 'View';
    viewBtn.onclick = () => openPatientDetail(p.id);

    const addFamBtn = document.createElement('button');
    addFamBtn.className = 'btn btn-ghost btn-sm'; addFamBtn.style.marginLeft = '6px';
    addFamBtn.textContent = '+ Family';
    addFamBtn.onclick = () => openFamilyModal(p.id);

    const zoneBtn = document.createElement('button');
    zoneBtn.className = 'btn btn-ghost btn-sm'; zoneBtn.style.marginLeft = '6px';
    zoneBtn.textContent = 'Safe zone';
    zoneBtn.onclick = () => {
      state.currentPatientId = p.id;
      showScreen('screen-dashboard');
      $('dash-name').textContent = p.firstName + ' ' + p.lastName;
      switchDashTab('map');
      toast("Editing " + p.firstName + "'s safe zone — log out to return to admin.");
    };

    actionsTd.appendChild(viewBtn); actionsTd.appendChild(addFamBtn); actionsTd.appendChild(zoneBtn);
    tbody.appendChild(tr);
  });
  $('cg-patient-empty').style.display = patients.length ? 'none' : 'block';
}
function openPatientAdminSignup() {
  $('asu-first').value = ''; $('asu-last').value = ''; $('asu-dob').value = ''; $('asu-nid').value = '';
  $('asu-error').textContent = '';
  openModalEl('modal-admin-signup');
}
async function adminCreatePatient() {
  const firstName = $('asu-first').value.trim(), lastName = $('asu-last').value.trim();
  const dob = $('asu-dob').value, nationalId = $('asu-nid').value.trim();
  if (!firstName || !lastName || !dob || !nationalId) { $('asu-error').textContent = 'Please fill in every field.'; return; }
  try {
    await Api.signup({ firstName, lastName, dob, nationalId });
    closeModal('modal-admin-signup');
    renderCaregiverTable();
    toast('Patient account created.');
  } catch (e) { $('asu-error').textContent = e.message; }
}
async function openPatientDetail(patientId) {
  let data;
  try { data = await Api.getPatient(patientId); } catch (e) { toast(e.message); return; }
  const p = data.profile;

  $('patient-detail-body').innerHTML =
    '<dl class="kv-list">' +
    '<dt>Name</dt><dd>' + escapeHtml(p.firstName + ' ' + p.lastName) + '</dd>' +
    '<dt>Date of birth</dt><dd>' + escapeHtml(p.dob) + ' (age ' + p.age + ')</dd>' +
    '<dt>National ID</dt><dd>' + escapeHtml(p.nationalId) + '</dd>' +
    '</dl>' +
    '<h3 style="margin-top:16px;">Family (' + data.family.length + ')</h3>' +
    (data.family.length ? ('<ul>' + data.family.map(f => '<li>' + escapeHtml(f.name) + ' — ' + escapeHtml(f.relationship) + (f.age != null ? ' (' + escapeHtml(String(f.age)) + ')' : '') + '</li>').join('') + '</ul>') : '<p class="empty-note">None yet.</p>') +
    '<h3 style="margin-top:16px;">Schedule / facts</h3>' +
    (Object.keys(data.facts).length ? Object.entries(data.facts).map(([k, v]) => '<p><strong>' + escapeHtml(k) + ':</strong> ' + escapeHtml(v) + '</p>').join('') : '<p class="empty-note">None yet.</p>') +
    '<h3 style="margin-top:16px;">Safe zone</h3>' +
    (data.safeZone ? ('<p>Center: (' + data.safeZone.center_lat.toFixed(5) + ', ' + data.safeZone.center_lon.toFixed(5) + ') — radius ' + data.safeZone.radius_meters + ' m.</p>') : '<p class="empty-note">Not set up yet.</p>');

  $('patient-delete-btn').onclick = () => confirmDeletePatient(patientId, p.firstName + ' ' + p.lastName);
  openModalEl('modal-patient-detail');
}
async function confirmDeletePatient(patientId, name) {
  const typed = prompt('Type DELETE to permanently remove ' + name + "'s account and all their data:");
  if (typed === 'DELETE') {
    try {
      await Api.deletePatient(patientId);
      closeModal('modal-patient-detail');
      renderCaregiverTable();
      toast(name + "'s account was deleted.");
    } catch (e) { toast(e.message); }
  }
}

/* boot */
showScreen('screen-role');
apiFetch('/patients').catch(() => {}); // early connectivity check, shows the red banner if the server is down

/* scroll-reveal animation for the landing page */
(function () {
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('in'); });
  }, { threshold: 0.15 });
  document.querySelectorAll('.reveal').forEach(el => io.observe(el));
})();

/* landing-page nav: the underline follows the link you click and the section you scroll to */
(function () {
  const links = Array.from(document.querySelectorAll('.landing-links a[data-spy]'));
  if (!links.length) return;

  const order = ['top', 'features', 'strip', 'role-pick'];          // top -> bottom on the page
  let lastRoleLink = links.find(l => l.dataset.spy === 'role-pick'); // "How It Works" and "Contact" share this section
  let pinned = null;                                                 // link the visitor just clicked; stays underlined until they scroll away themselves

  function setActive(link) {
    links.forEach(l => l.classList.toggle('active', l === link));
  }
  function linkFor(sectionId) {
    if (sectionId === 'role-pick') return lastRoleLink;
    return links.find(l => l.dataset.spy === sectionId);
  }
  function currentSection() {
    const doc = document.documentElement;
    if (window.innerHeight + window.scrollY >= doc.scrollHeight - 4) return 'role-pick'; // very bottom of the page
    const probe = 140; // px below the top of the viewport (clears the sticky nav)
    let current = order[0];
    order.forEach(id => {
      const el = document.getElementById(id);
      if (el && el.getBoundingClientRect().top <= probe) current = id;
    });
    return current;
  }
  function targetVisible(link) {
    const el = document.getElementById(link.dataset.spy);
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.bottom > 80 && r.top < window.innerHeight - 80;
  }
  function update() {
    if (!document.getElementById('screen-role').classList.contains('active')) return;
    // The last sections are short, so the page can't always scroll them to the very top.
    // Keep the clicked link underlined while its section is on screen.
    if (pinned) { setActive(pinned); return; }
    const link = linkFor(currentSection());
    if (link) setActive(link);
  }

  links.forEach(l => l.addEventListener('click', () => {
    if (l.dataset.spy === 'role-pick') lastRoleLink = l;
    pinned = l;
    setActive(l);
  }));
  // as soon as the visitor scrolls by themselves, go back to following the page
  ['wheel', 'touchstart', 'keydown'].forEach(ev => window.addEventListener(ev, () => { pinned = null; }, { passive: true }));

  let ticking = false, idleTimer = null;
  window.addEventListener('scroll', () => {
    // once scrolling has stopped, drop the pin if its section is no longer on screen (e.g. scrollbar drag)
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      if (pinned && !targetVisible(pinned)) { pinned = null; update(); }
    }, 250);
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => { ticking = false; update(); });
  }, { passive: true });
  window.addEventListener('resize', update);
  update();
})();
