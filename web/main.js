const state = {
  session: loadSession(),
  roomState: null,
  lobby: [],
  pollTimer: null,
};

const dom = {
  status: document.getElementById("status-text"),
  sessionInfo: document.getElementById("session-info"),
  startHandBtn: document.getElementById("start-hand-btn"),
  refreshStateBtn: document.getElementById("refresh-state-btn"),
  leaveBtn: document.getElementById("leave-room-btn"),
  createForm: document.getElementById("create-room-form"),
  joinForm: document.getElementById("join-room-form"),
  refreshLobbyBtn: document.getElementById("refresh-lobby-btn"),
  roomsList: document.getElementById("rooms-list"),
  tableRoom: document.getElementById("table-room-id"),
  tablePhase: document.getElementById("table-phase"),
  tablePot: document.getElementById("table-pot"),
  community: document.getElementById("community-cards"),
  tableEvent: document.getElementById("table-event"),
  currentPlayer: document.getElementById("current-player"),
  selfInfo: document.getElementById("self-info"),
  actionButtons: document.getElementById("action-buttons"),
  betAmount: document.getElementById("bet-amount"),
  playersList: document.getElementById("players-list"),
  actionLog: document.getElementById("action-log"),
};

function init() {
  dom.createForm.addEventListener("submit", handleCreateRoom);
  dom.joinForm.addEventListener("submit", handleJoinRoom);
  dom.refreshLobbyBtn.addEventListener("click", refreshLobby);
  dom.startHandBtn.addEventListener("click", startHand);
  dom.refreshStateBtn.addEventListener("click", refreshState);
  dom.leaveBtn.addEventListener("click", () => {
    clearSession();
    stopPolling();
    setStatus("已清除本地凭证。", "info");
    render();
  });
  render();
  if (state.session) {
    startPolling();
  } else {
    refreshLobby();
  }
}

