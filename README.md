# DeepSeek Poker 服务端

> 本项目完全由Codex完成，除了这句话之外没有任何人工编辑 :)

FastAPI 驱动的德州扑克后端，允许房主创建房间、指定席位数与 DeepSeek AI 人数，随后不同设备的玩家通过浏览器就能加入同桌，对局过程中 AI 会自动向 DeepSeek 查询策略。房间的全部状态保持在内存中，适合局域网或快速演示场景。

> ⚠️ 仅为演示用途：没有持久化，不支持边注，安全控制也很基础。若要上生产，请自行补充数据库、鉴权和更完备的规则处理。

## 快速上手

1. 安装依赖

   ```bash
   pip install -r requirements.txt
   ```

2. 配置 DeepSeek API
   - 推荐：导出环境变量 `DEEPSEEK_API_KEY`。
   - 或者：把密钥写在仓库根目录的 `APIKEY` 文件（单行字符串），`app/config.py` 会自动读取。
   - 可选环境变量：`DEEPSEEK_MODEL`、`DEEPSEEK_API_URL`、`DEFAULT_STACK`、`DEFAULT_SMALL_BLIND`、`DEFAULT_BIG_BLIND`、`MAX_ROOMS`。

3. 启动服务

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

   服务器监听 0.0.0.0 并默认开启 CORS，局域网设备可直接访问。成功启动后，在任意浏览器中打开 `http://<服务器IP>:8000/` 即可加载内置的前端界面。

## 浏览器界面

- 前端静态文件位于 `web/`，FastAPI 自动把 `/` 映射到 `index.html`，`/assets/*` 提供 JS/CSS，无需额外构建。
- 页面包含“创建房间”、“加入房间”、房间列表和实时牌桌视图，`player_id` 与 `player_secret` 会保存到 `localStorage`，刷新后可自动恢复身份。
- 动作区动态展示服务器返回的合法操作（`state.self.legal_actions`），若需要下注或加注，请输入 **行动后桌面上的总注额（raise to）**。
- 前端每 2.5 秒轮询一次 `/rooms/{room_id}`，实时刷新公共牌、奖池、行动记录和玩家筹码；AI 行动全部在服务器自动完成。

## API 流程（REST 接口说明）

1. **创建房间**

   ```
   POST /rooms
   {
     "host_name": "Alice",
     "total_seats": 6,
     "ai_players": 2,
     "starting_stack": 2000,
     "small_blind": 10,
     "big_blind": 20
   }
   ```

   返回 `room_id`、房主 `player_id` 与 `player_secret` 以及初始房间状态。后续提交动作需要带上这两个凭证。

2. **加入房间**

   ```
   POST /rooms/{room_id}/join
   {
     "player_name": "Bob"
   }
   ```

   返回新玩家的 `player_id`/`player_secret` 和当前状态快照。

3. **房主开始牌局**

   ```
   POST /rooms/{room_id}/start
   {
     "player_id": "<host-id>",
     "player_secret": "<host-secret>"
   }
   ```

   服务器会补齐 AI 玩家、发牌并自动执行 AI 的回合。

4. **查询房间状态**

   ```
   GET /rooms/{room_id}?player_id=<id>&player_secret=<secret>
   ```

   - `players`：所有座位信息，非本人只展示手牌张数；摊牌后公开全部手牌。
   - `state.self`：仅自己的合法动作、待跟注金额和筹码。
   - `community_cards`、`pot`、`actions`、`winners`：公共信息。

   若不带玩家参数，则返回公共视图。

5. **提交行动**

   ```
   POST /rooms/{room_id}/action
   {
     "player_id": "...",
     "player_secret": "...",
     "action": "raise",
     "amount": 2400
   }
   ```

   - 支持 `fold/check/call/bet/raise`。
   - `bet`、`raise` 的 `amount` 表示行动完成后你面前总共放入的筹码（即 “raise to”），服务端会自动计算实际需要补的筹码数。
   - 人类动作提交后，服务端立即驱动 AI 连续行动直至轮到下一位真人或手牌结束。

6. **查看房间列表**

   ```
   GET /rooms
   ```

   用于展示大厅或调试。

## DeepSeek AI 交互

`app/ai.py` 会为每个 AI 构造提示词，内容包括：

- 自己的两张底牌、公共牌、当前奖池、筹码、待跟注金额、最小加注额；
- 最近 12 条行动历史（玩家、动作、阶段）；
- 当前可执行的动作列表。

DeepSeek 必须返回一个 JSON 字符串，例如 `{"action":"call","amount":0,"explanation":"..."}`。若调用失败或建议非法动作，服务器会退回保守策略（优先过牌，其次跟注，再次弃牌）。

## 代码结构

- `app/main.py`：FastAPI 路由、静态资源挂载、CORS 配置。
- `app/rooms.py`：房间生命周期管理、玩家凭证校验、AI 自动行动循环。
- `app/poker.py`：牌堆、手牌评估、下注流程（单奖池简化版）。
- `app/ai.py`：DeepSeek API 客户端与 fallback 逻辑。
- `app/schemas.py`：Pydantic 请求体。
- `web/`：无需构建的前端页面与脚本。

## 已知限制

- 只实现单奖池，不支持边注；多人全下且筹码不同时时结果可能不符合正式规则。
- 服务器重启即清空所有房间与玩家。
- 玩家凭证仅存于本地浏览器和内存，没有完善的鉴权或断线恢复机制。
- 没有复杂的房间权限或踢人逻辑，安全性请自行把控。

基于此仓库你可以直接跑起来与好友/DeepSeek 对战，或继续扩展 UI、数据库、健壮性等能力。
