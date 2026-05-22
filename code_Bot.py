# ============================================================
#  Bot_Discord_XX.py  –  Anti-Scam Discord Bot Central (Python)
#  [ระบบแต่งคำผิด / ล็อกไอดีคนโกง / ลบห้องออโต้ / Keep Alive 24 ชม.]
# ============================================================

import os
import discord
from discord import app_commands, ui
from discord.ext import commands
import aiosqlite
import asyncio
import datetime
import re
import os

# 🌐 [KEEP ALIVE SYSTEM] สร้าง Web Server จำลองเพื่อดันบอทให้ออนไลน์ 24 ชม.
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Server is running! Bot is Online 24/7."

def run():
    app.run(host='0.0.0.0', port=8080)

def server_on():
    t = Thread(target=run)
    t.start()

# ============================================================
#  ⚙️ CONFIG – ตัว Token หลักของบอท
# ============================================================
STAFF_ROLE_ID    = 1507343362791833651            # Role ID ของทีมงาน/แอดมินระบบ
DB_PATH          = "antiscam.db"                  # ชื่อไฟล์ฐานข้อมูล SQLite

# ============================================================
#  DATABASE SETUP
# ============================================================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scammers (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id          TEXT UNIQUE,
                discord_id      TEXT,
                full_name       TEXT,
                bank_account    TEXT,
                phone           TEXT,
                bank_name       TEXT,
                description     TEXT,
                danger_score    INTEGER DEFAULT 0,
                report_count    INTEGER DEFAULT 1,
                status          TEXT DEFAULT 'active',
                created_at      TEXT,
                evidence_urls   TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS broadcast_messages (
                case_id     TEXT,
                guild_id    TEXT,
                channel_id  TEXT,
                message_id  TEXT,
                PRIMARY KEY (case_id, guild_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                guild_id TEXT PRIMARY KEY,
                ch_contact_report TEXT,
                ch_broadcast_alert TEXT,
                ch_contact_remove TEXT,
                ch_system_log TEXT,
                ch_case_update TEXT,
                ch_verify_pending TEXT
            )
        """)
        await db.commit()

async def get_config(guild_id: int, key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(f"SELECT {key} FROM system_config WHERE guild_id = ?", (str(guild_id),)) as cur:
            row = await cur.fetchone()
            if row and row[0]: return int(row[0])
    return None

def generate_case_id():
    import random
    return f"CS-{random.randint(1000,9999)}"

def censor_name(name: str) -> str:
    parts = name.split()
    censored = []
    for p in parts:
        if len(p) <= 1: censored.append("*")
        elif len(p) <= 3: censored.append(p[:1] + "**")
        else: censored.append(p[:2] + "***")
    return " ".join(censored)

def censor_account(account: str) -> str:
    digits = re.sub(r'\D', '', account)
    if not digits or len(digits) < 6: return "***"
    return digits[:3] + "-*-" + digits[-2:]

def censor_phone(phone: str) -> str:
    digits = re.sub(r'\D', '', phone)
    if not digits or len(digits) < 8: return "***"
    return digits[:3] + "--" + digits[-4:]

# ============================================================
#  BOT SETUP
# ============================================================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ============================================================
#  MODAL – /report
# ============================================================
class ReportModal(ui.Modal, title="📋 แจ้งแขวนคนโกง"):
    scammer_id   = ui.TextInput(label="Discord ID ของคนโกง (ตัวเลขเท่านั้น)", placeholder="เช่น 1507342124205736007", max_length=25, required=True)
    full_name    = ui.TextInput(label="ชื่อ-นามสกุลจริงผู้ถูกแขวน", placeholder="นายสมชาย รักดี", max_length=100)
    bank_account = ui.TextInput(label="เลขบัญชีธนาคาร / หมายเลขพร้อมเพย์", placeholder="123-4-56789-0", max_length=50)
    phone        = ui.TextInput(label="เบอร์โทรศัพท์สำหรับติดต่อ", placeholder="081-234-5678", max_length=20)
    description  = ui.TextInput(label="รายละเอียดและพฤติกรรมการโกง", style=discord.TextStyle.paragraph, placeholder="อธิบายพฤติกรรมการโกงอย่างละเอียด...", max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        clean_scammer_id = self.scammer_id.value.strip()
        if not clean_scammer_id.isdigit():
            await interaction.response.send_message("❌ กรุณากรอก Discord ID ของคนโกงให้ถูกต้อง (เลขล้วนเท่านั้น)", ephemeral=True)
            return

        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user:   discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
        }
        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role: overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        temp_channel = await guild.create_text_channel(
            name=f"evidence-{interaction.user.name[:10]}",
            overwrites=overwrites,
            reason="ห้องชั่วคราวแนบหลักฐานแจ้งโกง"
        )

        bank_options = [
            discord.SelectOption(label="KBANK (กสิกรไทย)",    value="KBANK"),
            discord.SelectOption(label="SCB (ไทยพาณิชย์)",    value="SCB"),
            discord.SelectOption(label="BBL (กรุงเทพ)",        value="BBL"),
            discord.SelectOption(label="KTB (กรุงไทย)",        value="KTB"),
            discord.SelectOption(label="BAY (กรุงศรี)",         value="BAY"),
            discord.SelectOption(label="TTB (ทหารไทยธนชาต)",   value="TTB"),
            discord.SelectOption(label="GSB (ออมสิน)",         value="GSB"),
            discord.SelectOption(label="PromptPay (พร้อมเพย์)", value="PromptPay"),
        ]

        view = BankSelectView(
            reporter_id  = interaction.user.id,
            scammer_id   = clean_scammer_id,
            full_name    = self.full_name.value,
            bank_account = self.bank_account.value,
            phone        = self.phone.value,
            description  = self.description.value,
            temp_channel = temp_channel,
            bank_options = bank_options,
        )

        embed = discord.Embed(
            title       = "📎 ขั้นตอนสุดท้าย – เลือกธนาคารและแนบหลักฐาน",
            description = "1️⃣ เลือกธนาคารของผู้ถูกแจ้งจาก Dropdown ด้านล่าง\n2️⃣ ส่งรูปภาพแชท/สลิปลงในห้องนี้\n3️⃣ รอทีมงานตรวจสอบเสร็จ ห้องนี้จะถูกลบอัตโนมัติ",
            color = discord.Color.orange()
        )
        embed.add_field(name="คนโกง (Discord ID)", value=f"<@{clean_scammer_id}> (`{clean_scammer_id}`)", inline=True)
        embed.add_field(name="ชื่อผู้ถูกแจ้ง",   value=self.full_name.value,   inline=True)
        embed.add_field(name="เลขบัญชี",          value=self.bank_account.value, inline=True)
        embed.add_field(name="เบอร์โทร",          value=self.phone.value,        inline=True)
        embed.add_field(name="รายละเอียด",        value=f"```\n{self.description.value}\n```",  inline=False)

        await temp_channel.send(f"{interaction.user.mention}", embed=embed, view=view)
        await interaction.response.send_message(f"✅ สร้างห้องชั่วคราวให้แล้ว → {temp_channel.mention}\nกรุณาเข้าไปเลือกธนาคารและแนบรูปหลักฐานในห้องนั้น", ephemeral=True)

# ============================================================
#  VIEW – เลือกธนาคาร + แนบหลักฐาน
# ============================================================
class BankSelectView(ui.View):
    def __init__(self, reporter_id, scammer_id, full_name, bank_account, phone, description, temp_channel, bank_options):
        super().__init__(timeout=600)
        self.reporter_id  = reporter_id
        self.scammer_id   = scammer_id
        self.full_name    = full_name
        self.bank_account = bank_account
        self.phone        = phone
        self.description  = description
        self.temp_channel = temp_channel
        self.selected_bank = None

        select = ui.Select(placeholder="🏦 เลือกธนาคาร...", options=bank_options)
        select.callback = self.bank_selected
        self.add_item(select)

        attach_btn = ui.Button(label="📎 แนบรูปหลักฐาน (ส่งในแชทนี้ได้เลย)", style=discord.ButtonStyle.primary)
        attach_btn.callback = self.attach_evidence
        self.add_item(attach_btn)

        submit_btn = ui.Button(label="✅ ส่งรายงานให้ทีมงาน", style=discord.ButtonStyle.success)
        submit_btn.callback = self.submit_report
        self.add_item(submit_btn)

    async def bank_selected(self, interaction: discord.Interaction):
        self.selected_bank = interaction.data["values"][0]
        await interaction.response.send_message(f"✅ เลือกธนาคาร **{self.selected_bank}** เรียบร้อย", ephemeral=True)

    async def attach_evidence(self, interaction: discord.Interaction):
        await interaction.response.send_message("📎 กรุณาส่งรูปภาพหลักฐานในห้องแชทนี้ได้เลยครับ เสร็จแล้วกดส่งรายงาน", ephemeral=True)

    async def submit_report(self, interaction: discord.Interaction):
        if not self.selected_bank:
            await interaction.response.send_message("⚠️ กรุณาเลือกธนาคารก่อนส่ง", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        evidence_urls = []
        async for msg in self.temp_channel.history(limit=50):
            for att in msg.attachments: evidence_urls.append(att.url)

        case_id = generate_case_id()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        async with aiosqlite.connect(DB_PATH) as db:
            while True:
                async with db.execute("SELECT id FROM scammers WHERE case_id=?", (case_id,)) as cur:
                    if not await cur.fetchone(): break
                case_id = generate_case_id()

            await db.execute("""
                INSERT INTO scammers (case_id, discord_id, full_name, bank_account, phone, bank_name, description, danger_score, report_count, status, created_at, evidence_urls)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (case_id, self.scammer_id, self.full_name, self.bank_account, self.phone, self.selected_bank, self.description, 40, 1, "pending", now, ",".join(evidence_urls)))
            await db.commit()

        verify_pending_id = await get_config(interaction.guild_id, "ch_verify_pending")
        pending_ch = interaction.guild.get_channel(verify_pending_id) if verify_pending_id else None

        if pending_ch:
            embed = discord.Embed(
                title       = f"🆕 เคสใหม่รอพิจารณา #{case_id}",
                description = f"**ผู้แจ้งเรื่อง:** <@{self.reporter_id}> (`{self.reporter_id}`)\n**ลิ้งค์ห้องส่งหลักฐานเดิม:** {self.temp_channel.mention}",
                color       = discord.Color.yellow(),
                timestamp   = datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="คนโกง (Discord)", value=f"<@{self.scammer_id}> (`{self.scammer_id}`)", inline=True)
            embed.add_field(name="ชื่อ-นามสกุล",   value=self.full_name,    inline=True)
            embed.add_field(name="เลขบัญชี",        value=self.bank_account, inline=True)
            embed.add_field(name="เบอร์โทร",        value=self.phone,        inline=True)
            embed.add_field(name="ธนาคาร",          value=self.selected_bank,inline=True)
            embed.add_field(name="รายละเอียด",      value=f"```\n{self.description}\n```",  inline=False)
            if evidence_urls:
                embed.set_image(url=evidence_urls[0])
                if len(evidence_urls) > 1:
                    embed.add_field(name="รูปหลักฐานทั้งหมด", value="\n".join(evidence_urls), inline=False)

            staff_view = StaffApproveView(case_id=case_id, temp_channel_id=self.temp_channel.id)
            await pending_ch.send(embed=embed, view=staff_view)

        await interaction.followup.send(f"✅ ส่งรายงาน **#{case_id}** ให้ทีมงานเรียบร้อยแล้ว", ephemeral=True)

