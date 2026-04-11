#!/usr/bin/env python3
"""
Generate animated GIF demo of cheetahclaws WeChat Bridge.
Shows: auto-start → QR login → incoming Chinese message → tool call →
       response → slash command passthrough → /stop from WeChat
"""
from PIL import Image, ImageDraw, ImageFont
import os

# ── Catppuccin Mocha palette ─────────────────────────────────────────────
BG      = (30,  30,  46)
SURFACE = (49,  50,  68)
TEXT    = (205, 214, 244)
SUBTEXT = (108, 112, 134)
CYAN    = (137, 220, 235)
GREEN   = (166, 227, 161)
YELLOW  = (249, 226, 175)
RED     = (243, 139, 168)
MAUVE   = (203, 166, 247)
BLUE    = (137, 180, 250)
WX_GREEN = (7, 193, 96)     # WeChat brand green

W, H = 960, 720
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
FONT_SIZE = 14
LINE_H    = 20
PAD_X     = 18
PAD_Y     = 16

# Phone panel dimensions
PHONE_X  = 560
PHONE_W  = 380
PHONE_H  = 560
PHONE_Y  = 80
PHONE_R  = 24

def make_font(size=FONT_SIZE, bold=False):
    path = FONT_BOLD if bold else FONT_PATH
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

FONT    = make_font()
FONT_B  = make_font(bold=True)
FONT_SM = make_font(FONT_SIZE - 2)

def seg(t, c=TEXT, b=False):
    return (t, c, b)

def render_line(draw, y, segments, x_start=PAD_X):
    x = x_start
    for text, color, bold in segments:
        font = FONT_B if bold else FONT
        draw.text((x, y), text, font=font, fill=color)
        x += font.getlength(text)
    return y + LINE_H


# ── Phone UI helpers (WeChat style) ─────────────────────────────────────

def draw_phone(img, chat_messages):
    d = ImageDraw.Draw(img)

    px, py, pw, ph = PHONE_X, PHONE_Y, PHONE_W, PHONE_H
    phone_bg    = (237, 237, 237)   # WeChat light grey bg
    header_bg   = (235, 235, 235)   # WeChat grey header
    bubble_user = WX_GREEN          # green bubbles (user)
    bubble_bot  = (255, 255, 255)   # white bubbles (bot)
    title_color = (30, 30, 30)

    # Phone background
    d.rounded_rectangle([px, py, px+pw, py+ph], radius=PHONE_R, fill=phone_bg)

    # Header bar
    header_h = 52
    d.rounded_rectangle([px, py, px+pw, py+header_h], radius=PHONE_R, fill=header_bg)
    d.rectangle([px, py+PHONE_R, px+pw, py+header_h], fill=header_bg)

    # Bot avatar — WeChat green circle
    av_x, av_y, av_r = px + 16, py + 12, 14
    d.ellipse([av_x, av_y, av_x+av_r*2, av_y+av_r*2], fill=WX_GREEN)
    d.text((av_x + 4, av_y + 2), "🤖", font=FONT_SM, fill=(255, 255, 255))

    # Contact name
    d.text((px + 52, py + 10), "CheetahClaws Bot", font=FONT_B, fill=title_color)
    d.text((px + 52, py + 30), "WeixinClawBot", font=FONT_SM, fill=(120, 120, 120))

    # Thin separator under header
    d.line([(px, py + header_h), (px + pw, py + header_h)], fill=(210, 210, 210), width=1)

    # Messages area
    msg_y   = py + header_h + 10
    max_msg_y = py + ph - 50

    for sender, text, _color in chat_messages:
        is_user = (sender == "user")
        bubble_color = bubble_user if is_user else bubble_bot
        text_color   = (255, 255, 255) if is_user else (30, 30, 30)

        # Word-wrap (handle CJK: each char ~ 1 "word")
        chars_per_line = 22
        lines_wrapped = []
        cur = ""
        for ch in text:
            if len(cur) >= chars_per_line:
                lines_wrapped.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines_wrapped.append(cur)

        bubble_h = len(lines_wrapped) * 18 + 12
        bubble_w = max(FONT.getlength(l) for l in lines_wrapped) + 20
        bubble_w = max(bubble_w, 40)

        if is_user:
            bx = px + pw - bubble_w - 10
        else:
            bx = px + 10

        if msg_y + bubble_h > max_msg_y:
            break

        d.rounded_rectangle([bx, msg_y, bx+bubble_w, msg_y+bubble_h], radius=8, fill=bubble_color)
        # Tail triangle
        if is_user:
            d.polygon([(bx+bubble_w, msg_y+8), (bx+bubble_w+6, msg_y+14), (bx+bubble_w, msg_y+20)], fill=bubble_color)
        else:
            d.polygon([(bx, msg_y+8), (bx-6, msg_y+14), (bx, msg_y+20)], fill=bubble_color)

        for li, ln in enumerate(lines_wrapped):
            d.text((bx+10, msg_y+6+li*18), ln, font=FONT_SM, fill=text_color)

        msg_y += bubble_h + 8

    # Input bar
    input_y = py + ph - 44
    d.rectangle([px, input_y - 1, px + pw, input_y], fill=(210, 210, 210))
    d.rounded_rectangle([px+8, input_y+4, px+pw-50, py+ph-8], radius=16, fill=(255, 255, 255))
    d.text((px + 22, input_y + 12), "发送消息", font=FONT_SM, fill=(160, 160, 160))
    # Send button
    d.ellipse([px+pw-44, input_y+2, px+pw-10, py+ph-10], fill=WX_GREEN)
    d.text((px+pw-34, input_y+10), "+", font=FONT_B, fill=(255, 255, 255))

    # Divider
    d.line([(PHONE_X - 14, PHONE_Y), (PHONE_X - 14, PHONE_Y + PHONE_H)], fill=SURFACE, width=1)


