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
  tablePhase: document.getElementById("phase-label"),
  potValue: document.getElementById("pot-value"),
  community: document.getElementById("community-cards"),
  tableEvent: document.getElementById("table-event"),
  currentPlayer: document.getElementById("current-player"),
  currentBet: document.getElementById("current-bet"),
  heroName: document.getElementById("hero-name"),
  heroStack: document.getElementById("hero-stack"),
  heroCall: document.getElementById("hero-call"),
  heroCards: document.getElementById("hero-cards"),
  actionButtons: document.getElementById("action-buttons"),
  betAmount: document.getElementById("bet-amount"),
  playersGrid: document.getElementById("players-grid"),
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
    dom.potValue.textContent = "0";
    dom.currentBet.textContent = "0";
    dom.community.innerHTML = placeholderCards(5);
    dom.tableEvent.textContent = "等待加入房间...";
    dom.currentPlayer.textContent = "-";
    dom.heroName.textContent = "未入座";
    dom.heroStack.textContent = "-";
    dom.heroCall.textContent = "-";
    dom.heroCards.innerHTML = placeholderCards(2, { large: true });
    dom.actionButtons.innerHTML = "";
    dom.playersGrid.innerHTML = '<p class="muted-text">暂无玩家。</p>';
    dom.actionLog.innerHTML = '<p class="muted-text">暂无行动记录。</p>';
    return;
  }
  dom.tableRoom.textContent = st.room_id;
  dom.tablePhase.textContent = st.phase;
  dom.potValue.textContent = st.pot;
  dom.currentBet.textContent = st.current_bet ?? 0;
  dom.tableEvent.textContent = st.last_event || "等待玩家行动...";
  const turnPlayer =
    (st.players || []).find((player) => player.id === st.current_player_id) || null;
  dom.currentPlayer.textContent = turnPlayer ? turnPlayer.name : st.current_player_id || "等待中";
  renderBoard(st.community_cards || []);
  renderHeroPanel(st);
  renderPlayers(st.players || [], st.current_player_id);
  renderActions(st.actions || []);
}

function renderHeroPanel(st) {
  const hero =
    (st.players || []).find((p) => state.session && p.id === state.session.playerId) || null;
  if (!state.session || !st.self || !hero) {
    dom.heroName.textContent = "请加入房间";
    dom.heroStack.textContent = "-";
    dom.heroCall.textContent = "-";
    dom.heroCards.innerHTML = placeholderCards(2, { large: true });
    dom.actionButtons.innerHTML = "";
    dom.betAmount.disabled = true;
    return;
  }
  dom.heroName.textContent = `${hero.name}${hero.is_ai ? " (AI)" : ""}`;
  dom.heroStack.textContent = st.self.stack;
  dom.heroCall.textContent = st.self.to_call;
  dom.heroCards.innerHTML = renderCardList(hero.cards, { large: true, padTo: 2 });
  const myTurn = Boolean(st.current_player_id && st.current_player_id === hero.id);
  dom.betAmount.disabled = !myTurn;
  dom.actionButtons.innerHTML = "";
  (st.self.legal_actions || []).forEach((action) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = action.toUpperCase();
    btn.disabled = !myTurn;
    btn.addEventListener("click", () => sendAction(action));
    dom.actionButtons.appendChild(btn);
  });
}

function renderBoard(cards) {
  dom.community.innerHTML = renderCardList(cards, { padTo: 5 });
}

