import discord
from discord.ext import commands
import mysql.connector
import hashlib
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

# Konfigurasi
TOKEN = "YOUR_DISCORD_BOT_TOKEN"
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "password"
DB_NAME = "samp_server"
GUILD_ID = YOUR_SERVER_ID
REFERRAL_ROLE_ID = YOUR_ROLE_ID
REFERRAL_NEEDED = 5

# Inisialisasi Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Database Connection
def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

# Hash Password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Generate Reset Token
def generate_reset_token():
    return secrets.token_urlsafe(32)

# Event Bot Ready
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

# Slash Command Group
ucp_group = discord.app_commands.Group(name="handleucp", description="UCP Management System")

# 1. REGISTER - Registrasi Akun Baru
@ucp_group.command(name="register", description="Register akun baru di SA-MP Server")
async def register(interaction: discord.Interaction, username: str, password: str, email: str):
    await interaction.response.defer()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Cek apakah username sudah ada
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            await interaction.followup.send("❌ Username sudah terdaftar!")
            return
        
        # Cek email
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            await interaction.followup.send("❌ Email sudah terdaftar!")
            return
        
        # Hash password
        password_hash = hash_password(password)
        discord_id = interaction.user.id
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Insert ke database
        cursor.execute("""
            INSERT INTO users (username, password, email, discord_id, created_at, verified)
            VALUES (%s, %s, %s, %s, %s, 0)
        """, (username, password_hash, email, discord_id, created_at))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        embed = discord.Embed(
            title="✅ Registrasi Berhasil!",
            description=f"Akun **{username}** berhasil didaftarkan!",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Username", value=username, inline=False)
        embed.add_field(name="Email", value=email, inline=False)
        embed.add_field(name="Discord ID", value=discord_id, inline=False)
        embed.set_footer(text="SAMP UCP System")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

# 2. CHECK ACCOUNT - Cek Data Akun
@ucp_group.command(name="check", description="Check akun Anda di SA-MP Server")
async def check_account(interaction: discord.Interaction, username: str = None):
    await interaction.response.defer()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Jika username tidak diberikan, gunakan discord_id
        if username is None:
            cursor.execute("SELECT * FROM users WHERE discord_id = %s", (interaction.user.id,))
        else:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user:
            await interaction.followup.send("❌ Akun tidak ditemukan!")
            return
        
        user_id, db_username, email, discord_id, created_at, verified, referral_count = user[:7]
        
        status = "✅ Verified" if verified else "⏳ Pending Verification"
        
        embed = discord.Embed(
            title="📋 Account Information",
            description=f"Data akun **{db_username}**",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Username", value=db_username, inline=False)
        embed.add_field(name="Email", value=email, inline=False)
        embed.add_field(name="Discord ID", value=discord_id, inline=False)
        embed.add_field(name="Created At", value=created_at, inline=False)
        embed.add_field(name="Status", value=status, inline=False)
        embed.add_field(name="Referral Count", value=f"{referral_count}/5", inline=False)
        embed.set_footer(text="SAMP UCP System")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

# 3. FORGOT PASSWORD - Reset Password
@ucp_group.command(name="password", description="Reset password akun Anda")
async def forgot_password(interaction: discord.Interaction, username: str, email: str):
    await interaction.response.defer()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Cek akun
        cursor.execute("SELECT * FROM users WHERE username = %s AND email = %s", (username, email))
        user = cursor.fetchone()
        
        if not user:
            await interaction.followup.send("❌ Username atau email salah!")
            return
        
        # Generate reset token
        reset_token = generate_reset_token()
        reset_expires = datetime.now().timestamp() + 3600  # 1 jam
        
        cursor.execute("""
            UPDATE users SET reset_token = %s, reset_expires = %s
            WHERE username = %s
        """, (reset_token, reset_expires, username))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Reset link (sesuaikan dengan web app Anda)
        reset_link = f"https://yourwebsite.com/reset?token={reset_token}"
        
        embed = discord.Embed(
            title="🔐 Password Reset",
            description="Link reset password telah dikirim ke email Anda!",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Reset Link", value=reset_link, inline=False)
        embed.add_field(name="Berlaku", value="1 jam", inline=False)
        embed.add_field(name="Catatan", value="Jangan bagikan link ini kepada orang lain!", inline=False)
        embed.set_footer(text="SAMP UCP System")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

# 4. REFERRAL - Sistem Referral & Role
@ucp_group.command(name="referral", description="Check status referral Anda")
async def check_referral(interaction: discord.Interaction, username: str = None):
    await interaction.response.defer()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Cek referral
        if username is None:
            cursor.execute("SELECT * FROM users WHERE discord_id = %s", (interaction.user.id,))
        else:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        
        user = cursor.fetchone()
        
        if not user:
            await interaction.followup.send("❌ Akun tidak ditemukan!")
            return
        
        user_id, db_username, email, discord_id, created_at, verified, referral_count = user[:7]
        
        # Cek apakah user sudah memiliki role
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(interaction.user.id)
        role = guild.get_role(REFERRAL_ROLE_ID)
        
        has_role = role in member.roles if member else False
        
        progress = "█" * (referral_count // 1) + "░" * (5 - (referral_count // 1))
        
        embed = discord.Embed(
            title="🎁 Referral System",
            description=f"Status referral **{db_username}**",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Referral Count", value=f"{referral_count}/5", inline=False)
        embed.add_field(name="Progress", value=progress, inline=False)
        embed.add_field(name="Status Role", value="✅ Unlocked" if has_role else "⏳ Locked", inline=False)
        
        if referral_count >= REFERRAL_NEEDED and not has_role:
            embed.add_field(
                name="⚠️ Action Required",
                value="Gunakan `/handleucp claim` untuk klaim role Anda!",
                inline=False
            )
        
        embed.set_footer(text="SAMP UCP System")
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

# 5. CLAIM ROLE - Klaim Role dari Referral
@ucp_group.command(name="claim", description="Klaim role Anda dari referral")
async def claim_role(interaction: discord.Interaction):
    await interaction.response.defer()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Cek referral user
        cursor.execute("SELECT * FROM users WHERE discord_id = %s", (interaction.user.id,))
        user = cursor.fetchone()
        
        if not user:
            await interaction.followup.send("❌ Akun tidak ditemukan!")
            return
        
        referral_count = user[6]
        
        if referral_count < REFERRAL_NEEDED:
            await interaction.followup.send(f"❌ Anda memerlukan {REFERRAL_NEEDED} referral untuk klaim role!")
            return
        
        # Add role
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(interaction.user.id)
        role = guild.get_role(REFERRAL_ROLE_ID)
        
        if member and role:
            if role in member.roles:
                await interaction.followup.send("✅ Anda sudah memiliki role ini!")
                return
            
            await member.add_roles(role)
            
            cursor.execute("UPDATE users SET referral_claimed = 1 WHERE discord_id = %s", (interaction.user.id,))
            conn.commit()
            
            embed = discord.Embed(
                title="🎉 Role Claimed!",
                description=f"Anda berhasil mendapatkan role **{role.name}**!",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed.set_footer(text="SAMP UCP System")
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Error: Server atau role tidak ditemukan!")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

# Add command group ke bot
bot.tree.add_command(ucp_group)

# Run Bot
bot.run(TOKEN)