# ── Terminal helpers ─────────────────────────────────────────────────────

def draw_frame(lines_segments, chat_messages=None):
    img = Image.new("RGB", (W, H), BG)
    d   = ImageDraw.Draw(img)
    y   = PAD_Y
    for item in lines_segments:
        if item is None:
            y += LINE_H
        elif isinstance(item, list):
            y = render_line(d, y, item)
        else:
            y = render_line(d, y, [item])
    if chat_messages is not None:
        draw_phone(img, chat_messages)
    return img


WX_COLOR = (100, 220, 120)   # terminal WeChat green accent

BANNER_WX = [
    [seg("╭─ CheetahClaws ─────────────────────────────────────────╮", SUBTEXT)],
    [seg("│  ", SUBTEXT), seg("Model: ", SUBTEXT), seg("claude-opus-4-6", CYAN, True)],
    [seg("│  ", SUBTEXT), seg("Permissions: ", SUBTEXT), seg("auto", YELLOW, True),
     seg("  flags: [", SUBTEXT), seg("wechat", WX_COLOR, True), seg("]", SUBTEXT)],
    [seg("│  Type /help for commands, Ctrl+C to cancel                 │", SUBTEXT)],
    [seg("╰────────────────────────────────────────────────────────────╯", SUBTEXT)],
    None,
]

def prompt_line(text="", cursor=False):
    cur = "█" if cursor else ""
    return [seg("[cheetahclaws] ", SUBTEXT), seg("» ", CYAN, True), seg(text + cur, TEXT)]

def ok_line(t):
    return [seg("  ✓ ", GREEN, True), seg(t, TEXT)]

def info_line(t):
    return [seg("  ℹ ", CYAN), seg(t, SUBTEXT)]

def warn_line(t):
    return [seg("  ⚠ ", YELLOW), seg(t, SUBTEXT)]

def claude_header():
    return [seg("╭─ Claude ", SUBTEXT), seg("●", GREEN), seg(" ─────────────────────────────────────────────", SUBTEXT)]

def claude_sep():
    return [seg("╰──────────────────────────────────────────────────────────", SUBTEXT)]

def tool_line(icon, name, arg, color=CYAN):
    return [seg(f"  {icon}  ", SUBTEXT), seg(name, color),
            seg("(", SUBTEXT), seg(arg, TEXT), seg(")", SUBTEXT)]

def tool_ok(msg):
    return [seg("  ✓ ", GREEN), seg(msg, SUBTEXT)]

def text_line(t, indent=2):
    return [seg(" " * indent + t, TEXT)]

def wx_incoming(text):
    return [seg("  📩 WeChat ", WX_COLOR, True), seg("[o9cq80_Q]: ", SUBTEXT), seg(text, TEXT)]