function renderPlayers(players, currentId) {
  if (!dom.playersGrid) return;
  if (!players.length) {
    dom.playersGrid.innerHTML = '<p class="muted-text">等待玩家加入...</p>';
    return;
  }
  const sorted = orderPlayers(players);
  dom.playersGrid.innerHTML = "";
  sorted.forEach((player, index) => {
    const tile = document.createElement("div");
    tile.className = "player-tile";
    if (player.id === currentId) tile.classList.add("current");
    if (player.folded || player.busted) tile.classList.add("folded");
    tile.dataset.order = index;
    const badges = [];
    if (state.roomState?.dealer_player_id === player.id) badges.push({ label: "D", cls: "dealer" });
    if (state.roomState?.small_blind_player_id === player.id) badges.push({ label: "SB", cls: "blind" });
    if (state.roomState?.big_blind_player_id === player.id) badges.push({ label: "BB", cls: "blind" });
    const badgeHtml = badges.length
      ? `<div class="badges">${badges
          .map((badge) => `<span class="badge ${badge.cls}">${badge.label}</span>`)
          .join("")}</div>`
      : "";
    tile.innerHTML = `
      <header>
        <span>${player.name}${player.is_ai ? " (AI)" : ""}</span>
        <span class="stack">${player.stack}</span>
      </header>
      ${badgeHtml}
      <div class="meta">
        seat #${player.seat} · ${player.folded ? "已弃牌" : player.busted ? "出局" : player.all_in ? "ALL-IN" : "在局中"}
      </div>
      <div class="bet-chip">当前下注：${player.bet}</div>
      <div class="cards">${renderCardList(player.cards, { padTo: 2 })}</div>
    `;
    dom.playersGrid.appendChild(tile);
  });
}

function orderPlayers(players) {
  if (!Array.isArray(players)) return [];
  const dealerId = state.roomState?.dealer_player_id;
  if (!dealerId) {
    return [...players].sort((a, b) => a.seat - b.seat);
  }
  const seatOrder = [...players].sort((a, b) => a.seat - b.seat);
  const dealerIndex = seatOrder.findIndex((player) => player.id === dealerId);
  if (dealerIndex === -1) return seatOrder;
  const ordered = [];
  for (let offset = 1; offset <= seatOrder.length; offset += 1) {
    ordered.push(seatOrder[(dealerIndex + offset) % seatOrder.length]);
  }
  return ordered;
}

function renderActions(actions) {
  if (!actions.length) {
    dom.actionLog.innerHTML = '<p class="muted-text">暂无行动记录。</p>';
    return;
  }
  dom.actionLog.innerHTML = "";
  actions.slice(-40).forEach((entry) => {
    const el = document.createElement("div");
    el.className = "action-entry";
    el.innerHTML = `<strong>${entry.player_name}</strong> @ ${entry.phase} → ${entry.action.toUpperCase()} ${entry.amount || ""}`;
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

const SUIT_SYMBOL = { S: "♠", H: "♥", D: "♦", C: "♣" };
const RANK_MAP = { T: "10" };

function renderCardList(data, options = {}) {
  const { padTo = 0, large = false } = options;
  let count = 0;
  let markup = "";
  if (Array.isArray(data)) {
    count = data.length;
    markup = data
      .map((label) => createCard(label, { large }))
      .join("");
  } else if (typeof data === "number") {
    count = data;
    markup = placeholderCards(data, { large });
  } else if (typeof data === "string" && data) {
    count = 1;
    markup = createCard(data, { large });
  }
  const diff = Math.max(0, padTo - count);
  if (diff > 0) {
    markup += placeholderCards(diff, { large });
  }
  if (!markup) {
    markup = placeholderCards(padTo || 1, { large });
  }
  return markup;
}

function placeholderCards(count, { large = false } = {}) {
  return Array.from({ length: count }, () => createCard(null, { hidden: true, large })).join("");
}

function createCard(label, { hidden = false, large = false } = {}) {
  let rank = "";
  let suit = "";
  if (!label) hidden = true;
  if (!hidden) {
    rank = label.slice(0, -1).toUpperCase();
    suit = label.slice(-1).toUpperCase();
    if (!rank) {
      hidden = true;
    }
  }
  const classes = ["poker-card"];
  if (large) classes.push("large");
  if (hidden) {
    classes.push("back");
    return `<div class="${classes.join(" ")}"></div>`;
  }
  if (suit === "H" || suit === "D") classes.push("red");
  const suitSymbol = SUIT_SYMBOL[suit] || "•";
  const rankSymbol = RANK_MAP[rank] || rank;
  return `<div class="${classes.join(" ")}"><div class="rank">${rankSymbol}</div><div class="suit">${suitSymbol}</div></div>`;
}

init();
