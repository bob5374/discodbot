import discord
from discord.ext import commands
from discord import ui
import random
import string
import os
from datetime import datetime, timedelta, timezone
import requests
import threading
from flask import Flask

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Bot token - get from environment variable
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Global variables to store message info
keys_message_id = None
keys_channel_id = None
user_reset_times = {}  # Track when users last reset HWID

# Railway-optimized Flask server for health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "Discord Bot is running on Railway!"

@app.route('/health')
def health():
    return {"status": "healthy", "bot": "online"}


class CustomerKeyView(ui.View):
    """Custom view with Fetch Key and Reset HWID buttons"""
    
    def __init__(self, user_id=0):
        super().__init__(timeout=None)  # No timeout so buttons stay active
        self.user_id = user_id  # 0 means anyone can use it
    
    @ui.button(label="Fetch Key", style=discord.ButtonStyle.secondary, emoji="☁️")
    async def fetch_key_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle Fetch Key button click"""
        if self.user_id != 0 and interaction.user.id != self.user_id:
            await interaction.response.send_message("This interface is not for you!", ephemeral=True)
            return
        
        try:
            # Use the same logic as login.py to find keys
            keys_channel = await find_keys_channel(interaction.guild)
            if not keys_channel:
                await interaction.response.send_message("No keys channel found!", ephemeral=True)
                return
            
            keys_message = await find_keys_message(keys_channel)
            if not keys_message:
                await interaction.response.send_message("No keys message found!", ephemeral=True)
                return
            
            # Extract keys from the embed using the same function as login.py
            keys = extract_keys_from_embed(keys_message.embeds[0])
            
            # Get user's keys
            user_keys = get_user_keys(keys, interaction.user.id)
            
            if not user_keys:
                await interaction.response.send_message("You don't have any keys!", ephemeral=True)
                return
            
            # Create embed with user's keys
            embed = discord.Embed(
                title="🔑 Your Authentication Keys",
                color=0x0099ff,
                timestamp=get_utc_time()
            )
            
            for key, data in user_keys.items():
                status = "Used" if data['used'] else "Unused"
                duration = data.get('duration', 'Unknown')
                expires_at = data.get('expires_at')
                hwid = data.get('hwid')
                
                # Check if key is expired
                if expires_at and not data['used']:
                    try:
                        expire_time = datetime.fromisoformat(expires_at)
                        if get_utc_time() > expire_time:
                            status = "Expired"
                    except:
                        pass
                
                value_text = f"**Status:** {status}\n**Duration:** {duration}"
                if expires_at and status != "Expired":
                    try:
                        expire_time = datetime.fromisoformat(expires_at)
                        value_text += f"\n**Expires:** {expire_time.strftime('%Y-%m-%d %H:%M:%S')}"
                    except:
                        pass
                
                if hwid:
                    value_text += f"\n**HWID:** `{hwid[:8]}...`"
                
                embed.add_field(
                    name=f"`{key}`",
                    value=value_text,
                    inline=True
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"Error loading your keys: {str(e)}", ephemeral=True)
    
    @ui.button(label="Reset HWID", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def reset_hwid_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle Reset HWID button click"""
        if self.user_id != 0 and interaction.user.id != self.user_id:
            await interaction.response.send_message("This interface is not for you!", ephemeral=True)
            return
        
        try:
            # Use the same logic as login.py to find keys
            keys_channel = await find_keys_channel(interaction.guild)
            if not keys_channel:
                await interaction.response.send_message("No keys channel found!", ephemeral=True)
                return
            
            keys_message = await find_keys_message(keys_channel)
            if not keys_message:
                await interaction.response.send_message("No keys message found!", ephemeral=True)
                return
            
            # Extract keys from the embed using the same function as login.py
            keys = extract_keys_from_embed(keys_message.embeds[0])
            
            # Get user's keys
            user_keys = get_user_keys(keys, interaction.user.id)
            
            if not user_keys:
                await interaction.response.send_message("You don't have any keys!", ephemeral=True)
                return
            
            # Check if user can reset (once per day)
            if not can_user_reset_hwid(interaction.user.id):
                last_reset = datetime.fromisoformat(user_reset_times[interaction.user.id])
                next_reset = last_reset + timedelta(days=1)
                await interaction.response.send_message(f"⏰ You can reset your HWID again at: **{next_reset.strftime('%Y-%m-%d %H:%M:%S')} UTC**", ephemeral=True)
                return
            
            # Find a used key to reset
            used_keys = [key for key, data in user_keys.items() if data['used']]
            if not used_keys:
                await interaction.response.send_message("ℹ️ You don't have any used keys to reset!", ephemeral=True)
                return
            
            # Reset the first used key
            key_to_reset = used_keys[0]
            key_data = keys[key_to_reset]
            
            # Verify key validity like login.py does
            expires_at = key_data.get('expires_at')
            if expires_at:
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    if get_utc_time() > expire_time:
                        await interaction.response.send_message("❌ Key has expired!", ephemeral=True)
                        return
                except:
                    pass
            
            # Reset HWID and used status
            keys[key_to_reset]['hwid'] = None
            keys[key_to_reset]['used'] = False
            
            # Mark user as having reset
            mark_user_reset_hwid(interaction.user.id)
            
            # Create new embed with updated keys (same as login.py mark_key_as_used)
            embed = discord.Embed(
                title="Generated Keys",
                color=0x0099ff,
                timestamp=keys_message.embeds[0].timestamp
            )
            
            for key_name, data in keys.items():
                status = "Used" if data['used'] else "Unused"
                duration = data.get('duration', 'Unknown')
                expires_at = data.get('expires_at')
                hwid = data.get('hwid')
                
                # Check if key is expired
                if expires_at and not data['used']:
                    try:
                        expire_time = datetime.fromisoformat(expires_at)
                        if get_utc_time() > expire_time:
                            status = "Expired"
                    except:
                        pass
                
                value_text = f"User: <@{data['user_id']}>\nStatus: {status}\nDuration: {duration}"
                if expires_at and status != "Expired":
                    try:
                        expire_time = datetime.fromisoformat(expires_at)
                        value_text += f"\nExpires: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}"
                    except:
                        pass
                
                if hwid:
                    value_text += f"\nHWID: {hwid}"
                
                embed.add_field(
                    name=f"`{key_name}`",
                    value=value_text,
                    inline=True
                )
            
            embed.set_footer(text=f"Total Keys: {len(keys)}")
            
            # Update the message
            await keys_message.edit(embed=embed)
            
            await interaction.response.send_message(f"✅ **HWID Reset Successful!**\nKey `{key_to_reset}` has been reset and can now be used again on any device.", ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Error resetting HWID: {str(e)}", ephemeral=True)

def get_utc_time():
    """Get current UTC time from online source"""
    try:
        response = requests.get('http://worldtimeapi.org/api/timezone/UTC', timeout=5)
        if response.status_code == 200:
            data = response.json()
            return datetime.fromisoformat(data['datetime'].replace('Z', '+00:00'))
    except:
        pass
    
    # Fallback to system UTC time if online fails
    return datetime.now(timezone.utc)

def can_user_reset_hwid(user_id):
    """Check if user can reset HWID (once per day)"""
    global user_reset_times
    now = get_utc_time()
    
    if user_id not in user_reset_times:
        return True
    
    last_reset = datetime.fromisoformat(user_reset_times[user_id])
    time_diff = now - last_reset
    
    # Allow reset if 24 hours have passed
    return time_diff.total_seconds() >= 86400  # 24 hours in seconds

def mark_user_reset_hwid(user_id):
    """Mark that user has reset their HWID"""
    global user_reset_times
    user_reset_times[user_id] = get_utc_time().isoformat()

def get_user_keys(keys, user_id):
    """Get all keys belonging to a specific user"""
    user_keys = {}
    for key, data in keys.items():
        if data['user_id'] == user_id:
            user_keys[key] = data
    return user_keys

def extract_keys_from_embed(embed):
    """Extract keys from Discord embed"""
    keys = {}
    if embed and embed.fields:
        for field in embed.fields:
            key_name = field.name.strip('`')
            # Extract user ID and status from field value
            lines = field.value.split('\n')
            user_line = lines[0]  # "User: <@123456789>"
            status_line = lines[1]  # "Status: Used/Unused"
            
            # Extract user ID from mention
            try:
                user_id = int(user_line.split('<@')[1].split('>')[0])
                
                # Determine if key is used
                used = "Used" in status_line
                
                # Extract duration and expiration info
                duration_text = "Unknown"
                expires_at = None
                if len(lines) >= 3:
                    duration_line = lines[2]  # "Duration: 1 hour"
                    if "Duration:" in duration_line:
                        duration_text = duration_line.split("Duration: ")[1]
                    if len(lines) >= 4:
                        expires_line = lines[3]  # "Expires: 2024-01-01 12:00:00"
                        if "Expires:" in expires_line:
                            try:
                                expires_str = expires_line.split("Expires: ")[1]
                                expires_at = datetime.fromisoformat(expires_str).isoformat()
                            except:
                                pass
                
                # Extract HWID info
                hwid = None
                if len(lines) >= 5:
                    hwid_line = lines[4]  # "HWID: abc123..."
                    if "HWID:" in hwid_line:
                        hwid = hwid_line.split("HWID: ")[1]
                
                keys[key_name] = {
                    'user_id': user_id,
                    'used': used,
                    'duration': duration_text,
                    'expires_at': expires_at,
                    'hwid': hwid
                }
            except:
                continue
    
    return keys

async def find_keys_channel(guild):
    """Find the keys channel in the server"""
    for channel in guild.channels:
        if channel.name.lower() == 'keys' and isinstance(channel, discord.TextChannel):
            return channel
    return None

async def find_keys_message(channel):
    """Find the keys message in the channel"""
    async for message in channel.history(limit=50):
        if message.embeds and message.embeds[0].title == "Generated Keys":
            return message
    return None

async def load_keys_from_discord(keys_channel):
    """Load keys from Discord message"""
    keys = {}
    global keys_message_id
    
    if keys_message_id:
        try:
            message = await keys_channel.fetch_message(keys_message_id)
            # Parse keys from the embed fields
            if message.embeds:
                embed = message.embeds[0]
                for field in embed.fields:
                    key_name = field.name.strip('`')
                    # Extract user ID and status from field value
                    lines = field.value.split('\n')
                    user_line = lines[0]  # "User: <@123456789>"
                    status_line = lines[1]  # "Status: Used/Unused"
                    
                    # Extract user ID from mention
                    user_id = int(user_line.split('<@')[1].split('>')[0])
                    
                    # Determine if key is used
                    used = "Used" in status_line
                    
                    # Extract duration and expiration info
                    duration_text = "Unknown"
                    expires_at = None
                    hwid = None
                    if len(lines) >= 3:
                        duration_line = lines[2]  # "Duration: 1 hour"
                        if "Duration:" in duration_line:
                            duration_text = duration_line.split("Duration: ")[1]
                        if len(lines) >= 4:
                            expires_line = lines[3]  # "Expires: 2024-01-01 12:00:00"
                            if "Expires:" in expires_line:
                                try:
                                    expires_str = expires_line.split("Expires: ")[1]
                                    expires_at = datetime.fromisoformat(expires_str).isoformat()
                                except:
                                    pass
                        if len(lines) >= 5:
                            hwid_line = lines[4]  # "HWID: abc123..."
                            if "HWID:" in hwid_line:
                                hwid = hwid_line.split("HWID: ")[1]
                    
                    keys[key_name] = {
                        'user_id': user_id,
                        'used': used,
                        'duration': duration_text,
                        'expires_at': expires_at,
                        'hwid': hwid
                    }
        except:
            pass
    
    return keys


async def update_keys_message(ctx, keys):
    """Update the keys message in Discord"""
    global keys_message_id, keys_channel_id
    
    # Find or create the keys channel
    keys_channel = None
    for channel in ctx.guild.channels:
        if channel.name.lower() == 'keys' and isinstance(channel, discord.TextChannel):
            keys_channel = channel
            break
    
    if not keys_channel:
        # Create keys channel if it doesn't exist
        keys_channel = await ctx.guild.create_text_channel('keys')
    
    # Create embed with all keys
    embed = discord.Embed(
        title="Generated Keys",
        color=0x0099ff,
        timestamp=datetime.now()
    )
    
    if keys:
        for key, data in keys.items():
            status = "Used" if data['used'] else "Unused"
            duration = data.get('duration', 'Unknown')
            expires_at = data.get('expires_at')
            
            # Check if key is expired
            if expires_at and not data['used']:
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    if get_utc_time() > expire_time:
                        status = "Expired"
                except:
                    pass
            
            value_text = f"User: <@{data['user_id']}>\nStatus: {status}\nDuration: {duration}"
            if expires_at and status != "Expired":
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    value_text += f"\nExpires: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}"
                except:
                    pass
            
            hwid = data.get('hwid')
            if hwid:
                value_text += f"\nHWID: {hwid}"
            
            embed.add_field(
                name=f"`{key}`",
                value=value_text,
                inline=True
            )
    else:
        embed.description = "No keys have been generated yet."
    
    embed.set_footer(text=f"Total Keys: {len(keys)}")
    
    # Update existing message or create new one
    if keys_message_id and keys_channel_id:
        try:
            message = await keys_channel.fetch_message(keys_message_id)
            await message.edit(embed=embed)
        except:
            # Message doesn't exist anymore, create new one
            message = await keys_channel.send(embed=embed)
            keys_message_id = message.id
            keys_channel_id = message.channel.id
    else:
        # Create new message
        message = await keys_channel.send(embed=embed)
        keys_message_id = message.id
        keys_channel_id = message.channel.id

def generate_key():
    """Generate a key in ASTRA-XXXXX format"""
    characters = string.ascii_uppercase + string.digits
    random_part = ''.join(random.choices(characters, k=5))
    return f"ASTRA-{random_part}"

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print('Bot is running on Railway!')
    
    # Auto-post customer message in customer channel
    await post_customer_message()

async def post_customer_message():
    """Post the customer message in the customer channel"""
    try:
        # Find the customer channel or create it
        customer_channel = None
        customer_category = None
        
        for guild in bot.guilds:
            # First, try to find existing customer channel
            for channel in guild.channels:
                if channel.name.lower() == 'customer' and isinstance(channel, discord.TextChannel):
                    customer_channel = channel
                    break
            
            if customer_channel:
                break
            
            # If no customer channel found, create category and channel
            # Find or create Customer category
            for category in guild.categories:
                if category.name.lower() == 'customer':
                    customer_category = category
                    break
            
            if not customer_category:
                # Create Customer category
                customer_category = await guild.create_category("Customer")
                print(f"Created 'Customer' category in {guild.name}")
            
            # Create customer channel
            customer_channel = await customer_category.create_text_channel("customer")
            print(f"Created 'customer' channel in {guild.name}")
            break
        
        if not customer_channel:
            print("Could not find or create customer channel!")
            return
        
        # Create embed with exact text from image
        embed = discord.Embed(
            title="👑 Customer Support",
            description="",
            color=0x2f3136  # Dark grey background
        )
        
        # Add the exact text from the image
        embed.add_field(
            name="**Fetch Key**",
            value="Forgot your key? Click \"**Fetch Key**\" to retrieve it if it's linked to your Discord account.",
            inline=False
        )
        
        embed.add_field(
            name="**Reset HWID**",
            value="Click \"**Reset HWID**\", enter your key – if it's assigned to you, the HWID will be reset.",
            inline=False
        )
        
        embed.add_field(
            name="***Note:***",
            value="*HWID resets have a 24h cooldown. Repeated resets may flag your key for sharing. Contact us if you need an early reset.*",
            inline=False
        )
        
        # Create buttons
        view = CustomerKeyView(0)  # 0 means anyone can use it
        
        # Check if message already exists
        async for message in customer_channel.history(limit=10):
            if message.embeds and message.embeds[0].fields and message.embeds[0].fields[0].name == "**Fetch Key**":
                # Update existing message
                await message.edit(embed=embed, view=view)
                return
        
        # Send new message
        await customer_channel.send(embed=embed, view=view)
        
    except Exception as e:
        print(f"Error posting customer message: {str(e)}")

@bot.command(name='setupcustomer')
async def setup_customer_channel(ctx):
    """Setup customer channel message (admin only)"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You need administrator permissions to use this command!")
        return
    
    await post_customer_message()
    await ctx.send("Customer channel message has been posted!")

@bot.command(name='genkey')
async def generate_key_command(ctx, user: discord.Member, duration: str):
    """Generate a key for a specific user with duration (mention them with @)"""
    
    # Check if user has permission (you can modify this check)
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You need administrator permissions to use this command!")
        return
    
    try:
        # Parse duration
        duration_lower = duration.lower()
        now = get_utc_time()
        
        if duration_lower == 'lifetime':
            expires_at = None
            duration_text = "Lifetime"
        elif 'min' in duration_lower:
            minutes = int(''.join(filter(str.isdigit, duration)))
            expires_at = now + timedelta(minutes=minutes)
            duration_text = f"{minutes} minute{'s' if minutes != 1 else ''}"
        elif 'hour' in duration_lower:
            hours = int(''.join(filter(str.isdigit, duration)))
            expires_at = now + timedelta(hours=hours)
            duration_text = f"{hours} hour{'s' if hours != 1 else ''}"
        elif 'day' in duration_lower:
            days = int(''.join(filter(str.isdigit, duration)))
            expires_at = now + timedelta(days=days)
            duration_text = f"{days} day{'s' if days != 1 else ''}"
        elif 'week' in duration_lower:
            weeks = int(''.join(filter(str.isdigit, duration)))
            expires_at = now + timedelta(weeks=weeks)
            duration_text = f"{weeks} week{'s' if weeks != 1 else ''}"
        elif 'month' in duration_lower:
            months = int(''.join(filter(str.isdigit, duration)))
            expires_at = now + timedelta(days=months * 30)
            duration_text = f"{months} month{'s' if months != 1 else ''}"
        else:
            await ctx.send("Invalid duration! Use: 1min, 1hour, 1day, 1week, 1month, or lifetime")
            return
        
        # Generate new key
        new_key = generate_key()
        
        # Find keys channel
        keys_channel = None
        for channel in ctx.guild.channels:
            if channel.name.lower() == 'keys' and isinstance(channel, discord.TextChannel):
                keys_channel = channel
                break
        
        if not keys_channel:
            keys_channel = await ctx.guild.create_text_channel('keys')
        
        # Load existing keys from Discord
        keys = await load_keys_from_discord(keys_channel)
        
        # Add new key with expiration
        keys[new_key] = {
            'user_id': user.id,
            'used': False,
            'duration': duration_text,
            'expires_at': expires_at.isoformat() if expires_at else None,
            'created_at': now.isoformat()
        }
        
        # Update the keys message in Discord
        await update_keys_message(ctx, keys)
        
        # Try to send key to user via DM
        try:
            embed = discord.Embed(
                title="New Authentication Key Generated",
                description=f"Your new key: `{new_key}`",
                color=0x00ff00
            )
            embed.add_field(name="Generated by", value=f"<@{ctx.author.id}>", inline=True)
            embed.add_field(name="Server", value=ctx.guild.name, inline=True)
            embed.add_field(name="Duration", value=duration_text, inline=True)
            embed.add_field(name="Generated at", value=f"<t:{int(now.timestamp())}:F>", inline=False)
            embed.set_footer(text="Keep this key safe and don't share it with anyone!")
            
            await user.send(embed=embed)
            
            # Confirm to admin
            await ctx.send(f"Key `{new_key}` has been generated and sent to {user.mention}!")
            
        except discord.Forbidden:
            await ctx.send(f"Key `{new_key}` generated but couldn't send DM to {user.mention} (DMs disabled).")
        except Exception as e:
            await ctx.send(f"Key `{new_key}` generated but error sending DM: {str(e)}")
            
    except Exception as e:
        await ctx.send(f"Error generating key: {str(e)}")

@bot.command(name='listkeys')
async def list_keys(ctx):
    """Update the keys message in Discord (admin only)"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You need administrator permissions to use this command!")
        return
    
    # Find keys channel
    keys_channel = None
    for channel in ctx.guild.channels:
        if channel.name.lower() == 'keys' and isinstance(channel, discord.TextChannel):
            keys_channel = channel
            break
    
    if not keys_channel:
        await ctx.send("No keys channel found!")
        return
    
    # Load keys from Discord
    keys = await load_keys_from_discord(keys_channel)
    
    # Update the keys message
    await update_keys_message(ctx, keys)
    await ctx.send("Keys list has been updated in the #keys channel!")