def wx_sent(preview):
    return [seg("  ✈  ", WX_COLOR), seg("Response sent → ", SUBTEXT), seg(preview, SUBTEXT)]

SPINNER = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]


# ── Scene builder ─────────────────────────────────────────────────────────

def build_scenes():
    scenes = []

    def add(lines, ms=120, chat=None):
        scenes.append((lines, ms, chat))

    # ── 0: Banner — wechat flag, auto-start ──────────────────────────────
    add(BANNER_WX + [
        ok_line("WeChat bridge started."),
        info_line("Send a message from WeChat — it will be processed here."),
        info_line("Stop with /wechat stop or send /stop from WeChat."),
        None,
        prompt_line(cursor=True),
    ], 1200, chat=[])

    # ── 1: /wechat status ────────────────────────────────────────────────
    base = BANNER_WX + [
        ok_line("WeChat bridge started."),
        info_line("Send a message from WeChat — it will be processed here."),
        info_line("Stop with /wechat stop or send /stop from WeChat."),
        None,
    ]
    cmd_status = "/wechat status"
    for i in range(0, len(cmd_status) + 1, 3):
        add(base + [prompt_line(cmd_status[:i], cursor=(i < len(cmd_status)))], 60, chat=[])
    add(base + [prompt_line(cmd_status)], 300, chat=[])

    add(base + [
        prompt_line(cmd_status),
        None,
        ok_line("WeChat bridge is running.  Account: 3cdf6fb6d104@im.bot"),
        None,
        prompt_line(cursor=True),
    ], 1000, chat=[])

    # Phone shows bot ready
    phone_init = [
        ("bot", "CheetahClaws 已就绪，请发送消息。", WX_COLOR),
    ]
    add(base + [prompt_line(cursor=True)], 800, chat=phone_init)

    # ── 2: First message — Chinese greeting ──────────────────────────────
    phone_q1 = phone_init + [("user", "你好！帮我列出项目里的文件", (7, 193, 96))]

    add(base + [
        prompt_line(cursor=True),
        None,
        wx_incoming("你好！帮我列出项目里的文件"),
    ], 900, chat=phone_q1)

    # ── 3: Typing indicator + model ──────────────────────────────────────
    wx_base = base + [
        prompt_line(cursor=False),
        None,
        wx_incoming("你好！帮我列出项目里的文件"),
        None,
    ]

    for si in range(6):
        spin = SPINNER[si % len(SPINNER)]
        add(wx_base + [
            [seg(f"  {spin} ", WX_COLOR), seg("sending typing indicator...", SUBTEXT)],
        ], 200, chat=phone_q1)

    add(wx_base + [
        [seg("  ✓ ", GREEN), seg("typing indicator sent", SUBTEXT)],
        None,
        claude_header(),
        tool_line("⚙", "Glob", "**/*", CYAN),
    ], 500, chat=phone_q1)

    add(wx_base + [
        [seg("  ✓ ", GREEN), seg("typing indicator sent", SUBTEXT)],
        None,
        claude_header(),
        tool_line("⚙", "Glob", "**/*", CYAN),
        tool_ok("12 files matched"),
    ], 600, chat=phone_q1)

    resp1_lines = [
        "你好！以下是项目中的文件：",
        "",
        "  cheetahclaws.py   — 主入口 REPL + 斜杠命令",
        "  agent.py          — 核心 Agent 循环",
        "  tools.py          — 内置工具 (Read/Write/Edit/Bash…)",
        "  providers.py      — API 提供商抽象层",
        "  config.py         — 配置管理",
        "  context.py        — 系统提示构建",
        "  memory/           — 持久化记忆系统",
    ]

    tool_done = wx_base + [
        [seg("  ✓ ", GREEN), seg("typing indicator sent", SUBTEXT)],
        None,
        claude_header(),
        tool_line("⚙", "Glob", "**/*", CYAN),
        tool_ok("12 files matched"),
        None,
        [seg("│ ", SUBTEXT)],
    ]

    streamed = []
    for i, line in enumerate(resp1_lines):
        streamed.append(text_line(line, 2) if line else None)
        add(tool_done + [x for x in streamed if x is not None], 55, chat=phone_q1)

    add(tool_done + [text_line(l, 2) if l else None for l in resp1_lines] + [claude_sep()], 500, chat=phone_q1)

    # ── 4: Response sent ─────────────────────────────────────────────────
    phone_r1 = phone_q1 + [("bot", "你好！项目文件：cheetahclaws.py, agent.py, tools.py, providers.py …", (30, 30, 30))]

    after_r1 = wx_base + [
        [seg("  ✓ ", GREEN), seg("typing indicator sent", SUBTEXT)],
        None,
        claude_header(),
        tool_line("⚙", "Glob", "**/*", CYAN),
        tool_ok("12 files matched"),
        None,
        [seg("│ ", SUBTEXT)],
    ] + [text_line(l, 2) if l else None for l in resp1_lines] + [claude_sep(), None]

    add(after_r1 + [wx_sent("你好！以下是项目中的文件：…")], 900, chat=phone_r1)
    add(after_r1 + [wx_sent("你好！以下是项目中的文件：…"), None, prompt_line(cursor=True)], 800, chat=phone_r1)

    # ── 5: Slash command /cost from WeChat ───────────────────────────────
    phone_q2 = phone_r1 + [("user", "/cost", (7, 193, 96))]

    add(after_r1 + [
        prompt_line(cursor=False),
        None,
        wx_incoming("/cost"),
        [seg("                            ", SUBTEXT), seg("(slash command passthrough)", SUBTEXT)],
    ], 900, chat=phone_q2)

    cost_base = after_r1 + [
        prompt_line(cursor=False),
        None,
        wx_incoming("/cost"),
        [seg("                            ", SUBTEXT), seg("(slash command passthrough)", SUBTEXT)],
        None,
    ]

    cost_lines = [
        [seg("  Input tokens:  ", CYAN), seg("2,847", TEXT, True)],
        [seg("  Output tokens: ", CYAN), seg("412",   TEXT, True)],
        [seg("  Est. cost:     ", CYAN), seg("$0.0431 USD", GREEN, True)],
    ]

    add(cost_base + cost_lines, 700, chat=phone_q2)

    phone_cost = phone_q2 + [("bot", "Input: 2,847 | Output: 412 | Cost: $0.0431", (30, 30, 30))]
    add(cost_base + cost_lines + [None, wx_sent("Input: 2,847 | Output: 412 | Cost: $0.0431")], 900, chat=phone_cost)
    add(cost_base + cost_lines + [None, wx_sent("Input: 2,847 | Output: 412 | Cost: $0.0431"), None, prompt_line(cursor=True)], 800, chat=phone_cost)

    # ── 6: Second question — code question ───────────────────────────────
    phone_q3 = phone_cost + [("user", "/brainstorm 是什么功能？", (7, 193, 96))]

    q3_base = after_r1 + [
        prompt_line(cursor=False),
        None,
        wx_incoming("/brainstorm 是什么功能？"),
        None,
    ]

    for si in range(5):
        spin = SPINNER[si % len(SPINNER)]
        add(q3_base + [
            [seg(f"  {spin} ", WX_COLOR), seg("sending typing indicator...", SUBTEXT)],
        ], 180, chat=phone_q3)

    add(q3_base + [
        [seg("  ✓ ", GREEN), seg("typing indicator sent", SUBTEXT)],
        None,
        claude_header(),
        tool_line("⚙", "Grep", "def cmd_brainstorm", MAUVE),
        tool_ok("Found in cheetahclaws.py:480"),
        None,
        tool_line("⚙", "Read", "cheetahclaws.py:480-550", CYAN),
        tool_ok("71 lines read"),
    ], 700, chat=phone_q3)

    resp3 = "/brainstorm 启动多角色 AI 辩论，生成专家视角，经多轮讨论后综合输出 Master Plan，并自动创建 todo_list.txt 待办清单。"
    resp3_parts = []
    cur = ""
    for ch in resp3:
        cur += ch
        resp3_parts.append(cur)

    step = max(1, len(resp3_parts) // 20)
    for idx in range(0, len(resp3_parts), step):
        add(q3_base + [
            [seg("  ✓ ", GREEN), seg("typing indicator sent", SUBTEXT)],
            None,
            claude_header(),
            tool_line("⚙", "Grep", "def cmd_brainstorm", MAUVE),
            tool_ok("Found in cheetahclaws.py:480"),
            None,
            tool_line("⚙", "Read", "cheetahclaws.py:480-550", CYAN),
            tool_ok("71 lines read"),
            None,
            [seg("│ ", SUBTEXT)],
            text_line(resp3_parts[idx], 2),
        ], 50, chat=phone_q3)

    phone_r3 = phone_q3 + [("bot", "/brainstorm 启动多角色 AI 辩论，综合输出 Master Plan…", (30, 30, 30))]

    add(q3_base + [
        [seg("  ✓ ", GREEN), seg("typing indicator sent", SUBTEXT)],
        None,
        claude_header(),
        tool_line("⚙", "Grep", "def cmd_brainstorm", MAUVE),
        tool_ok("Found in cheetahclaws.py:480"),
        None,
        tool_line("⚙", "Read", "cheetahclaws.py:480-550", CYAN),
        tool_ok("71 lines read"),
        None,
        [seg("│ ", SUBTEXT)],
        text_line(resp3, 2),
        claude_sep(),
        None,
        wx_sent("/brainstorm 启动多角色 AI 辩论…"),
        None,
        prompt_line(cursor=True),
    ], 1000, chat=phone_r3)

    # ── 7: /stop from WeChat ─────────────────────────────────────────────
    phone_stop    = phone_r3 + [("user", "/stop", (7, 193, 96))]
    phone_stopped = phone_stop + [("bot", "🔴 WeChat bridge stopped.", (200, 50, 50))]

    stop_base = q3_base + [
        [seg("  ✓ ", GREEN), seg("typing indicator sent", SUBTEXT)],
        None,
        claude_header(),
        tool_line("⚙", "Grep", "def cmd_brainstorm", MAUVE),
        tool_ok("Found in cheetahclaws.py:480"),
        None,
        tool_line("⚙", "Read", "cheetahclaws.py:480-550", CYAN),
        tool_ok("71 lines read"),
        None,
        [seg("│ ", SUBTEXT)],
        text_line(resp3, 2),
        claude_sep(),
        None,
        wx_sent("/brainstorm 启动多角色 AI 辩论…"),
        None,
        prompt_line(cursor=False),
        None,
        wx_incoming("/stop"),
        None,
    ]

    add(stop_base + [
        warn_line("WeChat bridge stopped by remote /stop command."),
        None,
        prompt_line(cursor=True),
    ], 2200, chat=phone_stopped)

    return scenes


# ── Render ─────────────────────────────────────────────────────────────────

def _build_palette():
    theme = [
        BG, SURFACE, TEXT, SUBTEXT,
        CYAN, GREEN, YELLOW, RED, MAUVE, BLUE,
        (7, 193, 96),       # WeChat green
        (100, 220, 120),    # terminal WX accent
        (255, 255, 255), (0, 0, 0),
        (237, 237, 237),    # phone bg
        (235, 235, 235),    # header bg
        (30, 30, 30),       # bot text
        (210, 210, 210),    # dividers
        (160, 160, 160),    # placeholder text
        (50, 55, 80), (90, 95, 120),
    ]
    flat = []
    for c in theme:
        flat.extend(c)
    while len(flat) < 256 * 3:
        flat.extend((0, 0, 0))
    return flat


def render_gif(output_path="wechat_demo.gif"):
    print("Building WeChat demo scenes...")
    scenes = build_scenes()
    print(f"  {len(scenes)} frames")

    pal_ref = Image.new("P", (1, 1))
    pal_ref.putpalette(_build_palette())

    print("  Rendering frames...")
    rgb_frames, durations = [], []
    for i, (lines, ms, chat) in enumerate(scenes):
        img = draw_frame(lines, chat_messages=chat)
        rgb_frames.append(img)
        durations.append(ms)
        if i % 30 == 0:
            print(f"    {i}/{len(scenes)}...")

    print("  Quantizing palette...")
    p_frames = [f.quantize(palette=pal_ref, dither=0) for f in rgb_frames]

    print(f"Saving → {output_path} ...")
    p_frames[0].save(
        output_path,
        save_all=True,
        append_images=p_frames[1:],
        duration=durations,
        loop=0,
        optimize=False,
    )
    size_kb = os.path.getsize(output_path) // 1024
    print(f"Done! {size_kb} KB — {len(p_frames)} frames")


if __name__ == "__main__":
    docs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
    out = os.path.join(docs_dir, "wechat_demo.gif")
    render_gif(out)
    print(f"\n→ {out}")