function loadSession() {
  const raw = localStorage.getItem("pokerSession");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveSession(session) {
  state.session = session;
  localStorage.setItem("pokerSession", JSON.stringify(session));
}

function clearSession() {
  state.session = null;
  state.roomState = null;
  localStorage.removeItem("pokerSession");
}

function setStatus(message, level = "info") {
  dom.status.textContent = message;
  dom.status.dataset.level = level;
}

function startPolling() {
  stopPolling();
  refreshState();
  state.pollTimer = setInterval(refreshState, 2500);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

async function handleCreateRoom(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    host_name: form.get("host_name"),
    total_seats: Number(form.get("total_seats")),
    ai_players: Number(form.get("ai_players")),
    starting_stack: Number(form.get("starting_stack")),
    small_blind: Number(form.get("small_blind")),
    big_blind: Number(form.get("big_blind")),
  };
  try {
    setStatus("正在创建房间...", "info");
    const res = await fetch("/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "创建失败");
    const data = await res.json();
    saveSession({
      roomId: data.room_id,
      playerId: data.player_id,
      secret: data.player_secret,
      playerName: payload.host_name,
      isHost: true,
    });
    state.roomState = data.state;
    setStatus(`房间 ${data.room_id} 创建完成。`, "success");
    startPolling();
    render();
  } catch (err) {
    console.error(err);
    setStatus(err.message || "创建房间失败", "error");
  }
}

async function handleJoinRoom(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const roomId = form.get("room_id")?.trim().toUpperCase();
  const playerName = form.get("player_name")?.trim();
  if (!roomId || !playerName) return;
  try {
    setStatus("正在加入房间...", "info");
    const res = await fetch(`/rooms/${roomId}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_name: playerName }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "加入失败");
    const data = await res.json();
    saveSession({
      roomId,
      playerId: data.player_id,
      secret: data.player_secret,
      playerName,
      isHost: false,
    });
    state.roomState = data.state;
    setStatus(`已加入房间 ${roomId}。`, "success");
    startPolling();
    render();
  } catch (err) {
    console.error(err);
    setStatus(err.message || "加入房间失败", "error");
  }
}

async function startHand() {
  if (!state.session) return;
  try {
    setStatus("正在开始新一手牌...", "info");
    const res = await fetch(`/rooms/${state.session.roomId}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_id: state.session.playerId,
        player_secret: state.session.secret,
      }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "无法开始牌局");
    const data = await res.json();
    state.roomState = data.state;
    setStatus("新一手牌已开始。", "success");
    render();
  } catch (err) {
    console.error(err);
    setStatus(err.message || "开始牌局失败", "error");
  }
}

async function refreshState() {
  if (!state.session) {
    dom.refreshStateBtn.disabled = true;
    return;
  }
  const { roomId, playerId, secret } = state.session;
  const params = new URLSearchParams({ player_id: playerId, player_secret: secret });
  try {
    const res = await fetch(`/rooms/${roomId}?${params.toString()}`);
    if (!res.ok) throw new Error((await res.json()).detail || "刷新失败");
    const data = await res.json();
    state.roomState = data.state;
    setStatus("状态已更新。", "success");
    render();
  } catch (err) {
    console.error(err);
    setStatus(err.message || "无法获取状态", "error");
  }
}

async function refreshLobby() {
  try {
    const res = await fetch("/rooms");
    if (!res.ok) throw new Error("无法读取房间列表");
    const data = await res.json();
    state.lobby = data.rooms || [];
    renderLobby();
  } catch (err) {
    console.error(err);
    setStatus(err.message || "获取房间列表失败", "error");
  }
}

async function sendAction(action) {
  if (!state.session) return;
  const needsAmount = action === "bet" || action === "raise";
  let amount = Number(dom.betAmount.value || 0);
  if (needsAmount && amount <= 0) {
    alert("请输入下注/加注后的总额。");
    return;
  }
  try {
    setStatus(`正在执行动作 ${action}...`, "info");
    const res = await fetch(`/rooms/${state.session.roomId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_id: state.session.playerId,
        player_secret: state.session.secret,
        action,
        amount,
      }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "动作失败");
    const data = await res.json();
    state.roomState = data.state;
    dom.betAmount.value = "";
    setStatus("动作已提交。", "success");
    render();
  } catch (err) {
    console.error(err);
    setStatus(err.message || "提交动作失败", "error");
  }
}

function render() {
  renderSessionInfo();
  renderState();
  renderLobby();
  dom.startHandBtn.disabled = !(state.session && state.session.isHost);
  dom.refreshStateBtn.disabled = !state.session;
  dom.leaveBtn.disabled = !state.session;
}

function renderSessionInfo() {
  if (!state.session) {
    dom.sessionInfo.innerHTML = "<p>尚未加入房间。</p>";
    return;
  }
  const { roomId, playerId, secret, playerName, isHost } = state.session;
  dom.sessionInfo.innerHTML = `
    <p><strong>玩家:</strong> ${playerName} ${isHost ? "(房主)" : ""}</p>
    <p><strong>房间:</strong> <code>${roomId}</code></p>
    <p><strong>Player ID:</strong> <code>${playerId}</code></p>
    <p><strong>Secret:</strong> <code>${secret}</code></p>
  `;
}

function renderState() {
  const st = state.roomState;
  if (!st) {
    dom.tableRoom.textContent = "-";
    dom.tablePhase.textContent = "-";
    dom.tablePot.textContent = "0";
    dom.community.textContent = "-";
    dom.tableEvent.textContent = "-";
    dom.currentPlayer.textContent = "-";
    dom.selfInfo.textContent = "无座位信息。";
    dom.actionButtons.innerHTML = "";
    dom.playersList.innerHTML = "<p>没有玩家数据。</p>";
    dom.actionLog.innerHTML = "";
    return;
  }
  dom.tableRoom.textContent = st.room_id;
  dom.tablePhase.textContent = st.phase;
  dom.tablePot.textContent = st.pot;
  dom.community.textContent = st.community_cards?.join(" ") || "-";
  dom.tableEvent.textContent = st.last_event || "-";
  dom.currentPlayer.textContent = st.current_player_id || "等待中";
  renderSelfPanel(st);
  renderPlayers(st.players || []);
  renderActions(st.actions || []);
}

function renderSelfPanel(st) {
  if (!state.session || !st.self) {
    dom.selfInfo.textContent = "请加入房间后查看自己的信息。";
    dom.actionButtons.innerHTML = "";
    return;
  }
  dom.selfInfo.innerHTML = `
    <p>剩余筹码：<strong>${st.self.stack}</strong></p>
    <p>待跟注：<strong>${st.self.to_call}</strong></p>
    <p>可执行动作：${(st.self.legal_actions || []).join(", ") || "-"}</p>
  `;
  dom.actionButtons.innerHTML = "";
  (st.self.legal_actions || []).forEach((action) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = action.toUpperCase();
    btn.addEventListener("click", () => sendAction(action));
    dom.actionButtons.appendChild(btn);
  });
}

function renderPlayers(players) {
  if (!players.length) {
    dom.playersList.innerHTML = "<p>等待玩家加入...</p>";
    return;
  }
  dom.playersList.innerHTML = "";
  players.forEach((player) => {
    const el = document.createElement("div");
    el.className = "player-card";
    el.innerHTML = `
      <div><strong>${player.name}</strong> ${player.is_ai ? "<span class='meta'>AI</span>" : ""}</div>
      <div class="chips">${player.stack} 芯片</div>
      <div class="meta">
        seat #${player.seat} · ${player.folded ? "已弃牌" : "在局中"}${player.all_in ? " · ALL-IN" : ""}${player.busted ? " · 出局" : ""}
      </div>
      <div class="meta">当前下注：${player.bet}</div>
      <div class="cards">${renderCards(player.cards)}</div>
    `;
    dom.playersList.appendChild(el);
  });
}

function renderCards(cards) {
  if (!cards) return "<span class='card'>?</span>";
  if (Array.isArray(cards)) {
    if (!cards.length) return "<span class='card'>无</span>";
    return cards.map((c) => `<span class="card">${c}</span>`).join("");
  }
  return `<span class="card">${cards} 张</span>`;
}

function renderActions(actions) {
  if (!actions.length) {
    dom.actionLog.innerHTML = "<p>暂无行动记录。</p>";
    return;
  }
  dom.actionLog.innerHTML = "";
  actions.slice(-40).forEach((entry) => {
    const el = document.createElement("div");
    el.className = "action-entry";
    el.textContent = `[${entry.phase}] ${entry.player_name}: ${entry.action} ${entry.amount || ""}`;
    dom.actionLog.appendChild(el);
  });
}

function renderLobby() {
  if (!state.lobby?.length) {
    dom.roomsList.innerHTML = "<p>无正在运行的房间。</p>";
    return;
  }
  dom.roomsList.innerHTML = "";
  state.lobby.forEach((room) => {
    const el = document.createElement("div");
    el.className = "room-row";
    el.innerHTML = `
      <div><strong>${room.room_id}</strong> · ${room.phase}</div>
      <div>席位：${room.humans}/${room.total_seats - room.ai_players} 人类 + ${room.ai_players} AI</div>
      <div>创建时间：${new Date(room.created_at).toLocaleString()}</div>
    `;
    dom.roomsList.appendChild(el);
  });
}

init();