@bot.command(name='usekey')
async def use_key(ctx, key: str):
    """Mark a key as used"""
    # Find keys channel
    keys_channel = None
    for channel in ctx.guild.channels:
        if channel.name.lower() == 'keys' and isinstance(channel, discord.TextChannel):
            keys_channel = channel
            break
    
    if not keys_channel:
        await ctx.send("No keys channel found!")
        return
    
    # Load keys from Discord
    keys = await load_keys_from_discord(keys_channel)
    
    if key not in keys:
        await ctx.send("Invalid key!")
        return
    
    if keys[key]['used']:
        await ctx.send("This key has already been used!")
        return
    
    if keys[key]['user_id'] != ctx.author.id:
        await ctx.send("This key doesn't belong to you!")
        return
    
    # Mark key as used
    keys[key]['used'] = True
    
    # Update the keys message in Discord
    await update_keys_message(ctx, keys)
    
    await ctx.send("Key has been successfully used!")

@bot.command(name='deletekey')
async def delete_key(ctx, key: str):
    """Delete a key (admin only) - uses same key extraction as login.py"""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You need administrator permissions to use this command!")
        return
    
    try:
        # Use the exact same logic as login.py
        # Find the keys channel
        keys_channel = await find_keys_channel(ctx.guild)
        if not keys_channel:
            await ctx.send("No keys channel found!")
            return
        
        # Find the keys message
        keys_message = await find_keys_message(keys_channel)
        if not keys_message:
            await ctx.send("No keys message found!")
            return
        
        # Extract keys from the embed using the same function as login.py
        keys = extract_keys_from_embed(keys_message.embeds[0])
        
        # Check if the key exists
        if key not in keys:
            await ctx.send("Key not found!")
            return
        
        # Remove the key
        del keys[key]
        
        # Create new embed with updated keys (same as login.py mark_key_as_used)
        embed = discord.Embed(
            title="Generated Keys",
            color=0x0099ff,
            timestamp=keys_message.embeds[0].timestamp
        )
        
        if keys:  # Only add fields if there are keys left
            for key_name, data in keys.items():
                status = "Used" if data['used'] else "Unused"
                duration = data.get('duration', 'Unknown')
                expires_at = data.get('expires_at')
                hwid = data.get('hwid')
                
                # Check if key is expired
                if expires_at and not data['used']:
                    try:
                        expire_time = datetime.fromisoformat(expires_at)
                        if get_utc_time() > expire_time:
                            status = "Expired"
                    except:
                        pass
                
                value_text = f"User: <@{data['user_id']}>\nStatus: {status}\nDuration: {duration}"
                if expires_at and status != "Expired":
                    try:
                        expire_time = datetime.fromisoformat(expires_at)
                        value_text += f"\nExpires: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}"
                    except:
                        pass
                
                if hwid:
                    value_text += f"\nHWID: {hwid}"
                
                embed.add_field(
                    name=f"`{key_name}`",
                    value=value_text,
                    inline=True
                )
        else:
            embed.description = "No keys have been generated yet."
        
        embed.set_footer(text=f"Total Keys: {len(keys)}")
        
        # Update the message
        await keys_message.edit(embed=embed)
        
        await ctx.send(f"Key `{key}` has been deleted!")
        
    except Exception as e:
        await ctx.send(f"Error deleting key: {str(e)}")

