# Discord Bot for Railway
# This bot manages authentication keys with Discord integration

## Railway Deployment Instructions:

1. **Create Railway Account:**
   - Go to railway.app
   - Sign up with GitHub
   - Connect your GitHub account

2. **Deploy from GitHub:**
   - Click "New Project"
   - Choose "Deploy from GitHub repo"
   - Select: bob5374/vavsabaecavsavba
   - Click "Deploy Now"

3. **Set Environment Variables:**
   - In Railway dashboard, go to "Variables" tab
   - Add: BOT_TOKEN = your_discord_bot_token
   - Railway will automatically restart the bot

4. **Configure Build Settings:**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python main.py`
   - Railway auto-detects Python projects

5. **Deploy:**
   - Railway automatically installs dependencies
   - Runs your bot with `python main.py`
   - Keeps it running 24/7

## Railway Advantages:

- ✅ **Always-on** - No sleeping after inactivity
- ✅ **Better performance** - More CPU/memory than free tiers
- ✅ **Automatic deployments** - Updates when you push to GitHub
- ✅ **Better uptime** - More reliable than Replit
- ✅ **No keep-alive needed** - Stays awake automatically
- ✅ **Real-time logs** - Easy debugging in dashboard

## Bot Commands:

- `!genkey @user <duration>` - Generate key for user
- `!mykeys` - View your keys
- `!customerreset <key>` - Reset HWID (once per day)
- `!setupcustomer` - Setup customer channel
- `!listkeys` - Update keys list
- `!deletekey <key>` - Delete a key
- `!customerpanel` - Create customer interface

## Features:

- Key generation with expiration
- HWID reset with 24h cooldown
- Customer support interface
- Discord button interactions
- Automatic channel creation
- Key validation and management
- Railway-optimized keep-alive

## Environment Variables:

- `BOT_TOKEN` - Your Discord bot token (required)

## Monitoring:

- Railway dashboard shows logs and status
- Automatic restarts if bot crashes
- Real-time logs for debugging
- No external monitoring needed

## Notes:

- Railway keeps bot online 24/7 automatically
- No need for UptimeRobot or external keep-alive
- Better performance than free hosting alternatives
- Automatic deployments from GitHub pushes