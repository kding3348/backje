import io
import json
import os
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from PIL import Image

# ============ 설정 ============
TOKEN = os.environ.get("DISCORD_TOKEN") or "여기에_봇_토큰"
ATTENDANCE_CHANNEL_ID = 123456789012345678   # 출퇴근 메시지를 보낼 채널 ID
MENTION_EVERYONE = True                       # @everyone 멘션 켜기/끄기
DATA_FILE = "attendance.json"
KST = timezone(timedelta(hours=9))

# 그라데이션 색상 (왼쪽 → 오른쪽), 원하는 색으로 바꿔도 돼요
IN_GRADIENT = ["#43E97B", "#38F9D7", "#4FACFE"]     # 출근: 민트 → 하늘
OUT_GRADIENT = ["#FF5E9C", "#FF9A6C", "#FFD86F"]    # 퇴근: 핑크 → 살구 → 노랑
# ==============================

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
SPARKLE = "⋆｡°✩ ━━━━━━━━━━━━━━ ✩°｡⋆"

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def make_gradient_file(colors, filename, width=1000, height=36) -> discord.File:
    """여러 색을 부드럽게 이어 붙인 그라데이션 띠 이미지를 만든다."""
    stops = [hex_to_rgb(c) for c in colors]
    row = Image.new("RGB", (width, 1))
    segments = len(stops) - 1
    for x in range(width):
        pos = x / (width - 1) * segments
        i = min(int(pos), segments - 1)
        t = pos - i
        a, b = stops[i], stops[i + 1]
        row.putpixel((x, 0), tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3)))
    img = row.resize((width, height))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return discord.File(buf, filename=filename)


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fmt_duration(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}시간 {m}분 {s}초"


def fmt_date(dt: datetime) -> str:
    return f"{dt:%Y-%m-%d} ({WEEKDAYS[dt.weekday()]})"


async def send_to_channel(embed: discord.Embed, file: discord.File):
    channel = client.get_channel(ATTENDANCE_CHANNEL_ID)
    if channel is None:
        channel = await client.fetch_channel(ATTENDANCE_CHANNEL_ID)
    await channel.send(
        content="@everyone" if MENTION_EVERYONE else None,
        embed=embed,
        file=file,
        allowed_mentions=discord.AllowedMentions(everyone=MENTION_EVERYONE, users=True),
    )


def base_embed(interaction: discord.Interaction, color: int, now: datetime, banner: str) -> discord.Embed:
    user = interaction.user
    embed = discord.Embed(color=color, timestamp=now)
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_image(url=f"attachment://{banner}")
    guild = interaction.guild
    embed.set_footer(
        text=f"{guild.name if guild else '출퇴근'} · 출퇴근 기록 💫",
        icon_url=guild.icon.url if guild and guild.icon else None,
    )
    return embed


@tree.command(name="출근", description="출근을 기록합니다")
async def clock_in(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)

    if uid in data:
        started = datetime.fromisoformat(data[uid])
        await interaction.response.send_message(
            f"이미 출근 상태예요! 🙈 (출근 시각: {started.astimezone(KST):%H:%M})",
            ephemeral=True,
        )
        return

    now = datetime.now(KST)
    data[uid] = now.isoformat()
    save_data(data)
    ts = int(now.timestamp())

    banner = "in.png"
    embed = base_embed(interaction, 0x38F9D7, now, banner)
    embed.description = (
        f"## 🌞💚  출 근  완 료  💚🌞\n"
        f"{SPARKLE}\n"
        f"> 🌸 {interaction.user.mention} 님이 출근했어요! 🌸\n"
        f"> ☕ 오늘도 힘차게 시작해볼까요? 화이팅! 💪✨\n"
        f"{SPARKLE}"
    )
    embed.add_field(name="📅  날짜", value=f"```{fmt_date(now)}```", inline=True)
    embed.add_field(name="⏰  출근 시간", value=f"```{now:%H:%M:%S}```", inline=True)
    embed.add_field(name="🔥  상태", value=f"🟢 **근무 중** · <t:{ts}:R> 출근 🚀", inline=False)

    await send_to_channel(embed, make_gradient_file(IN_GRADIENT, banner))
    await interaction.response.send_message("출근 처리 완료! ✅🎉", ephemeral=True)


@tree.command(name="퇴근", description="퇴근을 기록합니다")
async def clock_out(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)

    if uid not in data:
        await interaction.response.send_message(
            "출근 기록이 없어요 🥲 먼저 `/출근` 해주세요!", ephemeral=True
        )
        return

    started = datetime.fromisoformat(data.pop(uid)).astimezone(KST)
    save_data(data)
    now = datetime.now(KST)
    ts = int(now.timestamp())

    banner = "out.png"
    embed = base_embed(interaction, 0xFF9A6C, now, banner)
    embed.description = (
        f"## 🌙💖  퇴 근  완 료  💖🌙\n"
        f"{SPARKLE}\n"
        f"> 🌷 {interaction.user.mention} 님이 퇴근했어요! 🌷\n"
        f"> 🛁 오늘 하루도 정말 수고 많으셨어요! 푹 쉬세요 😴💤\n"
        f"{SPARKLE}"
    )
    embed.add_field(name="📅  날짜", value=f"```{fmt_date(now)}```", inline=False)
    embed.add_field(name="🟢  출근", value=f"```{started:%H:%M:%S}```", inline=True)
    embed.add_field(name="🔴  퇴근", value=f"```{now:%H:%M:%S}```", inline=True)
    embed.add_field(name="🕒  총 근무시간", value=f"```{fmt_duration(now - started)}```", inline=False)
    embed.add_field(name="🎉  상태", value=f"🔴 **퇴근 완료** · <t:{ts}:R> 퇴근 🏠", inline=False)

    await send_to_channel(embed, make_gradient_file(OUT_GRADIENT, banner))
    await interaction.response.send_message("퇴근 처리 완료! ✅🎉", ephemeral=True)


@client.event
async def on_ready():
    await tree.sync()
    print(f"로그인: {client.user} (명령어 동기화 완료)")


client.run(TOKEN)