@bot.command(name='customerpanel')
async def customer_panel(ctx):
    """Create customer interface with Fetch Key and Reset HWID buttons"""
    try:
        # Use the same logic as login.py to find keys
        keys_channel = await find_keys_channel(ctx.guild)
        if not keys_channel:
            await ctx.send("No keys channel found!")
            return
        
        keys_message = await find_keys_message(keys_channel)
        if not keys_message:
            await ctx.send("No keys message found!")
            return
        
        # Extract keys from the embed using the same function as login.py
        keys = extract_keys_from_embed(keys_message.embeds[0])
        
        # Get user's keys
        user_keys = get_user_keys(keys, ctx.author.id)
        
        if not user_keys:
            await ctx.send("You don't have any keys!")
            return
        
        # Create embed with user's keys
        embed = discord.Embed(
            title="🔑 Customer Key Management",
            description=f"Welcome {ctx.author.mention}! Manage your authentication keys below.",
            color=0x2f3136,  # Dark grey like the image
            timestamp=get_utc_time()
        )
        
        # Add key information
        key_count = len(user_keys)
        used_count = len([k for k, d in user_keys.items() if d['used']])
        unused_count = key_count - used_count
        
        embed.add_field(
            name="📊 Key Summary",
            value=f"**Total Keys:** {key_count}\n**Used:** {used_count}\n**Available:** {unused_count}",
            inline=True
        )
        
        # Add reset information
        can_reset = can_user_reset_hwid(ctx.author.id)
        if can_reset:
            embed.add_field(
                name="🔄 Reset Status",
                value="**Available** - You can reset your HWID",
                inline=True
            )
        else:
            last_reset = datetime.fromisoformat(user_reset_times[ctx.author.id])
            next_reset = last_reset + timedelta(days=1)
            embed.add_field(
                name="⏰ Reset Cooldown",
                value=f"**Next Reset:** {next_reset.strftime('%m/%d %H:%M')} UTC",
                inline=True
            )
        
        embed.set_footer(text="Click the buttons below to manage your keys")
        
        # Create the view with buttons
        view = CustomerKeyView(ctx.author.id)
        
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await ctx.send(f"Error creating customer panel: {str(e)}")