# ============================================================
#  VIEW – ปุ่มอนุมัติ/ปฏิเสธ สำหรับทีมงาน
# ============================================================
class StaffApproveView(ui.View):
    def __init__(self, case_id: str, temp_channel_id: int = None):
        super().__init__(timeout=None)
        self.case_id      = case_id
        self.temp_channel_id = temp_channel_id

    @ui.button(label="✅ Approve", style=discord.ButtonStyle.success, custom_id="staff_approve")
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
        if staff_role and staff_role not in interaction.user.roles:
            await interaction.response.send_message("❌ คุณไม่มีสิทธิ์กดปุ่มนี้", ephemeral=True)
            return

        await interaction.response.defer()

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE scammers SET status='active' WHERE case_id=?", (self.case_id,))
            await db.commit()
            async with db.execute("SELECT * FROM scammers WHERE case_id=?", (self.case_id,)) as cur:
                row = await cur.fetchone()

        if row: await broadcast_alert(interaction.guild, row)

        if self.temp_channel_id:
            chan = interaction.guild.get_channel(self.temp_channel_id)
            if chan:
                try: await chan.delete(reason="เคสได้รับอนุมัติแล้ว ลบห้องหลักฐานทิ้ง")
                except Exception: pass

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"✅ อนุมัติโดย {interaction.user} | {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
        await interaction.message.edit(embed=embed, view=None)

    @ui.button(label="❌ Reject", style=discord.ButtonStyle.danger, custom_id="staff_reject")
    async def reject(self, interaction: discord.Interaction, button: ui.Button):
        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
        if staff_role and staff_role not in interaction.user.roles:
            await interaction.response.send_message("❌ คุณไม่มีสิทธิ์กดปุ่มนี้", ephemeral=True)
            return

        await interaction.response.defer()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE scammers SET status='rejected' WHERE case_id=?", (self.case_id,))
            await db.commit()

        if self.temp_channel_id:
            chan = interaction.guild.get_channel(self.temp_channel_id)
            if chan:
                try: await chan.delete(reason="เคสถูกปฏิเสธ ลบห้องหลักฐานทิ้ง")
                except Exception: pass

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.dark_gray()
        embed.set_footer(text=f"❌ ปฏิเสธโดย {interaction.user} | {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
        await interaction.message.edit(embed=embed, view=None)

# ============================================================
#  BROADCAST – ยิงแจ้งเตือนแบล็กลิสต์กลาง
# ============================================================
async def broadcast_alert(guild, row):
    (db_id, case_id, discord_id, full_name, bank_account, phone, bank_name, description, danger_score, report_count, status, created_at, evidence_urls) = row
    censored_name    = censor_name(full_name)
    censored_account = censor_account(bank_account)
    censored_phone   = censor_phone(phone)
    danger_bar       = f"📊 {danger_score}% ({'อันตรายสูง' if danger_score >= 70 else 'อันตรายปานกลาง' if danger_score >= 40 else 'ต่ำ'})"

    embed = discord.Embed(
        title       = f"🚨 แจ้งเตือนบัญชีแบล็กลิสต์กลาง – #{case_id}",
        description = f"พบบุคคลต้องสงสัยในระบบ กรุณาระวัง!",
        color       = discord.Color.from_rgb(180, 0, 0),
        timestamp   = datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="รหัสเคส",              value=f"`#{case_id}`",      inline=True)
    embed.add_field(name="Discord (คนโกง)",     value=f"<@{discord_id}>" if discord_id and discord_id.isdigit() else "`ไม่ระบุไอดี`", inline=True)
    embed.add_field(name="ชื่อ-นามสกุล (เซ็นเซอร์)", value=censored_name,   inline=True)
    embed.add_field(name="ช่องทางการเงิน", value=f"🏦 {bank_name} : {censored_account}\n📱 พร้อมเพย์: {censored_phone}", inline=False)
    embed.add_field(name="พฤติกรรมความผิด",      value=description,          inline=False)
    embed.add_field(name="คะแนนความอันตราย",     value=danger_bar,           inline=True)
    embed.set_footer(text="ระบบแจ้งเตือนอัตโนมัติ | Anti-Scam Bot")

    urls = [u for u in (evidence_urls or "").split(",") if u.strip()]
    if urls: embed.set_image(url=urls[0])

    broadcast_ch_id = await get_config(guild.id, "ch_broadcast_alert")
    channel = guild.get_channel(broadcast_ch_id) if broadcast_ch_id else None
    
    if channel:
        try:
            ban_view = AutoBanView(scammer_discord_id=discord_id, case_id=case_id)
            msg = await channel.send(embed=embed, view=ban_view)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO broadcast_messages (case_id, guild_id, channel_id, message_id)
                    VALUES (?,?,?,?)
                """, (case_id, str(guild.id), str(channel.id), str(msg.id)))
                await db.commit()
        except Exception as e: print(f"[broadcast] ส่งแบล็กลิสต์ไม่ได้: {e}")

# ============================================================
#  VIEW – ปุ่ม Auto-Ban สำหรับแอดมินเท่านั้น
# ============================================================
class AutoBanView(ui.View):
    def __init__(self, scammer_discord_id: str, case_id: str):
        super().__init__(timeout=None)
        self.scammer_discord_id = scammer_discord_id
        self.case_id = case_id

    @ui.button(label="🛡️ Auto-Ban คนนี้ออกจาก Discord ทันที", style=discord.ButtonStyle.danger, custom_id="autoban_scammer")
    async def auto_ban(self, interaction: discord.Interaction, button: ui.Button):
        if not (interaction.user.guild_permissions.ban_members or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ เฉพาะแอดมินเซิร์ฟเวอร์เท่านั้นที่กดได้", ephemeral=True)
            return

        if not self.scammer_discord_id or not self.scammer_discord_id.isdigit():
            await interaction.response.send_message("⚠️ ไม่พบดีสคอร์ดไอดีในคิวแบน", ephemeral=True)
            return

        if str(interaction.guild.owner_id) == self.scammer_discord_id or interaction.user.id == int(self.scammer_discord_id):
            await interaction.response.send_message("❌ ปฏิเสธระบบความปลอดภัย: ไม่สามารถแบนเจ้าของเซิร์ฟเวอร์หรือตัวเองได้", ephemeral=True)
            return

        try:
            user_obj = await bot.fetch_user(int(self.scammer_discord_id))
            await interaction.guild.ban(user_obj, reason=f"[Anti-Scam Central] เคส #{self.case_id} – แบนโดยแอดมิน: {interaction.user}", delete_message_days=0)
            await interaction.response.send_message(f"🔨 แบนคนโกง **{user_obj}** ออกจากเซิร์ฟเวอร์เรียบร้อยแล้ว", ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"❌ บอทไม่มีสิทธิ์แบนไอดีนี้ หรือเกิดข้อผิดพลาด: {e}", ephemeral=True)

# ============================================================
#  TICKET คำร้องขอลบโพสต์
# ============================================================
class RemoveRequestModal(ui.Modal, title="🗑️ คำร้องขอลบโพสต์ / ถอนการแขวน"):
    case_id = ui.TextInput(label="รหัสเคส (Case ID) หรือ Discord ID คนโกง", placeholder="CS-1234", max_length=30)
    reason  = ui.TextInput(label="เหตุผลสั้นๆ ในการขอลบ", placeholder="เช่น โอนเงินคืนเรียบร้อยแล้ว", style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user:   discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
        }
        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role: overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-remove-{self.case_id.value[:8]}",
            overwrites=overwrites,
            reason="ห้อง Private Ticket ขอลบโพสต์"
        )

        embed = discord.Embed(
            title       = "📑 ศูนย์รับคำร้องขอถอนการแขวนและลบโพสต์",
            description = "สวัสดีครับ โปรดแนบหลักฐานการโอนเงินคืนหรือการยอมความลงในห้องนี้ เพื่อให้แอดมินพิจารณา",
            color       = discord.Color.gold()
        )
        embed.add_field(name="เคสที่ต้องการลบ", value=f"#{self.case_id.value}", inline=True)
        embed.add_field(name="เหตุผล",           value=self.reason.value,         inline=True)

        ticket_view = TicketAdminView(case_id=self.case_id.value)
        await ticket_channel.send(f"{interaction.user.mention}", embed=embed, view=ticket_view)
        await interaction.response.send_message(f"🎫 สร้างห้อง Ticket ให้แล้ว → {ticket_channel.mention}", ephemeral=True)

class TicketAdminView(ui.View):
    def __init__(self, case_id: str):
        super().__init__(timeout=None)
        self.case_id = case_id

    @ui.button(label="🟢 อนุมัติการลบโพสต์ / Approve Delete", style=discord.ButtonStyle.success, custom_id="ticket_approve_delete")
    async def approve_delete(self, interaction: discord.Interaction, button: ui.Button):
        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
        if staff_role and staff_role not in interaction.user.roles:
            await interaction.response.send_message("❌ เฉพาะแอดมินระบบเท่านั้น", ephemeral=True)
            return

        await interaction.response.defer()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE scammers SET status='resolved' WHERE case_id=?", (self.case_id,))
            await db.commit()

        await edit_broadcast_resolved(interaction.guild, self.case_id)
        try: await interaction.channel.delete(reason="ปิดตั๋วคำร้องขอลบโพสต์เสร็จสมบูรณ์")
        except Exception: pass

    @ui.button(label="🔴 ปฏิเสธคำร้อง / Reject", style=discord.ButtonStyle.danger, custom_id="ticket_reject_delete")
    async def reject_delete(self, interaction: discord.Interaction, button: ui.Button):
        staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
        if staff_role and staff_role not in interaction.user.roles:
            await interaction.response.send_message("❌ เฉพาะแอดมินระบบเท่านั้น", ephemeral=True)
            return

        await interaction.response.defer()
        try: await interaction.channel.delete(reason="แอดมินปฏิเสธตั๋วคำร้องขอลบโพสต์")
        except Exception: pass

async def edit_broadcast_resolved(guild, case_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT guild_id, channel_id, message_id FROM broadcast_messages WHERE case_id=?", (case_id,)) as cur:
            rows = await cur.fetchall()
    for (guild_id, channel_id, message_id) in rows:
        channel = guild.get_channel(int(channel_id))
        if not channel: continue
        try:
            msg = await channel.fetch_message(int(message_id))
            resolved_embed = discord.Embed(
                title       = f"✅ เคส #{case_id} – ได้รับการแก้ไขแล้ว",
                description = "เคสนี้ได้รับการแก้ไขและถอนการแขวนเรียบร้อยแล้ว",
                color       = discord.Color.dark_gray()
            )
            await msg.edit(embed=resolved_embed, view=None)
        except Exception: pass

# ============================================================
#  SLASH COMMANDS
# ============================================================

# ---------- /setup ----------
@tree.command(name="setup", description="[แอดมินระบบ] ตั้งค่าเชื่อมโยงช่องแชทต่าง ๆ ของระบบบอท")
@app_commands.describe(
    ห้องติดต่อแวน="ช่องสำหรับให้สมาชิกเข้ามากดปุ่มแจ้งรายงานเรื่องแบล็กลิสต์",
    ห้องแขวน_ประจาน="ช่องสำหรับยิงข้อความแบล็กลิสต์กลางแจ้งเตือนคนโกง",
    ห้องติดต่อขอลบโพสต์="ช่องสำหรับจัดการตั๋วขอลบรายชื่อและถอนการแขวน",
    ห้องระบบ_log="ช่องสำหรับเก็บบันทึกหลักฐานและ Log การทำงานของแอดมิน",
    ห้องแจ้งเคสอัพเดท="ช่องสำหรับส่งรายงานความเคลื่อนไหวเวลามีเคสเปลี่ยนสถานะ",
    ห้องยืนยันการโพสต์="ช่องสำหรับส่งเคสใหม่ไปให้แอดมินกดตรวจสอบ อนุมัติ/ปฏิเสธ"
)
async def setup_cmd(interaction: discord.Interaction,
                    ห้องติดต่อแวน: discord.TextChannel = None,
                    ห้องแขวน_ประจาน: discord.TextChannel = None,
                    ห้องติดต่อขอลบโพสต์: discord.TextChannel = None,
                    ห้องระบบ_log: discord.TextChannel = None,
                    ห้องแจ้งเคสอัพเดท: discord.TextChannel = None,
                    ห้องยืนยันการโพสต์: discord.TextChannel = None):
    
    staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
    if staff_role and staff_role not in interaction.user.roles:
        await interaction.response.send_message("❌ เฉพาะแอดมินระบบเท่านั้นที่มีสิทธิ์เชื่อมต่อห้องแชท", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM system_config WHERE guild_id = ?", (str(interaction.guild_id),)) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute("INSERT INTO system_config (guild_id) VALUES (?)", (str(interaction.guild_id),))
            await db.commit()

        if ห้องติดต่อแวน: await db.execute("UPDATE system_config SET ch_contact_report = ? WHERE guild_id = ?", (str(ห้องติดต่อแวน.id), str(interaction.guild_id)))
        if ห้องแขวน_ประจาน: await db.execute("UPDATE system_config SET ch_broadcast_alert = ? WHERE guild_id = ?", (str(ห้องแขวน_ประจาน.id), str(interaction.guild_id)))
        if ห้องติดต่อขอลบโพสต์: await db.execute("UPDATE system_config SET ch_contact_remove = ? WHERE guild_id = ?", (str(ห้องติดต่อขอลบโพสต์.id), str(interaction.guild_id)))
        if ห้องระบบ_log: await db.execute("UPDATE system_config SET ch_system_log = ? WHERE guild_id = ?", (str(ห้องระบบ_log.id), str(interaction.guild_id)))
        if ห้องแจ้งเคสอัพเดท: await db.execute("UPDATE system_config SET ch_case_update = ? WHERE guild_id = ?", (str(ห้องแจ้งเคสอัพเดท.id), str(interaction.guild_id)))
        if ห้องยืนยันการโพสต์: await db.execute("UPDATE system_config SET ch_verify_pending = ? WHERE guild_id = ?", (str(ห้องยืนยันการโพสต์.id), str(interaction.guild_id)))
        await db.commit()

    await interaction.followup.send("✅ บันทึกและซิงค์ข้อมูลโครงสร้างห้องระบบแบล็กลิสต์กลางเรียบร้อยแล้ว!", ephemeral=True)

# ---------- /close ----------
@tree.command(name="close", description="[แอดมินระบบ] สั่งลบห้องแชทปัจจุบันทิ้งทันที")
async def close_cmd(interaction: discord.Interaction):
    staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
    if staff_role and staff_role not in interaction.user.roles:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งลบห้องนี้", ephemeral=True)
        return
    await interaction.response.send_message("⚠️ ห้องนี้กำลังจะถูกลบภายใน 3 วินาที...")
    await asyncio.sleep(3)
    try: await interaction.channel.delete(reason="แอดมินสั่งลบห้องชั่วคราวผ่านคำสั่ง /close")
    except Exception as e: print(f"ลบห้องไม่ได้: {e}")

# ---------- /check ----------
@tree.command(name="check", description="ตรวจสอบประวัติคนโกงในฐานข้อมูลกลาง")
@app_commands.describe(ประเภท="เลือกประเภทการค้นหา", ข้อมูล="ข้อมูลที่ต้องการค้นหา")
@app_commands.choices(ประเภท=[
    app_commands.Choice(name="Discord ID",    value="discord_id"),
    app_commands.Choice(name="ชื่อ-นามสกุล", value="full_name"),
    app_commands.Choice(name="เลขบัญชี",     value="bank_account"),
    app_commands.Choice(name="เบอร์โทร",     value="phone"),
])
async def check_cmd(interaction: discord.Interaction, ประเภท: app_commands.Choice[str], ข้อมูล: str):
    field  = ประเภท.value
    query  = ข้อมูล.strip()
    col = {"discord_id": "discord_id", "full_name": "full_name", "bank_account": "bank_account", "phone": "phone"}[field]

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(f"SELECT * FROM scammers WHERE {col} LIKE ? AND status='active'", (f"%{query}%",)) as cur:
            rows = await cur.fetchall()

    if not rows:
        embed = discord.Embed(title="✅ ไม่พบประวัติในระบบ", description=f"ไม่พบข้อมูลที่ตรงกับ **{query}** ในฐานข้อมูลกลาง", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    row = rows[0]
    (_, case_id, discord_id, full_name, bank_account, phone, bank_name, description, danger_score, report_count, status, created_at, evidence_urls) = row
    embed = discord.Embed(title="🔴 ⚠️ พบประวัติในระบบ – ระวัง!", description="บุคคลนี้มีประวัติถูกแจ้งในระบบกลาง กรุณาระวัง!", color=discord.Color.red())
    embed.add_field(name="รหัสเคส",              value=f"`#{case_id}`",              inline=True)
    embed.add_field(name="Discord (คนโกง)",     value=f"<@{discord_id}>" if discord_id else "`ไม่ระบุไอดี`", inline=True)
    embed.add_field(name="ชื่อ (เซ็นเซอร์)",     value=censor_name(full_name),       inline=True)
    embed.add_field(name="บัญชี (เซ็นเซอร์)",    value=censor_account(bank_account), inline=True)
    embed.add_field(name="คะแนนความอันตราย",     value=f"📊 {danger_score}%",         inline=True)
    embed.add_field(name="จำนวนครั้งที่ถูกแจ้ง", value=str(report_count),            inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------- /report ----------
@tree.command(name="report", description="แจ้งแขวนคนโกง")
async def report_cmd(interaction: discord.Interaction):
    await interaction.response.send_modal(ReportModal())

# ---------- /remove-request ----------
@tree.command(name="remove-request", description="คำร้องขอลบโพสต์ / ถอนการแขวน")
async def remove_request_cmd(interaction: discord.Interaction):
    await interaction.response.send_modal(RemoveRequestModal())

# ---------- /verify ----------
@tree.command(name="verify", description="[แอดมินระบบ] อนุมัติเคสแจ้งโกงด้วยรหัสเคส")
@app_commands.describe(case_id="รหัสเคสที่ต้องการอนุมัติ เช่น CS-1234")
async def verify_cmd(interaction: discord.Interaction, case_id: str):
    staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
    if staff_role and staff_role not in interaction.user.roles:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    clean_case_id = case_id.strip().upper().replace("#", "")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM scammers WHERE case_id=?", (clean_case_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            await interaction.followup.send(f"❌ ไม่พบรหัสเคส `{clean_case_id}`", ephemeral=True)
            return
        await db.execute("UPDATE scammers SET status='active' WHERE case_id=?", (clean_case_id,))
        await db.commit()
        async with db.execute("SELECT * FROM scammers WHERE case_id=?", (clean_case_id,)) as cur:
            updated_row = await cur.fetchone()
    if updated_row: await broadcast_alert(interaction.guild, updated_row)
    await interaction.followup.send(f"✅ อนุมัติเคส `{clean_case_id}` และกระจายการแจ้งเตือนเรียบร้อย", ephemeral=True)

# ---------- /refuse ----------
@tree.command(name="refuse", description="[แอดมินระบบ] ปฏิเสธเคสแจ้งโกงด้วยรหัสเคส")
@app_commands.describe(case_id="รหัสเคสที่ต้องการปฏิเสธ เช่น CS-1234")
async def refuse_cmd(interaction: discord.Interaction, case_id: str):
    staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
    if staff_role and staff_role not in interaction.user.roles:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    clean_case_id = case_id.strip().upper().replace("#", "")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM scammers WHERE case_id=?", (clean_case_id,)) as cur:
            if not await cur.fetchone():
                await interaction.followup.send(f"❌ ไม่พบรหัสเคส `{clean_case_id}`", ephemeral=True)
                return
        await db.execute("UPDATE scammers SET status='rejected' WHERE case_id=?", (clean_case_id,))
        await db.commit()
    await interaction.followup.send(f"❌ ปฏิเสธเคส `{clean_case_id}` เรียบร้อยแล้ว", ephemeral=True)

# ============================================================
#  AUTO-SCAN & ON READY
# ============================================================
@bot.event
async def on_member_join(member: discord.Member):
    discord_id = str(member.id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM scammers WHERE discord_id=? AND status='active'", (discord_id,)) as cur:
            row = await cur.fetchone()
    if not row: return
    (_, case_id, _, full_name, bank_account, phone, bank_name, description, danger_score, report_count, status, created_at, evidence_urls) = row
    
    broadcast_ch_id = await get_config(member.guild.id, "ch_broadcast_alert")
    alert_channel = member.guild.get_channel(broadcast_ch_id) if broadcast_ch_id else member.guild.system_channel
    
    if alert_channel:
        embed = discord.Embed(title="⚠️ AUTO-SCAN: พบประวัติคนโกง!", description=f"{member.mention} เพิ่งเข้าเซิร์ฟเวอร์มาและมีประวัติในระบบ", color=discord.Color.red())
        embed.add_field(name="รหัสเคส", value=f"#{case_id}", inline=True)
        embed.add_field(name="Discord", value=f"<@{discord_id}>", inline=True)
        embed.add_field(name="ชื่อ", value=censor_name(full_name), inline=True)
        await alert_channel.send(embed=embed, view=AutoBanView(scammer_discord_id=discord_id, case_id=case_id))

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {error}", ephemeral=True)

@bot.event
async def on_ready():
    await init_db()
    print(f"✅ Bot พร้อมใช้งาน: {bot.user}")
    try:
        synced = await tree.sync()
        print(f"✅ Sync {len(synced)} commands เรียบร้อยและระบบรัน 24 ชม. พร้อมทำงาน")
    except Exception as e: print(f"❌ Sync commands ล้มเหลว: {e}")

# ============================================================
#  MAIN - สั่งรันระแบบ Web Server และรันบอทดิสคอร์ด
# ============================================================
if __name__ == "__main__":
    server_on()          # 👈 เปิดระบบ Web Server ยิงสัญญาณ Keep Alive
    bot.run(os.getenv('BOT_TOKEN'))   # 👈 รันตัวบอทดิสคอร์ดหลัก