@bot.command(name='mykeys')
async def my_keys(ctx):
    """Show user's keys and reset HWID option"""
    try:
        # Use the same logic as login.py to find keys
        keys_channel = await find_keys_channel(ctx.guild)
        if not keys_channel:
            await ctx.send("No keys channel found!")
            return
        
        keys_message = await find_keys_message(keys_channel)
        if not keys_message:
            await ctx.send("No keys message found!")
            return
        
        # Extract keys from the embed using the same function as login.py
        keys = extract_keys_from_embed(keys_message.embeds[0])
        
        # Get user's keys
        user_keys = get_user_keys(keys, ctx.author.id)
        
        if not user_keys:
            await ctx.send("You don't have any keys!")
            return
        
        # Create embed with user's keys
        embed = discord.Embed(
            title="🔑 Your Authentication Keys",
            color=0x0099ff,
            timestamp=get_utc_time()
        )
        
        for key, data in user_keys.items():
            status = "Used" if data['used'] else "Unused"
            duration = data.get('duration', 'Unknown')
            expires_at = data.get('expires_at')
            hwid = data.get('hwid')
            
            # Check if key is expired
            if expires_at and not data['used']:
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    if get_utc_time() > expire_time:
                        status = "Expired"
                except:
                    pass
            
            value_text = f"**Status:** {status}\n**Duration:** {duration}"
            if expires_at and status != "Expired":
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    value_text += f"\n**Expires:** {expire_time.strftime('%Y-%m-%d %H:%M:%S')}"
                except:
                    pass
            
            if hwid:
                value_text += f"\n**HWID:** `{hwid[:8]}...`"
            
            embed.add_field(
                name=f"`{key}`",
                value=value_text,
                inline=True
            )
        
        # Add reset information
        can_reset = can_user_reset_hwid(ctx.author.id)
        if can_reset:
            embed.add_field(
                name="🔄 HWID Reset Available",
                value="You can reset your HWID once per day. Use `!customerreset <key>` to reset a specific key's HWID.",
                inline=False
            )
        else:
            last_reset = datetime.fromisoformat(user_reset_times[ctx.author.id])
            next_reset = last_reset + timedelta(days=1)
            embed.add_field(
                name="⏰ HWID Reset Cooldown",
                value=f"You can reset your HWID again at: **{next_reset.strftime('%Y-%m-%d %H:%M:%S')} UTC**",
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"Error loading your keys: {str(e)}")

@bot.command(name='customerreset')
async def customer_reset_hwid(ctx, key: str):
    """Customer command to reset HWID for their own key (once per day)"""
    try:
        # Use the same logic as login.py to find keys
        keys_channel = await find_keys_channel(ctx.guild)
        if not keys_channel:
            await ctx.send("No keys channel found!")
            return
        
        keys_message = await find_keys_message(keys_channel)
        if not keys_message:
            await ctx.send("No keys message found!")
            return
        
        # Extract keys from the embed using the same function as login.py
        keys = extract_keys_from_embed(keys_message.embeds[0])
        
        # Check if the key exists
        if key not in keys:
            await ctx.send("❌ Key not found!")
            return
        
        key_data = keys[key]
        
        # Check if user owns this key
        if key_data['user_id'] != ctx.author.id:
            await ctx.send("❌ This key doesn't belong to you!")
            return
        
        # Check if user can reset (once per day)
        if not can_user_reset_hwid(ctx.author.id):
            last_reset = datetime.fromisoformat(user_reset_times[ctx.author.id])
            next_reset = last_reset + timedelta(days=1)
            await ctx.send(f"⏰ You can reset your HWID again at: **{next_reset.strftime('%Y-%m-%d %H:%M:%S')} UTC**")
            return
        
        # Verify key validity like login.py does
        expires_at = key_data.get('expires_at')
        if expires_at:
            try:
                expire_time = datetime.fromisoformat(expires_at)
                if get_utc_time() > expire_time:
                    await ctx.send("❌ Key has expired!")
                    return
            except:
                pass
        
        # Check if key is already unused (no need to reset)
        if not key_data['used']:
            await ctx.send(f"ℹ️ Key `{key}` is already unused!")
            return
        
        # Reset HWID and used status
        keys[key]['hwid'] = None
        keys[key]['used'] = False
        
        # Mark user as having reset
        mark_user_reset_hwid(ctx.author.id)
        
        # Create new embed with updated keys (same as login.py mark_key_as_used)
        embed = discord.Embed(
            title="Generated Keys",
            color=0x0099ff,
            timestamp=keys_message.embeds[0].timestamp
        )
        
        for key_name, data in keys.items():
            status = "Used" if data['used'] else "Unused"
            duration = data.get('duration', 'Unknown')
            expires_at = data.get('expires_at')
            hwid = data.get('hwid')
            
            # Check if key is expired
            if expires_at and not data['used']:
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    if get_utc_time() > expire_time:
                        status = "Expired"
                except:
                    pass
            
            value_text = f"User: <@{data['user_id']}>\nStatus: {status}\nDuration: {duration}"
            if expires_at and status != "Expired":
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    value_text += f"\nExpires: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}"
                except:
                    pass
            
            if hwid:
                value_text += f"\nHWID: {hwid}"
            
            embed.add_field(
                name=f"`{key_name}`",
                value=value_text,
                inline=True
            )
        
        embed.set_footer(text=f"Total Keys: {len(keys)}")
        
        # Update the message
        await keys_message.edit(embed=embed)
        
        await ctx.send(f"✅ **HWID Reset Successful!**\nKey `{key}` has been reset and can now be used again on any device.")
        
    except Exception as e:
        await ctx.send(f"❌ Error resetting HWID: {str(e)}")

@bot.command(name='resethwid')
async def reset_hwid(ctx, key: str):
    """Reset HWID for a specific key (once per day for users) - Legacy command"""
    # Redirect to customer reset command
    await customer_reset_hwid(ctx, key)

@bot.command(name='resetkey')
async def reset_key(ctx, key: str):
    """Reset a key's HWID - verifies key validity like login.py"""
    
    try:
        # Use the exact same logic as login.py
        # Find the keys channel
        keys_channel = await find_keys_channel(ctx.guild)
        if not keys_channel:
            await ctx.send("No keys channel found!")
            return
        
        # Find the keys message
        keys_message = await find_keys_message(keys_channel)
        if not keys_message:
            await ctx.send("No keys message found!")
            return
        
        # Extract keys from the embed using the same function as login.py
        keys = extract_keys_from_embed(keys_message.embeds[0])
        
        # Check if the key exists
        if key not in keys:
            await ctx.send("Key not found!")
            return
        
        key_data = keys[key]
        
        # Verify key validity like login.py does
        expires_at = key_data.get('expires_at')
        if expires_at:
            try:
                expire_time = datetime.fromisoformat(expires_at)
                if get_utc_time() > expire_time:
                    await ctx.send("Key has expired!")
                    return
            except:
                pass
        
        # Check if key is already unused (no need to reset)
        if not key_data['used']:
            await ctx.send(f"Key `{key}` is already unused!")
            return
        
        # Reset HWID and used status
        keys[key]['hwid'] = None
        keys[key]['used'] = False
        
        # Create new embed with updated keys (same as login.py mark_key_as_used)
        embed = discord.Embed(
            title="Generated Keys",
            color=0x0099ff,
            timestamp=keys_message.embeds[0].timestamp
        )
        
        for key_name, data in keys.items():
            status = "Used" if data['used'] else "Unused"
            duration = data.get('duration', 'Unknown')
            expires_at = data.get('expires_at')
            hwid = data.get('hwid')
            
            # Check if key is expired
            if expires_at and not data['used']:
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    if get_utc_time() > expire_time:
                        status = "Expired"
                except:
                    pass
            
            value_text = f"User: <@{data['user_id']}>\nStatus: {status}\nDuration: {duration}"
            if expires_at and status != "Expired":
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    value_text += f"\nExpires: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}"
                except:
                    pass
            
            if hwid:
                value_text += f"\nHWID: {hwid}"
            
            embed.add_field(
                name=f"`{key_name}`",
                value=value_text,
                inline=True
            )
        
        embed.set_footer(text=f"Total Keys: {len(keys)}")
        
        # Update the message
        await keys_message.edit(embed=embed)
        
        await ctx.send(f"Key `{key}` has been successfully reset! It can now be used again.")
        
    except Exception as e:
        await ctx.send(f"Error resetting key: {str(e)}")

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing required argument! Use `!genkey @username <duration>`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument! Make sure to mention a valid user with @username and provide duration (1min, 1hour, 1day, 1week, 1month, lifetime)")
    else:
        await ctx.send(f"An error occurred: {str(error)}")

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN environment variable not set!")
        print("Please set your Discord bot token in Railway Variables.")
    else:
        print("Starting Discord bot on Railway...")
        # Start Discord bot in a separate thread
        bot_thread = threading.Thread(target=bot.run, args=(BOT_TOKEN,))
        bot_thread.daemon = True
        bot_thread.start()
        
        # Start Flask server for health checks
        port = int(os.environ.get('PORT', 8080))
        app.run(host='0.0.0.0', port=port, debug=False)
